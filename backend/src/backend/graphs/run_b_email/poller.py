"""Run B: the inbox poll (plan section 6). Code-only steps around the conversation graph:

    fetch_new -> filter -> match_case -> verify_sender -> graph -> reply -> mark_handled

Every email the poll looks at is stored in `messages` by its Gmail ID, so it is read once: handled
ones with their case, ignored ones (auto-replies, mail not for the agent) with only the reason.
Read/unread is not used to find work (someone opening the inbox would hide an email); handled
emails are marked read for tidiness.

    uv run python -m backend.graphs.run_b_email.poller        # one poll by hand
"""

from __future__ import annotations

import logging

from langchain_core.messages import HumanMessage
from psycopg.types.json import Jsonb

from backend.config import get_settings
from backend.core.errors import MCPError
from backend.db.session import get_pool
from backend.graphs.run_a_chat.nodes import booking_from_state, booking_to_state
from backend.graphs.run_b_email import mail
from backend.mcp import email_mcp
from backend.mcp.email_mcp import Email
from backend.tools import cases, notify
from backend.tools.booking import load_booking, mark_notified, set_pending_change
from backend.tools.customers import find_customer, upsert_customer

log = logging.getLogger(__name__)
CLOSED = ("done", "closed", "cancelled")
_failures: dict[str, int] = {}          # message id -> AI failures in a row (model down)


def poll_once(graph=None) -> int:
    """One inbox check, oldest first, one turn per thread. Returns the number of emails handled."""
    s = get_settings()
    ids = email_mcp.search(s.email_poll_query, s.email_poll_max)
    new = set(ids) - _seen(ids)
    handled = 0
    for mid in ids:
        if mid not in new:
            continue
        batch = [e for e in email_mcp.read_thread(mid) if e.message_id in new]
        new -= {mid, *(e.message_id for e in batch)}
        try:
            handled += bool(batch) and handle(batch, graph)
        except Exception:
            log.exception("email thread %s failed; it is retried next poll", batch[-1].thread_id)
    return handled


def handle(batch: list[Email], graph=None) -> bool:
    """One customer turn: the new emails of one thread. True if answered or handed to a person."""
    s = get_settings()
    last = batch[-1]
    form = last.sender in {a.strip().lower() for a in s.email_form_senders.split(",") if a.strip()}
    if not form and mail.is_auto(last.sender, last.subject):
        return _ignore(batch, "auto-reply")
    text = "\n\n".join(t for t in (mail.strip_quoted(e.text) for e in batch) if t)
    if form:
        ident = mail.parse_form(last.text)
        text = ident["message"] or text
        if not ident["email"]:
            notify.post_alert(f":warning: A website form email could not be read (no valid customer email). "
                              f"Please handle it by hand. Subject: {last.subject}")
            _mark_read(batch)
            return _ignore(batch, "unreadable form email")
    else:
        ident = {"name": last.sender_name or None, "email": last.sender, "phone": None}

    # --- match_case (plan 6.3) ---
    with get_pool().connection() as conn:
        case = None if form else cases.find_by_thread(conn, last.thread_id)
        if case is None and not form and (ref := mail.case_ref(last.subject)):
            found = cases.get_case(conn, ref)
            if found and _customer(conn, found)["email"] == last.sender:
                case = found
        if case is None and not form and (s.email_agent_address or s.business_inbox).lower() not in last.to:
            # Not sent to the agent address: taken only from a customer with an open case (e.g. a chat booking).
            known = find_customer(conn, last.sender, None)
            case = known and cases.get_open_case(conn, known["customer_id"])
            if not case:
                return _ignore(batch, "not addressed to the agent")
        if case is None or case["status"] in CLOSED:
            # On an open case "ok, thanks" may be the yes to a summary, so only here is it skipped.
            if mail.is_thanks_only(text):
                _mark_read(batch)
                return _ignore(batch, "thanks only, no reply needed", case and case["case_id"])
            # A new request (also in the thread of a closed case): the sender's open case, or a new one.
            customer_id = upsert_customer(conn, ident["name"], ident["email"], ident["phone"], None)["customer_id"]
            case = cases.get_open_case(conn, customer_id)
            if case is None:
                case = cases.open_case(conn, customer_id, "email")
                if not form:
                    cases.set_email_thread(conn, case["case_id"], last.thread_id)
        customer = _customer(conn, case)
        case_id = case["case_id"]
        if case["status"] == "needs_person":
            _record(conn, batch, case_id)
        else:
            replies = conn.execute(
                "SELECT count(*) AS n FROM messages WHERE channel = 'email' AND direction = 'out' "
                "AND thread_key = %s AND created_at > now() - interval '1 hour'", (last.thread_id,)).fetchone()["n"]

    if case["status"] == "needs_person":        # the AI stays silent until the office hands it back
        notify.post_needs_person(case_id, "new email on a case waiting for a person",
                                 {"From": last.sender, "Email": text[:500]})
        _mark_read(batch)
        return True

    graph = graph or _graph()
    config = {"configurable": {"thread_id": f"email:{case_id}"}}
    out = graph.invoke({
        "messages": [HumanMessage(content=text)], "channel": "email", "letter": None,
        "session_id": f"Case #{case_id}, {last.sender}", "case_id": case_id,
        "customer_id": customer["customer_id"], "customer_email": customer["email"],
        "customer_name": customer["name"], "customer_phone": customer["phone"],
        # verify_sender (plan 6.5): the booking's own email address; never a form email
        "verified": not form and customer["email"] == last.sender,
        "needs_person": (f"over {s.max_ai_replies_per_thread_per_hour} AI replies in an hour"
                         if replies >= s.max_ai_replies_per_thread_per_hour else None),
        **_booking_state(graph, config, case_id),
    }, config)

    if out.get("fallback_form"):                # the AI failed: leave the email for the next poll
        n = _failures[last.message_id] = _failures.get(last.message_id, 0) + 1
        if n == 3:
            notify.post_alert(f":warning: The email agent's AI failed 3 times in a row on Case #{case_id} "
                              f"({last.sender}). It keeps retrying.")
        return False
    _failures.pop(last.message_id, None)

    # --- reply: to the sender only (form: the customer's parsed address), in the same thread ---
    name = (customer["name"] or "").split(" ")[0]
    body = out.get("letter") or notify.render("email/reply.txt.j2", name=name, text=out["reply"], case_id=case_id)
    if form:
        to, subject, thread = ident["email"], f"[Case #{case_id}] Your enquiry to {s.business_name}", None
    else:
        to, thread = last.sender, last.thread_id
        subject = last.subject if last.subject.lower().startswith("re:") else f"Re: {last.subject}"
    sent = _send(to, subject, body, thread, case_id)

    lb = out.get("last_booking")
    with get_pool().connection() as conn:
        _record(conn, batch, case_id)
        if sent:
            conn.execute("INSERT INTO messages (case_id, channel, direction, thread_key, provider_msg_id, body) "
                         "VALUES (%s, 'email', 'out', %s, %s, %s) ON CONFLICT DO NOTHING",
                         (case_id, sent.thread_id or last.thread_id, sent.message_id, body))
            if form and sent.thread_id:         # the customer's replies to us are matched (and verified)
                cases.set_email_thread(conn, case_id, sent.thread_id)
    _mark_read(batch)
    if lb and out.get("letter"):               # booked or changed: Slack only after the email went out
        if sent:
            mark_notified(lb["booking_id"], email=True)
        notify.post_booking(booking_from_state(lb))
    if out.get("booked") and lb:                # times offered for a change are recorded, not held
        set_pending_change(lb["booking_id"], [o["slot_id"] for o in out.get("offered_slots") or []])
    return True


def _booking_state(graph, config: dict, case_id: int) -> dict:
    """The booking as the database has it (the truth), unless the conversation already does."""
    prev = graph.get_state(config).values
    stored = load_booking(case_id)
    if stored is None:
        return {"booked": False, "last_booking": None, "booking": {}, "offered_slots": []} if prev.get("booked") else {}
    lb = prev.get("last_booking") or {}
    if (lb.get("booking_id"), lb.get("slot_label")) == (stored.result.booking_id, stored.result.slot_label):
        return {}
    r = stored.result.request
    return {"booked": True, "offered_slots": [], "chosen_slot": None, "awaiting_confirmation": False,
            "last_booking": {**booking_to_state(stored.result), "notified": True, "email_sent": not stored.email_pending},
            "booking": {k: v for k, v in dict(name=r.name, phone=r.phone, email=r.email, address=r.address,
                                              problem=r.problem, service=r.service).items() if v}}


def _send(to: str, subject: str, body: str, thread: str | None, case_id: int):
    """Send once, retry once; if both fail, a person replies by hand (the turn is not re-run)."""
    for attempt in (1, 2):
        try:
            return email_mcp.send_email(to, subject, body, thread_id=thread)
        except MCPError as exc:
            log.warning("reply for case %s, attempt %d failed: %s", case_id, attempt, exc)
    notify.post_alert(f":warning: The email reply for *Case #{case_id}* to {to} could not be sent. "
                      f"Please reply by hand:\n> {body[:1500]}")
    return None


def _customer(conn, case: dict) -> dict:
    return conn.execute("SELECT customer_id, name, lower(email) AS email, phone FROM customers "
                        "WHERE customer_id = %s", (case["customer_id"],)).fetchone()


def _seen(ids: list[str]) -> set[str]:
    if not ids:
        return set()
    with get_pool().connection() as conn:
        rows = conn.execute("SELECT provider_msg_id FROM messages WHERE channel = 'email' "
                            "AND provider_msg_id = ANY(%s)", (ids,)).fetchall()
    return {r["provider_msg_id"] for r in rows}


def _record(conn, batch: list[Email], case_id: int | None, ignored: str | None = None) -> None:
    """Store inbound emails by Gmail ID. Ignored ones keep no content, only the reason."""
    for e in batch:
        conn.execute(
            "INSERT INTO messages (case_id, channel, direction, thread_key, provider_msg_id, body, meta) "
            "VALUES (%s, 'email', 'in', %s, %s, %s, %s) ON CONFLICT DO NOTHING",
            (case_id, e.thread_id, e.message_id, None if ignored else mail.strip_quoted(e.text),
             Jsonb({"ignored": ignored} if ignored else {"from": e.sender, "subject": e.subject})))


def _ignore(batch: list[Email], reason: str, case_id: int | None = None) -> bool:
    with get_pool().connection() as conn:
        _record(conn, batch, case_id, ignored=reason)
    log.info("email %s ignored: %s", batch[-1].message_id, reason)
    return False


def _mark_read(batch: list[Email]) -> None:
    for e in batch:
        try:
            email_mcp.mark_read(e.message_id)
        except MCPError:
            log.warning("could not mark email %s read", e.message_id)


def _graph():
    from backend.graphs.run_b_email.graph import get_graph
    return get_graph()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    print(f"handled {poll_once()} email(s)")
