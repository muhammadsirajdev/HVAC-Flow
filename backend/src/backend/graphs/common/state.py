"""Shared state types for the LangGraph runs."""

from __future__ import annotations

from typing import Annotated, Literal, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

Channel = Literal["web", "email", "whatsapp"]

# Fields the chat must collect before it can book (plan section 5).
REQUIRED_BOOKING_FIELDS = ("name", "phone", "email", "address", "problem")


class BookingDraft(TypedDict, total=False):
    name: str
    phone: str            # E.164, validated by code
    email: str            # validated by code
    address: str
    problem: str
    service: str
    preferred_date: str   # YYYY-MM-DD
    part_of_day: str      # morning | afternoon | evening | any


class ChatState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]
    session_id: str
    channel: Channel

    # this turn
    intent: str
    analysis: dict
    reply: str
    fallback_form: bool
    emergency: bool

    # booking flow (persists across turns via the checkpointer)
    booking: BookingDraft
    invalid_fields: list[str]
    offered_slots: list[dict]        # [{slot_id, starts_at, label}]
    chosen_slot: dict | None
    awaiting_confirmation: bool
    booked: bool
    case_id: int | None
    customer_id: int | None
    last_booking: dict | None        # plain-data BookingResult, for the notify node
    pending_change: str | None       # detail we asked the customer to give (phone, email, ...)
    last_ask: str | None             # key of the last question, so it is never repeated verbatim
