from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import Icd10SearchResult
from app.security import get_current_user
from app.services.icd10_search import search_icd10

router = APIRouter(prefix="/icd10", tags=["icd10"])


@router.get("/search", response_model=list[Icd10SearchResult])
def search(
    q: str = Query(min_length=1),
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    results = search_icd10(db, q)
    return [Icd10SearchResult(code=c.code, description=c.description, score=round(score, 4)) for c, score in results]
