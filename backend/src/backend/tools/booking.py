"""get_open_slots, create_booking, change_booking (cancel_booking comes with Run B).

create_booking is the only way a case becomes 'booked'. It runs in one transaction
and locks the slot, so the same slot can never be booked twice.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from backend.config import get_settings
from psycopg.errors import UniqueViolation

from backend.core.errors import AlreadyBooked, ContactInUse, LateChange, SlotTaken
from backend.core.timeutil import business_tz, format_slot, now
from backend.db.session import get_pool
from backend.tools import cases
from backend.tools.customers import upsert_customer

PART_OF_DAY_HOUR = {"morning": 9, "afternoon": 14, "evening": 17, "any": 10}


@dataclass
class SlotOption:
    slot_id: int
    starts_at: datetime
    label: str

    def to_state(self) -> dict:
        return {"slot_id": self.slot_id, "starts_at": self.starts_at.isoformat(), "label": self.label}


@dataclass
class BookingRequest:
    slot_id: int
    service: str
    name: str
    phone: str
    email: str
    address: str
    problem: str
    channel: str = "web"


@dataclass
class BookingResult:
    booking_id: int
    case_id: int
    customer_id: int
    slot_label: str
    starts_at: datetime
    request: BookingRequest
    updated: bool = False                    # True when produced by change_booking
    previous_slot_label: str | None = None


def _target(preferred_date: str | None, part_of_day: str | None) -> datetime | None:
    if not preferred_date:
        return None
    try:
        day = date.fromisoformat(preferred_date)
    except ValueError:
        return None
    hour = PART_OF_DAY_HOUR.get(part_of_day or "any", 10)
    return datetime.combine(day, time(hour), tzinfo=business_tz())


def get_open_slots(preferred_date: str | None = None, part_of_day: str | None = None,
                   limit: int | None = None, exclude_ids: list[int] | None = None) -> list[SlotOption]:
    """Up to `limit` free slots, closest to the preferred day/time (or soonest if none given)."""
    s = get_settings()
    limit = limit or s.slot_offer_count
    earliest = now() + timedelta(hours=s.min_lead_hours)
    target = _target(preferred_date, part_of_day)
    order = "abs(extract(epoch FROM starts_at - %(target)s))" if target else "starts_at"
    sql = (
        "SELECT slot_id, starts_at FROM slots "
        "WHERE NOT taken AND starts_at >= %(earliest)s AND NOT (slot_id = ANY(%(exclude)s)) "
        f"ORDER BY {order} LIMIT %(limit)s"
    )
    with get_pool().connection() as conn:
        rows = conn.execute(sql, {"earliest": earliest, "target": target, "limit": limit,
                                  "exclude": exclude_ids or []}).fetchall()
    rows.sort(key=lambda r: r["starts_at"])
    return [SlotOption(r["slot_id"], r["starts_at"], format_slot(r["starts_at"])) for r in rows]


def create_booking(req: BookingRequest) -> BookingResult:
    """Save customer, case and booking atomically; set the case to booked.

    Raises SlotTaken if the slot is gone, AlreadyBooked if the customer already has
    a booked open case (changes go through email, not chat).
    """
    with get_pool().connection() as conn:
        slot = conn.execute(
            "SELECT slot_id, starts_at, taken FROM slots WHERE slot_id = %s FOR UPDATE", (req.slot_id,)
        ).fetchone()
        if slot is None or slot["taken"] or slot["starts_at"] < now():
            raise SlotTaken(req.slot_id)

        customer = upsert_customer(conn, req.name, req.email, req.phone, req.address)
        case = cases.open_case(conn, customer["customer_id"], req.channel)
        if case["status"] == "booked":
            raise AlreadyBooked(case["case_id"])

        booking = conn.execute(
            "INSERT INTO bookings (case_id, slot_id, service, address, problem) "
            "VALUES (%s, %s, %s, %s, %s) RETURNING booking_id",
            (case["case_id"], req.slot_id, req.service, req.address, req.problem),
        ).fetchone()
        conn.execute("UPDATE slots SET taken = true WHERE slot_id = %s", (req.slot_id,))
        cases.transition(conn, case["case_id"], "booked", f"create_booking via {req.channel}")

    return BookingResult(
        booking_id=booking["booking_id"], case_id=case["case_id"], customer_id=customer["customer_id"],
        slot_label=format_slot(slot["starts_at"]), starts_at=slot["starts_at"], request=req,
    )


def change_booking(booking_id: int, req: BookingRequest) -> BookingResult:
    """Move a booking to req.slot_id and/or update its details, in one transaction.

    Callers decide who may change (chat: same session only; email: verified sender).
    Raises SlotTaken, LateChange (visit is too close), ContactInUse.
    """
    s = get_settings()
    with get_pool().connection() as conn:
        old = conn.execute(
            "SELECT b.booking_id, b.case_id, b.slot_id, s.starts_at, c.customer_id, c.status "
            "FROM bookings b JOIN slots s USING (slot_id) JOIN cases c USING (case_id) "
            "WHERE b.booking_id = %s AND b.active FOR UPDATE OF b, c", (booking_id,)).fetchone()
        if old is None or old["status"] != "booked":
            raise LateChange(f"booking {booking_id} is not an active booking")
        if old["starts_at"] - now() < timedelta(hours=s.late_change_hours):
            raise LateChange(f"visit for case {old['case_id']} is within {s.late_change_hours} hours")

        starts_at = old["starts_at"]
        if req.slot_id != old["slot_id"]:
            new = conn.execute("SELECT slot_id, starts_at, taken FROM slots WHERE slot_id = %s FOR UPDATE",
                               (req.slot_id,)).fetchone()
            if new is None or new["taken"] or new["starts_at"] < now():
                raise SlotTaken(req.slot_id)
            conn.execute("UPDATE slots SET taken = false WHERE slot_id = %s", (old["slot_id"],))
            conn.execute("UPDATE slots SET taken = true WHERE slot_id = %s", (req.slot_id,))
            starts_at = new["starts_at"]

        # A change needs a new (updated) confirmation and Slack post.
        conn.execute(
            "UPDATE bookings SET slot_id = %s, service = %s, address = %s, problem = %s, reminded = false, "
            "confirmation_sent_at = NULL, slack_posted_at = NULL "
            "WHERE booking_id = %s", (req.slot_id, req.service, req.address, req.problem, booking_id))
        cust = conn.execute(
            "SELECT cu.name, cu.phone, lower(cu.email) AS email, cu.created_at >= c.created_at - interval '5 minutes' AS is_new "
            "FROM customers cu JOIN cases c ON c.customer_id = cu.customer_id WHERE c.case_id = %s",
            (old["case_id"],)).fetchone()
        if (cust["name"], cust["phone"], cust["email"]) != (req.name, req.phone, req.email):
            # An existing customer's contact details are never changed from unverified chat.
            if not cust["is_new"]:
                raise ContactInUse("contact details of an existing customer can only change by email")
            try:
                with conn.transaction():
                    conn.execute("UPDATE customers SET name = %s, phone = %s, email = %s WHERE customer_id = %s",
                                 (req.name, req.phone, req.email, old["customer_id"]))
            except UniqueViolation as exc:
                raise ContactInUse("that email or phone belongs to another customer") from exc
        cases.transition(conn, old["case_id"], "booked", f"change_booking via {req.channel}")

    return BookingResult(
        booking_id=booking_id, case_id=old["case_id"], customer_id=old["customer_id"],
        slot_label=format_slot(starts_at), starts_at=starts_at, request=req,
        updated=True, previous_slot_label=format_slot(old["starts_at"]),
    )


@dataclass
class StoredBooking:
    result: BookingResult
    email_pending: bool          # confirmation email never sent
    slack_pending: bool          # Slack booking post never sent


_STORED_SQL = (
    "SELECT b.booking_id, b.case_id, c.customer_id, b.slot_id, b.service, b.address, b.problem, "
    "       b.confirmation_sent_at, b.slack_posted_at, s.starts_at, c.channel, "
    "       cu.name, cu.phone, cu.email "
    "FROM bookings b JOIN cases c USING (case_id) JOIN slots s USING (slot_id) "
    "JOIN customers cu ON cu.customer_id = c.customer_id "
    "WHERE b.active AND c.status = 'booked' "
)


def _stored(row: dict) -> StoredBooking:
    req = BookingRequest(slot_id=row["slot_id"], service=row["service"], name=row["name"] or "",
                         phone=row["phone"] or "", email=row["email"] or "", address=row["address"],
                         problem=row["problem"] or "", channel=row["channel"])
    result = BookingResult(booking_id=row["booking_id"], case_id=row["case_id"],
                           customer_id=row["customer_id"], slot_label=format_slot(row["starts_at"]),
                           starts_at=row["starts_at"], request=req)
    return StoredBooking(result, row["confirmation_sent_at"] is None, row["slack_posted_at"] is None)


def load_booking(case_id: int) -> StoredBooking | None:
    """The active booking on a booked case, with what was never notified."""
    with get_pool().connection() as conn:
        row = conn.execute(_STORED_SQL + "AND b.case_id = %s", (case_id,)).fetchone()
    return _stored(row) if row else None


def pending_notifications() -> list[StoredBooking]:
    """Booked visits whose confirmation email or Slack post never went out."""
    with get_pool().connection() as conn:
        rows = conn.execute(_STORED_SQL + "AND (b.confirmation_sent_at IS NULL OR b.slack_posted_at IS NULL) "
                            "ORDER BY b.booking_id").fetchall()
    return [_stored(r) for r in rows]


def mark_notified(booking_id: int, *, email: bool = False, slack: bool = False) -> None:
    sets = [col for col, on in (("confirmation_sent_at", email), ("slack_posted_at", slack)) if on]
    if not sets:
        return
    with get_pool().connection() as conn:
        conn.execute(f"UPDATE bookings SET {', '.join(f'{c} = now()' for c in sets)} WHERE booking_id = %s",
                     (booking_id,))


def create_needs_person_case(name: str | None, phone: str | None, email: str | None,
                             address: str | None, note: str, channel: str = "web") -> int:
    """A case the office must pick up (fallback form, no open slots, agent stuck)."""
    with get_pool().connection() as conn:
        customer = upsert_customer(conn, name, email, phone, address)
        case = cases.open_case(conn, customer["customer_id"], channel, status="needs_person", note=note)
        if case["status"] != "needs_person":
            cases.transition(conn, case["case_id"], "needs_person", note)
        return case["case_id"]
