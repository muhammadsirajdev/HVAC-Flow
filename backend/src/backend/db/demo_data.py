"""Made-up customers for the public demo: every case status and channel, with real-looking history.

reset_demo_data() EMPTIES the app tables (customers, cases, bookings, messages, chat memory), then
writes the demo cases. It runs from `scripts/seed_demo_data.py --yes` or daily at DEMO_RESET_HOUR
when DEMO_MODE=true. All names, phones (555) and emails (example.com) are fictional.
"""

from __future__ import annotations

import logging
from datetime import datetime, time, timedelta

from psycopg import Connection
from psycopg.types.json import Jsonb

from backend.config import get_settings
from backend.core.timeutil import business_tz, format_slot, now
from backend.db.init_db import init_db
from backend.db.session import get_pool
from backend.db.slots import ensure_slots

log = logging.getLogger(__name__)

APP_TABLES = "customers, cases, case_events, bookings, messages, slack_events"
CHAT_MEMORY = ("checkpoints", "checkpoint_blobs", "checkpoint_writes")


class _Writer:
    """Small helpers so each demo case below reads like its story."""

    def __init__(self, conn: Connection):
        self.conn, self.now = conn, now()

    def ago(self, **kw) -> datetime:
        return self.now - timedelta(**kw)

    def workday(self, offset: int) -> datetime.date:
        """`offset` days from today, moved off Sunday (no slots on Sundays)."""
        d = self.now.date() + timedelta(days=offset)
        while d.weekday() == 6:
            d += timedelta(days=1 if offset >= 0 else -1)
        return d

    def slot(self, offset: int, hour: int, taken: bool = True) -> tuple[int, datetime]:
        start = datetime.combine(self.workday(offset), time(hour), tzinfo=business_tz())
        row = self.conn.execute(
            "INSERT INTO slots (starts_at, ends_at, taken) VALUES (%s, %s, %s) "
            "ON CONFLICT (starts_at) DO UPDATE SET taken = EXCLUDED.taken RETURNING slot_id",
            (start, start + timedelta(hours=2), taken)).fetchone()
        return row["slot_id"], start

    def customer(self, name, email, phone, address, at) -> int:
        return self.conn.execute(
            "INSERT INTO customers (name, email, phone, address, created_at) VALUES (%s,%s,%s,%s,%s) "
            "RETURNING customer_id", (name, email, phone, address, at)).fetchone()["customer_id"]

    def case(self, customer_id, status, channel, at, thread=None, updated=None, closed=None) -> int:
        return self.conn.execute(
            "INSERT INTO cases (customer_id, status, channel, email_thread_id, created_at, updated_at, closed_at) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING case_id",
            (customer_id, status, channel, thread, at, updated or at, closed)).fetchone()["case_id"]

    def event(self, case_id, frm, to, reason, at) -> None:
        self.conn.execute("INSERT INTO case_events (case_id, from_status, to_status, reason, created_at) "
                          "VALUES (%s,%s,%s,%s,%s)", (case_id, frm, to, reason, at))

    def chat(self, case_id, session, turns: list[tuple[str, str]], start: datetime, booked_last=False) -> datetime:
        """Website chat turns (customer, assistant), one minute apart. Returns the last time."""
        t = start
        for i, (said, reply) in enumerate(turns):
            booked = booked_last and i == len(turns) - 1
            self.message(case_id, "web", "in", session, said, None, t)
            self.message(case_id, "web", "out", session, reply,
                         {"intent": "booking" if booked else "question", "booked": booked, "emergency": False},
                         t + timedelta(seconds=20))
            t += timedelta(minutes=1)
        return t

    def email(self, case_id, direction, thread, body, at, subject=None, sender=None) -> None:
        meta = {"subject": subject, "from": sender} if direction == "in" else None
        self.message(case_id, "email", direction, thread, body, meta, at,
                     provider=f"demo-{case_id}-{direction}-{int(at.timestamp())}")

    def message(self, case_id, channel, direction, thread, body, meta, at, provider=None) -> None:
        self.conn.execute(
            "INSERT INTO messages (case_id, channel, direction, thread_key, provider_msg_id, body, meta, created_at) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
            (case_id, channel, direction, thread, provider, body, Jsonb(meta) if meta else None, at))

    def booking(self, case_id, slot_id, service, address, problem, at, active=True, confirmed=True,
                reminded=False) -> None:
        self.conn.execute(
            "INSERT INTO bookings (case_id, slot_id, service, address, problem, active, reminded, created_at, "
            "confirmation_sent_at, slack_posted_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (case_id, slot_id, service, address, problem, active, reminded, at,
             at + timedelta(seconds=4) if confirmed else None, at + timedelta(seconds=6)))


def _write_cases(w: _Writer) -> int:
    biz = get_settings().business_name

    # 1. Website chat -> booked for tomorrow morning.
    addr = "1420 SW 22nd St, Miami, FL 33145"
    slot_id, start = w.slot(1, 10)
    at = w.ago(hours=3)
    cid = w.customer("Maria Gonzalez", "maria.gonzalez@example.com", "+13055550118", addr, at)
    case = w.case(cid, "booked", "web", at)
    end = w.chat(case, "demo-maria", [
        ("Hi, my AC is running but the air coming out of the vents is warm.",
         "Sorry to hear that. Warm air from a running AC usually points to a refrigerant leak, a failing "
         "capacitor or a blocked coil. A technician can find the cause on a repair visit. Would you like me to book one?"),
        ("Yes please, tomorrow morning if you can.",
         f"Tomorrow I have {format_slot(start - timedelta(hours=2))}, {format_slot(start)} or "
         f"{format_slot(start + timedelta(hours=2))}. Which suits you?"),
        ("10 works. Maria Gonzalez, 305-555-0118, maria.gonzalez@example.com, 1420 SW 22nd St, Miami",
         f"You're booked for AC repair on {format_slot(start)} at 1420 SW 22nd St. A confirmation email is on "
         f"its way to maria.gonzalez@example.com. Your case number is #{case}."),
    ], at, booked_last=True)
    w.event(case, None, "open", "opened via web", end - timedelta(seconds=50))
    w.event(case, "open", "booked", "create_booking via web", end - timedelta(seconds=40))
    w.booking(case, slot_id, "AC repair", addr, "AC runs but blows warm air", end - timedelta(seconds=40))

    # 2. Email question -> answered by the AI, still open.
    at = w.ago(days=1, hours=2)
    cid = w.customer("James Whitfield", "james.whitfield@example.com", None, None, at)
    case = w.case(cid, "open", "email", at, thread="demo-thread-james")
    w.event(case, None, "open", "opened via email", at)
    w.email(case, "in", "demo-thread-james",
            "Hi, our heat pump is about 14 years old and struggling in the heat. Roughly what does it cost to "
            "replace a 3-ton heat pump, and do you offer financing?\n\nThanks,\nJames", at,
            subject="Heat pump replacement cost?", sender="James Whitfield <james.whitfield@example.com>")
    w.email(case, "out", "demo-thread-james",
            "Hi James,\n\nThanks for getting in touch. The price of a new heat pump depends on its size, "
            "efficiency rating and what your home needs, so we give a firm figure after a free in-home estimate. "
            "Financing is available, and we can go through the options at the estimate.\n\n"
            "Reply with a couple of times that suit you and we'll book it.\n\n"
            f"Best regards,\n{biz}", at + timedelta(minutes=2))

    # 3. Website enquiry form -> handed to a person (commercial work is priced by hand).
    at = w.ago(hours=5)
    cid = w.customer("Priya Raman", "priya@ramandental.example.com", "+17865550142", None, at)
    case = w.case(cid, "needs_person", "form", at, thread="demo-thread-priya")
    w.event(case, None, "open", "opened via form", at)
    w.email(case, "in", "demo-thread-priya",
            "Name: Priya Raman\nEmail: priya@ramandental.example.com\nPhone: (786) 555-0142\nMessage: We run a "
            "dental clinic in Doral with four rooftop units. Could you quote a yearly maintenance contract?", at,
            subject="Website enquiry form", sender="priya@ramandental.example.com")
    w.event(case, "open", "needs_person", "commercial maintenance contract: the office prices these by hand",
            at + timedelta(seconds=30))

    # 4. Booked in the chat, cancelled later by email.
    addr = "88 NE 168th St, North Miami Beach, FL 33162"
    slot_id, start = w.slot(2, 14, taken=False)
    at = w.ago(days=2, hours=4)
    cid = w.customer("Daniel Okafor", "d.okafor@example.com", "+19545550173", addr, at)
    case = w.case(cid, "cancelled", "web", at, thread="demo-thread-daniel", updated=w.ago(hours=7),
                  closed=w.ago(hours=7))
    end = w.chat(case, "demo-daniel", [
        ("Do you service Carrier furnaces? Mine makes a rattling noise.",
         "Yes, we service all major brands, Carrier included. A rattle often means a loose panel or a failing "
         "blower part. Shall I book a technician?"),
        ("Sure. Daniel Okafor, 954-555-0173, d.okafor@example.com, 88 NE 168th St, North Miami Beach. Any afternoon.",
         f"Done: heating repair on {format_slot(start)} at 88 NE 168th St. Your case number is #{case}."),
    ], at, booked_last=True)
    w.event(case, None, "open", "opened via web", end - timedelta(seconds=50))
    w.event(case, "open", "booked", "create_booking via web", end - timedelta(seconds=40))
    w.booking(case, slot_id, "Heating repair", addr, "Furnace rattles", end - timedelta(seconds=40), active=False)
    w.email(case, "in", "demo-thread-daniel",
            f"Hi, the noise turned out to be a loose panel and I fixed it myself. Please cancel case #{case}. Thanks!",
            w.ago(hours=7), subject=f"Re: [Case #{case}] Your visit is booked",
            sender="Daniel Okafor <d.okafor@example.com>")
    w.event(case, "booked", "cancelled", "cancelled by the customer by email", w.ago(hours=7) + timedelta(minutes=1))
    w.email(case, "out", "demo-thread-daniel",
            f"Hi Daniel,\n\nNo problem, your visit on {format_slot(start)} is cancelled. Glad the fix was simple. "
            f"If the noise comes back, just reply here.\n\nBest regards,\n{biz}",
            w.ago(hours=7) + timedelta(minutes=2))

    # 5. Email booking last week -> job done -> thank-you sent, case closed.
    addr = "2215 Ponce de Leon Blvd, Coral Gables, FL 33134"
    slot_id, start = w.slot(-3, 8)
    at = w.ago(days=8)
    cid = w.customer("Linda Chen", "linda.chen@example.com", "+13055550190", addr, at)
    case = w.case(cid, "closed", "email", at, thread="demo-thread-linda", updated=start + timedelta(hours=5),
                  closed=start + timedelta(hours=5))
    w.event(case, None, "open", "opened via email", at)
    w.email(case, "in", "demo-thread-linda",
            f"Hello, I'd like an AC tune-up before the summer. Mornings are best. My address is {addr}, "
            "phone 305-555-0190.\n\nLinda", at, subject="AC tune-up", sender="Linda Chen <linda.chen@example.com>")
    w.event(case, "open", "booked", "create_booking via email", at + timedelta(minutes=2))
    w.booking(case, slot_id, "AC maintenance", addr, "Pre-summer tune-up", at + timedelta(minutes=2), reminded=True)
    w.email(case, "out", "demo-thread-linda",
            f"Hi Linda,\n\nYou're booked for AC maintenance on {format_slot(start)} at {addr}. "
            f"Your case number is #{case}.\n\nBest regards,\n{biz}", at + timedelta(minutes=2))
    w.event(case, "booked", "done", "reported done in the Slack status channel", start + timedelta(hours=3))
    w.email(case, "out", "demo-thread-linda",
            f"Hi Linda,\n\nThank you for choosing {biz}. We hope your AC is running smoothly. If anything isn't "
            f"right, reply to this email.\n\nBest regards,\n{biz}", start + timedelta(hours=5))
    w.event(case, "done", "closed", "thank-you email sent", start + timedelta(hours=5))

    # 6. Booked in the chat, then moved to another day in the same chat.
    addr = "540 Brickell Key Dr, Miami, FL 33131"
    slot_id, start = w.slot(3, 14)
    at = w.ago(days=1, hours=6)
    cid = w.customer("Carlos Mendez", "carlos.mendez@example.com", "+17865550127", addr, at)
    case = w.case(cid, "booked", "web", at)
    end = w.chat(case, "demo-carlos", [
        ("I want a quote for a mini-split in my home office.",
         "Happy to help. A technician can measure the room and quote on site. Would you like an estimate visit?"),
        ("Yes. Carlos Mendez, 786-555-0127, carlos.mendez@example.com, 540 Brickell Key Dr, Miami. Tomorrow at 12.",
         f"You're booked for a mini-split estimate tomorrow at 12:00 PM. Your case number is #{case}."),
        ("Actually, can we do later in the week, in the afternoon?",
         f"Moved: your estimate is now on {format_slot(start)}. The updated confirmation is on its way."),
    ], at, booked_last=True)
    w.event(case, None, "open", "opened via web", at + timedelta(minutes=1, seconds=10))
    w.event(case, "open", "booked", "create_booking via web", at + timedelta(minutes=1, seconds=20))
    w.event(case, "booked", "booked", "change_booking via web", end - timedelta(seconds=40))
    w.booking(case, slot_id, "Mini-split installation estimate", addr, "Home office", at + timedelta(minutes=1))

    # 7. Website chat that sounds dangerous -> a person calls back.
    at = w.ago(minutes=40)
    cid = w.customer("Ahmed Hassan", "ahmed.hassan@example.com", "+13055550164", None, at)
    case = w.case(cid, "needs_person", "web", at)
    end = w.chat(case, "demo-ahmed", [
        ("There's a burning smell coming from the vents and the unit just shut off.",
         "Please turn the system off at the thermostat and the breaker, and don't run it again until it's checked. "
         "If you see smoke, leave the house and call 911. Can I have your name and phone so our team calls you now?"),
        ("Ahmed Hassan, 305-555-0164",
         f"Thanks, Ahmed. I've passed this to our team as urgent (case #{case}); someone will call you shortly."),
    ], at)
    w.event(case, None, "needs_person", "possible electrical fault: urgent call-back", end - timedelta(seconds=30))
    return 7


def reset_demo_data(force: bool = False) -> int:
    """Empty the app data and write the demo cases. Refuses unless DEMO_MODE=true or force=True."""
    if not (get_settings().demo_mode or force):
        raise RuntimeError("reset_demo_data wipes the database: it only runs with DEMO_MODE=true (or force=True)")
    init_db()
    with get_pool().connection() as conn:
        have = {r["table_name"] for r in conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'").fetchall()}
        memory = ", ".join(t for t in CHAT_MEMORY if t in have)
        conn.execute(f"TRUNCATE {APP_TABLES}{', ' + memory if memory else ''} RESTART IDENTITY CASCADE")
        conn.execute("DELETE FROM slots WHERE starts_at < now() - interval '30 days'")
        conn.execute("UPDATE slots SET taken = false")
        n = _write_cases(_Writer(conn))
    ensure_slots(14)
    log.info("demo data reset: %d cases", n)
    return n
