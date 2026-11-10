"""Public-demo rules: who sees the office in full, visitor limits, and which emails really go out.

Office access:
    signed in (OFFICE_PASSWORD)    -> full details
    DEMO_MODE, not signed in       -> contact details partly hidden (see backend.core.privacy)
    OFFICE_PASSWORD, not demo      -> 401 until signed in
    neither                        -> full details (local development)
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import time

from fastapi import HTTPException, Request

from backend.config import get_settings
from backend.core import ratelimit

TOKEN_DAYS = 7


# ---------- office sign-in ----------
def _key() -> bytes:
    # Changing OFFICE_PASSWORD signs everyone out.
    return hashlib.sha256(f"hvacx-office:{get_settings().office_password}".encode()).digest()


def make_token(days: int = TOKEN_DAYS) -> tuple[str, int]:
    expires = int(time.time()) + days * 86400
    sig = hmac.new(_key(), str(expires).encode(), hashlib.sha256).digest()
    return f"{expires}.{base64.urlsafe_b64encode(sig).decode().rstrip('=')}", expires


def token_valid(token: str | None) -> bool:
    if not token or not get_settings().office_password or "." not in token:
        return False
    expires, _, sig = token.partition(".")
    if not expires.isdigit() or int(expires) < time.time():
        return False
    good = base64.urlsafe_b64encode(hmac.new(_key(), expires.encode(), hashlib.sha256).digest()).decode().rstrip("=")
    return hmac.compare_digest(sig, good)


def password_ok(password: str) -> bool:
    expected = get_settings().office_password
    return bool(expected) and hmac.compare_digest(password.encode(), expected.encode())


def bearer(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    return auth[7:].strip() if auth.lower().startswith("bearer ") else None


def office_access(request: Request) -> bool:
    """FastAPI dependency for the office endpoints. Returns True when details must be masked."""
    s = get_settings()
    if token_valid(bearer(request)):
        return False
    if s.demo_mode:
        return True
    if s.office_password:
        raise HTTPException(401, "Sign in to open the office.")
    return False


# ---------- visitor limits (demo mode only) ----------
BUSY = "The demo has had a lot of visitors today and has paused new AI requests. Please try again tomorrow."


def guard_chat(request: Request) -> None:
    s = get_settings()
    if not s.demo_mode:
        return
    ratelimit.limit(f"chat:{ratelimit.client_ip(request)}", s.demo_chat_per_10min, 600,
                    "That's a lot of messages in a short time. Please wait a few minutes and try again.")
    ratelimit.daily_cap("ai", s.demo_ai_per_day, BUSY)


def guard_form(request: Request) -> None:
    s = get_settings()
    if not s.demo_mode:
        return
    ratelimit.limit(f"form:{ratelimit.client_ip(request)}", s.demo_forms_per_hour, 3600,
                    "You've sent a few forms already. Please wait an hour before sending another.")
    ratelimit.daily_cap("ai", s.demo_ai_per_day, BUSY)


# ---------- email ----------
def live_recipient(address: str) -> bool:
    """False in demo mode for anyone not on DEMO_LIVE_EMAILS: the email is written but not sent."""
    s = get_settings()
    if not s.demo_mode:
        return True
    allowed = {a.strip().lower() for a in s.demo_live_emails.split(",") if a.strip()}
    return address.strip().lower() in allowed
