import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from app.models.encounter import EncounterStatus
from app.models.user import Role


# ---- Auth ----
class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: Role
    full_name: str
    user_id: uuid.UUID


# ---- Users / providers ----
class ProviderCreate(BaseModel):
    email: str
    full_name: str
    password: str


class ProviderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    email: str
    full_name: str
    is_active: bool
    created_at: datetime


# ---- Patients ----
class PatientIdentity(BaseModel):
    first_name: str
    last_name: str
    date_of_birth: date


class PatientOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    first_name: str
    last_name: str
    date_of_birth: date


# ---- Templates ----
class TemplateCreate(BaseModel):
    name: str
    prompt_instructions: str


class TemplateUpdate(BaseModel):
    name: str | None = None
    prompt_instructions: str | None = None
    is_active: bool | None = None


class TemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    encounter_type: str
    prompt_instructions: str
    is_active: bool
    updated_at: datetime


# ---- Encounters ----
class EncounterCreate(BaseModel):
    patient: PatientIdentity
    template_id: uuid.UUID | None = None


class EncounterDraftSave(BaseModel):
    transcript_text: str | None = None
    template_id: uuid.UUID | None = None
    draft_subjective: str | None = None
    draft_objective: str | None = None
    draft_assessment: str | None = None
    draft_plan: str | None = None
    icd10_codes: list["Icd10CodeOut"] | None = None


class GenerateNoteRequest(BaseModel):
    transcript_text: str


class Icd10CodeOut(BaseModel):
    code: str
    description: str


class NoteVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    version_number: int
    subjective: str
    objective: str
    assessment: str
    plan: str
    icd10_codes: list[Icd10CodeOut]
    saved_by_user_id: uuid.UUID
    saved_by_name: str | None = None
    saved_at: datetime


class NoteSaveRequest(BaseModel):
    subjective: str
    objective: str
    assessment: str
    plan: str
    icd10_codes: list[Icd10CodeOut] = []


class EncounterOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    patient: PatientOut
    provider_id: uuid.UUID
    provider_name: str | None = None
    template_id: uuid.UUID | None
    template_name: str | None = None
    status: EncounterStatus
    transcript_text: str | None
    draft_subjective: str | None
    draft_objective: str | None
    draft_assessment: str | None
    draft_plan: str | None
    draft_icd10_codes: list[Icd10CodeOut] = []
    created_at: datetime
    updated_at: datetime
    latest_version: int = 0
    is_returning_patient: bool = False


# ---- ICD-10 search ----
class Icd10SearchResult(BaseModel):
    code: str
    description: str
    score: float
