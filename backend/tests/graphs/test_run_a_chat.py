"""Run A end to end with fake dependencies: no LLM, database, Chroma or MCP calls."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from backend.core.errors import SlotTaken
from backend.graphs.run_a_chat import build_graph, chat_turn
from backend.graphs.run_a_chat.deps import RunADeps
from backend.graphs.run_a_chat.schemas import TurnAnalysis
from backend.tools.booking import BookingResult, SlotOption

DEFAULTS = dict(intent="question", name=None, phone=None, email=None, address=None, problem=None,
                service=None, preferred_date=None, part_of_day=None, slot_choice=None,
                wants_other_times=False, wants_cancel=False, confirmation="none", search_query=None,
                sub_queries=[], change_target=None)


def A(**kw) -> TurnAnalysis:
    return TurnAnalysis(**{**DEFAULTS, **kw})


class Fake:
    """Scripted classifier + recorders for every side effect."""

    def __init__(self, script: dict[str, TurnAnalysis], slots=3, taken_once=False, model_down=False):
        self.script, self.calls = script, []
        base = datetime(2030, 10, 16, 9, tzinfo=timezone.utc)
        self.slots = [SlotOption(i + 1, base + timedelta(hours=2 * i), f"Slot {i + 1}") for i in range(slots)]
        self.taken_once, self.model_down = taken_once, model_down
        self.passages = [SimpleNamespace(id="p1", text="The AC diagnostic is $99.", score=0.6)]

    def deps(self) -> RunADeps:
        return RunADeps(
            analyze=self.analyze, search=lambda q: self.passages,
            answer=lambda q, p, h: f"ANSWER from: {p}", smalltalk=lambda m, n: "Hello there!",
            get_slots=self.get_slots, create_booking=self.create_booking,
            change_booking=self.change_booking,
            create_needs_person_case=lambda *a, **k: self._rec("needs_person", a, k) or 77,
            send_confirmation=lambda r, tools=None: self._rec("email", r) or True,
            post_booking=lambda r, tools=None: self._rec("slack_booking", r) or True,
            post_needs_person=lambda *a: self._rec("slack_needs_person", a) or True,
            post_urgent=lambda t, s, tools=None: self._rec("slack_urgent", t) or True,
        )

    def _rec(self, name, *args, **kw):
        self.calls.append(name)

    def analyze(self, message, history, ctx):
        if self.model_down:
            raise TimeoutError("model down")
        return self.script[message]

    def get_slots(self, preferred_date=None, part_of_day=None, limit=None, exclude_ids=None):
        return [s for s in self.slots if s.slot_id not in (exclude_ids or [])][: limit or 3]

    def create_booking(self, req):
        self.calls.append("create_booking")
        if self.taken_once:
            self.taken_once = False
            raise SlotTaken(req.slot_id)
        return BookingResult(booking_id=1, case_id=123, customer_id=9, slot_label="Slot X",
                             starts_at=datetime(2030, 10, 16, 9, tzinfo=timezone.utc), request=req)


    def change_booking(self, booking_id, req):
        self.calls.append("change_booking")
        self.changed_to = req
        return BookingResult(booking_id=booking_id, case_id=123, customer_id=9,
                             slot_label=f"Slot {req.slot_id}", request=req, updated=True,
                             starts_at=datetime(2030, 10, 16, 9, tzinfo=timezone.utc),
                             previous_slot_label="Slot X")


def run(fake: Fake, *messages: str, session: str = "test-session-1", graph=None) -> list[dict]:
    graph = graph or build_graph(fake.deps(), InMemorySaver())
    return [chat_turn(session, m, graph) for m in messages]


FULL_BOOKING = {
    "I need my AC fixed": A(intent="booking", problem="AC not cooling", service="AC Repair"),
    "Sam Lee, 786 555 0123": A(intent="booking", name="Sam Lee", phone="786 555 0123"),
    "sam@example.com, 1 Main St, Miami FL 33176": A(intent="booking", email="sam@example.com",
                                                    address="1 Main St, Miami FL 33176"),
    "the second one": A(intent="booking", slot_choice=2),
    "yes": A(intent="booking", confirmation="yes"),
}


def test_question_goes_to_rag():
    out, = run(Fake({"how much is a diagnostic?": A(search_query="AC diagnostic price")}),
               "how much is a diagnostic?")
    assert out["intent"] == "question"
    assert "$99" in out["reply"]


def test_no_passages_gives_dont_know_and_offer():
    fake = Fake({"do you fix boats?": A()})
    fake.passages = []
    out, = run(fake, "do you fix boats?")
    assert "not sure" in out["reply"] and "book" in out["reply"]


def test_full_booking_end_to_end():
    fake = Fake(FULL_BOOKING)
    outs = run(fake, *FULL_BOOKING)
    assert "name" in outs[0]["reply"].lower()                      # asks for details
    assert "phone" not in outs[1]["reply"].lower() or "email" in outs[1]["reply"].lower()
    assert "Slot 1" in outs[2]["reply"] and "Slot 3" in outs[2]["reply"]   # offers 3 times
    assert "Slot 2" in outs[3]["reply"] and "yes / no" in outs[3]["reply"]  # summary
    final = outs[4]
    assert final["booked"] and final["case_id"] == 123
    assert "Case #123" in final["reply"]
    assert fake.calls == ["create_booking", "email", "slack_booking"]


def test_phone_is_normalized_and_bad_email_rejected():
    script = {
        "book a visit": A(intent="booking", problem="noisy unit", name="Ana", phone="(786) 555-0123",
                          email="not-an-email", address="2 Bay Rd, Miami"),
    }
    out, = run(Fake(script), "book a visit")
    assert "email address doesn't look right" in out["reply"]


def test_slot_taken_offers_new_times():
    fake = Fake(FULL_BOOKING, taken_once=True)
    outs = run(fake, *FULL_BOOKING)
    assert "just taken" in outs[-1]["reply"]
    assert not outs[-1]["booked"]
    assert "email" not in fake.calls


def test_change_request_is_pointed_to_email_and_nothing_changes():
    fake = Fake({"can I move my visit?": A(intent="change_or_cancel")})
    out, = run(fake, "can I move my visit?")
    assert "confirmation email" in out["reply"]
    assert fake.calls == []


def test_emergency_skips_model_and_alerts_slack():
    fake = Fake({}, model_down=True)       # would raise if the classifier were called
    out, = run(fake, "There's a gas smell near the furnace")
    assert out["emergency"] and "911" in out["reply"]
    assert fake.calls == ["slack_urgent"]


def test_model_down_shows_fallback_form():
    out, = run(Fake({}, model_down=True), "hello?")
    assert out["fallback_form"]


def test_no_slots_creates_needs_person_case():
    fake = Fake(FULL_BOOKING, slots=0)
    outs = run(fake, *list(FULL_BOOKING)[:3])
    assert "office will email" in outs[-1]["reply"]
    assert fake.calls == ["needs_person", "slack_needs_person"]


@pytest.mark.parametrize("raw,expected", [
    ("(786) 797-6193", "+17867976193"), ("03001234567", "+923001234567"),
    ("+44 20 7946 0958", "+442079460958"), ("12345", None),
])
def test_phone_normalization(raw, expected):
    from backend.tools.validation import normalize_phone
    assert normalize_phone(raw) == expected


def test_emergency_words():
    from backend.tools.guardrails import is_emergency
    assert is_emergency("I see sparks from the unit")
    assert is_emergency("the closet is flooding")
    assert not is_emergency("my AC is not cooling")


# --- screenshot bugs + changing details -------------------------------------------------

def test_yes_books_even_if_model_guesses_a_service():
    """Bug: a bare 'yes' came back with service='Maintenance Visit' and looped the summary."""
    script = {**FULL_BOOKING, "yes": A(intent="booking", confirmation="yes", service="Maintenance Visit")}
    fake = Fake(script)
    final = run(fake, *script)[-1]
    assert final["booked"] and "Case #123" in final["reply"]
    assert fake.calls[0] == "create_booking"


def test_change_time_before_booking_offers_new_slots():
    """Bug: 'no change the timings' at the summary was sent to the email reply."""
    script = {**FULL_BOOKING,
              "no change the timings": A(intent="change_or_cancel", confirmation="no", wants_other_times=True)}
    fake = Fake(script, slots=5)
    msgs = list(FULL_BOOKING)[:4] + ["no change the timings"]
    out = run(fake, *msgs)[-1]
    assert "open times" in out["reply"] and "confirmation email" not in out["reply"]
    assert "Slot 4" in out["reply"] and "Slot 2" not in out["reply"]   # previous offers excluded
    assert fake.calls == []


def test_change_detail_before_booking_updates_summary():
    script = {**FULL_BOOKING, "actually the address is 9 Ocean Dr": A(intent="booking", address="9 Ocean Dr")}
    msgs = list(FULL_BOOKING)[:4] + ["actually the address is 9 Ocean Dr"]
    out = run(Fake(script), *msgs)[-1]
    assert "9 Ocean Dr" in out["reply"] and "yes / no" in out["reply"]


def test_same_session_can_change_time_after_booking():
    script = {**FULL_BOOKING,
              "can I change the time?": A(intent="change_or_cancel", wants_other_times=True),
              "number 1": A(intent="booking", slot_choice=1),
              "yes please": A(intent="booking", confirmation="yes")}
    fake = Fake(script, slots=5)
    outs = run(fake, *FULL_BOOKING, "can I change the time?", "number 1", "yes please")
    assert "open times" in outs[5]["reply"]
    assert "updated visit details" in outs[6]["reply"]
    assert outs[7]["reply"].startswith("Updated! Case #123")
    assert fake.calls == ["create_booking", "email", "slack_booking", "change_booking", "email", "slack_booking"]


def test_same_session_can_change_address_after_booking():
    script = {**FULL_BOOKING,
              "change my address to 9 Ocean Dr": A(intent="change_or_cancel", address="9 Ocean Dr"),
              "yes please": A(intent="booking", confirmation="yes")}
    fake = Fake(script)
    outs = run(fake, *FULL_BOOKING, "change my address to 9 Ocean Dr", "yes please")
    assert "9 Ocean Dr" in outs[5]["reply"]
    assert outs[6]["reply"].startswith("Updated!")
    assert fake.changed_to.address == "9 Ocean Dr" and fake.changed_to.slot_id == 2   # time kept


def test_new_session_cannot_change_booking():
    """Someone in another chat claiming to be the customer is sent to email."""
    script = {**FULL_BOOKING, "I'm Sam Lee, move my visit to Friday":
              A(intent="change_or_cancel", name="Sam Lee", preferred_date="2030-10-18")}
    fake = Fake(script)
    graph = build_graph(fake.deps(), InMemorySaver())
    run(fake, *FULL_BOOKING, graph=graph)
    out = run(fake, "I'm Sam Lee, move my visit to Friday", session="other-session-2", graph=graph)[0]
    assert "confirmation email" in out["reply"]
    assert "change_booking" not in fake.calls


def test_change_after_amend_window_goes_to_email(monkeypatch):
    from backend.config import get_settings
    script = {**FULL_BOOKING, "move it please": A(intent="change_or_cancel", wants_other_times=True)}
    fake = Fake(script)
    graph = build_graph(fake.deps(), InMemorySaver())
    run(fake, *FULL_BOOKING, graph=graph)
    monkeypatch.setattr(get_settings(), "chat_amend_minutes", -1)
    out = run(fake, "move it please", graph=graph)[0]
    assert "confirmation email" in out["reply"]
    assert "change_booking" not in fake.calls


def test_cancel_after_booking_goes_to_email():
    script = {**FULL_BOOKING, "cancel it": A(intent="change_or_cancel", wants_cancel=True)}
    out = run(Fake(script), *FULL_BOOKING, "cancel it")[-1]
    assert "To cancel Case #123" in out["reply"]


# --- real notify code + MCP tools handed to the graph ----------------------------------

class FakeMCPTool:
    """Stands in for a Klavis MCP tool loaded by MultiServerMCPClient."""

    def __init__(self, name, response="ok", fail=False):
        self.name, self.response, self.fail, self.calls = name, response, fail, []

    async def ainvoke(self, args):
        self.calls.append(args)
        if self.fail:
            raise RuntimeError("MCP server error")
        return self.response


def mcp_toolset(email_fails=False):
    channels = '{"channels": [{"id": "C0C9Y8B5RUY", "name": "slack_urgent_channel"}]}'
    return {
        "gmail_send_email": FakeMCPTool("gmail_send_email", fail=email_fails),
        "slack_user_post_message": FakeMCPTool("slack_user_post_message"),
        "slack_user_list_channels": FakeMCPTool("slack_user_list_channels", channels),
    }


def real_notify_deps(fake, tools):
    from backend.tools import notify
    d = fake.deps()
    d.send_confirmation, d.post_booking, d.mcp_tools = notify.send_booking_confirmation, notify.post_booking, tools
    return d


def test_booking_executes_gmail_and_slack_tools_handed_to_the_graph(monkeypatch):
    """The real notify code renders the templates and executes the MCP tools given to the node."""
    from backend.config import get_settings
    monkeypatch.setattr(get_settings(), "slack_post_tool", "slack_user_post_message")
    monkeypatch.setattr(get_settings(), "slack_bookings_channel", "")
    monkeypatch.setattr(get_settings(), "slack_urgent_channel", "slack_urgent_channel")
    fake, tools = Fake(FULL_BOOKING), mcp_toolset()
    graph = build_graph(real_notify_deps(fake, tools), InMemorySaver())
    final = run(fake, *FULL_BOOKING, graph=graph)[-1]

    assert final["booked"] and "confirmation email is on its way" in final["reply"]
    email = tools["gmail_send_email"].calls[0]
    assert email["to"] == ["sam@example.com"]                      # recipient chosen by code
    assert email["subject"].startswith("[Case #123] Your AC Repair visit")
    assert "Hi Sam Lee" in email["body"]
    post = tools["slack_user_post_message"].calls[0]
    assert post["channel_id"] == "C0C9Y8B5RUY" and "New booking" in post["text"]
    assert final["debug"]["last_booking"]["email_sent"] and final["debug"]["last_booking"]["slack_posted"]


def test_email_failure_never_fails_the_turn(monkeypatch):
    from backend.config import get_settings
    monkeypatch.setattr(get_settings(), "slack_post_tool", "slack_user_post_message")
    monkeypatch.setattr(get_settings(), "slack_urgent_channel", "slack_urgent_channel")
    fake, tools = Fake(FULL_BOOKING), mcp_toolset(email_fails=True)
    graph = build_graph(real_notify_deps(fake, tools), InMemorySaver())
    final = run(fake, *FULL_BOOKING, graph=graph)[-1]
    assert final["booked"] and "Case #123" in final["reply"]
    assert "our team will call you" in final["reply"]
    assert len(tools["gmail_send_email"].calls) == 2                # retried once
    texts = [c["text"] for c in tools["slack_user_post_message"].calls]
    assert any("could not be sent" in t for t in texts) and any("New booking" in t for t in texts)


# --- already booked + booking status ----------------------------------------------------

def test_already_booked_sends_missing_confirmation_to_address_on_file():
    """Case #4 situation: booked during a crash, never notified, customer tries again."""
    from backend.core.errors import AlreadyBooked
    from backend.tools.booking import StoredBooking
    fake = Fake(FULL_BOOKING)
    sent = []
    deps = fake.deps()
    stored_result = BookingResult(booking_id=4, case_id=4, customer_id=4, slot_label="Wed 14 Oct, 12:00 PM",
                                  starts_at=datetime(2030, 10, 14, 12, tzinfo=timezone.utc),
                                  request=SimpleNamespace(email="owner@example.com"))
    deps.create_booking = lambda req: (_ for _ in ()).throw(AlreadyBooked(4))
    deps.load_booking = lambda case_id: StoredBooking(stored_result, email_pending=True, slack_pending=True)
    deps.send_pending = lambda stored, tools=None: sent.append(stored.result.case_id) or {"email_sent": True}
    final = run(fake, *FULL_BOOKING, graph=build_graph(deps, InMemorySaver()))[-1]
    assert sent == [4]
    assert "already a visit booked" in final["reply"] and "just emailed" in final["reply"]
    assert "12:00" not in final["reply"] and "owner@example.com" not in final["reply"]   # no details leaked
    assert not final["booked"]


def test_already_booked_and_already_notified_sends_nothing():
    from backend.core.errors import AlreadyBooked
    from backend.tools.booking import StoredBooking
    fake = Fake(FULL_BOOKING)
    deps = fake.deps()
    deps.create_booking = lambda req: (_ for _ in ()).throw(AlreadyBooked(2))
    deps.load_booking = lambda case_id: StoredBooking(None, email_pending=False, slack_pending=False)
    deps.send_pending = lambda *a, **k: pytest.fail("must not resend")
    final = run(fake, *FULL_BOOKING, graph=build_graph(deps, InMemorySaver()))[-1]
    assert "was emailed to the address on file" in final["reply"]


def test_booking_status_after_booking_in_same_chat():
    script = {**FULL_BOOKING, "is my booking confirmed?": A(intent="booking_status")}
    out = run(Fake(script), *FULL_BOOKING, "is my booking confirmed?")[-1]
    assert out["reply"].startswith("Yes, you're booked. Case #123") and "sam@example.com" in out["reply"]


def test_booking_status_before_yes():
    script = {**FULL_BOOKING, "is my booking confirmed?": A(intent="booking_status")}
    out = run(Fake(script), *list(FULL_BOOKING)[:4], "is my booking confirmed?")[-1]
    assert out["reply"].startswith("Not yet")


def test_booking_status_in_new_chat_reveals_nothing():
    out = run(Fake({"is my booking confirmed?": A(intent="booking_status")}), "is my booking confirmed?")[0]
    assert "can't look up bookings" in out["reply"]


# --- retrieval fixes -----------------------------------------------------------------------

def test_sub_queries_reach_the_search():
    seen = []
    fake = Fake({"new ac in key largo, can i pay monthly?": A(
        search_query="Financing for a new AC", sub_queries=["Do you serve Key Largo?", "Free estimate?"])})
    deps = fake.deps()
    deps.search = lambda queries: seen.append(queries) or fake.passages
    run(fake, "new ac in key largo, can i pay monthly?", graph=build_graph(deps, InMemorySaver()))
    assert seen == [["Financing for a new AC", "Do you serve Key Largo?", "Free estimate?"]]


def test_diversify_caps_chunks_per_source():
    from backend.rag.retriever import _diversify
    from backend.rag.schema import Passage
    ranked = [Passage(f"p{i}", "t", 0.9 - i / 100, {"source_doc": src})
              for i, src in enumerate(["faq", "faq", "faq", "pricing", "faq", "hours"])]
    picked = _diversify(ranked, k=4, max_per_source=2)
    assert [p.id for p in picked] == ["p0", "p1", "p3", "p5"]


# --- human-like changes (screenshot: the bot asked the same question three times) ---------------

def test_update_contact_number_asks_for_the_number_then_shows_summary():
    script = {**FULL_BOOKING,
              "oh sorry i mistakenly gave wrong contact number please update it":
                  A(intent="change_or_cancel", change_target="phone"),
              "03488017721": A(intent="booking", phone="03488017721"),
              "yes please": A(intent="booking", confirmation="yes")}
    fake = Fake(script)
    outs = run(fake, *FULL_BOOKING, "oh sorry i mistakenly gave wrong contact number please update it",
               "03488017721", "yes please")
    assert "correct phone number" in outs[5]["reply"]                    # asks for exactly that
    assert "+923488017721" in outs[6]["reply"] and "update your booking" in outs[6]["reply"]
    assert outs[7]["reply"].startswith("Updated!") and fake.changed_to.phone == "+923488017721"


def test_contact_details_asks_for_the_value_not_the_same_menu():
    script = {**FULL_BOOKING,
              "I want to change something": A(intent="change_or_cancel"),
              "contact details": A(intent="change_or_cancel", change_target="contact")}
    outs = run(Fake(script), *FULL_BOOKING, "I want to change something", "contact details")
    assert "What would you like to change" in outs[5]["reply"]
    assert "phone number or email" in outs[6]["reply"]
    assert outs[6]["reply"] != outs[5]["reply"]


def test_same_question_is_never_repeated_verbatim():
    script = {**FULL_BOOKING, "hmm": A(intent="change_or_cancel"), "hmm ok": A(intent="change_or_cancel")}
    outs = run(Fake(script), *FULL_BOOKING, "hmm", "hmm ok")
    assert outs[5]["reply"] != outs[6]["reply"]


def test_reply_writer_text_is_used_when_safe():
    fake = Fake({**FULL_BOOKING, "wrong email sorry": A(intent="change_or_cancel", change_target="email")})
    deps = fake.deps()
    deps.phrase = lambda task, facts, fallback, message, history: "No worries! What's the right email?"
    outs = run(fake, *FULL_BOOKING, "wrong email sorry", graph=build_graph(deps, InMemorySaver()))
    assert outs[-1]["reply"] == "No worries! What's the right email?"


def test_reply_writer_guard_rejects_new_numbers():
    from backend.graphs.run_a_chat.deps import _safe_wording
    assert _safe_wording("No problem! What's the right number?", "ask for phone")
    assert not _safe_wording("Sure, I moved you to 3 PM.", "ask for phone")            # invented time
    assert not _safe_wording("The diagnostic is $99.", "ask for phone")                # invented price
    assert _safe_wording("Call us at (786) 797-6193.", "phone (786) 797-6193")
