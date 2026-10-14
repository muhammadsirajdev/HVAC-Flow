"""Run B: email rules, and email turns through the graph with fakes (no LLM, database or MCP)."""

from datetime import datetime, timedelta, timezone

import pytest
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import InMemorySaver

from backend.graphs.run_a_chat.nodes import booking_to_state
from backend.graphs.run_a_chat.schemas import TurnAnalysis
from backend.graphs.run_b_email import mail
from backend.graphs.run_b_email.deps import RunBDeps
from backend.graphs.run_b_email.graph import build_graph
from backend.graphs.run_b_email.nodes import acknowledgement
from backend.tools.booking import BookingRequest, BookingResult, SlotOption

# --- email rules ---------------------------------------------------------------------------


def test_auto_replies_are_recognised():
    assert mail.is_auto("no-reply@shop.com", "Your order")
    assert mail.is_auto("mailer-daemon@googlemail.com", "Delivery Status Notification (Failure)")
    assert mail.is_auto("ali@x.com", "Automatic reply: AC not cooling")
    assert mail.is_auto("ali@x.com", "Out of Office: back Monday")
    assert not mail.is_auto("ali@x.com", "Re: [Case #12] Your AC Repair visit")


def test_quoted_reply_is_stripped():
    text = "Can we move it to Friday?\n\nOn Wed, 15 Oct 2026 at 10:00, MD Cold <x@y.com> wrote:\n> Hi Ali,\n> booked"
    assert mail.strip_quoted(text) == "Can we move it to Friday?"
    assert mail.strip_quoted("Hello\n> old line\nThanks") == "Hello\nThanks"


def test_case_reference_and_thanks():
    assert mail.case_ref("Re: [Case #123] Your AC Repair visit") == 123
    assert mail.case_ref("AC not cooling") is None
    assert mail.is_thanks_only("Thanks a lot, see you then!")
    assert not mail.is_thanks_only("Thanks, can we move it to Friday?")
    assert not mail.is_thanks_only("Thanks. Please cancel my visit")


def test_form_email_is_parsed():
    body = ("New submission from Contact form\n\nName: Ali Khan\nEmail: ALI@Example.com\n"
            "Phone: (786) 555-0123\nMessage: My AC is not cooling.\nPlease call me.\n--\nSent from the website")
    assert mail.parse_form(body) == {"name": "Ali Khan", "email": "ali@example.com", "phone": "+17865550123",
                                     "message": "My AC is not cooling.\nPlease call me."}
    assert mail.parse_form("Name: Ali\nEmail: not-an-email")["email"] is None


# --- graph turns ---------------------------------------------------------------------------

DEFAULTS = dict(intent="question", name=None, phone=None, email=None, address=None, problem=None,
                service=None, preferred_date=None, part_of_day=None, slot_choice=None,
                wants_other_times=False, wants_cancel=False, confirmation="none", search_query=None,
                sub_queries=[], change_target=None)
BASE = datetime(2030, 10, 16, 14, tzinfo=timezone.utc)


def A(**kw) -> TurnAnalysis:
    return TurnAnalysis(**{**DEFAULTS, **kw})


def booked_result(slot_id=9, label="Thu 16 Oct, 10:00 AM", updated=False, previous=None) -> BookingResult:
    req = BookingRequest(slot_id=slot_id, service="AC Repair", name="Ali Khan", phone="+17865550123",
                         email="ali@example.com", address="1 Main St", problem="not cooling", channel="email")
    return BookingResult(booking_id=5, case_id=12, customer_id=3, slot_label=label,
                         starts_at=BASE, request=req, updated=updated, previous_slot_label=previous)


class Fake:
    def __init__(self, script: dict[str, TurnAnalysis]):
        self.script, self.calls = script, []
        self.slots = [SlotOption(i, BASE + timedelta(days=1, hours=i), f"Fri 17 Oct, {i}:00 PM") for i in (1, 2, 3)]

    def rec(self, name, value=True):
        self.calls.append(name)
        return value

    def deps(self) -> RunBDeps:
        return RunBDeps(
            analyze=lambda m, h, c: self.script[m], search=lambda q: [],
            answer=lambda q, p, h: "ANSWER", smalltalk=lambda m, n: "Hello!",
            get_slots=lambda d=None, p=None, limit=None, exclude_ids=None: [
                s for s in self.slots if s.slot_id not in (exclude_ids or [])],
            create_booking=lambda req: self.rec("create_booking", booked_result(req.slot_id)) and
                booked_result(req.slot_id, label="Fri 17 Oct, 2:00 PM"),
            change_booking=self.change_booking,
            create_needs_person_case=lambda *a, **k: 12,
            send_confirmation=lambda r, tools=None: self.rec("chat_confirmation"),
            post_booking=lambda r, tools=None: self.rec("slack_booking"),
            post_needs_person=lambda *a: self.rec("slack_needs_person"),
            post_urgent=lambda t, s, tools=None: self.rec("slack_urgent"),
            cancel_booking=lambda case_id, reason: self.rec("cancel_booking", booked_result()),
            post_cancellation=lambda r, tools=None: self.rec("slack_cancel"),
            to_needs_person=lambda case_id, reason: self.rec("to_needs_person"),
            confirmation_email=lambda r: ("subject", f"CONFIRMATION {r.slot_label} (was {r.previous_slot_label})"),
            find_slot=lambda day, hhmm: next((s for s in self.slots if hhmm == f"{12 + s.slot_id}:00"), None),
        )

    def change_booking(self, booking_id, req):
        self.calls.append("change_booking")
        self.changed_to = req
        return booked_result(req.slot_id, label=f"Fri 17 Oct, {req.slot_id}:00 PM", updated=True,
                             previous="Thu 16 Oct, 10:00 AM")


def email_turn(graph, text, *, verified=True, booked=True, first=False, needs_person=None) -> dict:
    """What the poller passes in: identity from code, the booking from the database."""
    inp = {"messages": [HumanMessage(content=text)], "channel": "email", "letter": None, "case_id": 12,
           "session_id": "Case #12, ali@example.com", "customer_id": 3, "customer_email": "ali@example.com",
           "customer_name": "Ali Khan", "customer_phone": "+17865550123", "verified": verified,
           "needs_person": needs_person}
    if booked and first:
        r = booked_result().request
        inp.update(booked=True, last_booking={**booking_to_state(booked_result()), "notified": True},
                   booking=dict(name=r.name, phone=r.phone, email=r.email, address=r.address,
                                problem=r.problem, service=r.service))
    return graph.invoke(inp, {"configurable": {"thread_id": "email:12"}})


@pytest.fixture
def run():
    def make(script):
        fake = Fake(script)
        return fake, build_graph(fake.deps(), InMemorySaver())
    return make


def test_change_request_shows_the_booking_then_changes_on_the_pick(run):
    fake, g = run({
        "I want to update my booking": A(intent="change_or_cancel", change_target="time"),
        "Please move it to Friday afternoon": A(intent="change_or_cancel", change_target="time",
                                                wants_other_times=True, preferred_date="2030-10-17",
                                                part_of_day="afternoon"),
        "The second one": A(intent="booking", slot_choice=2),
    })
    out = email_turn(g, "I want to update my booking", first=True)
    assert "current booking (Case #12)" in out["reply"] and "1 Main St" in out["reply"]
    assert "Thu 16 Oct, 10:00 AM" in out["reply"] and "change_booking" not in fake.calls

    out = email_turn(g, "Please move it to Friday afternoon")
    assert "Fri 17 Oct, 1:00 PM" in out["reply"] and len(out["offered_slots"]) == 3
    assert "change_booking" not in fake.calls              # offering times changes nothing

    out = email_turn(g, "The second one")                  # e.g. three days later: state restored
    assert fake.calls.count("change_booking") == 1 and fake.changed_to.slot_id == 2
    assert fake.changed_to.email == "ali@example.com"
    assert out["letter"] == "CONFIRMATION Fri 17 Oct, 2:00 PM (was Thu 16 Oct, 10:00 AM)"
    assert out["offered_slots"] == [] and "slack_booking" not in fake.calls   # Slack: poller, after the email


def test_exact_open_time_is_booked_at_once(run):
    fake, g = run({"friday works for me 10 AM": A(intent="booking", change_target="time",
                                                  preferred_date="2030-10-17", preferred_time="14:00")})
    out = email_turn(g, "friday works for me 10 AM", first=True)
    assert fake.changed_to.slot_id == 2 and out["letter"].startswith("CONFIRMATION Fri 17 Oct, 2:00 PM")


def test_exact_time_taken_offers_the_closest(run):
    fake, g = run({"Friday at 9 AM": A(intent="change_or_cancel", change_target="time",
                                       preferred_date="2030-10-17", preferred_time="09:00")})
    out = email_turn(g, "Friday at 9 AM", first=True)
    assert "isn't open" in out["reply"] and len(out["offered_slots"]) == 3 and "change_booking" not in fake.calls


def test_new_address_is_changed_at_once_keeping_the_time(run):
    fake, g = run({"New address: 5 Oak Ave": A(intent="change_or_cancel", change_target="address",
                                               address="5 Oak Ave")})
    out = email_turn(g, "New address: 5 Oak Ave", first=True)
    assert fake.changed_to.address == "5 Oak Ave" and fake.changed_to.slot_id == 9 and out["letter"]


def test_unverified_change_changes_nothing_and_tells_slack(run):
    fake, g = run({"Move it to Friday": A(intent="change_or_cancel", change_target="time",
                                          wants_other_times=True)})
    out = email_turn(g, "Move it to Friday", verified=False, first=True)
    assert "nothing has been changed" in out["reply"]
    assert "slack_needs_person" in fake.calls and "change_booking" not in fake.calls


def test_cancel_needs_a_yes(run):
    fake, g = run({"Cancel my visit": A(intent="change_or_cancel", wants_cancel=True),
                   "yes please": A(intent="booking", confirmation="yes")})
    out = email_turn(g, "Cancel my visit", first=True)
    assert out["confirm_cancel"] and "shall I cancel" in out["reply"] and "cancel_booking" not in fake.calls
    out = email_turn(g, "yes please")
    assert fake.calls[-2:] == ["cancel_booking", "slack_cancel"]
    assert "has been cancelled" in out["reply"] and not out["booked"] and not out["confirm_cancel"]


def test_unclear_email_goes_to_a_person_with_fixed_text(run):
    fake, g = run({"We sell SEO services": A(intent="off_topic")})
    out = email_turn(g, "We sell SEO services", booked=False)
    assert out["reply"] == acknowledgement()
    assert "to_needs_person" in fake.calls and "slack_needs_person" in fake.calls


def test_poller_escalation_skips_the_ai(run):
    fake, g = run({})                                       # analyze would raise KeyError if called
    out = email_turn(g, "anything", booked=False, needs_person="over 5 AI replies in an hour")
    assert out["reply"] == acknowledgement() and "to_needs_person" in fake.calls


def test_booking_uses_the_customer_address_not_one_in_the_email(run):
    fake, g = run({"Book me a visit, write to other@x.com": A(intent="booking", email="other@x.com",
                                                              problem="AC not cooling")})
    out = email_turn(g, "Book me a visit, write to other@x.com", booked=False)
    assert out["booking"]["email"] == "ali@example.com" and out["booking"]["name"] == "Ali Khan"
    assert "address" in out["reply"].lower()               # next missing detail is asked for


def test_emergency_email_gets_the_safety_message(run):
    fake, g = run({})
    out = email_turn(g, "I smell gas near the furnace", booked=False)
    assert out["emergency"] and "911" in out["reply"] and "slack_urgent" in fake.calls
