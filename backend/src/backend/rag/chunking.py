"""LLM chunking: turn one SourceDoc into self-contained chunks.

The chunking rules live in prompts/chunker_system.md. Code then normalises what
the model returns (context header, IDs, document metadata) so those parts never
depend on the model.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from langchain_openai import ChatOpenAI

from backend.config import get_settings
from backend.rag.schema import Chunk, ChunkMetadata, LLMChunk, LLMChunkList, SourceDoc

PROMPTS = Path(__file__).parent / "prompts"
SYSTEM_PROMPT = (PROMPTS / "chunker_system.md").read_text(encoding="utf-8")
USER_TEMPLATE = (PROMPTS / "chunker_user.md").read_text(encoding="utf-8")
# Changing a prompt or the chunker model invalidates every cached chunk.
CHUNKER_VERSION = hashlib.sha256(
    f"{SYSTEM_PROMPT}\n{USER_TEMPLATE}\n{get_settings().rag_chunker_model}".encode("utf-8")
).hexdigest()[:16]


def make_header(business: str, category: str, topic: str) -> str:
    return f"[Business: {business} | Category: {category} | Topic: {topic}]"


def strip_header(text: str) -> str:
    """Remove a leading context-header line if the model wrote one."""
    text = text.strip()
    first, _, rest = text.partition("\n")
    if first.strip().startswith("[Business:"):
        return rest.strip()
    return text


def slugify(value: str, max_len: int = 48) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:max_len].rstrip("-") or "chunk"


def build_user_message(doc: SourceDoc, feedback: str = "") -> str:
    values = {
        "{feedback}": f"\nFEEDBACK ON YOUR PREVIOUS ATTEMPT\n{feedback}\n" if feedback else "",
        "{source_doc}": doc.source_doc,
        "{title}": doc.title,
        "{doc_category}": doc.doc_category,
        "{source_urls}": ", ".join(doc.source_urls),
        "{last_scraped}": doc.last_scraped,
        "{body}": doc.body,
    }
    msg = USER_TEMPLATE
    for key, val in values.items():   # plain replace: the body may contain braces
        msg = msg.replace(key, val)
    return msg


def get_chunker_llm() -> ChatOpenAI:
    s = get_settings()
    return ChatOpenAI(model=s.rag_chunker_model, temperature=0, api_key=s.openai_api_key)


def to_chunk(raw: LLMChunk, doc: SourceDoc, business: str) -> Chunk:
    """Attach document metadata and a canonical header. The ID is assigned later."""
    topic = raw.topic.strip()
    keywords = list(dict.fromkeys(k.strip() for k in raw.keywords if k.strip()))
    return Chunk(
        id="",
        text=f"{make_header(business, raw.category, topic)}\n{strip_header(raw.text)}",
        metadata=ChunkMetadata(
            category=raw.category,
            topic=topic,
            service_type=raw.service_type,
            emergency=raw.emergency,
            source_doc=doc.source_doc,
            source_urls=doc.source_urls,
            keywords=keywords,
            doc_title=doc.title,
            doc_category=doc.doc_category,
            last_scraped=doc.last_scraped,
        ),
    )


def chunk_document(doc: SourceDoc, llm: ChatOpenAI | None = None, feedback: str = "") -> list[Chunk]:
    """One LLM call: the chunks for a single document."""
    llm = llm or get_chunker_llm()
    structured = llm.with_structured_output(LLMChunkList, method="json_schema", strict=True)
    result: LLMChunkList = structured.invoke([
        ("system", SYSTEM_PROMPT),
        ("user", build_user_message(doc, feedback)),
    ])
    business = get_settings().business_name
    return [to_chunk(c, doc, business) for c in result.chunks if strip_header(c.text)]


def assign_ids(chunks: list[Chunk]) -> list[Chunk]:
    """IDs are '<category>_<topic-slug>_<n>', n counting repeats of the same pair.

    Deterministic for the same chunk list, so re-ingesting unchanged chunks keeps
    their IDs (and skips re-embedding).
    """
    seen: dict[str, int] = {}
    for chunk in chunks:
        base = f"{chunk.metadata.category}_{slugify(chunk.metadata.topic)}"
        seen[base] = seen.get(base, 0) + 1
        chunk.id = f"{base}_{seen[base]}"
    return chunks
