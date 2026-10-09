"""Write raw and parsed matches to Postgres."""

from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from tftcoach.ingest.parse import Match


def stored_match_ids(conn: psycopg.Connection, match_ids: list[str]) -> set[str]:
    rows = conn.execute(
        "SELECT match_id FROM raw_matches WHERE match_id = ANY(%s)", (match_ids,)
    ).fetchall()
    return {row[0] for row in rows}


def get_cached_puuid(conn: psycopg.Connection, game_name: str, tag_line: str) -> str | None:
    row = conn.execute(
        """
        SELECT puuid FROM players
        WHERE lower(game_name) = lower(%s) AND lower(tag_line) = lower(%s)
        """,
        (game_name, tag_line),
    ).fetchone()
    return row[0] if row else None


def save_player(conn: psycopg.Connection, puuid: str, game_name: str, tag_line: str) -> None:
    conn.execute(
        """
        INSERT INTO players (puuid, game_name, tag_line) VALUES (%s, %s, %s)
        ON CONFLICT (puuid) DO UPDATE
        SET game_name = EXCLUDED.game_name, tag_line = EXCLUDED.tag_line
        """,
        (puuid, game_name, tag_line),
    )


def save_match(conn: psycopg.Connection, payload: dict[str, Any], match: Match) -> None:
    """Store the raw payload and its parsed rows. Call inside a transaction."""
    info = match.info
    match_id = match.metadata.match_id
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO raw_matches (match_id, payload) VALUES (%s, %s)",
            (match_id, Jsonb(payload)),
        )
        cur.execute(
            """
            INSERT INTO matches (match_id, game_datetime, game_length, queue_id, set_number)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (match_id, info.played_at, info.game_length, info.queue_id, info.tft_set_number),
        )
        cur.executemany(
            """
            INSERT INTO participants (match_id, puuid, placement, level, gold_left, last_round,
                time_eliminated, players_eliminated, damage_to_players, game_name, tag_line)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            [
                (match_id, p.puuid, p.placement, p.level, p.gold_left, p.last_round,
                 p.time_eliminated, p.players_eliminated, p.total_damage_to_players,
                 p.game_name, p.tag_line)
                for p in info.participants
            ],
        )  # fmt: skip
        cur.executemany(
            """
            INSERT INTO traits (match_id, puuid, trait_id, num_units, style,
                tier_current, tier_total)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            [
                (match_id, p.puuid, t.name, t.num_units, t.style, t.tier_current, t.tier_total)
                for p in info.participants
                for t in p.traits
            ],
        )
        cur.executemany(
            """
            INSERT INTO units (match_id, puuid, character_id, star_level, rarity, items)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            [
                (match_id, p.puuid, u.character_id, u.tier, u.rarity, u.items)
                for p in info.participants
                for u in p.units
            ],
        )
