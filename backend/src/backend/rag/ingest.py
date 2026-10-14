"""Ingestion pipeline: knowledge/*.md -> metadata -> LLM chunks -> checks -> embed -> Chroma.

Usage (from backend/):
    uv run python -m backend.rag.ingest                # chunk changed docs, embed changed chunks
    uv run python -m backend.rag.ingest --rechunk      # re-chunk every document
    uv run python -m backend.rag.ingest --chunk-only   # build chunks.jsonl + report, no embedding
    uv run python -m backend.rag.ingest --embed-only   # embed the existing chunks.jsonl as is

Outputs in knowledge/mdcold/build/ (commit these, they are reviewable):
    chunks.jsonl         one chunk per line, the schema from prompts/chunker_system.md
    manifest.json        source hashes, so unchanged documents are not re-chunked
    report.md            the FINAL CHECKS report
    eval_questions.json  20 test questions with expected chunk IDs (for rag.evaluate)
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from backend.config import get_settings
from backend.rag.chunking import CHUNKER_VERSION, assign_ids, chunk_document, get_chunker_llm
from backend.rag.embeddings import embedding_text, get_embeddings
from backend.rag.loader import load_documents
from backend.rag.report import review_chunks, write_report
from backend.rag.schema import Chunk, SourceDoc
from backend.rag.validation import check_document, validate
from backend.rag.vectorstore import content_hash, get_collection, to_chroma_metadata

log = logging.getLogger("rag.ingest")

MAX_ATTEMPTS = 3          # first try + 2 retries with feedback when facts are missing
EMBED_BATCH = 64


# --- build files ---------------------------------------------------------------

def _paths(build_dir: Path) -> dict[str, Path]:
    return {
        "chunks": build_dir / "chunks.jsonl",
        "manifest": build_dir / "manifest.json",
        "report": build_dir / "report.md",
        "eval": build_dir / "eval_questions.json",
    }


def read_chunks(path: Path) -> list[Chunk]:
    if not path.exists():
        return []
    return [Chunk.model_validate_json(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def write_chunks(path: Path, chunks: list[Chunk]) -> None:
    path.write_text(
        "".join(c.model_dump_json() + "\n" for c in chunks), encoding="utf-8"
    )


def read_manifest(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


# --- chunking --------------------------------------------------------------------

def chunk_with_checks(doc: SourceDoc, llm) -> list[Chunk]:
    """Chunk one document; if facts are missing or invented, retry with feedback."""
    feedback, best, best_problems = "", [], None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        chunks = chunk_document(doc, llm, feedback)
        check = check_document(doc, chunks)
        problems = len(check.missing_facts) + len(check.invented_facts) + len(check.missing_questions)
        if best_problems is None or problems < best_problems:
            best, best_problems = chunks, problems
        if check.ok:
            log.info("chunked %-40s %3d chunks (attempt %d)", doc.source_doc, len(chunks), attempt)
            return chunks
        log.warning("%s attempt %d: %s", doc.source_doc, attempt, check.feedback().replace("\n", " "))
        feedback = check.feedback()
    log.error("%s: kept best attempt with %d problems; see report.md", doc.source_doc, best_problems)
    return best


def build_chunks(docs: list[SourceDoc], cached: list[Chunk], manifest: dict, rechunk: bool,
                 workers: int = 4) -> tuple[list[Chunk], dict, int]:
    by_doc: dict[str, list[Chunk]] = {}
    for c in cached:
        by_doc.setdefault(c.metadata.source_doc, []).append(c)

    old = manifest.get("documents", {})
    same_chunker = manifest.get("chunker_version") == CHUNKER_VERSION
    todo = [d for d in docs
            if rechunk or not same_chunker or old.get(d.source_doc) != d.sha256 or d.source_doc not in by_doc]
    log.info("%d documents, %d to chunk, %d cached", len(docs), len(todo), len(docs) - len(todo))

    if todo:
        llm = get_chunker_llm()
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for doc, chunks in zip(todo, pool.map(lambda d: chunk_with_checks(d, llm), todo)):
                by_doc[doc.source_doc] = chunks

    ordered = [c for d in docs for c in by_doc.get(d.source_doc, [])]   # drops deleted docs
    new_manifest = {
        "chunker_version": CHUNKER_VERSION,
        "chunker_model": get_settings().rag_chunker_model,
        "documents": {d.source_doc: d.sha256 for d in docs},
    }
    return assign_ids(ordered), new_manifest, len(todo)


# --- embedding + Chroma --------------------------------------------------------

def sync_chroma(chunks: list[Chunk]) -> dict[str, int]:
    """Upsert new/changed chunks, delete chunks that no longer exist. Idempotent."""
    s = get_settings()
    collection = get_collection()
    stored_model = (collection.metadata or {}).get("embedding_model")
    if stored_model and stored_model != s.rag_embedding_model:
        raise SystemExit(
            f"Collection '{s.chroma_collection}' was embedded with {stored_model}, settings say "
            f"{s.rag_embedding_model}. Delete {s.chroma_dir} or use a new collection name."
        )

    existing = collection.get(include=["metadatas"])
    have = {i: (m or {}).get("content_hash") for i, m in zip(existing["ids"], existing["metadatas"])}

    texts = {c.id: embedding_text(c) for c in chunks}
    hashes = {cid: content_hash(t, s.rag_embedding_model) for cid, t in texts.items()}
    changed = [c for c in chunks if have.get(c.id) != hashes[c.id]]
    stale = sorted(set(have) - set(texts))

    embedder = get_embeddings()
    for start in range(0, len(changed), EMBED_BATCH):
        batch = changed[start:start + EMBED_BATCH]
        vectors = embedder.embed_documents([texts[c.id] for c in batch])
        collection.upsert(
            ids=[c.id for c in batch],
            embeddings=vectors,
            documents=[c.text for c in batch],
            metadatas=[to_chroma_metadata(c, hashes[c.id]) for c in batch],
        )
        log.info("embedded %d/%d", start + len(batch), len(changed))
    if stale:
        collection.delete(ids=stale)

    return {"embedded": len(changed), "unchanged": len(chunks) - len(changed),
            "deleted": len(stale), "total": collection.count()}


# --- entry point -------------------------------------------------------------------

def run(rechunk: bool = False, chunk_only: bool = False, embed_only: bool = False,
        skip_report: bool = False, force: bool = False) -> int:
    s = get_settings()
    if not s.openai_api_key:
        raise SystemExit("OPENAI_API_KEY is not set (backend/.env)")
    s.kb_build_dir.mkdir(parents=True, exist_ok=True)
    paths = _paths(s.kb_build_dir)

    docs = load_documents(s.kb_dir)
    if embed_only:
        chunks, changed_docs = read_chunks(paths["chunks"]), 0
        if not chunks:
            raise SystemExit(f"No chunks at {paths['chunks']}; run without --embed-only first")
        manifest = read_manifest(paths["manifest"])
    else:
        chunks, manifest, changed_docs = build_chunks(
            docs, read_chunks(paths["chunks"]), read_manifest(paths["manifest"]), rechunk)

    validation = validate(docs, chunks, s.business_name)
    write_chunks(paths["chunks"], chunks)
    paths["manifest"].write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    review = None
    if not skip_report and (changed_docs or not paths["eval"].exists()):
        log.info("reviewing chunks and writing test questions")
        review = review_chunks(chunks, [cid for cid, _ in validation.oversize])
        paths["eval"].write_text(
            json.dumps([q.model_dump() for q in review.eval_questions], indent=2, ensure_ascii=False),
            encoding="utf-8")
    if review is not None or not paths["report"].exists() or changed_docs:
        write_report(paths["report"], chunks, validation, review)

    log.info("%d chunks written to %s", len(chunks), paths["chunks"])
    for err in validation.errors:
        log.error("check failed: %s", err)

    if chunk_only:
        return 0
    if validation.errors and not force:
        log.error("Not embedding: fix the problems above (or review them and pass --force).")
        return 1
    stats = sync_chroma(chunks)
    log.info("chroma '%s': %s", s.chroma_collection, stats)
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--rechunk", action="store_true", help="re-chunk every document")
    p.add_argument("--chunk-only", action="store_true", help="stop before embedding")
    p.add_argument("--embed-only", action="store_true", help="embed the existing chunks.jsonl")
    p.add_argument("--skip-report", action="store_true", help="skip the LLM review step")
    p.add_argument("--force", action="store_true", help="embed even if checks failed")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")
    for noisy in ("httpx", "openai", "chromadb"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    return run(args.rechunk, args.chunk_only, args.embed_only, args.skip_report, args.force)


if __name__ == "__main__":
    sys.exit(main())
