"""Run C: job status from the staff Slack channel (plan 6.6).

    read_slack ─ close_cases

Staff post e.g. "case 123 status done" (a case number and a done word, any other details).
For each such case that is still booked, the customer gets the thank-you email (Gmail MCP) and the
case is closed. A closed case is skipped, so a message read again never sends a second thank-you;
a failed email leaves the case open for the next run.

Runs every SLACK_STATUS_HOURS in the app (SLACK_STATUS_ENABLED=true), or once by hand:
    uv run python -m backend.graphs.run_c_slack_status.graph
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Callable, TypedDict

from langgraph.graph import END, START, StateGraph

from backend.config import get_settings
from backend.core.errors import MCPError

log = logging.getLogger(__name__)

_CASE = re.compile(r"\bcase\s*#?\s*(\d+)", re.I)
_DONE = re.compile(r"\b(done|completed?|finished|closed)\b", re.I)
_NOT_DONE = re.compile(r"\bnot\s+(yet\s+)?(done|completed?|finished|closed)\b", re.I)


def done_cases(messages: list[dict]) -> list[int]:
    """Case numbers reported done, oldest message first. `messages` come newest first (Slack)."""
    ids: list[int] = []
    for m in reversed(messages):
        text = m.get("text") or ""
        if _DONE.search(text) and not _NOT_DONE.search(text):
            ids += [n for n in map(int, _CASE.findall(text)) if n not in ids]
    return ids


class StatusState(TypedDict, total=False):
    case_ids: list[int]
    closed: list[int]
    skipped: dict[int, str]


@dataclass
class RunCDeps:
    history: Callable[[], list[dict]]                 # status channel messages, newest first
    load_case: Callable[[int], dict | None]           # {status, name, email, service}
    send_email: Callable[[str, str, str], object]     # (to, subject, body); raises MCPError
    close_case: Callable[[int], None]
    render: Callable[..., str]                        # notify.render(template, **ctx)


def build_graph(deps: RunCDeps | None = None):
    deps = deps or default_deps()

    def read_slack(state: StatusState) -> dict:
        return {"case_ids": done_cases(deps.history())}

    def close_cases(state: StatusState) -> dict:
        closed, skipped = [], {}
        for case_id in state["case_ids"]:
            case = deps.load_case(case_id)
            if case is None or case["status"] not in ("booked", "done"):
                skipped[case_id] = f"status {case['status']}" if case else "no such case"
                continue
            body = deps.render("email/thank_you.txt.j2", name=(case["name"] or "").split(" ")[0],
                               service=case["service"], case_id=case_id)
            try:
                deps.send_email(case["email"], f"[Case #{case_id}] Thank you from {get_settings().business_name}",
                                body)
            except MCPError as exc:
                log.warning("thank-you for case %s failed, retried next run: %s", case_id, exc)
                skipped[case_id] = "email failed"
                continue
            deps.close_case(case_id)
            closed.append(case_id)
        log.info("Run C: closed %s, skipped %s", closed, skipped)
        return {"closed": closed, "skipped": skipped}

    g = StateGraph(StatusState)
    g.add_node("read_slack", read_slack)
    g.add_node("close_cases", close_cases)
    g.add_edge(START, "read_slack")
    g.add_edge("read_slack", "close_cases")
    g.add_edge("close_cases", END)
    return g.compile()


def default_deps() -> RunCDeps:
    from backend.db.session import get_pool
    from backend.mcp import email_mcp, slack_mcp
    from backend.tools import cases, notify

    def load_case(case_id: int) -> dict | None:
        with get_pool().connection() as conn:
            return conn.execute(
                "SELECT c.status, cu.name, lower(cu.email) AS email, b.service FROM cases c "
                "JOIN customers cu USING (customer_id) "
                "LEFT JOIN bookings b ON b.case_id = c.case_id AND b.active WHERE c.case_id = %s",
                (case_id,)).fetchone()

    def close_case(case_id: int) -> None:
        with get_pool().connection() as conn:
            if cases.get_case(conn, case_id)["status"] == "booked":
                cases.transition(conn, case_id, "done", "reported done in the Slack status channel")
            cases.transition(conn, case_id, "closed", "thank-you email sent")

    return RunCDeps(history=lambda: slack_mcp.channel_history(get_settings().slack_status_channel),
                    load_case=load_case, send_email=email_mcp.send_email, close_case=close_case,
                    render=notify.render)


def run_once() -> dict:
    return build_graph().invoke({})


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    out = run_once()
    print(f"closed {out['closed']}, skipped {out['skipped']}")
