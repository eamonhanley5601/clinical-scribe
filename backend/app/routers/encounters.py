import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from app.database import SessionLocal, get_db
from app.models.audit_log import AuditLog
from app.models.encounter import Encounter, EncounterStatus
from app.models.note_version import NoteVersion
from app.models.patient import Patient
from app.models.template import NoteTemplate
from app.models.user import User
from app.schemas import (
    EncounterCreate,
    EncounterDraftSave,
    EncounterOut,
    GenerateNoteRequest,
    NoteSaveRequest,
    NoteVersionOut,
    PatientOut,
)
from app.security import get_current_user, require_provider, require_provider_or_admin
from app.services.icd10_lookup import (
    normalize_assessment_icd10_placement,
    resolve_icd10_codes,
    resolve_icd10_codes_from_text,
)
from app.services.llm_service import GenerationFailedError, clean_generated_text, parse_soap_sections, stream_soap_note

router = APIRouter(prefix="/encounters", tags=["encounters"])


def _to_encounter_out(db: Session, encounter: Encounter) -> EncounterOut:
    patient = db.get(Patient, encounter.patient_id)
    provider = db.get(User, encounter.provider_id)
    template = db.get(NoteTemplate, encounter.template_id) if encounter.template_id else None
    latest_version = (
        db.query(func.max(NoteVersion.version_number)).filter(NoteVersion.encounter_id == encounter.id).scalar()
        or 0
    )
    prior_encounters = (
        db.query(NoteVersion)
        .join(Encounter, Encounter.id == NoteVersion.encounter_id)
        .filter(Encounter.patient_id == encounter.patient_id, Encounter.id != encounter.id)
        .count()
    )
    return EncounterOut(
        id=encounter.id,
        patient=PatientOut.model_validate(patient),
        provider_id=encounter.provider_id,
        provider_name=provider.full_name if provider else None,
        template_id=encounter.template_id,
        template_name=template.name if template else None,
        status=encounter.status,
        transcript_text=encounter.transcript_text,
        draft_subjective=encounter.draft_subjective,
        draft_objective=encounter.draft_objective,
        draft_assessment=encounter.draft_assessment,
        draft_plan=encounter.draft_plan,
        draft_icd10_codes=encounter.draft_icd10_codes or [],
        created_at=encounter.created_at,
        updated_at=encounter.updated_at,
        latest_version=latest_version,
        is_returning_patient=prior_encounters > 0,
    )


def _get_owned_encounter(db: Session, encounter_id: uuid.UUID, user: User) -> Encounter:
    encounter = db.get(Encounter, encounter_id)
    if encounter is None:
        raise HTTPException(status_code=404, detail="Encounter not found")
    if user.role.value != "admin" and encounter.provider_id != user.id:
        raise HTTPException(status_code=403, detail="Not your encounter")
    return encounter


@router.post("", response_model=EncounterOut)
def create_encounter(
    payload: EncounterCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_provider),
):
    patient = (
        db.query(Patient)
        .filter(
            Patient.first_name == payload.patient.first_name,
            Patient.last_name == payload.patient.last_name,
            Patient.date_of_birth == payload.patient.date_of_birth,
        )
        .one_or_none()
    )
    if patient is None:
        patient = Patient(
            first_name=payload.patient.first_name,
            last_name=payload.patient.last_name,
            date_of_birth=payload.patient.date_of_birth,
        )
        db.add(patient)
        db.flush()

    encounter = Encounter(
        patient_id=patient.id,
        provider_id=user.id,
        template_id=payload.template_id,
        status=EncounterStatus.draft,
    )
    db.add(encounter)
    db.commit()
    db.refresh(encounter)
    return _to_encounter_out(db, encounter)


@router.get("/current-draft", response_model=EncounterOut | None)
def get_current_draft(db: Session = Depends(get_db), user: User = Depends(require_provider)):
    """
    Powers cross-device session persistence: the client calls this on login / workspace
    load rather than trusting any local state, so the most recent in-progress draft is
    always resumed from the database regardless of which browser/device is asking.
    """
    encounter = (
        db.query(Encounter)
        .filter(Encounter.provider_id == user.id, Encounter.status == EncounterStatus.draft)
        .order_by(Encounter.updated_at.desc())
        .first()
    )
    if encounter is None:
        return None
    return _to_encounter_out(db, encounter)


@router.get("/mine", response_model=list[EncounterOut])
def list_my_encounters(db: Session = Depends(get_db), user: User = Depends(require_provider)):
    encounters = (
        db.query(Encounter)
        .filter(Encounter.provider_id == user.id)
        .order_by(Encounter.updated_at.desc())
        .all()
    )
    return [_to_encounter_out(db, e) for e in encounters]


@router.get("/{encounter_id}", response_model=EncounterOut)
def get_encounter(encounter_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    encounter = _get_owned_encounter(db, encounter_id, user)
    return _to_encounter_out(db, encounter)


@router.patch("/{encounter_id}/draft", response_model=EncounterOut)
def autosave_draft(
    encounter_id: uuid.UUID,
    payload: EncounterDraftSave,
    db: Session = Depends(get_db),
    user: User = Depends(require_provider_or_admin),
):
    encounter = _get_owned_encounter(db, encounter_id, user)

    for field in ("transcript_text", "template_id", "draft_subjective", "draft_objective", "draft_assessment", "draft_plan"):
        value = getattr(payload, field)
        if value is not None:
            setattr(encounter, field, value)
    if payload.icd10_codes is not None:
        # Re-resolve against the lookup table rather than trusting the client's descriptions
        # verbatim -- keeps every persisted code tied to the master icd10_codes table.
        encounter.draft_icd10_codes = resolve_icd10_codes(db, [c.code for c in payload.icd10_codes])
    db.commit()
    db.refresh(encounter)
    return _to_encounter_out(db, encounter)


@router.post("/{encounter_id}/generate")
async def generate_note(
    encounter_id: uuid.UUID,
    payload: GenerateNoteRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_provider_or_admin),
):
    encounter = _get_owned_encounter(db, encounter_id, user)

    template_instructions = None
    if encounter.template_id:
        # Fetched fresh on every generation call (not cached client-side), so an admin's
        # template edit takes effect on the provider's very next generation, no refresh needed.
        template = db.get(NoteTemplate, encounter.template_id)
        if template and template.is_active:
            template_instructions = template.prompt_instructions

    encounter.transcript_text = payload.transcript_text
    db.commit()

    async def event_stream():
        # The request-scoped `db` session (via Depends(get_db)) is closed by FastAPI once
        # this endpoint function returns, but this generator keeps running afterwards to
        # feed the SSE response -- so it needs its own session, not the closed one.
        stream_db = SessionLocal()
        try:
            accumulated = ""
            try:
                async for chunk in stream_soap_note(
                    stream_db, encounter_id, payload.transcript_text, template_instructions
                ):
                    accumulated += chunk
                    yield {"event": "delta", "data": chunk}
            except GenerationFailedError as e:
                # Upstream retries were already exhausted inside stream_soap_note (bounded to a
                # few seconds, not the multi-minute hangs this replaced) -- surface a clear,
                # actionable message instead of the connection just dying with no explanation.
                yield {"event": "generation_error", "data": str(e)}
                return

            # Free-tier quantized serving occasionally mis-emits a byte-fallback token for a
            # non-ASCII character (mojibake) or a stray foreign-script word. Streamed deltas
            # above are sent as-is (cleanup needs the full string), but the persisted/
            # authoritative version below is cleaned -- the "done" event carries it so the
            # client replaces its live-typed draft with the clean final text.
            cleaned = clean_generated_text(accumulated)
            sections = parse_soap_sections(cleaned)
            if sections is None:
                yield {"event": "no_clinical_content", "data": cleaned}
                return

            # Resolve any ICD-10-shaped tokens the model wrote into the Assessment against the
            # real lookup table -- this is what makes a code "attached" regardless of exactly
            # how the model phrased it. Falls back to semantic search when the exact code
            # doesn't match a seeded row (e.g. a slightly-wrong sub-code), so a real, close
            # code is still attached instead of the mention being lost.
            resolved_codes = resolve_icd10_codes_from_text(stream_db, sections["assessment"])
            # Don't trust the model's placement of the code mention within the Assessment prose
            # (sometimes mid-paragraph) -- strip it out and re-append the resolved codes as a
            # clean block at the very end, every time.
            sections["assessment"] = normalize_assessment_icd10_placement(sections["assessment"], resolved_codes)

            live_encounter = stream_db.get(Encounter, encounter_id)
            live_encounter.draft_subjective = sections["subjective"]
            live_encounter.draft_objective = sections["objective"]
            live_encounter.draft_assessment = sections["assessment"]
            live_encounter.draft_plan = sections["plan"]
            live_encounter.draft_icd10_codes = resolved_codes
            stream_db.commit()
            yield {"event": "done", "data": json.dumps({**sections, "icd10_codes": resolved_codes})}
        finally:
            stream_db.close()

    return EventSourceResponse(event_stream())


@router.post("/{encounter_id}/save", response_model=NoteVersionOut)
def save_note(
    encounter_id: uuid.UUID,
    payload: NoteSaveRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_provider_or_admin),
):
    encounter = _get_owned_encounter(db, encounter_id, user)

    latest_version = (
        db.query(func.max(NoteVersion.version_number)).filter(NoteVersion.encounter_id == encounter.id).scalar() or 0
    )
    # Resolve against the lookup table rather than trusting client-submitted descriptions
    # verbatim -- keeps the immutable audit trail tied to the master icd10_codes table too.
    resolved_codes = resolve_icd10_codes(db, [c.code for c in payload.icd10_codes])
    version = NoteVersion(
        encounter_id=encounter.id,
        version_number=latest_version + 1,
        subjective=payload.subjective,
        objective=payload.objective,
        assessment=payload.assessment,
        plan=payload.plan,
        icd10_codes=resolved_codes,
        saved_by_user_id=user.id,
    )
    db.add(version)

    encounter.status = EncounterStatus.saved
    encounter.draft_subjective = payload.subjective
    encounter.draft_objective = payload.objective
    encounter.draft_assessment = payload.assessment
    encounter.draft_plan = payload.plan
    encounter.draft_icd10_codes = resolved_codes

    db.add(
        AuditLog(
            user_id=user.id,
            action="save_note_version",
            entity_type="encounter",
            entity_id=str(encounter.id),
            details={"version_number": version.version_number},
        )
    )
    db.commit()
    db.refresh(version)

    out = NoteVersionOut.model_validate(version)
    out.saved_by_name = user.full_name
    return out


@router.get("/{encounter_id}/versions", response_model=list[NoteVersionOut])
def list_versions(encounter_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    encounter = _get_owned_encounter(db, encounter_id, user)
    versions = (
        db.query(NoteVersion)
        .filter(NoteVersion.encounter_id == encounter.id)
        .order_by(NoteVersion.version_number.desc())
        .all()
    )
    results = []
    for v in versions:
        out = NoteVersionOut.model_validate(v)
        saver = db.get(User, v.saved_by_user_id)
        out.saved_by_name = saver.full_name if saver else None
        results.append(out)
    return results
