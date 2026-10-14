"""FINAL CHECKS report for a chunk build.

Items 1-3 (counts, coverage, oversize) are computed in code from the validation
report. Items 4-5 (unclear chunks, 20 test questions) need judgement, so one LLM
call reviews all chunks at once.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from backend.config import get_settings
from backend.rag.schema import Chunk
from backend.rag.validation import ValidationReport


class UnclearChunk(BaseModel):
    id: str
    reason: str


class OversizeReason(BaseModel):
    id: str
    reason: str


class EvalQuestion(BaseModel):
    question: str = Field(description="A realistic question a customer would type")
    expected_ids: list[str] = Field(description="Chunk ID(s) that should answer it")


class ReviewResult(BaseModel):
    unclear_chunks: list[UnclearChunk]
    oversize_reasons: list[OversizeReason]
    eval_questions: list[EvalQuestion]


REVIEW_PROMPT = """You are reviewing chunks built for an HVAC business's customer-support RAG chatbot.

Tasks:
1. List any chunk that might be unclear on its own (vague references, missing subject,
   depends on another chunk to make sense). Give the ID and a one-line reason.
   Return an empty list if every chunk stands on its own.
2. For each of these oversize chunk IDs, explain in one line why it was not split
   (for example a single FAQ answer, price table or plan must stay intact): {oversize}
3. Write exactly 20 realistic customer questions, in the varied words customers use
   (typos and casual phrasing are fine), covering different categories: prices, plans,
   hours, emergencies, service areas, contact, services, brands, financing, policies,
   FAQs. For each, give the chunk ID(s) that should answer it. Use only IDs from the list.

CHUNKS (JSON lines: id, text):
{chunks}
"""


def review_chunks(chunks: list[Chunk], oversize_ids: list[str]) -> ReviewResult:
    s = get_settings()
    llm = ChatOpenAI(model=s.rag_report_model, temperature=0, api_key=s.openai_api_key)
    structured = llm.with_structured_output(ReviewResult, method="json_schema", strict=True)
    lines = "\n".join(json.dumps({"id": c.id, "text": c.text}, ensure_ascii=False) for c in chunks)
    result: ReviewResult = structured.invoke(
        REVIEW_PROMPT.format(oversize=oversize_ids or "none", chunks=lines)
    )
    valid = {c.id for c in chunks}
    for q in result.eval_questions:     # drop hallucinated IDs
        q.expected_ids = [i for i in q.expected_ids if i in valid]
    result.eval_questions = [q for q in result.eval_questions if q.expected_ids]
    return result


def write_report(
    path: Path,
    chunks: list[Chunk],
    validation: ValidationReport,
    review: ReviewResult | None,
) -> None:
    by_id = {c.id: c for c in chunks}
    out: list[str] = ["# Knowledge-base chunk report", ""]

    out += ["## 1. Chunks per category", "", "| Category | Chunks |", "|---|---|"]
    counts = Counter(c.metadata.category for c in chunks)
    out += [f"| {cat} | {n} |" for cat, n in sorted(counts.items())]
    out += [f"| **total** | **{len(chunks)}** |", ""]

    out += ["## 2. Coverage of source facts", ""]
    if not validation.errors:
        out.append("Every price, phone number, email, URL, license number, percentage, count "
                   "and FAQ question in the source documents appears in at least one chunk, "
                   "and no chunk contains a value that is not in its source document.")
    else:
        out += ["Problems:", ""] + [f"- {e}" for e in validation.errors]
    weak = [(d.source_doc, line, score) for d in validation.docs for line, score in d.weak_lines]
    if weak:
        out += ["", f"Source lines whose words are below {int(100 * 0.85)}% covered by any one "
                "chunk (usually rewording; review them):", ""]
        out += [f"- `{doc}` ({score:.0%}): {line}" for doc, line, score in weak]
    out.append("")

    out += ["## 3. Chunks over 450 tokens", ""]
    reasons = {r.id: r.reason for r in (review.oversize_reasons if review else [])}
    if validation.oversize:
        out += [f"- `{cid}` ({n} tokens): {reasons.get(cid, 'not reviewed')}"
                for cid, n in validation.oversize]
    else:
        out.append("None.")
    if validation.undersize:
        out += ["", "Chunks under 40 tokens (fine if the fact really is that short):", ""]
        out += [f"- `{cid}` ({n} tokens)" for cid, n in validation.undersize]
    out.append("")

    out += ["## 4. Chunks that may be unclear on their own", ""]
    if review is None:
        out.append("Not reviewed (run without --skip-report).")
    elif review.unclear_chunks:
        out += [f"- `{u.id}`: {u.reason}" for u in review.unclear_chunks]
    else:
        out.append("None.")
    out.append("")

    out += ["## 5. Retrieval test questions", ""]
    if review is None:
        out.append("Not generated.")
    else:
        out += ["| # | Question | Expected chunk(s) |", "|---|---|---|"]
        for i, q in enumerate(review.eval_questions, 1):
            ids = ", ".join(f"`{x}`" for x in q.expected_ids if x in by_id)
            out.append(f"| {i} | {q.question} | {ids} |")
    out.append("")
    path.write_text("\n".join(out), encoding="utf-8")
