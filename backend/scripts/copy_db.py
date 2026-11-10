"""Copy every row from one Postgres to another, e.g. the local database to Supabase.

    uv run python scripts/copy_db.py --to "postgresql://...supabase..."
    uv run python scripts/copy_db.py --from "postgresql://local..." --to "postgresql://..." --replace

--from defaults to DATABASE_URL in backend/.env. The target gets the app schema and the LangGraph
checkpoint tables first; then the app tables and chat memory are copied in one transaction and the
id sequences are moved past the copied ids. A target that already has cases is left alone unless
--replace is given (which empties it first).
"""

import argparse
import re
import sys

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from backend.config import get_settings
from backend.db.init_db import SCHEMA

# Parents before children (foreign keys); then LangGraph's chat memory.
APP_TABLES = ["customers", "cases", "case_events", "slots", "bookings", "messages", "slack_events"]
CHECKPOINT_TABLES = ["checkpoints", "checkpoint_blobs", "checkpoint_writes"]


def masked(url: str) -> str:
    return re.sub(r"://([^:/@]+):[^@]*@", r"://\1:***@", url)


def tables(conn) -> set[str]:
    rows = conn.execute("SELECT table_name FROM information_schema.tables "
                        "WHERE table_schema = 'public' AND table_type = 'BASE TABLE'").fetchall()
    return {r["table_name"] for r in rows}


def columns(conn, table: str) -> list[str]:
    rows = conn.execute("SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema = 'public' AND table_name = %s ORDER BY ordinal_position",
                        (table,)).fetchall()
    return [r["column_name"] for r in rows]


def prepare_target(url: str) -> None:
    """App schema + checkpoint tables (both idempotent)."""
    from langgraph.checkpoint.postgres import PostgresSaver

    with psycopg.connect(url, autocommit=True, prepare_threshold=None) as conn:
        conn.execute(SCHEMA.read_text(encoding="utf-8"))
        PostgresSaver(conn).setup()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--from", dest="src", default=get_settings().database_url, help="source (default: .env)")
    p.add_argument("--to", dest="dst", required=True, help="target database URL")
    p.add_argument("--replace", action="store_true", help="empty the target's tables first")
    a = p.parse_args(argv)
    if not a.src:
        sys.exit("No source: pass --from or set DATABASE_URL in backend/.env")
    if a.src == a.dst:
        sys.exit("--from and --to are the same database")

    print(f"from {masked(a.src)}\n  to {masked(a.dst)}")
    prepare_target(a.dst)

    with psycopg.connect(a.src, row_factory=dict_row) as src, \
         psycopg.connect(a.dst, row_factory=dict_row, prepare_threshold=None) as dst:
        have_src, have_dst = tables(src), tables(dst)
        todo = [t for t in APP_TABLES + CHECKPOINT_TABLES if t in have_src and t in have_dst]

        existing = dst.execute("SELECT count(*) AS n FROM cases").fetchone()["n"]
        if existing and not a.replace:
            sys.exit(f"The target already has {existing} cases. Nothing copied; pass --replace to overwrite.")

        # One transaction on the target: all of it lands, or none of it.
        dst.execute(sql.SQL("TRUNCATE {} RESTART IDENTITY CASCADE").format(
            sql.SQL(", ").join(sql.Identifier(t) for t in todo)))
        for t in todo:
            cols = [c for c in columns(src, t) if c in set(columns(dst, t))]
            col_list = sql.SQL(", ").join(sql.Identifier(c) for c in cols)
            with src.cursor().copy(sql.SQL("COPY {} ({}) TO STDOUT").format(sql.Identifier(t), col_list)) as out, \
                 dst.cursor().copy(sql.SQL("COPY {} ({}) FROM STDIN").format(sql.Identifier(t), col_list)) as inp:
                for block in out:
                    inp.write(block)
            n = dst.execute(sql.SQL("SELECT count(*) AS n FROM {}").format(sql.Identifier(t))).fetchone()["n"]
            # Move serial ids past the copied rows so new rows don't collide.
            for c in cols:
                seq = dst.execute("SELECT pg_get_serial_sequence(%s, %s) AS s", (t, c)).fetchone()["s"]
                if seq:
                    dst.execute(sql.SQL("SELECT setval(%s, coalesce(max({c}), 1), max({c}) IS NOT NULL) FROM {t}")
                                .format(c=sql.Identifier(c), t=sql.Identifier(t)), (seq,))
            print(f"  {t:<18} {n} rows")
        dst.commit()
    print("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
