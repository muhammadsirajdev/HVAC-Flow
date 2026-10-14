"""Run A nodes: website chat.

    guard ─┬─ emergency ──────────────────────────────────────────────┐
           └─ classify ─┬─ question ─────────── rag_answer ─────────┤
                        ├─ booking ──────────── booking_step ─┬─────┤
                        │                                     └─ create_booking ─ notify ─┤
                        ├─ change/payment/diy/off_topic ─ fixed_reply ─────────┤
                        ├─ smalltalk ─────────── smalltalk ───────────────────┤
                        └─ model down ───────── fallback_form ───────────────┴─ respond

The LLM only classifies, extracts details and phrases answers from the KB. Slots,
booking, status changes, confirmation text, email and Slack are all code.

Changing a booking from chat is allowed only in the SAME chat session that made it,
within CHAT_AMEND_MINUTES. Anyone else (a new session claiming to be the customer)
is sent to the confirmation email, which is the verified channel.
"""

from __future__ import annotations

import logging
from dataclasses import asdict
from datetime import datetime, timedelta

from langchain_core.messages import AIMessage
from langgraph.types import Command

from backend.config import get_settings
from backend.core.errors import AlreadyBooked, ContactInUse, LateChange, SlotTaken
from backend.core.timeutil import now
from backend.graphs.common.state import REQUIRED_BOOKING_FIELDS, ChatState
from backend.graphs.run_a_chat.deps import RunADeps, format_history
from backend.tools.booking import BookingRequest, BookingResult
from backend.tools.guardrails import is_emergency, safety_message
from backend.tools.validation import normalize_email, normalize_phone

log = logging.getLogger(__name__)

ASK_ORDER = ("problem", "name", "phone", "email", "address")
FIELD_QUESTIONS = {
    "problem": "Could you briefly describe what's going on with your system?",
    "name": "What name should I put the booking under?",
    "phone": "What's the best phone number to reach you?",
    "email": "What email address should we send the confirmation to?",
    "address": "What's the address for the visit (street, city and ZIP)?",
}
INVALID_MESSAGES = {
    "phone": "That phone number doesn't look right. Could you check it? For example (786) 555-0123.",
    "email": "That email address doesn't look right. Could you check it? For example name@example.com.",
}
DEFAULT_SERVICE = "HVAC Service Visit"
CHANGE_QUESTIONS = {
    "phone": "No problem. What's the correct phone number?",
    "email": "No problem. What's the correct email address?",
    "name": "Sure. What name should the booking be under?",
    "address": "Sure. What's the correct address for the visit?",
    "problem": "Sure. How would you describe the problem now?",
    "service": "Sure. Which service do you need?",
    "contact": "Sure. Just type the new phone number or email here and I'll update it.",
}
FIELD_LABELS = {"phone": "phone number", "email": "email address", "name": "name on the booking",
                "address": "visit address", "problem": "problem description", "service": "service",
                "contact": "contact details (phone number or email)"}


def _phone() -> str:
    return get_settings().business_phone


def _last_human_text(state: ChatState) -> str:
    for m in reversed(state.get("messages", [])):
        if m.type == "human":
            return str(m.content)
    return ""


def _booking_in_progress(state: ChatState) -> bool:
    return bool(state.get("booking")) and not state.get("booked")


def _amend_allowed(state: ChatState) -> bool:
    """Same session that booked, and still within the amend window."""
    lb = state.get("last_booking") or {}
    if not state.get("booked") or not lb.get("booked_at"):
        return False
    window = timedelta(minutes=get_settings().chat_amend_minutes)
    return now() - datetime.fromisoformat(lb["booked_at"]) <= window


def _email_only(case_id) -> str:
    ref = f" for Case #{case_id}" if case_id else " (its subject starts with [Case #...])"
    return (f"To change or cancel a booking, please reply to your confirmation email{ref} and we'll "
            f"take care of it there. For anything urgent, call us 24/7 at {_phone()}.")


def business_facts() -> str:
    """Always-true contact facts from config, given to the answer step as a passage."""
    s = get_settings()
    return (f"[Business: {s.business_name} | Category: contact | Topic: Phone and email]\n"
            f"{s.business_name} 24/7 service and emergency phone line: {s.business_phone}. "
            f"Email: {s.business_inbox}.")


def answer_context(passages) -> str:
    return "\n\n".join([p.text for p in passages] + [business_facts()])


def dont_know() -> str:
    return ("I'm not sure about that one, and I don't want to guess. I can book a technician "
            f"visit for you, or you can call us 24/7 at {_phone()}.")


def fallback_text() -> str:
    return ("Sorry, I'm having trouble answering right now. Please leave your details in the form "
            f"and our team will get back to you shortly, or call us 24/7 at {_phone()}.")


def booking_context(state: ChatState) -> str:
    """What the classifier needs to know about the booking in progress."""
    waiting = state.get("pending_change")
    note = (f"\nThe assistant is WAITING for the customer's new {FIELD_LABELS.get(waiting, waiting)}."
            if waiting else "")
    return _booking_context(state) + note


def _booking_context(state: ChatState) -> str:
    b = state.get("booking") or {}
    if state.get("booked"):
        lb = state.get("last_booking") or {}
        lines = [f"A visit is ALREADY BOOKED in this chat: Case #{state.get('case_id')} on "
                 f"{lb.get('slot_label')}. Details: " + ", ".join(f"{k}={v}" for k, v in b.items())]
        offered = state.get("offered_slots") or []
        if offered:
            lines.append("New times offered for the change: " +
                         "; ".join(f"{i}. {s['label']}" for i, s in enumerate(offered, 1)))
        if state.get("awaiting_confirmation"):
            lines.append(f"Awaiting yes/no on the UPDATED summary for {state['chosen_slot']['label']}.")
        return "\n".join(lines)
    if not b:
        return "No booking in progress."
    lines = [f"Booking in progress. Collected: " +
             (", ".join(f"{k}={v}" for k, v in b.items()) or "nothing")]
    missing = [f for f in REQUIRED_BOOKING_FIELDS if not b.get(f)]
    lines.append("Still needed: " + (", ".join(missing) or "nothing"))
    offered = state.get("offered_slots") or []
    if offered:
        lines.append("Times offered: " + "; ".join(f"{i}. {s['label']}" for i, s in enumerate(offered, 1)))
    if state.get("awaiting_confirmation"):
        lines.append(f"Awaiting yes/no on the summary for {state['chosen_slot']['label']}.")
    return "\n".join(lines)


def slot_list_text(slots: list[dict], intro: str) -> str:
    items = "\n".join(f"{i}. {s['label']}" for i, s in enumerate(slots, 1))
    return f"{intro}\n{items}\nWhich one works for you? You can also ask for a different day."


def summary_text(b: dict, slot: dict, updating: bool = False) -> str:
    title = "Please check your updated visit details:" if updating else "Please check your visit details:"
    question = "Shall I update your booking? (yes / no)" if updating else "Shall I book it? (yes / no)"
    return (
        f"{title}\n"
        f"- Service: {b.get('service') or DEFAULT_SERVICE}\n"
        f"- Time: {slot['label']}\n"
        f"- Address: {b['address']}\n"
        f"- Name: {b['name']}\n"
        f"- Phone: {b['phone']}\n"
        f"- Email: {b['email']}\n"
        f"- Problem: {b['problem']}\n"
        f"{question}"
    )


def booking_to_state(r: BookingResult, booked_at: str | None = None) -> dict:
    """Checkpointed state must be plain data. booked_at starts the chat amend window."""
    return {"booking_id": r.booking_id, "case_id": r.case_id, "customer_id": r.customer_id,
            "slot_id": r.request.slot_id, "slot_label": r.slot_label, "starts_at": r.starts_at.isoformat(),
            "request": asdict(r.request), "updated": r.updated, "previous_slot_label": r.previous_slot_label,
            "booked_at": booked_at or now().isoformat(), "notified": False}


def booking_from_state(d: dict) -> BookingResult:
    return BookingResult(booking_id=d["booking_id"], case_id=d["case_id"], customer_id=d["customer_id"],
                         slot_label=d["slot_label"], starts_at=datetime.fromisoformat(d["starts_at"]),
                         request=BookingRequest(**d["request"]), updated=d.get("updated", False),
                         previous_slot_label=d.get("previous_slot_label"))


class RunANodes:
    def __init__(self, deps: RunADeps):
        self.deps = deps

    # --- entry --------------------------------------------------------------------

    def guard(self, state: ChatState) -> Command:
        """Code-only emergency check, before any model call."""
        reset = {"reply": "", "fallback_form": False, "emergency": False, "intent": "", "analysis": {}}
        text = _last_human_text(state)
        if is_emergency(text):
            try:
                self.deps.post_urgent(text, state.get("session_id", "?"), self.deps.mcp_tools)
            except Exception:
                log.exception("urgent Slack alert failed")
            return Command(goto="respond", update={**reset, "emergency": True, "intent": "emergency",
                                                   "reply": safety_message()})
        return Command(goto="classify", update=reset)

    def classify(self, state: ChatState) -> Command:
        text = _last_human_text(state)
        history = format_history(state.get("messages", [])[:-1])
        try:
            analysis = self.deps.analyze(text, history, booking_context(state))
        except Exception:
            log.exception("classifier failed")
            return Command(goto="fallback_form")

        # Merge extracted details into the draft; code validates email and phone.
        # A draft starts only when the customer asks to book (a question about a leak
        # should not start a booking).
        booking = dict(state.get("booking") or {})
        collect = analysis.intent in ("booking", "change_or_cancel") or bool(booking)
        # A plain "yes" to the summary carries no new details, whatever the model extracted.
        if state.get("awaiting_confirmation") and analysis.confirmation == "yes":
            collect = False
        # After booking, only the same session (within the window) may change details.
        if state.get("booked") and not _amend_allowed(state):
            collect = False
        invalid, changed = [], []
        for field in ("name", "address", "problem", "service", "preferred_date", "part_of_day"):
            value = getattr(analysis, field)
            if collect and value and str(value).strip() and booking.get(field) != value:
                booking[field] = str(value).strip()
                changed.append(field)
        for field, normalize in (("phone", normalize_phone), ("email", normalize_email)):
            raw = getattr(analysis, field)
            if collect and raw:
                value = normalize(raw)
                if value:
                    if booking.get(field) != value:
                        booking[field] = value
                        changed.append(field)
                else:
                    invalid.append(field)

        update = {"analysis": {**analysis.model_dump(), "changed": changed}, "intent": analysis.intent,
                  "invalid_fields": invalid}
        if booking:
            update["booking"] = booking

        goto = {
            "question": "rag_answer",
            "booking": "booking_step",
            "smalltalk": "smalltalk",
        }.get(analysis.intent, "fixed_reply")
        # "Change the time" before booking, or in the session that booked: handled in chat.
        if analysis.intent == "change_or_cancel" and (_booking_in_progress(state) or state.get("booked")):
            goto = "booking_step"
        # Details given mid-booking with an unclear intent still advance the booking.
        if analysis.intent in ("smalltalk", "off_topic") and _booking_in_progress(state) and (changed or invalid):
            goto = "booking_step"
        return Command(goto=goto, update=update)

    # --- question -> RAG -------------------------------------------------------------

    def rag_answer(self, state: ChatState) -> dict:
        a = state["analysis"]
        question = a.get("search_query") or _last_human_text(state)
        queries = [question] + [q for q in (a.get("sub_queries") or []) if q][:2]
        try:
            passages = self.deps.search(queries)
        except Exception:
            log.exception("knowledge-base search failed")
            return {"reply": f"Sorry, I can't look that up right now. Please call us 24/7 at {_phone()}."}
        if not passages:
            reply = dont_know()
        else:
            context = answer_context(passages)
            original = _last_human_text(state)
            asked = original if original.strip() == question.strip() else f"{original}\n(in other words: {question})"
            try:
                reply = self.deps.answer(asked, context, format_history(state["messages"][:-1], 4))
            except Exception:
                log.exception("answer model failed")
                return {"reply": fallback_text(), "fallback_form": True}
            if not reply or "NO_ANSWER" in reply:
                reply = dont_know()
        if _booking_in_progress(state):
            reply += "\n\nWhenever you're ready, we can carry on with your booking."
        return {"reply": reply}

    # --- fixed replies -------------------------------------------------------------------

    def fixed_reply(self, state: ChatState) -> dict:
        intent = state.get("intent")
        case_id = state.get("case_id")
        if intent == "booking_status":
            reply = self._status_text(state)
        elif intent == "change_or_cancel":
            reply = _email_only(case_id)
        elif intent == "payment":
            reply = ("Please don't share card or payment details here. We never take payment in this "
                     "chat. I'm happy to help with questions or book a visit.")
        elif intent == "diy_or_diagnosis":
            reply = ("It's best to have a technician take a look rather than guess at the cause or try "
                     "a fix yourself. Would you like me to book a visit?")
        else:
            reply = (f"I can help with heating and cooling questions and booking a visit with "
                     f"{get_settings().business_name}. What can I do for you?")
        return {"reply": reply}

    def _status_text(self, state: ChatState) -> str:
        """Booking status from THIS chat's state only; never looked up by contact details."""
        lb = state.get("last_booking") or {}
        if state.get("booked") and lb:
            r = lb.get("request") or {}
            email = (f"The confirmation email was sent to {r.get('email')}." if lb.get("email_sent")
                     else "We couldn't send the confirmation email, so our team will call you to confirm.")
            return (f"Yes, you're booked. Case #{lb['case_id']}: {r.get('service')} on {lb['slot_label']} "
                    f"at {r.get('address')}. {email}")
        if _booking_in_progress(state):
            return ("Not yet: nothing is booked until you say yes to the summary. "
                    "Shall we carry on with your booking?")
        return ("I can't look up bookings in this chat. Please check your confirmation email (its subject "
                f"starts with [Case #...]) or call us 24/7 at {_phone()}.")

    def smalltalk(self, state: ChatState) -> dict:
        note = ("A booking is in progress; gently invite them to continue it."
                if _booking_in_progress(state) else "")
        try:
            reply = self.deps.smalltalk(_last_human_text(state), note)
        except Exception:
            log.exception("smalltalk model failed")
            reply = ""
        return {"reply": reply or (
            f"Hi! I'm the {get_settings().business_name} assistant. I can answer questions about our "
            "services, prices and service areas, or book a technician visit. How can I help?")}

    def fallback_form(self, state: ChatState) -> dict:
        return {"reply": fallback_text(), "fallback_form": True}

    # --- booking (code-driven) ----------------------------------------------------------

    def _say(self, state: ChatState, key: str, task: str, fallback: str, facts: str = "",
             **update) -> Command:
        """Ask/acknowledge in natural words. Code decided WHAT; the reply writer decides HOW.
        The same question (key) is never sent twice in a row with the same wording."""
        if state.get("last_ask") == key:
            task += (" You ALREADY asked this in your previous message and the customer did not give it."
                     " Say it differently and show them how to answer.")
        history = format_history(state.get("messages", [])[:-1], 6)
        text = self.deps.phrase(task, facts, fallback, _last_human_text(state), history)
        if state.get("last_ask") == key and text.strip() == fallback.strip():
            text = fallback + " You can just type it here."
        return Command(goto="respond", update={"reply": text, "last_ask": key, **update})

    def _ask_change(self, state: ChatState, target: str, **update) -> Command:
        """The customer wants to change one detail but has not given the new value yet."""
        label = FIELD_LABELS.get(target, target)
        task = (f"The customer wants to change the {label} on their booking but has not given the new "
                f"one yet. Acknowledge briefly and ask for the new {label}. Do not ask about anything else.")
        return self._say(state, f"change:{target}", task, CHANGE_QUESTIONS[target],
                         pending_change=target, **update)

    def booking_step(self, state: ChatState) -> Command:
        a = state["analysis"]
        b = dict(state.get("booking") or {})
        invalid = state.get("invalid_fields") or []
        amending = bool(state.get("booked"))
        lb = state.get("last_booking") or {}

        if amending:
            if not _amend_allowed(state):
                return Command(goto="respond", update={"reply": _email_only(state.get("case_id"))})
            if a.get("wants_cancel"):
                return Command(goto="respond", update={"reply": (
                    f"To cancel Case #{state.get('case_id')}, please reply to your confirmation email "
                    "and our team will take care of it.")})
        elif a.get("wants_cancel"):
            return Command(goto="respond", update={
                "booking": {}, "offered_slots": [], "chosen_slot": None, "awaiting_confirmation": False,
                "reply": "No problem, I've stopped the booking. Nothing was booked. Anything else I can help with?"})

        target = a.get("change_target")
        if target == "time":
            a = {**a, "wants_other_times": True}
        # They named a detail to change but did not give the new value: ask for exactly that.
        if target in CHANGE_QUESTIONS and not a.get("changed") and not state.get("invalid_fields"):
            return self._ask_change(state, target)

        if state.get("awaiting_confirmation"):
            if a.get("confirmation") == "yes":
                return Command(goto="create_booking", update={"pending_change": None, "last_ask": None})
            if a.get("confirmation") == "no" and not a.get("changed") and not a.get("wants_other_times"):
                return self._say(
                    state, "what_to_change",
                    "The customer said no to the booking summary. Reassure them and ask what they would "
                    "like to change: the time, the address, the problem, or their name/phone/email.",
                    "No problem. What would you like to change: the time, the address, or your details?",
                    awaiting_confirmation=False, chosen_slot=None)
            # Anything else: fall through and re-plan with what we now know.

        # 1. Collect missing or invalid details, one or two at a time.
        missing = [f for f in ASK_ORDER if not b.get(f) or f in invalid]
        if missing:
            parts = [INVALID_MESSAGES[f] for f in invalid if f in INVALID_MESSAGES]
            asks = [FIELD_QUESTIONS[f] for f in missing if f not in invalid][: 2 - min(len(parts), 1)]
            prefix = f"Thanks, {b['name'].split()[0]}! " if "name" in a.get("changed", []) else ""
            if not parts and not prefix and not state.get("booking"):
                prefix = "I can help you book a visit. "
            fallback = prefix + " ".join(parts + asks)
            wanted = [FIELD_LABELS.get(f, f) for f in missing if f not in invalid][: 2 - min(len(parts), 1)]
            bad = [FIELD_LABELS.get(f, f) for f in invalid]
            task = ("You are collecting details to book an HVAC visit. "
                    + (f"The customer's {', '.join(bad)} looks invalid; ask them to check it. " if bad else "")
                    + (f"Ask for: {' and '.join(wanted)}. " if wanted else "")
                    + ("Thank them by first name for what they just gave. " if prefix.startswith("Thanks") else ""))
            facts = f"customer first name: {b['name'].split()[0]}" if b.get("name") else ""
            return self._say(state, "missing:" + ",".join(missing), task, fallback, facts,
                             awaiting_confirmation=False)

        # 2. Pick a time.
        offered = state.get("offered_slots") or []
        choice = a.get("slot_choice")
        new_preference = any(f in a.get("changed", []) for f in ("preferred_date", "part_of_day"))
        time_change = bool(a.get("wants_other_times") or new_preference)

        if offered and choice and 1 <= choice <= len(offered) and not a.get("wants_other_times"):
            chosen = offered[choice - 1]
            return Command(goto="respond", update={
                "chosen_slot": chosen, "awaiting_confirmation": True, "pending_change": None, "last_ask": None,
                "reply": summary_text(b, chosen, amending)})
        if state.get("awaiting_confirmation") and state.get("chosen_slot") and not time_change:
            # Details changed while confirming: show the summary again.
            return Command(goto="respond", update={"reply": summary_text(b, state["chosen_slot"], amending),
                                                   "pending_change": None, "last_ask": None})
        if amending and not time_change:
            if a.get("changed"):        # details only, keep the booked time
                current = {"slot_id": lb["slot_id"], "label": lb["slot_label"]}
                return Command(goto="respond", update={
                    "chosen_slot": current, "awaiting_confirmation": True, "pending_change": None,
                    "last_ask": None, "reply": summary_text(b, current, updating=True)})
            return self._say(
                state, "what_to_change",
                "The customer wants to change their booking but has not said what. Ask what they would "
                "like to change: the time, the address, the problem description, or their name/phone/email.",
                "Sure. What would you like to change: the time, the address, the problem description, "
                "or your name, phone or email?")
        if offered and not time_change and not amending:
            return Command(goto="respond", update={
                "reply": slot_list_text(offered, "These times are still open:")})

        exclude = [s["slot_id"] for s in offered] if a.get("wants_other_times") else []
        if amending:
            exclude.append(lb["slot_id"])
        slots = [s.to_state() for s in self.deps.get_slots(
            b.get("preferred_date"), b.get("part_of_day"), exclude_ids=exclude)]
        if not slots:
            if amending:
                return Command(goto="respond", update={"reply": (
                    f"I couldn't find another open time right now, so your visit stays on "
                    f"{lb['slot_label']}. Please call us 24/7 at {_phone()} to find another time.")})
            return self._no_slots(state, b)
        intro = ("Here are the closest open times to what you asked for:" if b.get("preferred_date")
                 else "Here are the next open times:")
        return Command(goto="respond", update={
            "offered_slots": slots, "chosen_slot": None, "awaiting_confirmation": False,
            "reply": slot_list_text(slots, intro)})

    def _no_slots(self, state: ChatState, b: dict) -> Command:
        try:
            case_id = self.deps.create_needs_person_case(
                b.get("name"), b.get("phone"), b.get("email"), b.get("address"),
                note=f"No open slots in chat. Problem: {b.get('problem')}")
            self.deps.post_needs_person(case_id, "no open times in website chat", b, self.deps.mcp_tools)
        except Exception:
            log.exception("could not open needs_person case")
            case_id = None
        ref = f" (Case #{case_id})" if case_id else ""
        return Command(goto="respond", update={"case_id": case_id, "booked": False, "reply": (
            f"I couldn't find an open time right now{ref}. Our office will email you at "
            f"{b.get('email')} with a time. For anything urgent, call us 24/7 at {_phone()}.")})

    def create_booking(self, state: ChatState) -> Command:
        """Saves a new booking, or (same session) applies the change to the existing one."""
        b, slot = state["booking"], state["chosen_slot"]
        amending = bool(state.get("booked"))
        lb = state.get("last_booking") or {}
        req = BookingRequest(slot_id=slot["slot_id"], service=b.get("service") or DEFAULT_SERVICE,
                             name=b["name"], phone=b["phone"], email=b["email"], address=b["address"],
                             problem=b["problem"], channel=state.get("channel", "web"))
        try:
            if amending:
                if not _amend_allowed(state):
                    return Command(goto="respond", update={
                        "awaiting_confirmation": False, "chosen_slot": None,
                        "reply": _email_only(state.get("case_id"))})
                result = self.deps.change_booking(lb["booking_id"], req)
            else:
                result = self.deps.create_booking(req)
        except SlotTaken:
            exclude = [slot["slot_id"]] + ([lb["slot_id"]] if amending else [])
            slots = [s.to_state() for s in self.deps.get_slots(
                b.get("preferred_date"), b.get("part_of_day"), exclude_ids=exclude)]
            update = {"chosen_slot": None, "awaiting_confirmation": False, "offered_slots": slots}
            if not slots:
                if amending:
                    update["reply"] = (f"Sorry, that time was just taken and I couldn't find another, so your "
                                       f"visit stays on {lb['slot_label']}. Please call us at {_phone()}.")
                    return Command(goto="respond", update=update)
                return self._no_slots(state, b)
            update["reply"] = slot_list_text(slots, "Sorry, that time was just taken. Here are other open times:")
            return Command(goto="respond", update=update)
        except AlreadyBooked as exc:
            return Command(goto="respond", update={"awaiting_confirmation": False, "chosen_slot": None,
                                                   "reply": self._already_booked(exc.case_id)})
        except LateChange:
            try:
                self.deps.post_needs_person(state.get("case_id"), "late change requested in website chat",
                                            b, self.deps.mcp_tools)
            except Exception:
                log.exception("needs-person Slack post failed")
            return Command(goto="respond", update={
                "awaiting_confirmation": False, "chosen_slot": None, "reply": (
                    f"Your visit is coming up soon, so a team member needs to make this change. "
                    f"We've let them know. You can also call us 24/7 at {_phone()}.")})
        except ContactInUse:
            return Command(goto="respond", update={
                "awaiting_confirmation": False, "chosen_slot": None, "reply": (
                    "I can't change those contact details in chat. Please reply to your confirmation "
                    "email and our team will update them.")})
        except Exception:
            log.exception("booking write failed")
            return Command(goto="respond", update={"fallback_form": True, "reply": (
                f"Sorry, I couldn't complete that just now. Please call us 24/7 at {_phone()}, "
                "or leave your details in the form and we'll call you.")})

        if amending:
            reply = f"Updated! Case #{result.case_id}: {req.service} on {result.slot_label} at {req.address}."
        else:
            reply = f"You're booked! Case #{result.case_id}: {req.service} on {result.slot_label} at {req.address}."
        return Command(goto="notify", update={
            "booked": True, "awaiting_confirmation": False, "offered_slots": [], "chosen_slot": None,
            "case_id": result.case_id, "customer_id": result.customer_id, "reply": reply,
            "last_booking": booking_to_state(result, lb.get("booked_at") if amending else None)})

    def _already_booked(self, case_id: int) -> str:
        """Contact details that already have a booked case. The visitor is not verified, so the
        booking's details are not shown; anything never sent goes to the address ON FILE."""
        sent_now = False
        try:
            stored = self.deps.load_booking(case_id)
            if stored and (stored.email_pending or stored.slack_pending):
                log.warning("case %s was never fully notified; sending now", case_id)
                sent_now = bool(self.deps.send_pending(stored, self.deps.mcp_tools).get("email_sent"))
        except Exception:
            log.exception("could not check notifications for case %s", case_id)
        email = ("We've just emailed its confirmation to the address on file." if sent_now
                 else "Its confirmation was emailed to the address on file.")
        return (f"There's already a visit booked for these contact details (Case #{case_id}). {email} "
                "We keep one open booking per customer; to change or cancel it, reply to that email. "
                f"For anything urgent, call us 24/7 at {_phone()}.")

    def notify(self, state: ChatState) -> dict:
        """Confirmation email (Gmail MCP) then Slack. Failures alert people, never undo."""
        saved = state.get("last_booking")
        update: dict = {}
        if not saved or saved.get("notified"):
            return update
        result = booking_from_state(saved)
        # The booking is already saved: a notification failure must never fail the turn.
        try:
            email_sent = bool(self.deps.send_confirmation(result, self.deps.mcp_tools))
        except Exception:
            log.exception("confirmation email step failed for case %s", result.case_id)
            email_sent = False
        if email_sent:
            what = "An updated confirmation" if result.updated else "A confirmation"
            tail = (f" {what} email is on its way to {result.request.email}. You can make changes here "
                    "for now; later, just reply to that email.")
        else:
            tail = " We couldn't send the confirmation email just now; our team will call you to confirm."
        try:
            slack_posted = bool(self.deps.post_booking(result, self.deps.mcp_tools))
        except Exception:
            log.exception("Slack booking post failed for case %s", result.case_id)
            slack_posted = False
        update["reply"] = state["reply"] + tail
        update["last_booking"] = {**saved, "notified": True, "email_sent": email_sent,
                                  "slack_posted": slack_posted}
        return update

    # --- exit ----------------------------------------------------------------------------

    def respond(self, state: ChatState) -> dict:
        return {"messages": [AIMessage(content=state.get("reply") or dont_know())]}
