"""Chunk, embed, and store patch notes."""

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import psycopg
from pgvector.psycopg import register_vector

from tftcoach.rag.chunk import Chunk, chunk_notes
from tftcoach.rag.embed import Embedder


@dataclass
class IndexResult:
    patch: str
    chunks: int
    embedded: int  # chunks that needed a new embedding (the rest came from the cache)


def _cached_embeddings(
    conn: psycopg.Connection, hashes: list[str], model: str
) -> dict[str, np.ndarray]:
    rows = conn.execute(
        "SELECT content_hash, embedding FROM embedding_cache "
        "WHERE model = %s AND content_hash = ANY(%s)",
        (model, hashes),
    ).fetchall()
    return dict(rows)


def index_chunks(
    conn: psycopg.Connection, patch: str, chunks: list[Chunk], embedder: Embedder
) -> IndexResult:
    """Replace a patch's chunks, embedding only text not already in the cache."""
    register_vector(conn)
    cache = _cached_embeddings(conn, [c.content_hash for c in chunks], embedder.model)
    missing = list({c.content_hash: c for c in chunks if c.content_hash not in cache}.values())
    if missing:
        vectors = embedder.embed([c.content for c in missing])
        new = {
            c.content_hash: np.array(v, dtype=np.float32)
            for c, v in zip(missing, vectors, strict=True)
        }
        conn.cursor().executemany(
            "INSERT INTO embedding_cache (content_hash, model, embedding) VALUES (%s, %s, %s) "
            "ON CONFLICT DO NOTHING",
            [(h, embedder.model, v) for h, v in new.items()],
        )
        cache.update(new)

    with conn.transaction():
        conn.execute("DELETE FROM patch_chunks WHERE patch = %s", (patch,))
        conn.cursor().executemany(
            """
            INSERT INTO patch_chunks
                (chunk_key, patch, section, entity, midpatch, content, content_hash, embedding)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            [
                (c.key, c.patch, c.section, c.entity, c.midpatch, c.content, c.content_hash,
                 cache[c.content_hash])
                for c in chunks
            ],
        )  # fmt: skip
    conn.commit()
    return IndexResult(patch=patch, chunks=len(chunks), embedded=len(missing))


def index_notes_file(conn: psycopg.Connection, path: Path, embedder: Embedder) -> IndexResult:
    patch = path.stem  # files are named "<patch>.md"
    return index_chunks(conn, patch, chunk_notes(path.read_text(encoding="utf-8"), patch), embedder)
