"""CLI: print a player's recent TFT match IDs and save one match as JSON.

Usage: python -m tftcoach.riot --riot-id "Name#TAG"
"""

import argparse
import json
from pathlib import Path

from tftcoach.config import get_settings
from tftcoach.riot.client import RiotClient, parse_riot_id

DEFAULT_OUT_DIR = Path("tests/fixtures")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--riot-id", required=True, help='Riot ID, e.g. "Name#TAG"')
    parser.add_argument("--count", type=int, default=20, help="number of match IDs to list")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args(argv)

    game_name, tag_line = parse_riot_id(args.riot_id)
    settings = get_settings()

    with RiotClient(settings.riot_api_key.get_secret_value(), settings.riot_region) as client:
        puuid = client.get_puuid(game_name, tag_line)
        match_ids = client.get_match_ids(puuid, count=args.count)
        print(f"{len(match_ids)} most recent matches for {args.riot_id}:")
        for match_id in match_ids:
            print(f"  {match_id}")

        if not match_ids:
            return
        match = client.get_match(match_ids[0])

    args.out_dir.mkdir(parents=True, exist_ok=True)
    out_path = args.out_dir / f"match_{match_ids[0]}.json"
    out_path.write_text(json.dumps(match, indent=2))
    print(f"Saved {match_ids[0]} to {out_path}")


if __name__ == "__main__":
    main()
