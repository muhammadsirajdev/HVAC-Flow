"""Structured output of the Run A classifier."""

from typing import Literal

from pydantic import BaseModel, Field

Intent = Literal["question", "booking", "booking_status", "change_or_cancel", "payment",
                 "diy_or_diagnosis", "smalltalk", "off_topic"]

SERVICES = [
    "AC Repair", "AC Installation & Replacement", "Ductwork Services", "Mini Split Systems",
    "Heat Pump Services", "Attic Insulation", "Commercial HVAC", "Maintenance Visit",
]


class TurnAnalysis(BaseModel):
    intent: Intent
    name: str | None
    phone: str | None
    email: str | None
    address: str | None
    problem: str | None
    service: str | None = Field(description="One of the listed services, or null")
    preferred_date: str | None = Field(description="YYYY-MM-DD")
    part_of_day: Literal["morning", "afternoon", "evening", "any"] | None
    slot_choice: int | None = Field(description="1-based number of an offered time")
    wants_other_times: bool
    wants_cancel: bool
    change_target: Literal["time", "address", "problem", "name", "phone", "email", "contact",
                           "service"] | None = Field(description="Detail the customer wants to change")
    confirmation: Literal["yes", "no", "none"]
    search_query: str | None
    sub_queries: list[str] = Field(description="Extra standalone queries for multi-part questions")
