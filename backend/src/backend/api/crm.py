"""Office view (CRM): read-only data for the frontend. Enabled with DEV_UI=true.

    /crm/overview     dispatch-board counts and the business details
    /crm/cases        case list (filter by status, channel, search)
    /crm/cases/{id}   one case: customer, bookings, events, messages, the customer's other cases
    /crm/activity     the latest happenings across all cases
    /crm/schedule     slots for the next days, open or booked

Who sees what is decided by backend.core.demo.office_access: signed in -> everything; public demo ->
contact details partly hidden (backend.core.privacy); OFFICE_PASSWORD without demo -> sign in first.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from backend.config import get_settings
from backend.core import demo, privacy
from backend.core.timeutil import business_tz, format_slot, now as business_now
from backend.db.session import get_pool

router = APIRouter(prefix="/crm", tags=["crm"])
STATUSES = ("open", "booked", "needs_person", "done", "closed", "cancelled")


def _access(request: Request) -> bool:
    """Dependency: 404 when the office is off; True when contact details must be partly hidden."""
    if not get_settings().dev_ui:
        raise HTTPException(404)
    return demo.office_access(request)


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def _day_start(offset: int = 0) -> datetime:
    """Midnight in the business time zone, `offset` days from today."""
    d = business_now().date() + timedelta(days=offset)
    return datetime.combine(d, time.min, tzinfo=business_tz())


def _hide(masked: bool, fn, value):
    """privacy.<fn>(value) for the public demo's view; the value itself otherwise."""
    return fn(value) if masked else value


def _person(masked: bool, name, email, phone) -> dict:
    return {"name": _hide(masked, privacy.name, name), "email": _hide(masked, privacy.email, email),
            "phone": _hide(masked, privacy.phone, phone)}


def _meta(meta: dict, masked: bool) -> dict:
    """Message metadata; addresses in it (an email's From/To) are hidden like the rest."""
    if not masked:
        return meta
    return {k: privacy.text(v) if isinstance(v, str) else v for k, v in meta.items()}


def _visit(row: dict, masked: bool = False) -> dict | None:
    if not row.get("booking_id"):
        return None
    return {"booking_id": row["booking_id"], "service": row["service"],
            "address": _hide(masked, privacy.address, row["address"]),
            "active": row.get("active", True), "starts_at": _iso(row["starts_at"]),
            "slot": format_slot(row["starts_at"]) if row.get("starts_at") else None}


@router.get("/overview")
def overview(masked: bool = Depends(_access)) -> dict:
    s = get_settings()
    window = {"t0": _day_start(0), "t1": _day_start(1), "t2": _day_start(2)}
    with get_pool().connection() as conn:
        by_status = {r["status"]: r["n"] for r in conn.execute(
            "SELECT status::text AS status, count(*) AS n FROM cases GROUP BY status").fetchall()}
        by_channel = {r["channel"]: r["n"] for r in conn.execute(
            "SELECT channel, count(*) AS n FROM cases GROUP BY channel").fetchall()}
        counts = conn.execute("""
            SELECT
              (SELECT count(*) FROM cases WHERE created_at > now() - interval '7 days') AS new_7d,
              (SELECT count(*) FROM bookings b JOIN slots s ON s.slot_id = b.slot_id
                WHERE b.active AND s.starts_at >= %(t0)s AND s.starts_at < %(t1)s) AS visits_today,
              (SELECT count(*) FROM bookings b JOIN slots s ON s.slot_id = b.slot_id
                WHERE b.active AND s.starts_at >= %(t1)s AND s.starts_at < %(t2)s) AS visits_tomorrow,
              (SELECT count(*) FROM slots WHERE NOT taken AND starts_at > now()) AS open_slots,
              (SELECT count(*) FROM customers) AS customers""", window).fetchone()
        nxt = conn.execute("""
            SELECT b.case_id, b.service, s.starts_at, cu.name
            FROM bookings b JOIN slots s ON s.slot_id = b.slot_id
            JOIN cases c ON c.case_id = b.case_id JOIN customers cu ON cu.customer_id = c.customer_id
            WHERE b.active AND s.starts_at > now() ORDER BY s.starts_at LIMIT 1""").fetchone()
    return {
        "business": {"name": s.business_name, "phone": s.business_phone, "tz": s.business_tz,
                     "inbox": s.email_agent_address or s.business_inbox},
        "by_status": {k: by_status.get(k, 0) for k in STATUSES},
        "by_channel": by_channel,
        **counts,
        "next_visit": nxt and {"case_id": nxt["case_id"], "service": nxt["service"],
                               "name": _hide(masked, privacy.name, nxt["name"]),
                               "starts_at": _iso(nxt["starts_at"]), "slot": format_slot(nxt["starts_at"])},
    }


@router.get("/cases")
def list_cases(status: str | None = None, channel: str | None = None, q: str | None = None,
               limit: int = Query(100, ge=1, le=300), masked: bool = Depends(_access)) -> dict:
    q = (q or "").strip() or None
    params = {"status": status or None, "channel": channel or None, "limit": limit,
              "like": f"%{q}%" if q else None, "num": q.lstrip("#") if q else None}
    with get_pool().connection() as conn:
        rows = conn.execute("""
            SELECT c.case_id, c.status::text AS status, c.channel, c.note, c.created_at, c.updated_at,
                   cu.customer_id, cu.name, cu.email, cu.phone,
                   bk.booking_id, bk.service, bk.address, bk.active, bk.starts_at,
                   ev.to_status::text AS last_status, ev.reason AS last_reason, ev.created_at AS last_at,
                   (SELECT count(*) FROM messages m WHERE m.case_id = c.case_id
                      AND m.meta->>'ignored' IS NULL) AS messages
            FROM cases c
            JOIN customers cu ON cu.customer_id = c.customer_id
            LEFT JOIN LATERAL (
                SELECT b.booking_id, b.service, b.address, b.active, s.starts_at
                FROM bookings b JOIN slots s ON s.slot_id = b.slot_id
                WHERE b.case_id = c.case_id ORDER BY b.active DESC, b.booking_id DESC LIMIT 1) bk ON true
            LEFT JOIN LATERAL (
                SELECT to_status, reason, created_at FROM case_events e
                WHERE e.case_id = c.case_id ORDER BY e.event_id DESC LIMIT 1) ev ON true
            WHERE (%(status)s::text IS NULL OR c.status::text = %(status)s)
              AND (%(channel)s::text IS NULL OR c.channel = %(channel)s)
              AND (%(like)s::text IS NULL OR cu.name ILIKE %(like)s OR cu.email ILIKE %(like)s
                   OR cu.phone ILIKE %(like)s OR c.case_id::text = %(num)s)
            ORDER BY COALESCE(ev.created_at, c.updated_at) DESC
            LIMIT %(limit)s""", params).fetchall()
    return {"cases": [{
        "case_id": r["case_id"], "status": r["status"], "channel": r["channel"],
        "note": _hide(masked, privacy.text, r["note"]),
        "created_at": _iso(r["created_at"]), "updated_at": _iso(r["updated_at"]),
        "customer": {"customer_id": r["customer_id"], **_person(masked, r["name"], r["email"], r["phone"])},
        "visit": _visit(r, masked),
        "last_event": r["last_status"] and {"to_status": r["last_status"],
                                            "reason": _hide(masked, privacy.text, r["last_reason"]),
                                            "at": _iso(r["last_at"])},
        "messages": r["messages"],
    } for r in rows]}


@router.get("/cases/{case_id}")
def case_detail(case_id: int, masked: bool = Depends(_access)) -> dict:
    with get_pool().connection() as conn:
        case = conn.execute("""
            SELECT c.case_id, c.status::text AS status, c.channel, c.note, c.email_thread_id,
                   c.created_at, c.updated_at, c.closed_at,
                   cu.customer_id, cu.name, cu.email, cu.phone, cu.address, cu.opted_out,
                   cu.created_at AS customer_since
            FROM cases c JOIN customers cu ON cu.customer_id = c.customer_id
            WHERE c.case_id = %s""", (case_id,)).fetchone()
        if case is None:
            raise HTTPException(404, f"Case #{case_id} does not exist.")
        bookings = conn.execute("""
            SELECT b.booking_id, b.service, b.address, b.problem, b.technician, b.active, b.reminded,
                   b.created_at, b.confirmation_sent_at, b.slack_posted_at, s.starts_at, s.ends_at
            FROM bookings b JOIN slots s ON s.slot_id = b.slot_id
            WHERE b.case_id = %s ORDER BY b.booking_id""", (case_id,)).fetchall()
        events = conn.execute("""
            SELECT event_id, from_status::text AS from_status, to_status::text AS to_status, reason, created_at
            FROM case_events WHERE case_id = %s ORDER BY event_id""", (case_id,)).fetchall()
        messages = conn.execute("""
            SELECT message_id, channel, direction, body, meta, created_at
            FROM messages WHERE case_id = %s AND meta->>'ignored' IS NULL
            ORDER BY created_at, message_id""", (case_id,)).fetchall()
        others = conn.execute("""
            SELECT case_id, status::text AS status, channel, created_at FROM cases
            WHERE customer_id = %s AND case_id <> %s ORDER BY case_id DESC""",
            (case["customer_id"], case_id)).fetchall()
    return {
        "case": {"case_id": case["case_id"], "status": case["status"], "channel": case["channel"],
                 "note": _hide(masked, privacy.text, case["note"]), "email_thread": bool(case["email_thread_id"]),
                 "created_at": _iso(case["created_at"]), "updated_at": _iso(case["updated_at"]),
                 "closed_at": _iso(case["closed_at"])},
        "customer": {"customer_id": case["customer_id"], **_person(masked, case["name"], case["email"], case["phone"]),
                     "address": _hide(masked, privacy.address, case["address"]), "opted_out": case["opted_out"],
                     "since": _iso(case["customer_since"])},
        "bookings": [{
            "booking_id": b["booking_id"], "service": b["service"],
            "address": _hide(masked, privacy.address, b["address"]),
            "problem": _hide(masked, privacy.text, b["problem"]), "technician": b["technician"], "active": b["active"],
            "reminded": b["reminded"], "created_at": _iso(b["created_at"]),
            "confirmation_sent_at": _iso(b["confirmation_sent_at"]), "slack_posted_at": _iso(b["slack_posted_at"]),
            "starts_at": _iso(b["starts_at"]), "ends_at": _iso(b["ends_at"]), "slot": format_slot(b["starts_at"]),
        } for b in bookings],
        "events": [{**e, "reason": _hide(masked, privacy.text, e["reason"]), "created_at": _iso(e["created_at"])}
                   for e in events],
        "messages": [{"message_id": m["message_id"], "channel": m["channel"], "direction": m["direction"],
                      "body": _hide(masked, privacy.text, (m["body"] or "")[:4000]),
                      "meta": _meta(m["meta"] or {}, masked),
                      "created_at": _iso(m["created_at"])} for m in messages],
        "other_cases": [{**o, "created_at": _iso(o["created_at"])} for o in others],
    }


@router.get("/activity")
def activity(limit: int = Query(40, ge=1, le=200), masked: bool = Depends(_access)) -> dict:
    """Status changes and emails, newest first. Chat turns are left out: they would drown the rest."""
    with get_pool().connection() as conn:
        events = conn.execute("""
            SELECT e.event_id, e.case_id, e.from_status::text AS from_status, e.to_status::text AS to_status,
                   e.reason, e.created_at, c.channel, cu.name, cu.email,
                   -- A move rewrites the booking row, so its time is only true for the latest booking event.
                   CASE WHEN e.event_id = (SELECT max(event_id) FROM case_events x
                                           WHERE x.case_id = e.case_id AND x.to_status = 'booked') THEN
                     (SELECT s.starts_at FROM bookings b JOIN slots s ON s.slot_id = b.slot_id
                       WHERE b.case_id = e.case_id ORDER BY b.active DESC, b.booking_id DESC LIMIT 1)
                   END AS starts_at
            FROM case_events e JOIN cases c ON c.case_id = e.case_id
            JOIN customers cu ON cu.customer_id = c.customer_id
            ORDER BY e.event_id DESC LIMIT %s""", (limit,)).fetchall()
        mails = conn.execute("""
            SELECT m.message_id, m.case_id, m.direction, m.meta, m.created_at, left(m.body, 160) AS preview,
                   cu.name, cu.email, c.channel
            FROM messages m JOIN cases c ON c.case_id = m.case_id
            JOIN customers cu ON cu.customer_id = c.customer_id
            WHERE m.channel = 'email' AND m.meta->>'ignored' IS NULL
            ORDER BY m.message_id DESC LIMIT %s""", (limit,)).fetchall()
    items = [{"kind": "event", "id": f"e{e['event_id']}", "case_id": e["case_id"], "at": _iso(e["created_at"]),
              "from_status": e["from_status"], "to_status": e["to_status"], "reason": e["reason"],
              "channel": e["channel"], "name": _hide(masked, privacy.name, e["name"]),
              "email": _hide(masked, privacy.email, e["email"]),
              "slot": format_slot(e["starts_at"]) if e["starts_at"] else None} for e in events]
    items += [{"kind": "email", "id": f"m{m['message_id']}", "case_id": m["case_id"], "at": _iso(m["created_at"]),
               "direction": m["direction"], "channel": m["channel"], "name": _hide(masked, privacy.name, m["name"]),
               "email": _hide(masked, privacy.email, m["email"]),
               "subject": _hide(masked, privacy.text, (m["meta"] or {}).get("subject")),
               "preview": _hide(masked, privacy.text, m["preview"])} for m in mails]
    for i in items:
        if i["kind"] == "event":
            i["reason"] = _hide(masked, privacy.text, i["reason"])
    items.sort(key=lambda i: i["at"], reverse=True)
    return {"items": items[:limit]}


@router.get("/schedule")
def schedule(days: int = Query(7, ge=1, le=21), masked: bool = Depends(_access)) -> dict:
    with get_pool().connection() as conn:
        rows = conn.execute("""
            SELECT s.slot_id, s.starts_at, s.ends_at, s.taken, b.case_id, b.service,
                   cu.name, c.status::text AS status
            FROM slots s
            LEFT JOIN bookings b ON b.slot_id = s.slot_id AND b.active
            LEFT JOIN cases c ON c.case_id = b.case_id
            LEFT JOIN customers cu ON cu.customer_id = c.customer_id
            WHERE s.starts_at >= %s AND s.starts_at < %s ORDER BY s.starts_at""",
            (_day_start(0), _day_start(days))).fetchall()
    return {"tz": get_settings().business_tz, "slots": [{
        "slot_id": r["slot_id"], "starts_at": _iso(r["starts_at"]), "ends_at": _iso(r["ends_at"]),
        "taken": r["taken"], "case_id": r["case_id"], "service": r["service"],
        "name": _hide(masked, privacy.name, r["name"]),
        "status": r["status"], "past": r["starts_at"] < business_now(),
    } for r in rows]}
