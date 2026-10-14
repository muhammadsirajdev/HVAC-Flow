"""Business time zone helpers."""

from datetime import datetime
from functools import lru_cache
from zoneinfo import ZoneInfo

from backend.config import get_settings


@lru_cache
def business_tz() -> ZoneInfo:
    return ZoneInfo(get_settings().business_tz)


def now() -> datetime:
    return datetime.now(business_tz())


def local(dt: datetime) -> datetime:
    return dt.astimezone(business_tz())


def format_slot(dt: datetime) -> str:
    """'Thu 16 Oct, 11:00 AM' in the business time zone (used in chat, email subject, Slack)."""
    d = local(dt)
    return f"{d:%a} {d.day} {d:%b}, {d:%I:%M %p}".replace(", 0", ", ")
