# Kyron Medical Technical Challenge — Requirements Walkthrough

Assignment source: Dana Giedd (Spine-Search), email "Kyron Medical - Technical Challenge",
received 2026-07-14, deadline Friday 7/17 12:00 PM EST. Each section below quotes the original
requirement, then explains exactly how it was implemented, with file references.

---

## Overview

> You will build a provider-facing AI clinical documentation platform... a provider either
> pastes a raw encounter transcript... or types freeform clinical observations, and the AI
> transforms that input into a structured, professional SOAP note (Subjective, Objective,
> Assessment, Plan), including suggested ICD-10 diagnosis codes based on the clinical content.

Built as a FastAPI (Python) backend + React/TypeScript frontend. A provider pastes/types a
transcript into the Encounter Workspace, clicks Generate, and the note streams back in
real time, structured into the four SOAP sections plus ICD-10 codes. See `NewEncounter.tsx` /
`EncounterEditor.tsx` for the input UI and `backend/app/services/llm_service.py` for generation.

---

## Core Requirements

### Authentication and Multi-Role Access

> Implement a real login system with two distinct roles: Provider and Admin... Hard-code at
> least three provider accounts and one admin account... Use JWTs or session tokens.

- JWT-based auth (`python-jose`, HS256), issued on login (`backend/app/routers/auth.py`),
  verified on every request via `get_current_user` (`backend/app/security.py`).
- Passwords hashed with bcrypt (`passlib`), never stored or logged in plaintext.
- Two roles enforced via a Postgres enum (`Role.provider` / `Role.admin`,
  `backend/app/models/user.py`) and per-route dependencies: `require_provider`,
  `require_admin`, and `require_provider_or_admin` (added later so an admin can open and edit
  any provider's note, not just view it).
- Seeded accounts (`backend/app/seed.py`): 3 providers (Dr. Ananya Patel, Dr. Marcus Reyes,
  Dr. Lily Chen) + 1 admin (Sam Whitfield), all `ChangeMe123!` for demo purposes.
- Ownership enforcement: `_get_owned_encounter` in `encounters.py` blocks a provider from
  reading/editing another provider's encounter (403), while admins bypass this check by design.
- Session expiry (60 min token TTL) is handled gracefully client-side — see the Non-Happy-Path
  section below, since "session expires mid-save" was one of the two chosen scenarios.

### Encounter Workspace (Provider View)

> Start a new encounter by entering patient first/last name and DOB... paste a transcript...
> Click Generate Note, AI streams a SOAP note back in real time via SSE or WebSockets... must
> include Subjective/Objective/Assessment (with ≥1 ICD-10 code)/Plan... editable inline...
> Save the finalized note.

- **New encounter**: `NewEncounter.tsx` — patient identity fields, template picker, transcript
  textarea (optionally voice-dictated, see Pioneer Features), Generate button.
- **Streaming**: Server-Sent Events, not WebSockets — chosen because generation is strictly
  one-directional (server → client); SSE gives the same real-time, no-full-reload progressive
  rendering with a simpler transport (plain `fetch` + `ReadableStream`, no upgrade handshake,
  auto-reconnect semantics available if needed later). Backend: `sse_starlette.EventSourceResponse`
  in `generate_note`/`event_stream()` (`backend/app/routers/encounters.py`). Frontend: manual SSE
  parsing over `fetch` in `frontend/src/api.ts`'s `streamGenerateNote` (manual parsing, not the
  browser `EventSource` API, because `EventSource` cannot send an `Authorization` header and
  this endpoint is authenticated like everything else).
- **Section structure**: the model is instructed (system prompt in `llm_service.py`) to emit
  `##SUBJECTIVE##` / `##OBJECTIVE##` / `##ASSESSMENT##` / `##PLAN##` markers; `parse_soap_sections()`
  splits the streamed text into the four fields. The frontend tolerantly parses partial markers
  as they arrive (`soapParse.ts`'s `parsePartialSoap`) so the note visibly fills in section by
  section while streaming, not "spinner then dump."
- **ICD-10 in Assessment**: codes are resolved server-side against the lookup table (not just
  asked-for-in-the-prompt) — see the ICD-10 Code Search section below for the full mechanism —
  and are deterministically placed at the end of the Assessment text on every generation
  (`normalize_assessment_icd10_placement` in `icd10_lookup.py`), regardless of where the model
  originally wrote them.
- **Inline editing**: all four SOAP textareas in `EncounterEditor.tsx` are plain controlled
  inputs — fully editable before save.
- **Save**: `POST /encounters/{id}/save` writes an immutable `note_versions` row (see Note
  Versioning below).

### Patient History and Context Injection

> When a provider starts an encounter for a patient with prior saved notes (matched by
> first/last/DOB), the AI must automatically retrieve and inject that history via a **backend
> tool or function call during generation**, not by stuffing prior notes into the frontend
> prompt. The AI should behave demonstrably differently for a returning vs. first-time patient.

- Patients are matched by a DB unique constraint on `(first_name, last_name, date_of_birth)`
  (`backend/app/models/patient.py`) — the same name+DOB always resolves to the same `Patient`
  row, so "returning patient" is a real DB lookup, not a guess.
- Generation runs in **two model calls** (`llm_service.py`):
  1. A **forced tool call**: `tool_choice="required"` on `get_patient_history` — the model
     *must* invoke it before writing anything, so retrieval happens via an actual backend
     function call every generation, never by the frontend pre-pending prior notes into the
     prompt text. `_run_forced_tool_call()` handles this round trip.
  2. A second call continues the same conversation with the tool result appended
     (`_format_patient_history()` queries the last 5 saved `note_versions` for that patient,
     excluding the current encounter), then streams the actual note.
  - Free-tier models are inconsistent about honoring forced tool-calling; if the model ignores
    `tool_choice="required"` and answers in plain text instead, the code falls back to folding
    the same history text in as a system message rather than failing the whole generation — a
    deliberately degraded-but-graceful path, not a crash, while still preserving the
    returning/first-time behavioral distinction either way.
- The system prompt explicitly instructs: reference relevant prior diagnoses/treatments for a
  returning patient; treat a first-time patient as first-time and never invent history —
  demonstrated via `is_returning_patient` on `EncounterOut`, shown as a "Returning patient" /
  "New patient" pill in the UI.

### Note Versioning and Audit Trail

> Every re-save writes a new version; the prior version must never be overwritten or deleted.
> Providers can view full version history, including who saved each version and when. Must be
> stored in and retrieved from AWS RDS.

- `note_versions` table (`backend/app/models/note_version.py`) is **append-only** by
  construction: `POST /encounters/{id}/save` always `INSERT`s a new row with
  `version_number = max(existing) + 1` (`save_note` in `encounters.py`) — there is no UPDATE or
  DELETE path anywhere in the codebase for this table. A `UniqueConstraint(encounter_id,
  version_number)` makes a version collision a hard DB error, not silently possible.
- Every version records `saved_by_user_id` and `saved_at` (server-side timestamp) —
  `GET /encounters/{id}/versions` returns full history including the saver's name.
- **Pioneer feature bonus**: `VersionHistory.tsx` + `frontend/src/diff.ts` add a word-level diff
  view between any two versions (LCS-based, client-side, no library) — see Pioneer Features.
- Lives in AWS RDS PostgreSQL (see Infrastructure below) — never in memory or a flat file.

### ICD-10 Code Search

> A standalone ICD-10 search widget... type a symptom/condition in plain English, top
> semantically relevant codes via vector similarity or an AI call... click to append to
> Assessment... 200-300 hardcoded/embedded codes... no external ICD-10 API.

- 231 real ICD-10-CM codes seeded (`backend/app/data/icd10_seed.py`), weighted toward
  musculoskeletal/spine conditions given the recruiter's spine-surgery specialization, stored in
  an `icd10_codes` table with a `pgvector` `Vector(384)` embedding column
  (`backend/app/models/icd10.py`).
- Embeddings generated locally with `sentence-transformers/all-MiniLM-L6-v2` (CPU-only,
  pre-downloaded at Docker build time — `embedding_service.py`, `Dockerfile`) — **no external
  embeddings API**, satisfying "no external ICD-10 API" for both the code list and the
  similarity search itself.
- Search (`icd10_search.py`'s `search_icd10`) does a `pgvector` cosine-distance query
  (`embedding <=> query_embedding`, ordered, top-K) — genuine vector similarity, not string
  matching.
- Widget: `Icd10Search.tsx`, a debounced search-as-you-type dropdown, wired into
  `EncounterEditor.tsx` as a floating "+ ICD-10 code" popover; selecting a result appends
  `CODE - Description` to the Assessment text and adds a removable chip.
- **Beyond the literal ask**: codes aren't just trusted as typed/generated text. A resolver
  (`icd10_lookup.py`) validates every code mentioned in a generated Assessment against the same
  `icd10_codes` table — exact match first, falling back to the same semantic search when the
  model writes a slightly-wrong or deprecated sub-code (e.g. it once wrote `M54.4`, a pre-2021
  code, next to the correct description "Low back pain" — the resolver matched it to the real
  current code `M54.5` via similarity search on the description). Codes that don't resolve to a
  real seeded row (hallucinations) are silently dropped rather than shown to the physician.
  Attached codes are persisted as structured JSONB (`draft_icd10_codes` on `encounters`,
  `icd10_codes` on `note_versions`), not re-derived by fragile text parsing on every reload.

### Admin Dashboard

> Viewing all encounters across all providers, filterable by provider and date range; adding
> and deactivating provider accounts; managing note templates (create/edit/delete) that shape
> generation differently per encounter type; template changes must take effect immediately, no
> refresh needed.

- `AdminDashboard.tsx`, three tabs:
  - **All encounters**: `GET /admin/encounters?provider_id=&start_date=&end_date=`
    (`admin.py`'s `list_all_encounters`) — filters auto-apply as soon as a dropdown/date changes
    (no separate "Filter" button), rows are clickable straight into the same
    `EncounterEditor.tsx` a provider uses, so an admin can open and edit any note directly.
  - **Providers**: add (`POST /admin/providers`) and deactivate/reactivate
    (`POST /admin/providers/{id}/deactivate|reactivate`) — deactivation doesn't delete the
    account or its history, it flips `is_active=false` and is enforced on every subsequent
    request (see Non-Happy-Path below).
  - **Note templates**: full CRUD (`admin.py`'s `create_template`/`update_template`/
    `delete_template`). 6 seeded templates (Orthopedic Follow-Up, New Patient Evaluation, Urgent
    Care Visit, Post-Operative Follow-Up, Telehealth Visit, Physical Therapy Progress Check),
    each with distinct `prompt_instructions` text injected into the system prompt
    (`_build_system_prompt` in `llm_service.py`) — e.g. the Telehealth template explicitly tells
    the model there's no hands-on exam and Objective must be limited to what's visible/audible
    over video, while Post-Op instructs it to focus on incision/wound status and recovery
    milestones. This is what makes the AI **visibly** behave differently per template, not just
    cosmetically labeled differently.
  - The admin no longer has to invent a template's internal "encounter type key" — it's
    auto-derived server-side from the template Name (`_slugify_encounter_type` in `admin.py`),
    with automatic disambiguation on collision.
- **Live propagation**: `generate_note` fetches the template's `prompt_instructions` fresh from
  the DB on *every* generation call (`encounters.py`) — never cached client-side — so an admin's
  edit to an in-use template takes effect on the very next generation any provider runs, with no
  page refresh anywhere in the loop.

### Session Persistence

> Mid-encounter (transcript entered, not yet saved) + refresh or close/reopen browser → draft
> restored from the database. Must work across devices.

- There is no separate "draft" store — the `encounters` row itself doubles as the working draft:
  `transcript_text`, `draft_subjective/objective/assessment/plan`, and `draft_icd10_codes` are
  columns on `encounters` (`backend/app/models/encounter.py`), autosaved via a debounced
  (1200ms) `PATCH /encounters/{id}/draft` on every edit (`EncounterEditor.tsx`).
  `GET /encounters/{id}` and `GET /encounters/mine` read this same DB state directly — so a
  refresh, a new tab, or logging in from an entirely different browser/device all resolve to
  identical draft state, because it's the database, not `localStorage` or component state, that
  is authoritative.
- The Dashboard (`Dashboard.tsx`) lists every encounter (draft or saved) sorted by
  `updated_at desc`, so resuming an in-progress note from any device is a single click.

### Non-Happy-Path Scenarios

> At least two, substantive, demonstrated in the walkthrough.

**1. Transcript with no clinically meaningful content.** The system prompt instructs the model
to emit a sentinel (`##NO_CLINICAL_CONTENT##`) instead of fabricating a note when the input is
empty, gibberish, or unrelated to a clinical encounter. `parse_soap_sections()` detects the
sentinel and the backend emits a distinct `no_clinical_content` SSE event rather than the `done`
event; the frontend shows a clear warning banner instead of a hallucinated SOAP note
(`EncounterEditor.tsx`'s `noClinicalContent` state). Demonstrated in
`patient_visit_scenarios.md` with two example inputs (pure gibberish; an off-topic
conversation).

**2. Admin deactivates a provider mid-draft.** `get_current_user`
(`backend/app/security.py`) checks `user.is_active` on **every** authenticated request, not just
at login — so the moment an admin deactivates a provider, that provider's very next
request (autosave, generate, save, anything) fails closed with a 403 "Account has been
deactivated," surfaced via a dedicated `DeactivatedError` class in `api.ts` and a
`DeactivatedNotice` component, rather than continuing to silently accept writes from a
deactivated account.

**3 (bonus, effectively a third).** Session expiry mid-action. A 401 mid-autosave/generate/save
throws a typed `SessionExpiredError` (`api.ts`); rather than losing the provider's in-progress
edits, a `ReauthModal` pops up in place, and on successful re-login the exact same action (the
draft PATCH, the generate call, the save) is silently retried — the provider never has to
re-type anything.

---

## Infrastructure Requirements

> AWS EC2, real HTTPS, no self-signed certs; all persistent data in AWS RDS, normalized/
> defensible schema; connection pooling; secrets via Secrets Manager, no hardcoded credentials;
> nginx reverse proxy, app not directly exposed on 80/443; RDS not publicly accessible, VPC-only.

- **Compute**: single EC2 instance (t3.micro, free-tier eligible), Elastic IP `54.90.5.8`.
- **HTTPS**: `nginx` + **Let's Encrypt** via `certbot --nginx` — a real, browser-trusted
  certificate, not self-signed. Public domain is `54-90-5-8.sslip.io` (sslip.io is a wildcard-DNS
  service that resolves `<ip-with-dashes>.sslip.io` to that literal IP with zero signup/cost —
  used instead of a registered domain purely to keep this take-home at zero marginal cost).
- **Database**: AWS RDS PostgreSQL (db.t3.micro, free-tier eligible) with the **pgvector**
  extension enabled, deployed in a **private subnet** with no public accessibility flag — only
  reachable from the EC2 instance's security group, confirmed via the VPC's subnet/route-table
  layout (private subnets have no route to an Internet Gateway; no NAT gateway either, since
  outbound internet from the private subnet was never needed and skipping it avoids ~$32/mo).
- **Connection pooling**: SQLAlchemy engine configured with `pool_size=10, max_overflow=20,
  pool_pre_ping=True, pool_recycle=1800` (`backend/app/database.py`), created once at process
  start and shared across every request via FastAPI's `Depends(get_db)` — the app never opens a
  raw per-request connection.
- **Secrets**: production reads `database_url` / `jwt_secret` / `openrouter_api_key` from **AWS
  Secrets Manager** (`kyron-scribe/app-secrets`) via an **IAM instance-profile role** (not a
  static access key) — `_load_from_secrets_manager()` in `config.py`, gated on `APP_ENV=aws`.
  Locally, the same `Settings` class reads from a git-ignored `.env` (`.gitignore` excludes
  `.env`/`.env.*`, plus `*.pem`/`*.key`) — no credential of any kind is committed to the repo.
- **Reverse proxy**: `nginx` (`infra/nginx.conf`) is the sole entry point on 80/443; it proxies
  `/api/` to the FastAPI process, which is bound to `127.0.0.1:8000` only
  (`docker-compose.prod.yml`) — never reachable directly from outside the instance.
  `proxy_buffering off` + `chunked_transfer_encoding on` are set specifically so SSE streaming
  isn't batched/delayed by nginx.
- **Schema normalization**: see the Database Schema appendix below — every table, FK, and the
  one deliberate JSONB denormalization (and why) are spelled out for the ERD walkthrough.

---

## Pioneer Features

The assignment suggested (non-exhaustive) examples: provider writing-style learning, red-flag
transcript flagging, a version diff view, or bulk patient PDF export.

**1. Version diff view (implemented).** `VersionHistory.tsx` lets a provider pick any two saved
versions and see a word-level diff per SOAP section (added text highlighted green, removed text
struck through red), computed client-side with a small LCS-based diff algorithm
(`frontend/src/diff.ts`) — no external diff library. This is one of the assignment's own
suggested pioneer features, built out fully rather than left as a stub.

**2. Voice-to-transcript dictation (implemented, not in the assignment's own suggestion list).**
A doctor can click a record button next to the transcript field (on both New Encounter and the
Encounter Editor) and dictate instead of typing/pasting — recognized speech is appended live
into the same transcript textarea, fully optional and freely mixable with typing.
`frontend/src/components/VoiceRecorder.tsx`, using the browser's native Web Speech API rather
than a paid transcription service (consistent with the project's zero-marginal-cost design;
Wispr Flow was evaluated and rejected — its API requires manual vendor approval with no
self-serve free tier). Known, disclosed tradeoff: Chrome/Edge only, and recognition isn't fully
on-device (the browser vendor's speech backend produces the text) — surfaced directly in the UI,
not hidden.

(An earlier scaffolded stub toward "provider-specific writing style learning" — an unused
`users.style_profile` column — was removed rather than left half-built; see migration
`0003_drop_style_profile`. Better to ship two complete pioneer features than three, one of which
does nothing.)

---

## Tech Stack

### Backend
- **FastAPI 0.115** (Python 3.11) — async-native, native SSE support via `sse-starlette 2.1.3`,
  automatic OpenAPI docs at `/docs` used throughout development for manual endpoint testing.
- **SQLAlchemy 2.0.35** (ORM) + **Alembic 1.13.2** (migrations) — three migrations:
  `0001_initial` (full schema), `0002_draft_icd10_codes` (added the persisted draft-codes
  column later), and `0003_drop_style_profile` (removed an unused stub column, see Pioneer
  Features).
- **psycopg 3.2.1** (`psycopg[binary]`) — PostgreSQL driver.
- **pgvector 0.3.4** (Python client) + the `pgvector` Postgres extension — vector column type and
  cosine-distance operator for ICD-10 semantic search.
- **pydantic 2.9.2** / **pydantic-settings 2.5.2** — request/response schemas (`schemas.py`) and
  typed settings loading (`config.py`).
- **python-jose[cryptography] 3.3.0** — JWT encode/decode.
- **passlib[bcrypt] 1.7.4** + **bcrypt 4.0.1** (pinned explicitly — newer bcrypt versions broke
  passlib's version-sniffing) — password hashing.
- **openai 1.51.2** SDK, pointed at OpenRouter's OpenAI-compatible endpoint rather than OpenAI
  directly (see AI Model below).
- **sentence-transformers 3.1.1** (+ CPU-only **PyTorch**, installed explicitly before
  `requirements.txt` in the Dockerfile to avoid pulling ~6GB of CUDA packages that OOM'd a
  1GB-RAM `t3.micro`) — local embedding model for ICD-10 search.
- **boto3 1.35.24** — AWS Secrets Manager client.
- **ftfy 6.2.3** — post-generation text cleanup (fixes mojibake/byte-fallback artifacts the
  free-tier model occasionally emits) combined with a Latin-script allowlist regex that strips
  stray non-Latin-script tokens the model sometimes injects mid-sentence.

### AI Model
- **OpenRouter** (OpenAI-compatible API surface) rather than calling any single provider's SDK
  directly — the model is a one-line config change (`llm_model` in `config.py`), so the same
  code path works unmodified against a paid frontier model in production; the free-tier default
  (`openai/gpt-oss-20b:free`) keeps this take-home at zero marginal cost.
- Chosen after testing several free-tier models specifically for **reliable forced tool-calling**
  (`tool_choice="required"`) — some smaller/faster free models were noticeably quicker but
  ignored forced tool choice outright, which would have broken the "retrieval via backend
  function call" requirement; `gpt-oss-20b:free` was the one that honored it consistently while
  still being usable on a free tier.
- Generation is bounded and fails fast rather than hanging: explicit 20s per-request timeout,
  max 2 retry attempts on rate-limit/timeout (previously unbounded retries let a single
  generation take multiple minutes in practice) — `_create_with_retry` in `llm_service.py`.

### Frontend
- **React 18.3** + **TypeScript 5.6**, built with **Vite 5.4**.
- **react-router-dom 6.26** — client-side routing, role-gated (`RequireAuth` in `App.tsx`).
- No UI component library or CSS framework — a small hand-written `styles.css` following a
  deliberately restrained, clinical-tool visual language (flat cards, no drop shadows, muted
  blue accent, dense tables) rather than a consumer-app aesthetic, per the assignment's explicit
  UI-quality bar.
- No state-management library — plain `useState`/`useEffect`, since the app's state is
  fundamentally per-page and server-authoritative (autosave-to-DB pattern above), not a case
  that benefits from global client state.
- Web Speech API (`SpeechRecognition`) for the voice pioneer feature — a browser global, not an
  npm dependency; a small hand-written ambient `.d.ts` file supplies the TypeScript types since
  `lib.dom.d.ts` doesn't ship them.

### Infrastructure / DevOps
- **AWS EC2** (t3.micro) running **Docker Compose** — `docker-compose.prod.yml` builds the
  backend image and binds it to `127.0.0.1:8000`; the frontend is a static Vite build served
  directly by nginx (`/var/www/kyron-scribe`), not containerized, since it's just static assets.
- **AWS RDS** (PostgreSQL, db.t3.micro) — see Infrastructure Requirements above.
- **AWS Secrets Manager** — `kyron-scribe/app-secrets`, read via an IAM instance-profile role
  scoped to that one secret (least-privilege, no long-lived access keys on the instance).
- **AWS VPC**: public + private subnets across two AZs, no NAT gateway (cost avoidance — nothing
  in the private subnet needs outbound internet).
- **nginx** — reverse proxy + static file server + SSE-aware proxying (buffering disabled).
- **Let's Encrypt / certbot** — real HTTPS certificate.
- **AWS Budget alert** — a $5/month threshold notification, set up specifically because this
  environment is meant to be free/near-free and torn down after the submission window.

---

## Database Schema

7 tables, PostgreSQL, all in RDS. Prepared to defend every relationship below.

| Table | Purpose | Key columns | Relationships |
|---|---|---|---|
| `users` | Providers + admin accounts | `role` (enum: provider/admin), `is_active`, `hashed_password` | referenced by `encounters.provider_id`, `note_versions.saved_by_user_id`, `note_templates.created_by`, `audit_log.user_id` |
| `patients` | Patient identity | `UNIQUE(first_name, last_name, date_of_birth)` | referenced by `encounters.patient_id`; this unique constraint *is* the "returning patient" matching logic |
| `note_templates` | Admin-managed generation prompts per encounter type | `encounter_type` (auto-derived slug), `prompt_instructions`, `is_active` | referenced by `encounters.template_id` (nullable — "General" has no template) |
| `encounters` | One row per patient visit; doubles as the live draft | `status` (draft/saved/abandoned), `transcript_text`, `draft_subjective/objective/assessment/plan`, `draft_icd10_codes` (JSONB) | FK → `patients`, `users` (provider), `note_templates`; parent of `note_versions` |
| `note_versions` | Immutable save history (the audit trail) | `version_number`, 4 SOAP text fields, `icd10_codes` (JSONB), `saved_by_user_id`, `saved_at`; `UNIQUE(encounter_id, version_number)` | FK → `encounters`, `users` (saver); append-only, never updated/deleted |
| `icd10_codes` | Master ICD-10 lookup/embedding table | `code` (unique), `description`, `embedding` (`pgvector`, 384-dim) | standalone; `encounters.draft_icd10_codes` / `note_versions.icd10_codes` reference it *by value*, not FK (see below) |
| `audit_log` | System/security action log (logins, saves, deactivations, template edits) | `action`, `entity_type`, `entity_id`, `details` (JSONB) | FK → `users` (nullable, for system-initiated entries) |

**Indexing**: unique indexes on `users.email`, `patients(first_name, last_name, date_of_birth)`,
`note_versions(encounter_id, version_number)`, `icd10_codes.code`; plain indexes on
`encounters.patient_id` / `.provider_id` and `note_versions.encounter_id` for the FK lookups that
happen on every request (encounter fetch, version history, patient-history retrieval).

**One deliberate denormalization, defended**: `note_versions.icd10_codes` and
`encounters.draft_icd10_codes` store `{code, description}` pairs as JSONB rather than a proper
many-to-many join table against `icd10_codes`. This is intentional, not an oversight — a
`note_version` is an **immutable historical snapshot**; it must record the code and description
exactly as they were understood at save time, decoupled from whatever the master `icd10_codes`
table looks like later. A join table would implicitly make old versions "live" against the
current lookup table, which is wrong for an audit trail. Every code that lands in this JSONB is
still validated against `icd10_codes` before being written (`resolve_icd10_codes` /
`resolve_icd10_codes_from_text` in `icd10_lookup.py`) — so it's a controlled denormalization
(values are always sourced from the lookup table), not an unvalidated free-text field.

Everything else is in standard third normal form: no repeating groups, no derived/computed
columns stored redundantly, and every non-key column depends only on its table's primary key.
