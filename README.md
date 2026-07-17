# Kyron Clinical Scribe

An AI clinical documentation platform: a provider pastes a raw encounter transcript (or types
freeform clinical observations), and the app streams back a structured SOAP note — Subjective,
Objective, Assessment (with semantically-matched ICD-10 codes), Plan — in real time. Built for
Kyron Medical's technical challenge (see `requirements_walkthrough.md` for a full,
line-by-line walkthrough of how each requirement was met).

## Features

- JWT auth with **Provider** and **Admin** roles; providers only see their own encounters,
  admins see everything and can edit any note.
- Encounter workspace: patient intake → transcript (typed, pasted, or voice-dictated) →
  streamed SOAP generation (Server-Sent Events) → inline editing → save.
- Patient history retrieval via a **backend tool call** during generation (not frontend
  prompt-stuffing) — the AI behaves differently for a returning vs. first-time patient.
- Append-only note versioning with a word-level **diff view** between any two versions.
- Standalone ICD-10 search widget — 231 seeded codes, `pgvector` semantic search, no external
  ICD-10 API.
- Admin dashboard: provider roster, cross-provider encounter view (auto-filtering, no button),
  note template management with live propagation to in-flight generations.
- Session persistence across devices/refreshes (the DB, not `localStorage`, is authoritative).
- Two-plus non-happy-path scenarios: no-clinical-content transcripts, session expiry mid-save,
  admin deactivating a provider mid-draft.
- Optional voice-to-transcript dictation (Web Speech API, zero cost, zero backend involvement).

## Tech stack

| Layer | Choice |
|---|---|
| Backend | FastAPI (Python 3.11), SQLAlchemy 2.0, Alembic |
| Database | PostgreSQL + `pgvector`, hosted on AWS RDS |
| AI | OpenRouter (OpenAI-compatible API), free-tier `openai/gpt-oss-20b:free` |
| Embeddings | `sentence-transformers/all-MiniLM-L6-v2`, self-hosted (no external embeddings API) |
| Frontend | React 18 + TypeScript, Vite, no UI framework |
| Infra | AWS EC2 + nginx + Let's Encrypt, RDS in a private subnet, Secrets Manager |

Full rationale for each choice (why SSE over WebSockets, why OpenRouter, why `pgvector`, etc.)
is in `requirements_walkthrough.md`'s **Tech Stack** section.

## Prerequisites

- Docker + Docker Compose
- Node.js 18+
- A free [OpenRouter](https://openrouter.ai) API key

## Local setup

```bash
# 1. Backend environment
cp backend/.env.example backend/.env
# edit backend/.env: set JWT_SECRET (any random string) and OPENROUTER_API_KEY

# 2. Start Postgres + backend
docker compose up --build

# 3. In another terminal: apply migrations
docker compose exec backend alembic upgrade head

# 4. Seed demo data (3 providers, 1 admin, 6 templates, 231 ICD-10 codes)
docker compose exec backend python -m app.seed

# 5. Frontend
cd frontend
npm install
npm run dev
```

The app is now at **http://localhost:5173** (backend on `:8000`, proxied under `/api` by Vite
in dev — see `frontend/vite.config.ts`).

### Demo logins

All accounts use password `ChangeMe123!`.

| Email | Role |
|---|---|
| `dr.patel@kyronclinic.demo` | Provider |
| `dr.reyes@kyronclinic.demo` | Provider |
| `dr.chen@kyronclinic.demo` | Provider |
| `admin@kyronclinic.demo` | Admin |

See `patient_visit_scenarios.md` for ready-to-paste example transcripts, including the two
non-happy-path scenarios.

## Project structure

```
backend/
  app/
    models/        # SQLAlchemy models (7 tables — see schema.dbml)
    routers/        # FastAPI route handlers (auth, encounters, icd10, admin, templates)
    services/       # LLM generation, ICD-10 lookup/search, embeddings
    schemas.py       # Pydantic request/response models
    security.py      # JWT + password hashing + role dependencies
    config.py        # Settings (.env locally, AWS Secrets Manager in prod)
    seed.py          # Demo data seeding
  alembic/versions/  # 3 migrations: initial schema, draft ICD-10 codes, drop unused column
frontend/
  src/
    pages/           # Dashboard, NewEncounter, EncounterEditor, AdminDashboard, Login
    components/      # Icd10Search, VersionHistory, VoiceRecorder, ReauthModal, etc.
    api.ts           # fetch wrapper + manual SSE parsing
infra/
  nginx.conf         # reverse proxy config (production)
docker-compose.yml       # local dev (Postgres + backend)
docker-compose.prod.yml  # production (backend only, points at RDS via Secrets Manager)
```

## Database

7 tables, all in PostgreSQL/RDS: `users`, `patients`, `note_templates`, `encounters`,
`note_versions`, `icd10_codes`, `audit_log`.

- **`schema.dbml`** — paste at [dbdiagram.io](https://dbdiagram.io) (or *File → Import → DBML*)
  for a full ERD with precise column-to-column FK arrows.
- **`requirements_walkthrough.md`**'s Database Schema section defends every relationship,
  including the one deliberate denormalization: ICD-10 codes are stored *by value* in JSONB on
  `encounters`/`note_versions` rather than a join table, because a saved note version must
  freeze the code+description exactly as understood at save time, independent of later edits to
  the master `icd10_codes` table.

## Deployment (AWS)

Runs on a single EC2 instance behind `nginx`, with a real Let's Encrypt HTTPS certificate (no
self-signed certs). RDS PostgreSQL lives in a private subnet with no public accessibility;
secrets (`DATABASE_URL`, `JWT_SECRET`, `OPENROUTER_API_KEY`) come from AWS Secrets Manager via
an IAM instance-profile role, not static keys or committed `.env` files. `docker-compose.prod.yml`
builds just the backend image (bound to `127.0.0.1:8000`, never exposed directly); the frontend
is a static Vite build served straight from `nginx`.

Full infrastructure walkthrough — VPC/subnet layout, connection pooling config, why no NAT
gateway, deploy steps — is in `requirements_walkthrough.md`'s **Infrastructure Requirements**
section.

