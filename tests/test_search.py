from typing import Any

import psycopg

from tests.fakes import FakeEmbedder
from tftcoach.db.core import seed_patches
from tftcoach.rag.chunk import chunk_notes
from tftcoach.rag.index import index_chunks
from tftcoach.rag.search import RECENCY_PENALTY, SearchResult, rerank, search_notes


def result(key: str, patch: str, entity: str | None, similarity: float) -> SearchResult:
    return SearchResult(key, patch, "Traits", entity, None, "text", similarity, similarity)


def test_rerank_keeps_only_newest_chunk_per_entity() -> None:
    candidates = [
        result("18.2-5", "18.2", "Juggernaut", 0.90),
        result("18.4-20", "18.4", "Juggernaut", 0.80),
        result("18.4-21", "18.4", "Lunar", 0.50),
    ]
    ranked = rerank(candidates, ["18.4", "18.3", "18.2"], k=5)
    assert [r.chunk_key for r in ranked] == ["18.4-20", "18.4-21"]


def test_rerank_entity_match_ignores_parenthetical() -> None:
    candidates = [
        result("18.3-1", "18.3", "Executioner", 0.9),
        result("18.4-1", "18.4", "Executioner (3/4)", 0.7),
    ]
    assert [r.chunk_key for r in rerank(candidates, ["18.4", "18.3"], k=5)] == ["18.4-1"]


def test_rerank_penalizes_older_patches() -> None:
    candidates = [result("18.3-1", "18.3", None, 0.80), result("18.4-1", "18.4", None, 0.79)]
    ranked = rerank(candidates, ["18.4", "18.3"], k=5)
    assert ranked[0].chunk_key == "18.4-1"
    assert ranked[1].score == 0.80 - RECENCY_PENALTY


NOTES_184 = """## LARGE CHANGES
### TRAITS
- Juggernaut
  - Durability: 20/33/45% ⇒ 20/30/42%
- Lunar
  - Ability Power: 7/10/14/18% ⇒ 7/12/16/20%
"""
NOTES_183 = """## LARGE CHANGES
### TRAITS
- Juggernaut
  - Durability: 15/30/45% ⇒ 20/33/45%
"""


def index(db: psycopg.Connection, embedder: FakeEmbedder) -> list[Any]:
    seed_patches(db)
    return [
        index_chunks(db, "18.3", chunk_notes(NOTES_183, "18.3"), embedder),
        index_chunks(db, "18.4", chunk_notes(NOTES_184, "18.4"), embedder),
    ]


def test_index_reuses_cached_embeddings(db: psycopg.Connection) -> None:
    embedder = FakeEmbedder()
    first = index(db, embedder)
    assert [r.embedded for r in first] == [1, 2]

    second = index(db, embedder)
    assert [r.embedded for r in second] == [0, 0]
    assert db.execute("SELECT count(*) FROM patch_chunks").fetchone()[0] == 3


def test_search_prefers_newest_patch_and_can_filter(
    db: psycopg.Connection, fake_search_cutoff
) -> None:
    embedder = FakeEmbedder()
    index(db, embedder)

    [top, *_] = search_notes(db, embedder, "Juggernaut durability")
    assert (top.patch, top.entity) == ("18.4", "Juggernaut")

    filtered = search_notes(db, embedder, "Juggernaut durability", patch="18.3")
    assert [r.chunk_key for r in filtered] == ["18.3-1"]


def test_lexical_bonus_requires_whole_word() -> None:
    from tftcoach.rag.search import LEXICAL_BONUS, lexical_bonus

    assert lexical_bonus("Juggernaut nerf", "- Juggernaut\n  - Durability") == LEXICAL_BONUS
    assert lexical_bonus("Jugg", "- Juggernaut") == 0.0
    assert lexical_bonus("an", "anything") == 0.0  # words under 3 letters are ignored


def test_low_scores_are_dropped(db: psycopg.Connection) -> None:
    embedder = FakeEmbedder()
    index(db, embedder)
    assert search_notes(db, embedder, "Juggernaut durability", min_score=0.99) == []
    assert search_notes(db, embedder, "Juggernaut durability", min_score=0)
