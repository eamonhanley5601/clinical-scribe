"""
Resolves ICD-10 codes mentioned anywhere in generated/submitted text against the
`icd10_codes` lookup table -- the master 231-code seed table, same one the search widget
queries. This is what makes "attached to an encounter" mean "a real code in our table", not
"whatever text the free-tier model happened to phrase" -- the model's prose format varies
(sometimes it prefixes "CODE", sometimes not), but the code shape itself plus a lookup-table
match is stable regardless of phrasing.

Free-tier models occasionally write a plausible-looking but slightly wrong sub-code next to
an otherwise-correct description (e.g. "M54.4 Low back pain" -- the real seeded code for that
description is M54.5; M54.4 was a pre-2021 ICD-10-CM code since split into M54.41/.42/.49). An
exact-code match alone would silently drop that as "not a real code" even though the clinical
content is right there in the description. `resolve_icd10_codes_from_text` falls back to the
same semantic search the ICD-10 widget uses, querying on the text next to a non-matching code,
so a real, close code from the lookup table still gets attached instead of the mention being
lost over a wrong digit. True hallucinations (no real code anywhere near that meaning) still
fall below the similarity threshold and get dropped.
"""

import re

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.icd10 import Icd10Code
from app.services.icd10_search import search_icd10

_CODE_CANDIDATE_RE = re.compile(r"\b([A-Za-z]\d{2}(?:\.\d{1,4}[A-Za-z]?)?)\b")

# Below this cosine-similarity score, a non-exact-matching code's nearby text is treated as
# not actually describing a real seeded code (vertebral-level shorthand like "T12", genuine
# hallucinations) rather than attached via the semantic fallback.
_SEMANTIC_FALLBACK_THRESHOLD = 0.55


def extract_code_candidates(text: str) -> list[str]:
    seen: set[str] = set()
    candidates: list[str] = []
    for match in _CODE_CANDIDATE_RE.finditer(text or ""):
        code = match.group(1).upper()
        if code not in seen:
            seen.add(code)
            candidates.append(code)
    return candidates


def _extract_code_mentions(text: str) -> list[tuple[str, str]]:
    """Like extract_code_candidates, but also returns the nearby description text on the same
    line (code token and list/markdown decoration stripped out) for use as a semantic-search
    fallback query when the code itself doesn't exactly match a seeded row."""
    seen: set[str] = set()
    mentions: list[tuple[str, str]] = []
    for line in (text or "").split("\n"):
        for match in _CODE_CANDIDATE_RE.finditer(line):
            code = match.group(1).upper()
            if code in seen:
                continue
            seen.add(code)
            remainder = line[: match.start()] + line[match.end() :]
            remainder = re.sub(r"\([^)]*\)", " ", remainder)  # drop parenthetical annotations
            remainder = re.sub(r"\*+", "", remainder)
            remainder = remainder.strip(" \t-–—:()*•")
            mentions.append((code, remainder))
    return mentions


def _exact_match(db: Session, codes: list[str]) -> dict[str, Icd10Code]:
    if not codes:
        return {}
    rows = db.query(Icd10Code).filter(func.upper(Icd10Code.code).in_(codes)).all()
    return {row.code.upper(): row for row in rows}


def resolve_icd10_codes(db: Session, candidate_codes: list[str]) -> list[dict]:
    """Exact-match only -- used to re-validate an already-resolved, client-submitted code list
    (draft autosave / save), where there's no surrounding free text to fall back on."""
    if not candidate_codes:
        return []
    uppered = [c.upper() for c in candidate_codes]
    by_code = _exact_match(db, uppered)
    resolved = []
    seen: set[str] = set()
    for code in uppered:
        row = by_code.get(code)
        if row and row.code.upper() not in seen:
            seen.add(row.code.upper())
            resolved.append({"code": row.code, "description": row.description})
    return resolved


def resolve_icd10_codes_from_text(db: Session, text: str) -> list[dict]:
    """Exact-match first; for any code that doesn't match a real seeded row, fall back to
    semantic search on its nearby description text so a close real code still gets attached."""
    mentions = _extract_code_mentions(text)
    if not mentions:
        return []
    by_code = _exact_match(db, [code for code, _ in mentions])

    resolved: list[dict] = []
    seen: set[str] = set()
    for code, remainder in mentions:
        row = by_code.get(code)
        if row is None and remainder:
            top = search_icd10(db, remainder, limit=1)
            if top and top[0][1] >= _SEMANTIC_FALLBACK_THRESHOLD:
                row = top[0][0]
        if row and row.code.upper() not in seen:
            seen.add(row.code.upper())
            resolved.append({"code": row.code, "description": row.description})
    return resolved


def normalize_assessment_icd10_placement(text: str, resolved_codes: list[dict]) -> str:
    """
    Strips the model's own inline ICD-10 code mentions out of the Assessment prose -- wherever
    it happened to put them, since the free-tier model is inconsistent about this (sometimes
    mid-paragraph, sometimes trailing, sometimes prefixed with "CODE", sometimes not) -- and
    re-appends the resolved, lookup-table-verified codes as a clean block at the very end. This
    makes code placement deterministic on every generation instead of depending on the model's
    formatting.

    A line whose code mention(s) are its only real content (the common case -- a dedicated
    "CODE - Description" line) is dropped entirely, including hallucinated codes that didn't
    resolve to a real seeded row (showing a fabricated code would be worse than dropping the
    line). But if a code is embedded inline within a longer line that also carries independent
    clinical reasoning (rare, but possible), only the code token itself is stripped -- dropping
    the whole line would destroy that reasoning, which matters more than perfect placement.
    """
    lines = (text or "").split("\n")
    kept_lines = []
    for line in lines:
        if not _CODE_CANDIDATE_RE.search(line):
            kept_lines.append(line)
            continue
        remainder = _CODE_CANDIDATE_RE.sub("", line)
        if len(remainder.split()) <= 10:
            continue  # essentially just a code mention -- drop the whole line
        kept_lines.append(re.sub(r"[ \t]{2,}", " ", remainder))
    body = "\n".join(kept_lines).strip()
    if not resolved_codes:
        return body
    codes_block = "\n".join(f"{c['code']} - {c['description']}" for c in resolved_codes)
    return f"{body}\n\nICD-10:\n{codes_block}" if body else f"ICD-10:\n{codes_block}"
