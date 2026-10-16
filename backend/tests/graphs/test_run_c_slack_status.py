"""Run C: staff status messages -> thank-you email + case closed, with fakes (no Slack, Gmail or DB)."""

from backend.core.errors import MCPError
from backend.graphs.run_c_slack_status.graph import RunCDeps, build_graph, done_cases


def test_done_messages_are_recognised():
    msgs = [{"text": "Case #130 done, replaced the capacitor"},     # newest first, like Slack
            {"text": "case 125 status: delayed, parts on order"},
            {"text": "case 124 not done yet"},
            {"text": "CASE 123 status DONE. Customer happy. case 122 completed too"}]
    assert done_cases(msgs) == [123, 122, 130]


def run(cases: dict[int, dict], messages: list[str], fail_for: int | None = None):
    sent, closed = [], []

    def send(to, subject, body):
        if subject.startswith(f"[Case #{fail_for}]"):
            raise MCPError("gmail down")
        sent.append((to, subject, body))

    deps = RunCDeps(history=lambda: [{"text": t} for t in messages], load_case=cases.get, send_email=send,
                    close_case=lambda cid: (closed.append(cid), cases[cid].update(status="closed")),
                    render=lambda tpl, **ctx: f"Thanks {ctx['name']} for {ctx['service']} #{ctx['case_id']}")
    return build_graph(deps).invoke({}), sent, closed


def case(status="booked"):
    return {"status": status, "name": "Ali Khan", "email": "ali@example.com", "service": "AC Repair"}


def test_booked_case_is_thanked_and_closed_once():
    cases = {123: case()}
    out, sent, closed = run(cases, ["case 123 status done"])
    assert closed == [123] and sent == [("ali@example.com", "[Case #123] Thank you from MD Cold Services",
                                         "Thanks Ali for AC Repair #123")]
    out, sent, closed = run(cases, ["case 123 status done"])          # next run reads it again
    assert sent == [] and closed == [] and out["skipped"] == {123: "status closed"}


def test_unknown_unbooked_and_failed_cases_stay_open():
    cases = {1: case("open"), 2: case(), 3: case()}
    out, sent, closed = run(cases, ["case 9 done", "case 1 done", "case 2 done", "case 3 done"], fail_for=2)
    assert closed == [3] and out["skipped"] == {1: "status open", 2: "email failed", 9: "no such case"}
