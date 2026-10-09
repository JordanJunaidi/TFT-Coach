"""Load internal-ID -> display-name mappings from Community Dragon's TFT static data."""

from typing import Any

import httpx
import psycopg

CDRAGON_TFT_URL = "https://raw.communitydragon.org/latest/cdragon/tft/en_us.json"


def fetch_static_data(url: str = CDRAGON_TFT_URL) -> dict[str, Any]:
    response = httpx.get(url, timeout=60.0, follow_redirects=True)
    response.raise_for_status()
    return response.json()


NameRow = tuple[str, str, str, int | None, list[str] | None]


def extract_names(data: dict[str, Any]) -> list[NameRow]:
    """Return (api_name, kind, display_name, set_number, components) rows.

    `components` is the item's recipe for items and None for units and traits.

    `setData` holds one entry per game mode of a set (standard, Double Up, etc.), so the
    same unit appears several times; the first occurrence wins.
    """
    rows: dict[str, NameRow] = {}
    for set_entry in data.get("setData", []):
        set_number = set_entry.get("number")
        for kind, key in (("unit", "champions"), ("trait", "traits")):
            for entity in set_entry.get(key, []):
                api_name, name = entity.get("apiName"), entity.get("name")
                if api_name and name and api_name not in rows:
                    rows[api_name] = (api_name, kind, name, set_number, None)
    for item in data.get("items", []):
        api_name, name = item.get("apiName"), item.get("name")
        if api_name and name and api_name not in rows:
            rows[api_name] = (api_name, "item", name, None, item.get("composition") or None)
    return list(rows.values())


def load_static_names(conn: psycopg.Connection, data: dict[str, Any]) -> int:
    rows = extract_names(data)
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO static_names (api_name, kind, display_name, set_number, components)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (api_name) DO UPDATE
            SET kind = EXCLUDED.kind, display_name = EXCLUDED.display_name,
                set_number = EXCLUDED.set_number, components = EXCLUDED.components
            """,
            rows,
        )
    conn.commit()
    return len(rows)
