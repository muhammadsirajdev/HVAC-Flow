"""Chroma persistent collection for knowledge-base chunks."""

from __future__ import annotations

import hashlib
from functools import lru_cache

import chromadb
from chromadb.api.models.Collection import Collection

from backend.config import get_settings
from backend.rag.schema import Chunk

LIST_SEP = " | "


@lru_cache
def get_client() -> chromadb.ClientAPI:
    s = get_settings()
    s.chroma_dir.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(s.chroma_dir))


def get_collection() -> Collection:
    s = get_settings()
    return get_client().get_or_create_collection(
        name=s.chroma_collection,
        metadata={"hnsw:space": "cosine", "embedding_model": s.rag_embedding_model},
    )


def content_hash(embed_text: str, model: str) -> str:
    """Changes when the embedded text or the embedding model changes."""
    return hashlib.sha256(f"{model}\n{embed_text}".encode("utf-8")).hexdigest()


def to_chroma_metadata(chunk: Chunk, chash: str) -> dict:
    """Chroma metadata values must be str/int/float/bool: lists are joined, None -> 'none'."""
    m = chunk.metadata
    return {
        "category": m.category,
        "topic": m.topic,
        "service_type": m.service_type or "none",
        "emergency": m.emergency,
        "source_doc": m.source_doc,
        "source_urls": LIST_SEP.join(m.source_urls),
        "keywords": LIST_SEP.join(m.keywords),
        "doc_title": m.doc_title,
        "doc_category": m.doc_category,
        "last_scraped": m.last_scraped,
        "token_count": m.token_count,
        "content_hash": chash,
    }


def from_chroma_metadata(meta: dict) -> dict:
    """Inverse of to_chroma_metadata for the fields that were flattened."""
    out = dict(meta)
    for key in ("source_urls", "keywords"):
        out[key] = [v for v in str(out.get(key, "")).split(LIST_SEP) if v]
    if out.get("service_type") == "none":
        out["service_type"] = None
    return out
