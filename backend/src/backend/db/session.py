"""Postgres connection pool (psycopg 3)."""

from functools import lru_cache

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from backend.config import get_settings


@lru_cache
def get_pool() -> ConnectionPool:
    """App pool. `with get_pool().connection() as conn:` commits on success, rolls back on error."""
    url = get_settings().database_url
    if not url:
        raise RuntimeError("DATABASE_URL is not set (backend/.env)")
    return ConnectionPool(url, min_size=1, max_size=10, kwargs={"row_factory": dict_row}, open=True)
