"""Seed demo data: create tables, then open slots for the next 14 days.

    uv run python scripts/seed_demo_client.py

The schedule itself is in backend.db.slots.
"""

from backend.db.init_db import init_db
from backend.db.slots import ensure_slots

DAYS = 14


def main() -> None:
    init_db()
    free = ensure_slots(DAYS)
    print(f"slots ensured for {DAYS} days; {free} open future slots")


if __name__ == "__main__":
    main()
