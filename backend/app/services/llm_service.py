"""
Generation flow, in two model calls, against OpenRouter's OpenAI-compatible Chat Completions
API (base_url swapped, everything else is standard OpenAI tool-calling):

1. A forced tool-use call: the model must invoke get_patient_history before writing anything.
   Forcing it (rather than leaving it optional) is what makes "retrieval happens via a backend
   tool call, not frontend prompt-stuffing" true in every generation, not just when the model
   happens to decide to look. It also means phase 1 never emits user-visible preamble text.
2. A streamed call that continues the conversation with the tool result appended, so every
   token the client sees over SSE is part of the actual note.

We run against OpenRouter (OpenAI-compatible surface) rather than calling a single provider's
SDK directly, so the model is a one-line config change (see app.config.llm_model) rather than
a code change -- the free-tier default keeps this take-home at zero marginal cost, and the same
code path works unmodified against a paid frontier model in production.

Free-tier models are less reliable at *forced* tool_choice than frontier models: some ignore
it and answer in plain text instead of emitting a tool call. _run_forced_tool_call falls back
to "no prior history" in that case rather than failing the whole generation -- a deliberately
degraded-but-graceful path, not a crash.

The model is instructed to emit a sentinel line instead of a fabricated note when the
transcript has no clinically meaningful content -- this is the "graceful non-happy-path"
handling for garbage/empty transcript input, detected by the caller before it's ever treated
as a savable note.
"""

import re
import time
from collections.abc import AsyncIterator

import ftfy
from openai import APIConnectionError, APITimeoutError, OpenAI, RateLimitError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.encounter import Encounter
from app.models.note_version import NoteVersion
from app.models.patient import Patient

settings = get_settings()
client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=settings.openrouter_api_key)

# A free small quantized model has been observed to inject stray non-Latin-script noise mid-
# sentence in otherwise-English output (a real word in the wrong language, not corrupted bytes
# -- ftfy doesn't touch this). Enumerating specific script blocks to strip proved too fragile
# (missed Georgian on one run after Greek/Cyrillic/etc. had already been covered) since the
# model can inject essentially any script. Allowlisting instead: a clinical note has no
# legitimate reason to contain anything outside Latin script, so any run of characters outside
# ASCII + Latin-1 Supplement (covers accented names) + a short list of typographic punctuation
# actually used in these notes is treated as generation noise and dropped.
_ALLOWED_EXTRA_CHARS = "‐‑‒–—‘’“”•…"
_STRAY_SCRIPT_RE = re.compile(f"[^\x00-ÿ{_ALLOWED_EXTRA_CHARS}]+")


def clean_generated_text(text: str) -> str:
    fixed = ftfy.fix_text(text)
    stripped = _STRAY_SCRIPT_RE.sub("", fixed)
    return re.sub(r"[ \t]{2,}", " ", stripped)

NO_CLINICAL_CONTENT_SENTINEL = "##NO_CLINICAL_CONTENT##"


class GenerationFailedError(Exception):
    """Raised when the upstream model is unavailable/too slow after retries are exhausted."""

GET_PATIENT_HISTORY_TOOL = {
    "type": "function",
    "function": {
        "name": "get_patient_history",
        "description": (
            "Retrieve this patient's prior saved encounter notes (if any) from the clinical "
            "record, so relevant prior diagnoses/treatments can be referenced in the new note."
        ),
        "parameters": {"type": "object", "properties": {}},
    },
}

BASE_SYSTEM_PROMPT = """You are a clinical scribe assistant. You convert a raw encounter \
transcript or freeform clinical observations into a structured SOAP note for a physician \
to review and finalize. You are assisting a licensed clinician, not making independent \
treatment decisions.

Output format -- use exactly these section markers, each on its own line, in this order:

##SUBJECTIVE##
<subjective content>
##OBJECTIVE##
<objective content>
##ASSESSMENT##
<assessment content, including at least one suggested ICD-10 code as "CODE - Description">
##PLAN##
<plan content>

If, and only if, the transcript contains no clinically meaningful content (empty, gibberish, \
or entirely unrelated to a patient encounter), do not fabricate a note. Instead output ONLY:
##NO_CLINICAL_CONTENT##
<one sentence explaining why>

You have already been given the results of checking this patient's prior encounter history \
(see the tool result message below, if present). If prior notes exist, reference clinically \
relevant prior diagnoses or treatments in your Subjective/Assessment where appropriate -- this \
is a returning patient. If no prior notes exist, treat this purely as a first-time encounter \
and do not invent history."""


def _format_patient_history(db: Session, patient: Patient, exclude_encounter_id) -> str:
    prior_versions = (
        db.query(NoteVersion)
        .join(Encounter, Encounter.id == NoteVersion.encounter_id)
        .filter(Encounter.patient_id == patient.id, Encounter.id != exclude_encounter_id)
        .order_by(NoteVersion.saved_at.desc())
        .limit(5)
        .all()
    )
    if not prior_versions:
        return "No prior encounters found for this patient. This is a first-time encounter."

    lines = [f"Prior encounters on file for {patient.first_name} {patient.last_name} (most recent first):"]
    for v in prior_versions:
        codes = ", ".join(c["code"] for c in v.icd10_codes) if v.icd10_codes else "none recorded"
        lines.append(
            f"- {v.saved_at.date()}: Assessment: {v.assessment.strip()[:400]} (ICD-10: {codes}); "
            f"Plan: {v.plan.strip()[:300]}"
        )
    return "\n".join(lines)


def _build_system_prompt(template_prompt_instructions: str | None) -> str:
    if template_prompt_instructions:
        return f"{BASE_SYSTEM_PROMPT}\n\nTemplate-specific instructions for this encounter type:\n{template_prompt_instructions}"
    return BASE_SYSTEM_PROMPT


def _create_with_retry(max_attempts: int = 2, **kwargs):
    """
    OpenRouter's free-tier models share upstream capacity across all free users, so 429s from
    the upstream provider (not our own quota) are routine, not exceptional -- retry with the
    provider's requested Retry-After rather than immediately surfacing it as a failed generation.

    Two things bound this tightly on purpose, after generation was observed taking *several
    minutes* in practice:
    - An explicit per-request `timeout` (the OpenAI SDK's default is ~10 minutes, which lets a
      slow/stuck upstream response hang silently with zero feedback -- worse than a fast failure).
    - A low attempt count and short sleep cap. Both the forced tool-call phase and the streaming
      phase go through this independently, so the old bounds (4 attempts x up to 31s) allowed a
      worst case of ~4 minutes across the two phases combined. This caps each phase's worst case
      at roughly one timeout-or-429 plus one short retry -- well under 30s -- trading a slightly
      higher chance of a single failed generation (the caller surfaces a clear error and the
      provider just clicks Generate again) for a hard, predictable ceiling on wait time.
    """
    kwargs.setdefault("timeout", 20)
    # gpt-oss-20b is a reasoning model: uncapped, it can spend its entire max_tokens budget
    # on chain-of-thought and emit zero visible content. Capping effort to "low" via
    # OpenRouter's unified reasoning param keeps thinking short and reliably leaves room for
    # the actual note.
    kwargs.setdefault("extra_body", {})["reasoning"] = {"effort": "low"}

    last_error: Exception | None = None
    for attempt in range(max_attempts):
        try:
            return client.chat.completions.create(**kwargs)
        except RateLimitError as e:
            last_error = e
            retry_after = 3.0
            try:
                retry_after = float(e.response.json()["error"]["metadata"]["retry_after_seconds"])
            except Exception:
                pass
            if attempt < max_attempts - 1:
                time.sleep(min(retry_after, 8) + 1)
        except (APITimeoutError, APIConnectionError) as e:
            # A slow/stuck connection can surface as either type depending on which stage it
            # fails at (connect vs. read) -- catching both is what actually bounds a hung
            # request, since either one left uncaught would propagate as an unhandled exception
            # all the way up through the SSE generator.
            last_error = e
            # No Retry-After to honor here -- the request never got a response at all.
            if attempt < max_attempts - 1:
                time.sleep(2)
    raise GenerationFailedError(
        "The AI provider is currently slow or unavailable. Please try generating again."
    ) from last_error


def _run_forced_tool_call(system_prompt: str, user_message: str) -> tuple[list[dict], str | None]:
    """
    Returns (messages_to_append, tool_call_id_used). tool_call_id_used is None if the model
    didn't cooperate with tool_choice="required" (some free-tier models ignore it) -- callers
    treat that as "assume first-time encounter" rather than failing the generation.
    """
    response = _create_with_retry(
        model=settings.llm_model,
        max_tokens=200,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        tools=[GET_PATIENT_HISTORY_TOOL],
        tool_choice="required",
    )
    message = response.choices[0].message
    tool_calls = message.tool_calls or []
    if not tool_calls:
        return [], None

    tool_call = tool_calls[0]
    assistant_msg = {
        "role": "assistant",
        "content": message.content or "",
        "tool_calls": [
            {
                "id": tool_call.id,
                "type": "function",
                "function": {"name": tool_call.function.name, "arguments": tool_call.function.arguments},
            }
        ],
    }
    return [assistant_msg], tool_call.id


async def stream_soap_note(
    db: Session,
    encounter_id,
    transcript_text: str,
    template_prompt_instructions: str | None,
) -> AsyncIterator[str]:
    # Takes an id rather than an ORM instance: the caller's streaming generator runs on its
    # own DB session (see app.routers.encounters.generate_note), so we look the row up fresh
    # here rather than risk a DetachedInstanceError on an object bound to a different session.
    encounter = db.get(Encounter, encounter_id)
    patient = db.get(Patient, encounter.patient_id)

    system_prompt = _build_system_prompt(template_prompt_instructions)
    user_message = f"Encounter transcript / clinical observations:\n\n{transcript_text}"
    history_text = _format_patient_history(db, patient, exclude_encounter_id=encounter.id)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    tool_messages, tool_call_id = _run_forced_tool_call(system_prompt, user_message)
    if tool_call_id:
        messages.extend(tool_messages)
        messages.append({"role": "tool", "tool_call_id": tool_call_id, "content": history_text})
    else:
        # Degraded path: model didn't emit a tool call. Fold the same history text in as a
        # plain system note so behavior (returning vs. first-time patient) is preserved even
        # though the retrieval didn't happen via an explicit tool round-trip this time.
        messages.append({"role": "system", "content": f"[Patient history lookup]\n{history_text}"})

    stream = _create_with_retry(
        model=settings.llm_model,
        # A real 4-section SOAP note with one ICD-10 code runs ~500-700 tokens in practice;
        # 800 leaves headroom without letting a slow reasoning model ramble toward the old
        # 1500 ceiling and add tens of seconds of wall-clock time for no clinical benefit.
        max_tokens=800,
        messages=messages,
        stream=True,
    )
    for chunk in stream:
        delta = chunk.choices[0].delta.content if chunk.choices else None
        if delta:
            yield delta


def parse_soap_sections(full_text: str) -> dict[str, str] | None:
    """Returns None if the model emitted the no-clinical-content sentinel."""
    if NO_CLINICAL_CONTENT_SENTINEL in full_text:
        return None

    markers = ["##SUBJECTIVE##", "##OBJECTIVE##", "##ASSESSMENT##", "##PLAN##"]
    positions = {}
    for marker in markers:
        idx = full_text.find(marker)
        if idx == -1:
            continue
        positions[marker] = idx

    ordered = sorted(positions.items(), key=lambda kv: kv[1])
    sections: dict[str, str] = {}
    for i, (marker, start) in enumerate(ordered):
        end = ordered[i + 1][1] if i + 1 < len(ordered) else len(full_text)
        content = full_text[start + len(marker) : end].strip()
        key = marker.strip("#").lower()
        sections[key] = content

    return {
        "subjective": sections.get("subjective", ""),
        "objective": sections.get("objective", ""),
        "assessment": sections.get("assessment", ""),
        "plan": sections.get("plan", ""),
    }
