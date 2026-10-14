"""Knowledge base: ingestion (ingest.py) and retrieval (retriever.py)."""

from backend.rag.retriever import format_passages, search_kb, search_kb_multi
from backend.rag.schema import Passage

__all__ = ["Passage", "format_passages", "search_kb", "search_kb_multi"]
