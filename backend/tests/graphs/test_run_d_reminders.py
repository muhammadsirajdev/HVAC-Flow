"""Run D: day-before reminders with fakes (no Gmail, Slack or DB)."""

from datetime import datetime, timedelta

from backend.core.errors import MCPError
from backend.core.timeutil import now
from backend.graphs.run_d_reminders.graph import RunDDeps, build_graph


def visit(case_id, pending=False):
    starts = datetime.combine(now().date() + timedelta(days=1), datetime.min.time(), now().tzinfo) + timedelta(hours=10)
    return {"booking_id": case_id * 10, "case_id": case_id, "service": "AC Repair", "address": "1 Main St",
            "pending_since": now() if pending else None, "starts_at": starts, "name": "Ali Khan",
            "email": "ali@example.com", "phone": "+17865550123"}


def run(visits, fail_for=None):
    sent, marked, alerts, window = [], [], [], []

    def send(to, subject, body):
        if subject.startswith(f"[Case #{fail_for}]"):
            raise MCPError("gmail down")
        sent.append(subject)

    def due(start, end):
        window.append((start, end))
        return visits

    deps = RunDDeps(due=due, send_email=send, mark_reminded=marked.append, post_alert=alerts.append,
                    render=lambda tpl, **ctx: f"{tpl} {ctx['slot_label']}")
    return build_graph(deps).invoke({}), sent, marked, alerts, window


def test_tomorrows_visits_are_reminded_and_marked():
    out, sent, marked, alerts, window = run([visit(1), visit(2)])
    start, end = window[0]
    assert start.date() == now().date() + timedelta(days=1) and end - start == timedelta(days=1)
    assert out["reminded"] == [1, 2] and marked == [10, 20] and alerts == []
    assert sent[0].startswith("[Case #1] Reminder: your AC Repair visit tomorrow,")


def test_failed_email_alerts_slack_and_is_not_marked():
    out, sent, marked, alerts, _ = run([visit(1), visit(2)], fail_for=1)
    assert out["failed"] == [1] and marked == [20] and "remind by phone" in alerts[0]


def test_unanswered_change_offer_alerts_slack():
    out, sent, marked, alerts, _ = run([visit(3, pending=True)])
    assert "hasn't picked a new time" in alerts[0] and out["reminded"] == [3]
