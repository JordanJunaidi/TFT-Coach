"""CLI: personal stats.

Usage: python -m tftcoach.analysis top-comps --riot-id "Name#TAG" [--patch latest|previous|all|18.3]
"""

import argparse

from tftcoach.analysis.comps import comp_label, display_name, summarize_comps
from tftcoach.analysis.queries import (
    LATEST_PATCH,
    load_boards,
    load_display_names,
    load_item_components,
    puuid_for_riot_id,
    resolve_patch,
)
from tftcoach.config import get_settings
from tftcoach.db.core import connect
from tftcoach.riot.client import parse_riot_id

# Below this many games, a comp's numbers are mostly noise.
MIN_RELIABLE_GAMES = 10


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="TFT Coach personal stats")
    parser.add_argument("command", choices=["top-comps"])
    parser.add_argument("--riot-id", required=True, help='Riot ID, e.g. "Name#TAG"')
    parser.add_argument(
        "--patch", default=LATEST_PATCH, help='"latest", "previous", "all", or e.g. "18.3"'
    )
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--include-normals", action="store_true", help="include non-ranked games")
    parser.add_argument(
        "--by-trait", action="store_true", help="split comps by main trait as well as carry"
    )
    args = parser.parse_args(argv)

    game_name, tag_line = parse_riot_id(args.riot_id)
    ranked_only = not args.include_normals
    with connect(get_settings().database_url) as conn:
        puuid = puuid_for_riot_id(conn, game_name, tag_line)
        patch = resolve_patch(conn, puuid, args.patch, ranked_only)
        boards = load_boards(conn, puuid, patch, ranked_only)
        names = load_display_names(conn)
        components = load_item_components(conn)

    scope = f"patch {patch}" if patch else "all patches"
    queue = "ranked" if ranked_only else "all queues"
    print(f"Top {args.limit} comps for {args.riot_id}, {scope} ({queue}, {len(boards)} games)\n")
    if not boards:
        print("No games found.")
        return

    header = "Comp" if args.by_trait else "Carry"
    detail = "" if args.by_trait else f" {'Usual trait':<16}"
    print(f"{header:<28}{detail} {'Games':>5} {'Avg place':>9} {'Top 4':>6}")
    for stats in summarize_comps(boards, components, by_trait=args.by_trait)[: args.limit]:
        trait = "" if args.by_trait else f" {display_name(stats.usual_trait, names):<16}"
        note = "  (small sample)" if stats.games < MIN_RELIABLE_GAMES else ""
        print(
            f"{comp_label(stats.comp, names):<28}{trait} {stats.games:>5} "
            f"{stats.avg_placement:>9.2f} {stats.top4_rate:>6.0%}{note}"
        )


if __name__ == "__main__":
    main()
