"""Retrieval: embed the query with the ingestion model and search Chroma.

    from backend.rag import search_kb, search_kb_multi, format_passages
    passages = search_kb("how much is the AC diagnostic?")
    passages = search_kb_multi(["Elite plan diagnostic", "after-hours charges"])  # multi-part question
    if not passages:   # nothing close enough -> the agent says it does not know
        ...
    context = format_passages(passages)

Selection (both functions):
  1. take the best `k * CANDIDATE_FACTOR` candidates by cosine similarity,
  2. drop those below KB_MIN_SCORE,
  3. keep at most KB_MAX_PER_SOURCE chunks from one source file, so near-duplicate
     chunks (a FAQ and the service page saying the same thing) cannot fill every slot.
"""

from __future__ import annotations

from backend.config import get_settings
from backend.rag.embeddings import get_embeddings
from backend.rag.schema import Passage
from backend.rag.vectorstore import from_chroma_metadata, get_collection

CANDIDATE_FACTOR = 3


def _query(vector: list[float], n: int, where: dict | None) -> list[Passage]:
    collection = get_collection()
    count = collection.count()
    if count == 0:
        raise RuntimeError("Knowledge base is empty: run `python -m backend.rag.ingest` first")
    res = collection.query(query_embeddings=[vector], n_results=min(n, count), where=where,
                           include=["documents", "metadatas", "distances"])
    return [
        Passage(id=i, text=doc, score=round(1.0 - dist, 4), metadata=from_chroma_metadata(meta))
        for i, doc, meta, dist in zip(res["ids"][0], res["documents"][0], res["metadatas"][0],
                                      res["distances"][0])
    ]


def _diversify(ranked: list[Passage], k: int, max_per_source: int) -> list[Passage]:
    picked, per_source = [], {}
    for p in ranked:
        if per_source.get(p.source, 0) >= max_per_source:
            continue
        picked.append(p)
        per_source[p.source] = per_source.get(p.source, 0) + 1
        if len(picked) == k:
            break
    return picked


def search_kb_multi(
    queries: list[str],
    k: int | None = None,
    min_score: float | None = None,
    where: dict | None = None,
    max_per_source: int | None = None,
) -> list[Passage]:
    """Passages for one or more queries (sub-questions of one customer message), best first.

    Each query's best passage is guaranteed a slot, so a multi-part question
    ("new AC in Key Largo, can I pay monthly?") gets context for every part.
    Returns [] when nothing passes the threshold.
    """
    s = get_settings()
    k = k or s.kb_top_k
    min_score = s.kb_min_score if min_score is None else min_score
    max_per_source = max_per_source or s.kb_max_per_source
    queries = list(dict.fromkeys(q.strip() for q in queries if q and q.strip()))[:3]
    if not queries:
        return []

    vectors = get_embeddings().embed_documents(queries) if len(queries) > 1 else \
        [get_embeddings().embed_query(queries[0])]
    per_query = [[p for p in _query(v, k * CANDIDATE_FACTOR, where) if p.score >= min_score]
                 for v in vectors]

    # Best score per chunk across queries.
    best: dict[str, Passage] = {}
    for results in per_query:
        for p in results:
            if p.id not in best or p.score > best[p.id].score:
                best[p.id] = p
    ranked = sorted(best.values(), key=lambda p: p.score, reverse=True)

    # Seed with each query's top passage, then fill by score with the per-source cap.
    seeds = [results[0] for results in per_query if results]
    seeds = list({p.id: best[p.id] for p in seeds}.values())
    rest = [p for p in ranked if p.id not in {s.id for s in seeds}]
    picked = _diversify(seeds + rest, k, max_per_source)
    return sorted(picked, key=lambda p: p.score, reverse=True)


def search_kb(
    query: str,
    k: int | None = None,
    min_score: float | None = None,
    where: dict | None = None,
    max_per_source: int | None = None,
) -> list[Passage]:
    """Top-k passages for one query with cosine similarity >= min_score, best first.

    where: optional Chroma metadata filter, e.g. {"category": "pricing"}.
    Returns [] when nothing passes the threshold.
    """
    return search_kb_multi([query], k=k, min_score=min_score, where=where, max_per_source=max_per_source)


def format_passages(passages: list[Passage]) -> str:
    """Context block for the agent prompt; IDs let the answer be traced to a source."""
    if not passages:
        return "NO_RELEVANT_PASSAGES"
    return "\n\n".join(f"<passage id=\"{p.id}\" score=\"{p.score:.2f}\">\n{p.text}\n</passage>"
                       for p in passages)
