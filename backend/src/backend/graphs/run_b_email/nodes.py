"""Run B nodes: the email conversation. Run A's nodes with the email rules on top.

    gate ─┬─ needs_person (set by the poller, e.g. reply limit) ───────────────┐
          └─ guard ─ classify ─ ... as Run A ...                               │
                       ├─ off_topic (can't tell what it needs) ─ needs_person ─┤
                       └─ booking_step ─ cancel_booking (verified, after yes) ─┴─ respond

Differences from chat (plan 6.4-6.5):
- Changes and cancellations need state["verified"] (set by the poller): the email comes from the
  address on the booking. Otherwise nothing changes and Slack is told.
- A booking always uses the case customer's address, never one typed in the email.
- An email the agent can't handle goes to a person; the customer gets only a fixed acknowledgement.
- A verified customer changing a booking is shown its details, and the change is made as soon as
  they say what (a time, an offered option, a new address...): no extra yes/no.
- After a booking or change, the reply IS the code-written confirmation (one email, not two);
  the poller posts to Slack after that email is sent.
"""

from __future__ import annotations

import logging

from langgraph.types import Command

from backend.config import get_settings
from backend.core.errors import LateChange
from backend.graphs.common.state import EmailState
from backend.graphs.run_a_chat.nodes import (CHANGE_QUESTIONS, RunANodes, _last_human_text, booking_from_state,
                                             slot_list_text)
from backend.graphs.run_b_email.deps import RunBDeps

log = logging.getLogger(__name__)


def acknowledgement() -> str:
    """Fixed text (never generated) sent when a case goes to a person."""
    return ("Thanks for your email. We've received it and a member of our team will reply shortly. "
            f"For anything urgent, call our 24/7 line at {get_settings().business_phone}.")


def booking_details(state: EmailState) -> str:
    """The customer's current booking, read back when they ask to change it."""
    lb = state["last_booking"]
    r = lb["request"]
    return (f"Here is your current booking (Case #{lb['case_id']}):\n"
            f"- Service: {r['service']}\n- Time: {lb['slot_label']}\n- Address: {r['address']}\n"
            f"- Name: {r['name']}\n- Phone: {r['phone']}\n- Email: {r['email']}\n- Problem: {r['problem']}\n\n"
            "What would you like to change? For a new time, tell me the day and time (for example "
            "\"Friday at 10 AM\"). You can also change the address or the problem description.")


class RunBNodes(RunANodes):
    deps: RunBDeps

    def gate(self, state: EmailState) -> Command:
        return Command(goto="needs_person" if state.get("needs_person") else "guard")

    # --- Run A hooks ------------------------------------------------------------------------

    def context(self, state: EmailState) -> str:
        ctx = super().context(state)
        if state.get("confirm_cancel"):
            ctx += f"\nAwaiting yes/no on CANCELLING the visit on {state['last_booking']['slot_label']}."
        return ctx

    def amend_allowed(self, state: EmailState) -> bool:
        return bool(state.get("booked") and state.get("verified"))

    def change_refused(self, state: EmailState) -> Command:
        self._alert_person(state, "change/cancel request that could not be verified")
        return Command(goto="respond", update={"awaiting_confirmation": False, "chosen_slot": None, "reply": (
            "We couldn't confirm this request, so nothing has been changed. For your security, bookings "
            "are only changed or cancelled by email from the address you booked with. "
            "Our team has also been notified.")})

    def cancel_requested(self, state: EmailState) -> Command:
        lb = state["last_booking"]
        return Command(goto="respond", update={"confirm_cancel": True, "reply": (
            f"Just to confirm: shall I cancel your {lb['request']['service']} visit on {lb['slot_label']} "
            f"(Case #{lb['case_id']})? Please reply yes or no.")})

    def classify(self, state: EmailState) -> Command:
        cmd = super().classify(state)
        if cmd.goto == "fallback_form":
            return cmd
        update = cmd.update
        if state.get("confirm_cancel"):
            update["confirm_cancel"] = False
            answer = update["analysis"].get("confirmation")
            if answer == "yes":
                return Command(goto="cancel_booking", update=update)
            if answer == "no":
                return Command(goto="respond", update={**update, "reply": (
                    f"No problem, your visit on {state['last_booking']['slot_label']} stays as it is.")})
        if cmd.goto == "booking_step":
            # Code-chosen identity: the case customer's address, plus details already on file.
            b = dict(update.get("booking") or state.get("booking") or {})
            b["email"] = state["customer_email"]
            for key in ("name", "phone"):
                b[key] = b.get(key) or state.get(f"customer_{key}") or None
            update["booking"] = {k: v for k, v in b.items() if v}
            update["invalid_fields"] = [f for f in update.get("invalid_fields", []) if f != "email"]
            update["analysis"]["changed"] = [f for f in update["analysis"]["changed"] if f != "email"]
        return cmd

    def booking_step(self, state: EmailState) -> Command:
        """A verified customer changing their booking: show it, then make the change as soon as they
        say what. New bookings, refusals and cancellations go as in Run A."""
        a = state["analysis"]
        if not (state.get("booked") and self.amend_allowed(state)) or a.get("wants_cancel"):
            return super().booking_step(state)
        b, lb = state.get("booking") or {}, state["last_booking"]
        offered = state.get("offered_slots") or []
        choice = a.get("slot_choice")
        if offered and choice and 1 <= choice <= len(offered):
            return self._change_to(offered[choice - 1])
        day = a.get("preferred_date") or b.get("preferred_date")
        if a.get("preferred_time") and day:
            slot = self.deps.find_slot(day, a["preferred_time"])
            if slot:
                return self._change_to(slot.to_state())
            intro = "Sorry, that time isn't open. Here are the closest open times:"
        elif a.get("preferred_date") or a.get("part_of_day") or a.get("wants_other_times"):
            intro = "Here are the open times closest to what you asked for:"
        elif [f for f in a.get("changed", []) if f not in ("preferred_date", "part_of_day")]:
            return self._change_to({"slot_id": lb["slot_id"], "label": lb["slot_label"]})   # details only
        elif a.get("change_target") in CHANGE_QUESTIONS:
            return self._ask_change(state, a["change_target"])
        else:
            return Command(goto="respond", update={"reply": booking_details(state)})

        exclude = [lb["slot_id"]] + ([s["slot_id"] for s in offered] if a.get("wants_other_times") else [])
        slots = [s.to_state() for s in self.deps.get_slots(day, a.get("part_of_day") or b.get("part_of_day"),
                                                           exclude_ids=exclude)]
        if not slots:
            return Command(goto="respond", update={"reply": (
                f"I couldn't find another open time near that, so your visit stays on {lb['slot_label']}. "
                f"Tell me another day, or call us 24/7 at {get_settings().business_phone}.")})
        return Command(goto="respond", update={"offered_slots": slots, "chosen_slot": None,
                                               "reply": slot_list_text(slots, intro)})

    def _change_to(self, slot: dict) -> Command:
        return Command(goto="create_booking", update={"chosen_slot": slot, "awaiting_confirmation": False})

    def fixed_reply(self, state: EmailState) -> Command:
        if state.get("intent") == "off_topic":
            return Command(goto="needs_person",
                           update={"needs_person": "the email agent could not tell what this email needs"})
        return super().fixed_reply(state)

    def notify(self, state: EmailState) -> dict:
        """The confirmation becomes this turn's email; the poller sends it, then posts to Slack."""
        saved = state.get("last_booking")
        if not saved or saved.get("notified"):
            return {}
        return {"letter": self.deps.confirmation_email(booking_from_state(saved))[1],
                "last_booking": {**saved, "notified": True}}

    # --- email-only nodes -------------------------------------------------------------------

    def cancel_booking(self, state: EmailState) -> dict:
        case_id = state["case_id"]
        try:
            result = self.deps.cancel_booking(case_id, "cancelled by the customer by email")
        except LateChange:
            self._alert_person(state, "cancellation requested close to the visit")
            return {"reply": ("Your visit is coming up soon, so a team member needs to handle this "
                              "cancellation. We've let them know. You can also call us 24/7 at "
                              f"{get_settings().business_phone}.")}
        try:
            self.deps.post_cancellation(result, self.deps.mcp_tools)
        except Exception:
            log.exception("Slack cancellation post failed for case %s", case_id)
        return {"booked": False, "last_booking": None, "booking": {}, "offered_slots": [], "reply": (
            f"Done: your visit on {result.slot_label} (Case #{case_id}) has been cancelled. If you need "
            "us again, just reply to this email.")}

    def needs_person(self, state: EmailState) -> dict:
        reason = state.get("needs_person") or "the email agent could not handle this email"
        try:
            self.deps.to_needs_person(state["case_id"], reason)
        except Exception:
            log.exception("could not hand case %s to a person", state.get("case_id"))
        self._alert_person(state, reason)
        return {"reply": acknowledgement()}

    def _alert_person(self, state: EmailState, reason: str) -> None:
        details = {"From": state.get("customer_email"), "Email": _last_human_text(state)[:500]}
        try:
            self.deps.post_needs_person(state.get("case_id"), f"{reason} (email)", details, self.deps.mcp_tools)
        except Exception:
            log.exception("needs-person Slack post failed")
