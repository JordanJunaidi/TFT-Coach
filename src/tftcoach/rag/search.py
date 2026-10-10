"""Vector search over patch-note chunks, preferring newer patches."""

import re
from dataclasses import dataclass, replace

import numpy as np
import psycopg
from pgvector.psycopg import register_vector

from tftcoach.rag.embed import Embedder

# Score penalty per patch of age when no patch is specified. Similarities of relevant
# chunks typically differ by a few hundredths, so this nudges ties toward newer notes
# without letting a stale but much better match lose to an irrelevant new one.
RECENCY_PENALTY = 0.03
# Candidates pulled from SQL before re-ranking and de-duplication in Python.
CANDIDATE_MULTIPLIER = 4
# Embeddings are weak at exact names ("Maokai" scored 0.63 against unrelated chunks while
# the real Juggernaut chunk scored 0.67), so chunks that literally contain a query word get
# a bonus, and results below MIN_SCORE are dropped. A search for something that isn't in
# the notes then returns nothing, which tells the model "no changes" instead of handing it
# noise. Hand-tuned on spot checks; Milestone 5 evaluates vector vs. hybrid properly.
LEXICAL_BONUS = 0.10
MIN_SCORE = 0.65


@dataclass(frozen=True)
class SearchResult:
    chunk_key: str
    patch: str
    section: str
    entity: str | None
    midpatch: str | None
    content: str
    similarity: float
    score: float


def _query_words(query: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9']+", query.lower()) if len(w) >= 3}


def lexical_bonus(query: str, content: str) -> float:
    text = content.lower()
    hit = any(re.search(rf"\b{re.escape(w)}\b", text) for w in _query_words(query))
    return LEXICAL_BONUS if hit else 0.0


def _entity_key(entity: str | None) -> str | None:
    return entity.split("(")[0].strip().lower() if entity else None


def rerank(candidates: list[SearchResult], patch_order: list[str], k: int) -> list[SearchResult]:
    """Apply the recency penalty to each score, keep the newest chunk per entity, return top k.

    `patch_order` lists patches newest first. If Juggernaut changed in 18.2 and again in
    18.4, only the 18.4 chunk survives, so the model can't present a superseded value as
    current. (Asking about a specific patch bypasses this by filtering instead.)
    """
    age = {patch: i for i, patch in enumerate(patch_order)}
    newest_patch_for: dict[str, int] = {}
    for c in candidates:
        key = _entity_key(c.entity)
        if key is not None:
            newest_patch_for[key] = min(
                newest_patch_for.get(key, len(age)), age.get(c.patch, len(age))
            )

    kept = [
        replace(c, score=c.score - RECENCY_PENALTY * age.get(c.patch, len(age)))
        for c in candidates
        if (key := _entity_key(c.entity)) is None
        or age.get(c.patch, len(age)) == newest_patch_for[key]
    ]
    return sorted(kept, key=lambda r: r.score, reverse=True)[:k]


def indexed_patches(conn: psycopg.Connection) -> list[str]:
    """Patches that have indexed notes, newest first."""
    rows = conn.execute(
        """
        SELECT p.patch FROM patches p
        WHERE EXISTS (SELECT 1 FROM patch_chunks c WHERE c.patch = p.patch)
        ORDER BY p.start_date DESC
        """
    ).fetchall()
    return [row[0] for row in rows]


def search_notes(
    conn: psycopg.Connection,
    embedder: Embedder,
    query: str,
    patch: str | None = None,
    k: int = 5,
    min_score: float | None = None,
) -> list[SearchResult]:
    """Top-k chunks for `query`. `min_score` defaults to MIN_SCORE; pass 0 to keep all."""
    register_vector(conn)
    [vector] = embedder.embed([query])
    rows = conn.execute(
        """
        SELECT chunk_key, patch, section, entity, midpatch, content,
               1 - (embedding <=> %(q)s) AS similarity
        FROM patch_chunks
        WHERE %(patch)s::text IS NULL OR patch = %(patch)s
        ORDER BY embedding <=> %(q)s
        LIMIT %(limit)s
        """,
        {
            "q": np.array(vector, dtype=np.float32),
            "patch": patch,
            "limit": k * CANDIDATE_MULTIPLIER,
        },
    ).fetchall()
    candidates = [SearchResult(*row, score=row[-1] + lexical_bonus(query, row[5])) for row in rows]
    threshold = MIN_SCORE if min_score is None else min_score
    candidates = [c for c in candidates if c.score >= threshold]
    if patch is not None:
        return sorted(candidates, key=lambda r: r.score, reverse=True)[:k]
    return rerank(candidates, indexed_patches(conn), k)
