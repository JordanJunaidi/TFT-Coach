import json
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import psycopg
import pytest

from tftcoach.db.core import init_schema

FIXTURES = Path(__file__).parent / "fixtures"
MATCH_FIXTURE = FIXTURES / "match_NA1_5656832942.json"
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "postgresql://localhost/tftcoach_test")

TABLES = [
    "units", "traits", "participants", "matches", "raw_matches",
    "players", "patches", "static_names",
]  # fmt: skip


@pytest.fixture
def match_payload() -> dict[str, Any]:
    return json.loads(MATCH_FIXTURE.read_text())


@pytest.fixture
def db() -> Iterator[psycopg.Connection]:
    """A fresh schema in the test database. Skips if Postgres isn't reachable."""
    # Guard against ever pointing this destructive fixture at a real database.
    assert psycopg.conninfo.conninfo_to_dict(TEST_DATABASE_URL)["dbname"].endswith("_test")
    try:
        conn = psycopg.connect(TEST_DATABASE_URL)
    except psycopg.OperationalError as exc:
        pytest.skip(f"test database unavailable: {exc}")
    with conn:
        conn.execute(f"DROP TABLE IF EXISTS {', '.join(TABLES)} CASCADE")
        init_schema(conn)
        yield conn
