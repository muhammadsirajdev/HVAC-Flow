"""Data models for knowledge-base documents, chunks and retrieval results."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field

Category = Literal[
    "overview", "contact", "hours", "service_area", "service", "product", "pricing",
    "plan", "faq", "policy", "booking", "brands", "trust", "blog", "other",
]
ServiceType = Literal["cooling", "heating", "air_quality", "ventilation", "general"]


@dataclass
class SourceDoc:
    """One Markdown file from the knowledge base, with its front-matter metadata."""

    source_doc: str              # path relative to the KB dir, e.g. "03_services/ac-repair.md"
    title: str
    doc_category: str
    source_urls: list[str]
    last_scraped: str
    body: str                    # Markdown without the front-matter block
    sha256: str                  # hash of the whole file, for re-chunk caching
    extra: dict = field(default_factory=dict)


# --- What the chunker LLM returns (structured output) ---------------------------

class LLMChunk(BaseModel):
    category: Category
    topic: str = Field(description="Specific topic, e.g. 'AC Repair Diagnostic Price'")
    text: str = Field(description="Context header line, newline, then the chunk content")
    service_type: ServiceType | None
    emergency: bool
    keywords: list[str] = Field(description="Customer search terms not already in the text")


class LLMChunkList(BaseModel):
    chunks: list[LLMChunk]


# --- Final chunk, as written to chunks.jsonl -----------------------------------

class ChunkMetadata(BaseModel):
    category: Category
    topic: str
    service_type: ServiceType | None
    emergency: bool
    source_doc: str
    source_urls: list[str]
    keywords: list[str]
    # added by the pipeline
    doc_title: str
    doc_category: str
    last_scraped: str
    token_count: int = 0


class Chunk(BaseModel):
    id: str
    text: str
    metadata: ChunkMetadata


# --- Retrieval result ------------------------------------------------------------

@dataclass
class Passage:
    id: str
    text: str
    score: float                 # cosine similarity, higher is better
    metadata: dict

    @property
    def source(self) -> str:
        return self.metadata.get("source_doc", "")
