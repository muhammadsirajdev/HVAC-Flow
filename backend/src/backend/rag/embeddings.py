"""Embedding model client, shared by ingestion and retrieval.

Both sides must call get_embeddings() so documents and queries are embedded by
the same model (text-embedding-3-large, 3072 dimensions).
"""

from __future__ import annotations

from functools import lru_cache

from langchain_openai import OpenAIEmbeddings

from backend.config import get_settings
from backend.rag.schema import Chunk


@lru_cache
def get_embeddings() -> OpenAIEmbeddings:
    s = get_settings()
    return OpenAIEmbeddings(model=s.rag_embedding_model, api_key=s.openai_api_key)


def embedding_text(chunk: Chunk) -> str:
    """What gets embedded: header + content, plus the customer search keywords.

    The keywords are embedded (not shown to the LLM) so a query like "house is hot"
    can find the AC repair chunk even when those words are not in its text.
    """
    if not chunk.metadata.keywords:
        return chunk.text
    return f"{chunk.text}\nSearch terms: {', '.join(chunk.metadata.keywords)}"
