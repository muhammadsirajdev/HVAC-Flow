"""Run D: day-before reminders (plan 6.7).

    find_tomorrow ─ send_reminders

Every booked visit tomorrow (business time zone) that was not reminded yet gets a reminder email
(Gmail MCP) and is marked `reminded`, so it is never sent twice; a moved booking is reminded again.
A failed email goes to Slack ("remind by phone"); the next run would be too late. A visit whose
customer still has unanswered change offers also goes to Slack ("please call").

Runs daily at REMINDER_HOUR in the app (REMINDERS_ENABLED=true), or once by hand:
    uv run python -m backend.graphs.run_d_reminders.graph
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Callable, TypedDict

from langgraph.graph import END, START, StateGraph

from backend.config import get_settings
from backend.core.errors import MCPError
from backend.core.timeutil import business_tz, format_slot, now

log = logging.getLogger(__name__)


class ReminderState(TypedDict, total=False):
    due: list[dict]
    reminded: list[int]
    failed: list[int]


@dataclass
class RunDDeps:
    due: Callable[[datetime, datetime], list[dict]]   # booked, not reminded, starting in [start, end)
    send_email: Callable[[str, str, str], object]     # (to, subject, body); raises MCPError
    mark_reminded: Callable[[int], None]               # booking_id
    post_alert: Callable[[str], object]
    render: Callable[..., str]                         # notify.render(template, **ctx)


def build_graph(deps: RunDDeps | None = None):
    deps = deps or default_deps()

    def find_tomorrow(state: ReminderState) -> dict:
        start = datetime.combine(now().date() + timedelta(days=1), time(0), tzinfo=business_tz())
        return {"due": deps.due(start, start + timedelta(days=1))}

    def send_reminders(state: ReminderState) -> dict:
        reminded, failed = [], []
        for v in state["due"]:
            label = format_slot(v["starts_at"])
            if v["pending_since"]:
                deps.post_alert(f":hourglass: *Case #{v['case_id']}* asked to move the visit and hasn't picked a "
                                f"new time; the visit is tomorrow, {label}. Please call {v['name']}, {v['phone']}.")
            body = deps.render("email/reminder.txt.j2", name=(v["name"] or "").split(" ")[0], service=v["service"],
                               case_id=v["case_id"], slot_label=label, address=v["address"])
            try:
                deps.send_email(v["email"], f"[Case #{v['case_id']}] Reminder: your {v['service']} visit "
                                            f"tomorrow, {label}", body)
            except MCPError as exc:
                log.warning("reminder for case %s failed: %s", v["case_id"], exc)
                deps.post_alert(f":warning: The reminder for *Case #{v['case_id']}* could not be emailed. "
                                f"Please remind by phone: {v['name']}, {v['phone']}, {label}.")
                failed.append(v["case_id"])
                continue
            deps.mark_reminded(v["booking_id"])
            reminded.append(v["case_id"])
        log.info("Run D: reminded %s, failed %s", reminded, failed)
        return {"reminded": reminded, "failed": failed}

    g = StateGraph(ReminderState)
    g.add_node("find_tomorrow", find_tomorrow)
    g.add_node("send_reminders", send_reminders)
    g.add_edge(START, "find_tomorrow")
    g.add_edge("find_tomorrow", "send_reminders")
    g.add_edge("send_reminders", END)
    return g.compile()


def default_deps() -> RunDDeps:
    from backend.db.session import get_pool
    from backend.mcp import email_mcp
    from backend.tools import notify

    def due(start: datetime, end: datetime) -> list[dict]:
        with get_pool().connection() as conn:
            return conn.execute(
                "SELECT b.booking_id, b.case_id, b.service, b.address, b.pending_since, s.starts_at, "
                "       cu.name, lower(cu.email) AS email, cu.phone "
                "FROM bookings b JOIN slots s USING (slot_id) JOIN cases c USING (case_id) "
                "JOIN customers cu ON cu.customer_id = c.customer_id "
                "WHERE b.active AND c.status = 'booked' AND NOT b.reminded "
                "AND s.starts_at >= %s AND s.starts_at < %s ORDER BY s.starts_at", (start, end)).fetchall()

    def mark_reminded(booking_id: int) -> None:
        with get_pool().connection() as conn:
            conn.execute("UPDATE bookings SET reminded = true WHERE booking_id = %s", (booking_id,))

    return RunDDeps(due=due, send_email=email_mcp.send_email, mark_reminded=mark_reminded,
                    post_alert=notify.post_alert, render=notify.render)


def run_once() -> dict:
    return build_graph().invoke({})


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    out = run_once()
    print(f"reminded cases {out['reminded']}, failed {out['failed']}")
