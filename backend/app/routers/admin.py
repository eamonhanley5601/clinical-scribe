import re
import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.audit_log import AuditLog
from app.models.encounter import Encounter
from app.models.template import NoteTemplate
from app.models.user import Role, User
from app.schemas import ProviderCreate, ProviderOut, TemplateCreate, TemplateOut, TemplateUpdate
from app.security import hash_password, require_admin
from app.routers.encounters import _to_encounter_out

router = APIRouter(prefix="/admin", tags=["admin"])


# ---- Provider roster ----
@router.get("/providers", response_model=list[ProviderOut])
def list_providers(db: Session = Depends(get_db), _admin: User = Depends(require_admin)):
    return db.query(User).filter(User.role == Role.provider).order_by(User.created_at).all()


@router.post("/providers", response_model=ProviderOut)
def create_provider(payload: ProviderCreate, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    if db.query(User).filter(User.email == payload.email).one_or_none() is not None:
        raise HTTPException(status_code=409, detail="A user with this email already exists")
    provider = User(
        email=payload.email,
        full_name=payload.full_name,
        role=Role.provider,
        hashed_password=hash_password(payload.password),
    )
    db.add(provider)
    db.flush()
    db.add(
        AuditLog(user_id=admin.id, action="create_provider", entity_type="user", entity_id=str(provider.id), details={})
    )
    db.commit()
    db.refresh(provider)
    return provider


@router.post("/providers/{provider_id}/deactivate", response_model=ProviderOut)
def deactivate_provider(provider_id: uuid.UUID, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    provider = db.get(User, provider_id)
    if provider is None or provider.role != Role.provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    provider.is_active = False
    db.add(
        AuditLog(
            user_id=admin.id, action="deactivate_provider", entity_type="user", entity_id=str(provider.id), details={}
        )
    )
    db.commit()
    db.refresh(provider)
    return provider


@router.post("/providers/{provider_id}/reactivate", response_model=ProviderOut)
def reactivate_provider(provider_id: uuid.UUID, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    provider = db.get(User, provider_id)
    if provider is None or provider.role != Role.provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    provider.is_active = True
    db.add(
        AuditLog(
            user_id=admin.id, action="reactivate_provider", entity_type="user", entity_id=str(provider.id), details={}
        )
    )
    db.commit()
    db.refresh(provider)
    return provider


# ---- Templates ----
@router.get("/templates", response_model=list[TemplateOut])
def list_templates(db: Session = Depends(get_db), _admin: User = Depends(require_admin)):
    return db.query(NoteTemplate).order_by(NoteTemplate.name).all()


def _slugify_encounter_type(db: Session, name: str) -> str:
    """
    Derives the internal encounter_type key from the template's display Name, so the admin
    never has to invent one -- it's an implementation detail (seed.py's upsert key, and a
    reference column in the admin table), not a decision that affects generation behavior
    (that's driven entirely by prompt_instructions).
    """
    base = re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_") or "template"
    slug = base
    suffix = 2
    existing = {t.encounter_type for t in db.query(NoteTemplate.encounter_type).all()}
    while slug in existing:
        slug = f"{base}_{suffix}"
        suffix += 1
    return slug


@router.post("/templates", response_model=TemplateOut)
def create_template(payload: TemplateCreate, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    template = NoteTemplate(
        name=payload.name,
        encounter_type=_slugify_encounter_type(db, payload.name),
        prompt_instructions=payload.prompt_instructions,
        created_by=admin.id,
    )
    db.add(template)
    db.commit()
    db.refresh(template)
    return template


@router.patch("/templates/{template_id}", response_model=TemplateOut)
def update_template(
    template_id: uuid.UUID,
    payload: TemplateUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    template = db.get(NoteTemplate, template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="Template not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(template, field, value)
    db.add(
        AuditLog(
            user_id=admin.id, action="update_template", entity_type="note_template", entity_id=str(template.id), details={}
        )
    )
    db.commit()
    db.refresh(template)
    return template


@router.delete("/templates/{template_id}")
def delete_template(template_id: uuid.UUID, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    template = db.get(NoteTemplate, template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="Template not found")
    db.delete(template)
    db.commit()
    return {"status": "deleted"}


# ---- All encounters (cross-provider) ----
@router.get("/encounters")
def list_all_encounters(
    provider_id: uuid.UUID | None = Query(default=None),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    query = db.query(Encounter)
    if provider_id:
        query = query.filter(Encounter.provider_id == provider_id)
    if start_date:
        query = query.filter(Encounter.created_at >= start_date)
    if end_date:
        query = query.filter(Encounter.created_at <= end_date)
    encounters = query.order_by(Encounter.created_at.desc()).all()
    return [_to_encounter_out(db, e) for e in encounters]
