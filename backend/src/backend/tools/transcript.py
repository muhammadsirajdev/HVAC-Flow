"""Website chat turns stored in `messages`, so the office view can show the conversation.

The LangGraph checkpoint keeps the chat for the agent; this is the readable copy for people.
A chat usually gets its case only when the visitor books or is handed to a person, so earlier
turns are stored without a case and linked when the case appears.
"""

from __future__ import annotations

from psycopg.types.json import Jsonb

from backend.db.session import get_pool


def record_chat_turn(session_id: str, text: str, reply: str, case_id: int | None, meta: dict) -> None:
    with get_pool().connection() as conn:
        conn.execute(
            "INSERT INTO messages (case_id, channel, direction, thread_key, body) VALUES (%s, 'web', 'in', %s, %s)",
            (case_id, session_id, text))
        conn.execute(
            "INSERT INTO messages (case_id, channel, direction, thread_key, body, meta) "
            "VALUES (%s, 'web', 'out', %s, %s, %s)",
            (case_id, session_id, reply, Jsonb(meta)))
        if case_id is not None:
            conn.execute("UPDATE messages SET case_id = %s WHERE channel = 'web' AND thread_key = %s "
                         "AND case_id IS NULL", (case_id, session_id))
