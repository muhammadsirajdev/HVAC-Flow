"""Public-demo rules: masking, office sign-in, visitor limits and email previews. No database needed."""

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from backend.config import get_settings
from backend.core import demo, privacy, ratelimit
from backend.mcp import email_mcp


@pytest.fixture
def settings(monkeypatch):
    s = get_settings()
    for k, v in {"demo_mode": False, "office_password": "", "demo_live_emails": "",
                 "demo_chat_per_10min": 2, "demo_forms_per_hour": 1, "demo_ai_per_day": 100}.items():
        monkeypatch.setattr(s, k, v)
    ratelimit.reset()
    yield s
    ratelimit.reset()


def req(token: str | None = None, ip: str = "1.2.3.4") -> Request:
    headers = [(b"cf-connecting-ip", ip.encode())]
    if token:
        headers.append((b"authorization", f"Bearer {token}".encode()))
    return Request({"type": "http", "headers": headers, "client": ("10.0.0.1", 1)})


def test_masking():
    assert privacy.name("Maria Gonzalez") == "Maria G."
    assert privacy.email("maria.gonzalez@gmail.com") == "ma•••@gmail.com"
    assert privacy.phone("+13055550142") == "(•••) •••-0142"
    assert privacy.address("1420 Coral Way, Miami, FL") == "•••, Miami, FL"
    t = privacy.text("I'm Maria, 305-555-0118, maria@x.com, 1420 SW 22nd St, Miami. Case #12 at 10:00 AM")
    assert "305-555" not in t and "maria@x.com" not in t and "1420 SW" not in t
    assert "Case #12" in t and "10:00 AM" in t


def test_office_access(settings):
    assert demo.office_access(req()) is False                      # local dev: everything
    settings.office_password = "s3cret"
    with pytest.raises(HTTPException) as e:
        demo.office_access(req())
    assert e.value.status_code == 401
    token, _ = demo.make_token()
    assert demo.office_access(req(token)) is False                 # signed in: everything
    settings.demo_mode = True
    assert demo.office_access(req()) is True                       # public demo: masked
    assert demo.office_access(req("1." + token.split(".")[1])) is True   # expired/forged -> masked
    settings.office_password = "changed"                           # new password signs everyone out
    assert demo.token_valid(token) is False


def test_password_check(settings):
    assert demo.password_ok("x") is False                          # no password set: never
    settings.office_password = "s3cret"
    assert demo.password_ok("s3cret") and not demo.password_ok("S3cret")


def test_visitor_limits_only_in_demo(settings):
    for _ in range(5):
        demo.guard_chat(req())                                     # not demo: unlimited
    settings.demo_mode = True
    demo.guard_chat(req()), demo.guard_chat(req())
    with pytest.raises(HTTPException) as e:
        demo.guard_chat(req())
    assert e.value.status_code == 429
    demo.guard_chat(req(ip="5.6.7.8"))                             # another visitor is fine
    demo.guard_form(req())
    with pytest.raises(HTTPException):
        demo.guard_form(req())


def test_daily_cap(settings):
    settings.demo_mode, settings.demo_ai_per_day = True, 2
    demo.guard_chat(req(ip="a")), demo.guard_form(req(ip="b"))
    with pytest.raises(HTTPException) as e:
        demo.guard_chat(req(ip="c"))
    assert "tomorrow" in e.value.detail


def test_demo_emails_are_not_sent(settings, monkeypatch):
    calls = []
    monkeypatch.setattr(email_mcp, "call_tool", lambda *a, **k: calls.append(a) or '{"id": "real-1"}')
    settings.demo_mode, settings.demo_live_emails = True, "Owner@Example.com"
    out = email_mcp.send_email("visitor@example.com", "Hi", "Body", thread_id="t1")
    assert calls == [] and out.message_id.startswith("demo-") and out.thread_id == "t1"
    out = email_mcp.send_email("owner@example.com", "Hi", "Body", thread_id="t1")
    assert len(calls) == 1 and out.message_id == "real-1"
