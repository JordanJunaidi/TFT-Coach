"""Load a player's boards and related lookups from Postgres."""

import psycopg

from tftcoach.analysis.comps import BoardTrait, BoardUnit, PlayerBoard
from tftcoach.ingest.parse import RANKED_QUEUE_ID
from tftcoach.ingest.store import get_cached_puuid

ALL_PATCHES = "all"
LATEST_PATCH = "latest"
PREVIOUS_PATCH = "previous"


class NoDataError(Exception):
    """Raised when a player or patch has no stored games."""


def puuid_for_riot_id(conn: psycopg.Connection, game_name: str, tag_line: str) -> str:
    puuid = get_cached_puuid(conn, game_name, tag_line)
    if puuid is None:
        raise NoDataError(f"No stored player {game_name}#{tag_line}. Run ingestion first.")
    return puuid


def played_patches(conn: psycopg.Connection, puuid: str, ranked_only: bool = True) -> list[str]:
    """Patches the player has games on, newest first."""
    rows = conn.execute(
        """
        SELECT p.patch
        FROM patches p
        WHERE EXISTS (
            SELECT 1 FROM matches m JOIN participants pa USING (match_id)
            WHERE m.patch = p.patch AND pa.puuid = %(puuid)s
              AND (NOT %(ranked_only)s OR m.queue_id = %(ranked)s)
        )
        ORDER BY p.start_date DESC
        """,
        {"puuid": puuid, "ranked_only": ranked_only, "ranked": RANKED_QUEUE_ID},
    ).fetchall()
    return [row[0] for row in rows]


def resolve_patch(
    conn: psycopg.Connection, puuid: str, patch: str, ranked_only: bool = True
) -> str | None:
    """Turn "latest"/"previous"/"all"/"18.3" into a concrete patch, or None for all patches."""
    if patch == ALL_PATCHES:
        return None
    if patch not in (LATEST_PATCH, PREVIOUS_PATCH):
        return patch
    patches = played_patches(conn, puuid, ranked_only)
    index = 0 if patch == LATEST_PATCH else 1
    if len(patches) <= index:
        raise NoDataError(f"No games found for the {patch} patch.")
    return patches[index]


def load_boards(
    conn: psycopg.Connection, puuid: str, patch: str | None, ranked_only: bool = True
) -> list[PlayerBoard]:
    params = {
        "puuid": puuid,
        "patch": patch,
        "ranked_only": ranked_only,
        "ranked": RANKED_QUEUE_ID,
    }
    games = conn.execute(
        """
        SELECT m.match_id, m.patch, pa.placement
        FROM matches m JOIN participants pa USING (match_id)
        WHERE pa.puuid = %(puuid)s
          AND (%(patch)s::text IS NULL OR m.patch = %(patch)s)
          AND (NOT %(ranked_only)s OR m.queue_id = %(ranked)s)
        ORDER BY m.game_datetime DESC
        """,
        params,
    ).fetchall()
    boards = {match_id: PlayerBoard(match_id, p, placement) for match_id, p, placement in games}
    if not boards:
        return []

    match_ids = list(boards)
    for match_id, character_id, star, rarity, items in conn.execute(
        """
        SELECT match_id, character_id, star_level, rarity, items FROM units
        WHERE puuid = %s AND match_id = ANY(%s)
        """,
        (puuid, match_ids),
    ):
        boards[match_id].units.append(BoardUnit(character_id, star, rarity, tuple(items)))

    for match_id, trait_id, num_units, style, tier_current, tier_total in conn.execute(
        """
        SELECT match_id, trait_id, num_units, style, tier_current, tier_total FROM traits
        WHERE puuid = %s AND match_id = ANY(%s)
        """,
        (puuid, match_ids),
    ):
        boards[match_id].traits.append(
            BoardTrait(trait_id, num_units, style, tier_current, tier_total)
        )

    return list(boards.values())


def load_display_names(conn: psycopg.Connection) -> dict[str, str]:
    return dict(conn.execute("SELECT api_name, display_name FROM static_names").fetchall())


def load_item_components(conn: psycopg.Connection) -> dict[str, list[str]]:
    return dict(
        conn.execute(
            "SELECT api_name, components FROM static_names WHERE components IS NOT NULL"
        ).fetchall()
    )
