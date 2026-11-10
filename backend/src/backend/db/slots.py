"""Bookable visit windows. A deployed app keeps a rolling schedule open: `ensure_slots` runs at
start-up and daily (backend.scheduler), so the calendar never runs dry.

Demo schedule (the real hours are not stated on the website): Mon-Sat, 2-hour windows starting
8 AM, 10 AM, 12 PM, 2 PM and 4 PM, business time zone.
"""

from datetime import datetime, time, timedelta

from backend.core.timeutil import business_tz, now
from backend.db.session import get_pool

START_HOURS = (8, 10, 12, 14, 16)


def ensure_slots(days: int = 14) -> int:
    """Create any missing windows for the next `days` days. Returns the open future slots."""
    tz, today = business_tz(), now().date()
    rows = []
    for offset in range(days):
        day = today + timedelta(days=offset)
        if day.weekday() == 6:      # Sunday
            continue
        for hour in START_HOURS:
            start = datetime.combine(day, time(hour), tzinfo=tz)
            rows.append((start, start + timedelta(hours=2)))
    with get_pool().connection() as conn:
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO slots (starts_at, ends_at) VALUES (%s, %s) ON CONFLICT (starts_at) DO NOTHING",
                rows)
        return conn.execute("SELECT count(*) AS n FROM slots WHERE NOT taken AND starts_at > now()").fetchone()["n"]
