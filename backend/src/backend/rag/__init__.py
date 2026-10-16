"""Knowledge base: ingestion (ingest.py) and retrieval (retriever.py)."""

from backend.rag.retriever import search_kb, search_kb_multi
from backend.rag.schema import Passage

__all__ = ["Passage", "search_kb", "search_kb_multi"]
