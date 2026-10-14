"""LangGraph checkpointer: Postgres when DATABASE_URL is set, in-memory otherwise."""

from __future__ import annotations

import logging
from functools import lru_cache

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver

from backend.config import get_settings

log = logging.getLogger(__name__)


@lru_cache
def get_checkpointer() -> BaseCheckpointSaver:
    url = get_settings().database_url
    if not url:
        log.warning("DATABASE_URL not set: chat memory is in-process only")
        return InMemorySaver()
    from langgraph.checkpoint.postgres import PostgresSaver
    from psycopg.rows import dict_row
    from psycopg_pool import ConnectionPool

    pool = ConnectionPool(url, min_size=1, max_size=5, open=True,
                          kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row})
    return PostgresSaver(pool)


def setup_checkpointer() -> None:
    """Create the checkpoint tables (run once; init_db calls it)."""
    saver = get_checkpointer()
    if hasattr(saver, "setup"):
        saver.setup()
