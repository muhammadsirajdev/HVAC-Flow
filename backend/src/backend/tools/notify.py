"""Customer and team notifications: confirmation email (Gmail MCP), Slack posts (Slack MCP).

Every function accepts `tools`: the MCP tools (gmail_send_email, slack_user_post_message,
slack_user_list_channels) loaded from Klavis and handed to the graph node. The node
executes them through these functions with arguments chosen by code: the recipient is
always the customer on the booking, the channel is always the configured one.

Message text is rendered from templates by code after the action succeeded, so the
model can never confirm a booking that does not exist.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined
from langchain_core.tools import BaseTool

from backend.config import get_settings
from backend.core.errors import MCPError
from backend.db.session import get_pool
from backend.graphs.common.state import CHANNEL_LABELS
from backend.mcp import email_mcp, slack_mcp
from backend.tools import cases
from backend.tools.booking import BookingResult, StoredBooking, mark_notified

log = logging.getLogger(__name__)
TEMPLATES = Path(__file__).resolve().parents[1] / "templates"
Tools = Mapping[str, BaseTool] | None


@lru_cache
def _env() -> Environment:
    return Environment(loader=FileSystemLoader(TEMPLATES), undefined=StrictUndefined,
                       keep_trailing_newline=False, autoescape=False)


def render(template: str, /, **ctx) -> str:
    # `template` is positional-only: templates use a `name` variable (the customer's name).
    s = get_settings()
    return _env().get_template(template).render(business_name=s.business_name,
                                                business_phone=s.business_phone, **ctx).strip()


def confirmation_email(result: BookingResult) -> tuple[str, str]:
    """(subject, body) of the booking/change confirmation, written by code after the write succeeded."""
    r = result.request
    ctx = dict(case_id=result.case_id, service=r.service, slot_label=result.slot_label, name=r.name,
               address=r.address, problem=r.problem, phone=r.phone, updated=result.updated,
               previous_slot_label=result.previous_slot_label)
    return render("email/confirmation_subject.txt.j2", **ctx), render("email/confirmation.txt.j2", **ctx)


def send_booking_confirmation(result: BookingResult, tools: Tools = None) -> bool:
    """Email the confirmation with gmail_send_email; retried once. Links the thread to the case."""
    r = result.request
    subject, body = confirmation_email(result)
    send_tool = (tools or {}).get(get_settings().gmail_send_tool)
    for attempt in (1, 2):
        try:
            sent = email_mcp.send_email(r.email, subject, body, tool=send_tool)
            break
        except MCPError as exc:
            log.warning("confirmation email attempt %d for case %s failed: %s", attempt, result.case_id, exc)
    else:
        post_alert(f":warning: Confirmation email for *Case #{result.case_id}* could not be sent. "
                   f"Please confirm by phone: {r.name}, {r.phone}, {result.slot_label}.", tools)
        return False

    log.info("confirmation email for case %s sent to %s", result.case_id, r.email)
    _mark(result.booking_id, email=True)
    if sent.thread_id:
        with get_pool().connection() as conn:
            cases.set_email_thread(conn, result.case_id, sent.thread_id)
    else:
        log.info("Gmail MCP returned no thread id for case %s; Run B will match by [Case #N]", result.case_id)
    return True


def _post(channel: str, text: str, tools: Tools = None) -> bool:
    s = get_settings()
    channel = channel or s.slack_bookings_channel or s.slack_urgent_channel
    if not channel:
        log.warning("Slack channel not configured; message not posted: %s", text[:120])
        return False
    try:
        slack_mcp.post_message(channel, text, tools)
        log.info("Slack message posted to %s", channel)
        return True
    except MCPError as exc:
        log.error("Slack post failed: %s", exc)
        return False


def _booking_lines(result: BookingResult) -> str:
    r = result.request
    return (f"*Customer:* {r.name}\n*Service:* {r.service}\n*Time:* {result.slot_label}\n"
            f"*Address:* {r.address}\n*Phone:* {r.phone}\n*Email:* {r.email}\n*Problem:* {r.problem}")


def post_booking(result: BookingResult, tools: Tools = None) -> bool:
    via = CHANNEL_LABELS.get(result.request.channel, result.request.channel)
    if not result.updated:
        title = f":calendar: *New booking — Case #{result.case_id}* ({via})"
    elif result.previous_slot_label != result.slot_label:
        title = (f":repeat: *Case #{result.case_id} rescheduled:* {result.previous_slot_label} → "
                 f"{result.slot_label} ({via})")
    else:
        title = f":pencil2: *Booking details changed — Case #{result.case_id}* ({via})"
    ok = _post(get_settings().slack_bookings_channel, f"{title}\n{_booking_lines(result)}", tools)
    if ok:
        _mark(result.booking_id, slack=True)
    return ok


def post_cancellation(result: BookingResult, tools: Tools = None) -> bool:
    via = CHANNEL_LABELS.get(result.request.channel, result.request.channel)
    return _post(get_settings().slack_bookings_channel,
                 f":x: *Case #{result.case_id} cancelled* ({via})\n{_booking_lines(result)}", tools)


def _mark(booking_id: int, **flags) -> None:
    """Record a successful send; never let bookkeeping break a notification."""
    try:
        mark_notified(booking_id, **flags)
    except Exception:
        log.exception("could not record notification for booking %s", booking_id)


def send_pending(stored: StoredBooking, tools: Tools = None) -> dict:
    """Send whatever a booking is still missing (email to the address ON FILE, Slack post)."""
    out = {"email_sent": None, "slack_posted": None}
    if stored.email_pending:
        out["email_sent"] = send_booking_confirmation(stored.result, tools)
    if stored.slack_pending:
        out["slack_posted"] = post_booking(stored.result, tools)
    return out


def post_needs_person(case_id: int, reason: str, details: dict, tools: Tools = None) -> bool:
    lines = "\n".join(f"*{k}:* {v}" for k, v in details.items() if v)
    return _post(get_settings().slack_bookings_channel,
                 f":raising_hand: *Case #{case_id} needs a person* — {reason}\n{lines}", tools)


def post_urgent(text: str, source: str, tools: Tools = None) -> bool:
    """`source` says where it came from: "website chat, <session id>" or "email, Case #12, <sender>"."""
    s = get_settings()
    return _post(s.slack_urgent_channel or s.slack_bookings_channel,
                 f":rotating_light: *URGENT — possible emergency* ({source})\n"
                 f"> {text[:500]}", tools)


def post_alert(text: str, tools: Tools = None) -> bool:
    s = get_settings()
    return _post(s.slack_urgent_channel or s.slack_bookings_channel, text, tools)
