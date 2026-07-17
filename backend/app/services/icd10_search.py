from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.icd10 import Icd10Code
from app.services.embedding_service import embed_text


def search_icd10(db: Session, query: str, limit: int = 8) -> list[tuple[Icd10Code, float]]:
    query_embedding = embed_text(query)
    # cosine_distance via pgvector's <=> operator; embeddings are normalized so
    # similarity = 1 - distance.
    distance = Icd10Code.embedding.cosine_distance(query_embedding)
    stmt = select(Icd10Code, distance.label("distance")).order_by(distance).limit(limit)
    rows = db.execute(stmt).all()
    return [(code, 1 - dist) for code, dist in rows]
