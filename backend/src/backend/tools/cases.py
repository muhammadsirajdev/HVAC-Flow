"""Case lifecycle. Every status write goes through transition(); the model never sets status."""

from psycopg import Connection

from backend.core.errors import InvalidTransition

OPEN_STATUSES = ("open", "booked", "needs_person")

# from -> allowed targets (plan section 4). needs_person can go anywhere: a person decides.
ALLOWED = {
    None: {"open", "needs_person"},
    "open": {"booked", "needs_person", "cancelled"},
    "booked": {"booked", "done", "cancelled", "needs_person"},
    "done": {"closed", "needs_person"},
    "needs_person": {"open", "booked", "done", "closed", "cancelled"},
    "closed": set(),
    "cancelled": set(),
}


def transition(conn: Connection, case_id: int, to: str, reason: str) -> None:
    row = conn.execute("SELECT status FROM cases WHERE case_id = %s FOR UPDATE", (case_id,)).fetchone()
    if row is None:
        raise InvalidTransition(f"case {case_id} does not exist")
    current = row["status"]
    if to not in ALLOWED.get(current, set()):
        raise InvalidTransition(f"case {case_id}: {current} -> {to} not allowed")
    conn.execute(
        "UPDATE cases SET status = %s, updated_at = now(), "
        "closed_at = CASE WHEN %s IN ('closed','cancelled') THEN now() ELSE closed_at END "
        "WHERE case_id = %s",
        (to, to, case_id),
    )
    conn.execute(
        "INSERT INTO case_events (case_id, from_status, to_status, reason) VALUES (%s, %s, %s, %s)",
        (case_id, current, to, reason),
    )


def get_open_case(conn: Connection, customer_id: int) -> dict | None:
    return conn.execute(
        "SELECT * FROM cases WHERE customer_id = %s AND status = ANY(%s) FOR UPDATE",
        (customer_id, list(OPEN_STATUSES)),
    ).fetchone()


def open_case(conn: Connection, customer_id: int, channel: str, status: str = "open",
              note: str | None = None) -> dict:
    """The customer's open case, or a new one (one open case per customer)."""
    existing = get_open_case(conn, customer_id)
    if existing:
        return existing
    case = conn.execute(
        "INSERT INTO cases (customer_id, status, channel, note) VALUES (%s, %s, %s, %s) RETURNING *",
        (customer_id, status, channel, note),
    ).fetchone()
    conn.execute(
        "INSERT INTO case_events (case_id, from_status, to_status, reason) VALUES (%s, NULL, %s, %s)",
        (case["case_id"], status, f"opened via {channel}"),
    )
    return case


def set_email_thread(conn: Connection, case_id: int, thread_id: str) -> None:
    conn.execute(
        "UPDATE cases SET email_thread_id = %s, updated_at = now() WHERE case_id = %s",
        (thread_id, case_id),
    )
