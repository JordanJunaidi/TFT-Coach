"""Fetch a player's recent matches and store the ones not already in the database."""

from dataclasses import dataclass

import psycopg

from tftcoach.db.core import assign_patches
from tftcoach.ingest.parse import parse_match
from tftcoach.ingest.store import get_cached_puuid, save_match, save_player, stored_match_ids
from tftcoach.riot.client import RiotClient

# Page size for the match-ID endpoint. Paging keeps each request small and predictable.
PAGE_SIZE = 100


@dataclass
class IngestResult:
    puuid: str
    listed: int
    skipped: int
    fetched: int
    api_calls: int


def list_match_ids(client: RiotClient, puuid: str, count: int) -> list[str]:
    match_ids: list[str] = []
    while len(match_ids) < count:
        page = client.get_match_ids(
            puuid, count=min(PAGE_SIZE, count - len(match_ids)), start=len(match_ids)
        )
        match_ids.extend(page)
        if len(page) < PAGE_SIZE:
            break  # no older matches available
    return match_ids


def ingest_player(
    conn: psycopg.Connection,
    client: RiotClient,
    game_name: str,
    tag_line: str,
    count: int,
    progress: bool = False,
) -> IngestResult:
    calls_before = client.request_count

    puuid = get_cached_puuid(conn, game_name, tag_line)
    if puuid is None:
        puuid = client.get_puuid(game_name, tag_line)
        save_player(conn, puuid, game_name, tag_line)
        conn.commit()

    match_ids = list_match_ids(client, puuid, count)
    already_stored = stored_match_ids(conn, match_ids)
    to_fetch = [m for m in match_ids if m not in already_stored]
    conn.commit()  # end the implicit read transaction so each match below commits on its own

    for i, match_id in enumerate(to_fetch, start=1):
        payload = client.get_match(match_id)
        match = parse_match(payload)
        # One transaction per match: an interrupted run leaves only complete matches behind,
        # and the next run picks up where this one stopped.
        with conn.transaction():
            save_match(conn, payload, match)
        if progress:
            print(f"  [{i}/{len(to_fetch)}] {match_id}", flush=True)

    assign_patches(conn)
    conn.commit()
    return IngestResult(
        puuid=puuid,
        listed=len(match_ids),
        skipped=len(already_stored),
        fetched=len(to_fetch),
        api_calls=client.request_count - calls_before,
    )
