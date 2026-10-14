"""Load knowledge-base Markdown files and extract their front-matter metadata."""

from __future__ import annotations

import hashlib
from pathlib import Path

import yaml

from backend.rag.schema import SourceDoc

# Folders under the KB dir that are not customer-facing content.
SKIP_DIRS = {"_meta", "build"}


def parse_front_matter(raw: str) -> tuple[dict, str]:
    """Split a '---' YAML front-matter block from the Markdown body."""
    if not raw.startswith("---"):
        return {}, raw
    end = raw.find("\n---", 3)
    if end == -1:
        return {}, raw
    meta = yaml.safe_load(raw[3:end]) or {}
    body = raw[end + 4:].lstrip("\n")
    return meta, body


def load_document(path: Path, kb_dir: Path) -> SourceDoc:
    raw_bytes = path.read_bytes()
    meta, body = parse_front_matter(raw_bytes.decode("utf-8"))
    urls = meta.get("source_urls") or []
    if isinstance(urls, str):
        urls = [u.strip() for u in urls.strip("[]").split(",") if u.strip()]
    known = {"title", "category", "source_urls", "last_scraped"}
    return SourceDoc(
        source_doc=path.relative_to(kb_dir).as_posix(),
        title=str(meta.get("title", path.stem)),
        doc_category=str(meta.get("category", "other")),
        source_urls=[str(u) for u in urls],
        last_scraped=str(meta.get("last_scraped", "")),
        body=body,
        sha256=hashlib.sha256(raw_bytes).hexdigest(),
        extra={k: v for k, v in meta.items() if k not in known},
    )


def load_documents(kb_dir: Path) -> list[SourceDoc]:
    """All customer-facing .md files under kb_dir, in a stable order."""
    paths = sorted(
        p for p in kb_dir.rglob("*.md")
        if not SKIP_DIRS.intersection(p.relative_to(kb_dir).parts)
    )
    return [load_document(p, kb_dir) for p in paths]
