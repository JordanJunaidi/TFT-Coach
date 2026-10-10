"""CLI: patch-notes retrieval.

Usage:
  python -m tftcoach.rag fetch 18.5          # download notes to patch_notes/18.5.md
  python -m tftcoach.rag index               # chunk + embed every file in patch_notes/
  python -m tftcoach.rag search "juggernaut nerf" [--patch 18.4]
"""

import argparse

from tftcoach.config import get_settings
from tftcoach.db.core import connect
from tftcoach.openai_compat import OpenAICompatClient
from tftcoach.rag.embed import APIEmbedder
from tftcoach.rag.index import index_notes_file
from tftcoach.rag.notes import NOTES_DIR, fetch_notes
from tftcoach.rag.search import search_notes


def make_embedder() -> tuple[APIEmbedder, OpenAICompatClient]:
    settings = get_settings()
    if settings.llm_api_key is None:
        raise SystemExit("LLM_API_KEY is not set in .env")
    client = OpenAICompatClient(settings.llm_base_url, settings.llm_api_key.get_secret_value())
    return APIEmbedder(client, settings.embedding_model, settings.embedding_dims), client


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="TFT Coach patch-notes retrieval")
    sub = parser.add_subparsers(dest="command", required=True)
    fetch = sub.add_parser("fetch")
    fetch.add_argument("patch")
    sub.add_parser("index")
    search = sub.add_parser("search")
    search.add_argument("query")
    search.add_argument("--patch")
    search.add_argument("-k", type=int, default=5)
    args = parser.parse_args(argv)

    if args.command == "fetch":
        print(f"Saved {fetch_notes(args.patch)}")
        return

    embedder, client = make_embedder()
    try:
        with connect(get_settings().database_url) as conn:
            if args.command == "index":
                for path in sorted(NOTES_DIR.glob("*.md")):
                    result = index_notes_file(conn, path, embedder)
                    print(
                        f"{result.patch}: {result.chunks} chunks ({result.embedded} newly embedded)"
                    )
            else:
                for r in search_notes(conn, embedder, args.query, args.patch, args.k):
                    where = f"[{r.chunk_key}] {r.section} / {r.entity or '-'}"
                    print(f"{where}  sim={r.similarity:.3f} score={r.score:.3f}")
                    print("   " + r.content.split("\n\n", 1)[-1][:200].replace("\n", " | "))
    finally:
        client.close()


if __name__ == "__main__":
    main()
