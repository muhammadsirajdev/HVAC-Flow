"""Code-side guardrails. Emergency detection runs before the model sees the message.

Email-channel guards (DKIM/DMARC, auto-reply filter, reply rate limit) are added
with Run B.
"""

import re
from functools import lru_cache
from pathlib import Path

from backend.config import get_settings

TEMPLATES = Path(__file__).resolve().parents[1] / "templates"

# English + Roman Urdu. Keep phrases specific: a false positive stops a booking.
EMERGENCY_PATTERNS = [
    r"\bgas\s+(smell|leak|odou?r)", r"\bsmell(s|ing)?\s+(of\s+)?gas\b", r"\bsmells?\s+like\s+gas\b",
    r"\bspark(s|ing)?\b", r"\bsmoke\b", r"\bsmoking\b", r"\bon\s+fire\b", r"\bfire\b", r"\bburning\s+smell\b",
    r"\bsmell(s|ing)?\s+(of\s+)?burning\b", r"\bflood(ed|ing)?\b", r"\belectric(al)?\s+shock\b",
    r"\bcarbon\s+monoxide\b", r"\bco\s+alarm\b",
    r"\bgas\s+ki\s+(bu|boo)\b", r"\bdhuan\b", r"\bdhuwan\b", r"\baag\b", r"\bpani\s+bhar\b",
]
_EMERGENCY_RE = re.compile("|".join(EMERGENCY_PATTERNS), re.IGNORECASE)


def is_emergency(text: str) -> bool:
    return bool(_EMERGENCY_RE.search(text or ""))


@lru_cache
def safety_message() -> str:
    """Approved, fixed safety wording (never generated)."""
    text = (TEMPLATES / "safety_message.txt").read_text(encoding="utf-8")
    return text.replace("{phone}", get_settings().business_phone).strip()
