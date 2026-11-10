"""In-process rate limits for the public demo (one app instance, so memory is enough).

    limit("chat:1.2.3.4", 20, 600)    # raises 429 when the 21st call lands inside 10 minutes
    daily_cap("ai", 300)              # all visitors together, resets at midnight business time
"""

from __future__ import annotations

import threading
import time
from collections import deque

from fastapi import HTTPException, Request

from backend.core.timeutil import now as business_now

_lock = threading.Lock()
_hits: dict[str, deque[float]] = {}
_daily: dict[str, tuple[str, int]] = {}


def client_ip(request: Request) -> str:
    """The visitor's address. Render sits behind Cloudflare, which sets CF-Connecting-IP itself."""
    for header in ("cf-connecting-ip", "true-client-ip"):
        if value := request.headers.get(header):
            return value.strip()
    return request.client.host if request.client else "unknown"


def limit(key: str, max_calls: int, window_s: int, message: str) -> None:
    t = time.monotonic()
    with _lock:
        q = _hits.setdefault(key, deque())
        while q and q[0] <= t - window_s:
            q.popleft()
        if len(q) >= max_calls:
            retry = int(q[0] + window_s - t) + 1
            raise HTTPException(429, message, headers={"Retry-After": str(retry)})
        q.append(t)
        if len(_hits) > 10_000:             # forget idle visitors
            for k in [k for k, v in _hits.items() if not v]:
                del _hits[k]


def daily_cap(key: str, max_calls: int, message: str) -> None:
    today = business_now().date().isoformat()
    with _lock:
        day, n = _daily.get(key, (today, 0))
        if day != today:
            day, n = today, 0
        if n >= max_calls:
            raise HTTPException(429, message)
        _daily[key] = (day, n + 1)


def reset() -> None:
    """Tests only."""
    with _lock:
        _hits.clear()
        _daily.clear()
