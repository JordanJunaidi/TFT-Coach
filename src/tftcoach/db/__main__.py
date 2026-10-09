"""CLI: database setup.

Usage:
  python -m tftcoach.db init          # create tables, seed patches
  python -m tftcoach.db load-static   # load display names from Community Dragon
"""

import argparse

from tftcoach.config import get_settings
from tftcoach.db.core import connect, init_schema
from tftcoach.db.static_data import fetch_static_data, load_static_names


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="TFT Coach database setup")
    parser.add_argument("command", choices=["init", "load-static"])
    args = parser.parse_args(argv)

    with connect(get_settings().database_url) as conn:
        if args.command == "init":
            init_schema(conn)
            print("Schema ready and patches seeded.")
        else:
            count = load_static_names(conn, fetch_static_data())
            print(f"Loaded {count} display names.")


if __name__ == "__main__":
    main()
