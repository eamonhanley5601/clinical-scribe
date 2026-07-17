from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.template import NoteTemplate
from app.schemas import TemplateOut
from app.security import get_current_user

router = APIRouter(prefix="/templates", tags=["templates"])


@router.get("", response_model=list[TemplateOut])
def list_active_templates(db: Session = Depends(get_db), _user=Depends(get_current_user)):
    """
    Read-only, any authenticated role. Providers select from this list before generating;
    fetched fresh (not cached) so an admin's edit is live on the provider's next page load.
    """
    return db.query(NoteTemplate).filter(NoteTemplate.is_active == True).order_by(NoteTemplate.name).all()  # noqa: E712
