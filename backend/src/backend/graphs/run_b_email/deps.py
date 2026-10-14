"""Run B dependencies: Run A's (with email-worded prompts), plus cancel and escalation."""

from __future__ import annotations

from dataclasses import dataclass, fields
from functools import partial
from typing import Callable

from backend.graphs.run_a_chat import deps as run_a
from backend.graphs.run_a_chat.deps import RunADeps


@dataclass
class RunBDeps(RunADeps):
    cancel_booking: Callable = None          # booking.cancel_booking(case_id, reason)
    post_cancellation: Callable = None       # notify.post_cancellation(result, tools)
    to_needs_person: Callable = None         # booking.to_needs_person(case_id, reason)
    confirmation_email: Callable = None      # notify.confirmation_email(result) -> (subject, body)
    find_slot: Callable = None               # booking.find_slot(day, hhmm) -> SlotOption | None


def default_deps() -> RunBDeps:
    from backend.tools import booking, notify
    base = run_a.default_deps()
    shared = {f.name: getattr(base, f.name) for f in fields(RunADeps)}
    shared.update({name: partial(getattr(run_a, name), channel="email")
                   for name in ("analyze", "answer", "smalltalk", "phrase")})
    return RunBDeps(**shared, cancel_booking=booking.cancel_booking, post_cancellation=notify.post_cancellation,
                    to_needs_person=booking.to_needs_person, confirmation_email=notify.confirmation_email,
                    find_slot=booking.find_slot)
