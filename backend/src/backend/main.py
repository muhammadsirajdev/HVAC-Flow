"""FastAPI app: mounts routers. The scheduler (Runs B and D) is added later.

    uv run uvicorn backend.main:app --reload
"""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api import chat, dev, health
from backend.config import get_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")

app = FastAPI(title="Speed-to-Lead", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in get_settings().widget_allowed_origins.split(",") if o.strip()],
    allow_methods=["POST", "GET"],
    allow_headers=["Content-Type"],
)
app.include_router(health.router)
app.include_router(chat.router)
if get_settings().dev_ui:
    app.include_router(dev.router)      # test console at http://localhost:8000/
