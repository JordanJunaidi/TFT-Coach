"""Connection, schema, and patch-table helpers."""

import csv
from importlib import resources

import psycopg

# Patches roll out to NA during the Pacific-time day, so a match's local date decides its patch.
PATCH_TIMEZONE = "America/Los_Angeles"


def connect(database_url: str) -> psycopg.Connection:
    return psycopg.connect(database_url)


def init_schema(conn: psycopg.Connection) -> None:
    schema = resources.files("tftcoach.db").joinpath("schema.sql").read_text()
    conn.execute(schema)  # type: ignore[arg-type]  # trusted, static SQL shipped with the package
    seed_patches(conn)
    conn.commit()


def seed_patches(conn: psycopg.Connection) -> None:
    """Upsert patches.csv into `patches`, then re-derive every match's patch."""
    with resources.files("tftcoach.db").joinpath("patches.csv").open() as f:
        rows = [(r["patch"], int(r["set_number"]), r["start_date"]) for r in csv.DictReader(f)]
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO patches (patch, set_number, start_date) VALUES (%s, %s, %s)
            ON CONFLICT (patch) DO UPDATE
            SET set_number = EXCLUDED.set_number, start_date = EXCLUDED.start_date
            """,
            rows,
        )
    assign_patches(conn)


def assign_patches(conn: psycopg.Connection) -> None:
    """Set matches.patch to the latest patch that started on or before the match date.

    Re-run whenever patches.csv changes, so adding a patch fixes already-ingested matches.
    """
    conn.execute(
        """
        UPDATE matches m
        SET patch = (
            SELECT p.patch FROM patches p
            WHERE p.start_date <= (m.game_datetime AT TIME ZONE %s)::date
            ORDER BY p.start_date DESC
            LIMIT 1
        )
        """,
        (PATCH_TIMEZONE,),
    )
