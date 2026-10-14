"""Retrieval eval: run the test questions and measure whether the right chunk comes back.

Usage (from backend/):
    uv run python -m backend.rag.evaluate            # build/eval_questions.json, k=4
    uv run python -m backend.rag.evaluate --k 6 --show-misses

Reports hit@1, hit@k and MRR, and suggests a KB_MIN_SCORE: off-topic questions
should score below it and real questions' best match above it.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys

from backend.config import get_settings
from backend.rag.retriever import search_kb

# Questions the KB should NOT answer; their best score sets the floor for the threshold.
OFF_TOPIC = [
    "What is the capital of France?",
    "Can you recommend a good pizza place near me?",
    "How do I reset my iPhone password?",
    "Who won the football world cup?",
    "Write me a poem about the ocean.",
]


def evaluate(k: int, show_misses: bool) -> int:
    s = get_settings()
    path = s.kb_build_dir / "eval_questions.json"
    if not path.exists():
        raise SystemExit(f"{path} not found: run `python -m backend.rag.ingest` first")
    questions = json.loads(path.read_text(encoding="utf-8"))

    hits1 = hitsk = 0
    rr, top_scores, misses = [], [], []
    for q in questions:
        passages = search_kb(q["question"], k=k, min_score=-1.0)
        ids = [p.id for p in passages]
        expected = set(q["expected_ids"])
        rank = next((i for i, cid in enumerate(ids, 1) if cid in expected), None)
        hits1 += rank == 1
        hitsk += rank is not None
        rr.append(1 / rank if rank else 0.0)
        top_scores.append(passages[0].score if passages else 0.0)
        if rank is None:
            misses.append((q["question"], q["expected_ids"], [(p.id, p.score) for p in passages]))

    off = [search_kb(q, k=1, min_score=-1.0) for q in OFF_TOPIC]
    off_scores = [p[0].score if p else 0.0 for p in off]

    n = len(questions)
    print(f"questions: {n}   k={k}   model={s.rag_embedding_model}")
    print(f"hit@1: {hits1}/{n} ({hits1 / n:.0%})")
    print(f"hit@{k}: {hitsk}/{n} ({hitsk / n:.0%})")
    print(f"MRR:   {statistics.mean(rr):.3f}")
    print(f"best-match score, real questions: min {min(top_scores):.3f}  "
          f"median {statistics.median(top_scores):.3f}")
    print(f"best-match score, off-topic:      max {max(off_scores):.3f}")
    lo, hi = max(off_scores), min(top_scores)
    if lo < hi:
        print(f"suggested KB_MIN_SCORE: {(lo + hi) / 2:.2f} (current {s.kb_min_score})")
    else:
        print(f"real and off-topic scores overlap; keep KB_MIN_SCORE near {lo:.2f} "
              f"(current {s.kb_min_score}) and rely on the prompt's 'answer only from passages'")

    if show_misses and misses:
        print("\nmisses:")
        for question, expected, got in misses:
            print(f"- {question}\n    expected {expected}\n    got      {got}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--k", type=int, default=get_settings().kb_top_k)
    p.add_argument("--show-misses", action="store_true")
    args = p.parse_args(argv)
    return evaluate(args.k, args.show_misses)


if __name__ == "__main__":
    sys.exit(main())
