"""Replace ALL app data with the made-up demo customers (backend.db.demo_data).

    uv run python scripts/seed_demo_data.py --yes

It empties customers, cases, bookings, messages and chat memory in the database DATABASE_URL points
to. Back up first if that data matters (scripts/copy_db.py can copy it elsewhere).
"""

import sys

from backend.config import get_settings
from backend.db.demo_data import reset_demo_data


def main() -> int:
    host = get_settings().database_url.rsplit("@", 1)[-1]
    if "--yes" not in sys.argv:
        print(f"This EMPTIES the app data in {host} and writes the demo cases.\n"
              "Run again with --yes to go ahead.")
        return 1
    n = reset_demo_data(force=True)
    print(f"{host}: {n} demo cases written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
