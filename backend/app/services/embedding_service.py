from functools import lru_cache

from sentence_transformers import SentenceTransformer

# Local model: no external embeddings API/key needed, works fully offline once downloaded,
# and keeps ICD-10 search entirely self-hosted per the "no external ICD-10 API" requirement.
_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


@lru_cache
def get_model() -> SentenceTransformer:
    return SentenceTransformer(_MODEL_NAME)


def embed_text(text: str) -> list[float]:
    return get_model().encode(text, normalize_embeddings=True).tolist()


def embed_batch(texts: list[str]) -> list[list[float]]:
    return get_model().encode(texts, normalize_embeddings=True, show_progress_bar=False).tolist()
