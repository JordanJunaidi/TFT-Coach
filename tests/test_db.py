"""Integration tests against the local Postgres test database."""

import json
from typing import Any

import httpx
import psycopg

from tests.conftest import FIXTURES
from tftcoach.analysis.comps import summarize_comps
from tftcoach.analysis.queries import (
    load_boards,
    load_item_components,
    resolve_patch,
    resolve_set,
)
from tftcoach.db.core import seed_patches
from tftcoach.db.static_data import load_static_names
from tftcoach.ingest.parse import parse_match
from tftcoach.ingest.pipeline import ingest_player
from tftcoach.ingest.store import save_match
from tftcoach.riot.client import RiotClient


def store(db: psycopg.Connection, payload: dict[str, Any]) -> None:
    with db.transaction():
        save_match(db, payload, parse_match(payload))
    seed_patches(db)


def test_save_match_writes_all_tables(db: psycopg.Connection, match_payload) -> None:
    store(db, match_payload)

    def count(table: str) -> int:
        return db.execute(f"SELECT count(*) FROM {table}").fetchone()[0]

    participants = match_payload["info"]["participants"]
    assert count("participants") == 8
    assert count("units") == sum(len(p["units"]) for p in participants)
    assert count("traits") == sum(len(p["traits"]) for p in participants)


def test_patch_is_derived_from_pacific_date(db: psycopg.Connection, match_payload) -> None:
    # 2026-10-09 03:55 UTC is the evening of Oct 8 in Pacific time, after 18.4 (Oct 7).
    store(db, match_payload)
    assert db.execute("SELECT patch FROM matches").fetchone()[0] == "18.4"


def test_match_before_first_known_patch_has_no_patch(db: psycopg.Connection, match_payload):
    match_payload["info"]["game_datetime"] = 1_600_000_000_000  # 2020
    store(db, match_payload)
    assert db.execute("SELECT patch FROM matches").fetchone()[0] is None


def test_loaded_boards_match_payload(db: psycopg.Connection, match_payload) -> None:
    store(db, match_payload)
    player = match_payload["info"]["participants"][0]

    boards = load_boards(db, player["puuid"], patch="18.4")

    assert len(boards) == 1
    assert boards[0].placement == player["placement"]
    assert len(boards[0].units) == len(player["units"])
    assert summarize_comps(boards, {})[0].games == 1
    assert load_boards(db, player["puuid"], patch="18.3") == []


def test_resolve_patch_keywords(db: psycopg.Connection, match_payload) -> None:
    store(db, match_payload)
    puuid = match_payload["info"]["participants"][0]["puuid"]

    assert resolve_patch(db, puuid, "latest") == "18.4"
    assert resolve_patch(db, puuid, "all") is None
    assert resolve_patch(db, puuid, "18.2") == "18.2"


def test_static_names_load(db: psycopg.Connection) -> None:
    data = json.loads((FIXTURES / "cdragon_tft_sample.json").read_text())
    load_static_names(db, data)
    row = db.execute("SELECT display_name FROM static_names WHERE api_name = 'DA_18_Diana'")
    assert row.fetchone()[0] == "Diana"
    assert load_item_components(db)["DA_InfinityEdge"] == [
        "DA_Component_BFSword",
        "DA_Component_SparringGloves",
    ]


def test_reingest_makes_no_duplicate_calls(db: psycopg.Connection, match_payload) -> None:
    match_id = match_payload["metadata"]["match_id"]
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if "/accounts/by-riot-id/" in request.url.path:
            return httpx.Response(200, json={"puuid": "me"})
        if request.url.path.endswith("/ids"):
            return httpx.Response(200, json=[match_id])
        return httpx.Response(200, json=match_payload)

    def run():
        with RiotClient("key", transport=httpx.MockTransport(handler)) as client:
            return ingest_player(db, client, "monk", "monke", count=20)

    first = run()
    assert (first.fetched, first.skipped) == (1, 0)
    assert len(calls) == 3  # account, match IDs, match details

    calls.clear()
    second = run()
    assert (second.fetched, second.skipped) == (0, 1)
    assert calls == ["/tft/match/v1/matches/by-puuid/me/ids"]  # PUUID cached, match skipped


def test_set_filter_excludes_previous_sets(db: psycopg.Connection, match_payload) -> None:
    store(db, match_payload)
    old = json.loads(json.dumps(match_payload))
    old["metadata"]["match_id"] = "NA1_OLD"
    old["info"]["tft_set_number"] = 17
    old["info"]["game_datetime"] = 1_780_000_000_000  # May 2026, Set 17
    store(db, old)
    puuid = match_payload["info"]["participants"][0]["puuid"]

    assert resolve_set(db, puuid, "current") == 18
    assert resolve_set(db, puuid, "all") is None
    assert resolve_set(db, puuid, "17") == 17
    assert [b.match_id for b in load_boards(db, puuid, None, set_number=18)] == ["NA1_5656832942"]
    assert len(load_boards(db, puuid, None, set_number=None)) == 2
