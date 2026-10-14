"""GET /health: app and database liveness."""

from fastapi import APIRouter

from backend.db.session import get_pool

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    try:
        with get_pool().connection() as conn:
            conn.execute("SELECT 1")
        db = "ok"
    except Exception as exc:
        db = f"error: {exc.__class__.__name__}"
    return {"status": "ok" if db == "ok" else "degraded", "database": db}
