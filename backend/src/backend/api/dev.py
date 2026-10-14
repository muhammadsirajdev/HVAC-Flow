"""Test console (GET /) and its read-only data endpoints. Enabled by DEV_UI=true.

    /            the test console page (chat + workflow + database panels)
    /dev/status  what is connected: LLM, knowledge base, database, Gmail/Slack MCP
    /dev/overview recent cases, bookings, events and open slots
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from backend.config import get_settings
from backend.core.timeutil import format_slot
from backend.db.session import get_pool

router = APIRouter(tags=["dev"])
PAGE = Path(__file__).resolve().parents[1] / "static" / "test_console.html"


def _enabled() -> None:
    if not get_settings().dev_ui:
        raise HTTPException(404)


@router.get("/", include_in_schema=False)
def console() -> FileResponse:
    _enabled()
    return FileResponse(PAGE, media_type="text/html")


def _check(fn) -> dict:
    try:
        return {"ok": True, "detail": fn()}
    except Exception as exc:
        return {"ok": False, "detail": f"{exc.__class__.__name__}: {exc}"[:300]}


@router.get("/dev/status")
def status() -> dict:
    _enabled()
    s = get_settings()

    def llm():
        pkg = "langchain_openai" if s.llm_provider == "openai" else "langchain_groq"
        if importlib.util.find_spec(pkg) is None:
            raise RuntimeError(f"{pkg} not installed")
        key = s.openai_api_key if s.llm_provider == "openai" else s.groq_api_key
        if not key:
            raise RuntimeError(f"{s.llm_provider.upper()}_API_KEY missing")
        return f"{s.llm_provider} / {s.llm_model}"

    def kb():
        if importlib.util.find_spec("chromadb") is None:
            raise RuntimeError("chromadb not installed")
        from backend.rag.vectorstore import get_collection
        n = get_collection().count()
        if n == 0:
            raise RuntimeError("Chroma collection is empty: run python -m backend.rag.ingest")
        return f"{n} chunks in '{s.chroma_collection}' ({s.rag_embedding_model})"

    def db():
        with get_pool().connection() as conn:
            n = conn.execute("SELECT count(*) AS n FROM slots WHERE NOT taken AND starts_at > now()").fetchone()["n"]
        if n == 0:
            raise RuntimeError("no open slots: run python scripts/seed_demo_client.py")
        return f"connected, {n} open future slots"

    def mcp():
        from backend.mcp.client import get_tools
        names = sorted(t.name for t in get_tools())
        if not names:
            raise RuntimeError("no MCP tools loaded")
        return ", ".join(names)

    def slack():
        from backend.mcp.slack_mcp import resolve_channel
        bookings = s.slack_bookings_channel or s.slack_urgent_channel
        return (f"bookings: #{bookings.lstrip('#')} ({resolve_channel(bookings)}), "
                f"urgent: #{s.slack_urgent_channel.lstrip('#')}")

    return {"llm": _check(llm), "knowledge_base": _check(kb), "database": _check(db),
            "mcp_tools": _check(mcp), "slack_channel": _check(slack)}


@router.get("/dev/overview")
def overview() -> dict:
    _enabled()
    with get_pool().connection() as conn:
        cases = conn.execute("""
            SELECT c.case_id, c.status, c.channel, c.email_thread_id, c.note, c.created_at,
                   cu.name, cu.email, cu.phone,
                   b.service, b.address, s.starts_at, b.booking_id,
                   b.confirmation_sent_at IS NOT NULL AS email_sent, b.slack_posted_at IS NOT NULL AS slack_posted
            FROM cases c
            JOIN customers cu USING (customer_id)
            LEFT JOIN bookings b ON b.case_id = c.case_id AND b.active
            LEFT JOIN slots s ON s.slot_id = b.slot_id
            ORDER BY c.case_id DESC LIMIT 10""").fetchall()
        events = conn.execute("""
            SELECT case_id, from_status, to_status, reason, created_at
            FROM case_events ORDER BY event_id DESC LIMIT 12""").fetchall()
        slots = conn.execute("""
            SELECT slot_id, starts_at FROM slots
            WHERE NOT taken AND starts_at > now() ORDER BY starts_at LIMIT 8""").fetchall()
        counts = conn.execute("""
            SELECT (SELECT count(*) FROM slots WHERE NOT taken AND starts_at > now()) AS open_slots,
                   (SELECT count(*) FROM bookings WHERE active) AS active_bookings,
                   (SELECT count(*) FROM cases) AS cases""").fetchone()
    for c in cases:
        c["slot"] = format_slot(c.pop("starts_at")) if c.get("starts_at") else None
        c["created_at"] = c["created_at"].isoformat()
    for e in events:
        e["created_at"] = e["created_at"].isoformat()
    return {"counts": counts, "cases": cases, "events": events,
            "next_slots": [{"slot_id": s["slot_id"], "label": format_slot(s["starts_at"])} for s in slots]}
