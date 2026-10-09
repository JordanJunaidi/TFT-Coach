"""CLI: ingest a player's recent TFT matches into Postgres.

Usage: python -m tftcoach.ingest --riot-id "Name#TAG" [--count 150]
"""

import argparse

from tftcoach.config import get_settings
from tftcoach.db.core import connect
from tftcoach.ingest.pipeline import ingest_player
from tftcoach.riot.client import RiotClient, parse_riot_id


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Ingest recent TFT matches")
    parser.add_argument("--riot-id", required=True, help='Riot ID, e.g. "Name#TAG"')
    parser.add_argument("--count", type=int, default=150, help="how many recent matches")
    args = parser.parse_args(argv)

    game_name, tag_line = parse_riot_id(args.riot_id)
    settings = get_settings()
    with (
        connect(settings.database_url) as conn,
        RiotClient(settings.riot_api_key.get_secret_value(), settings.riot_region) as client,
    ):
        result = ingest_player(conn, client, game_name, tag_line, args.count, progress=True)

    print(
        f"Listed {result.listed} matches: {result.skipped} already stored, "
        f"{result.fetched} fetched. API calls this run: {result.api_calls} "
        f"({result.fetched} match details)."
    )


if __name__ == "__main__":
    main()
