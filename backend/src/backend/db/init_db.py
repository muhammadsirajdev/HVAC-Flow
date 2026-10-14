"""Create the app tables and the LangGraph checkpoint tables.

    uv run python -m backend.db.init_db
"""

from pathlib import Path

from backend.db.session import get_pool
from backend.graphs.common.checkpointer import setup_checkpointer

SCHEMA = Path(__file__).with_name("schema.sql")


def init_db() -> None:
    with get_pool().connection() as conn:
        conn.execute(SCHEMA.read_text(encoding="utf-8"))
    setup_checkpointer()


if __name__ == "__main__":
    init_db()
    print("database ready")
