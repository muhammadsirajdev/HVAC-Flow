"""Code-side checks on chunks: nothing missing, nothing invented, sizes in range.

These run without any LLM. The chunker is asked to copy facts exactly, and these
checks catch the cases where it did not.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache

import tiktoken

from backend.rag.schema import Chunk, SourceDoc

MAX_TOKENS = 450          # report anything above this (target is 150-400)
MIN_TOKENS = 40           # report suspiciously tiny chunks
LINE_COVERAGE_MIN = 0.85  # share of a source line's words that must appear in one chunk

FACT_PATTERNS = {
    "url": r"https?://[^\s)\]>\"'|]+",
    "email": r"[\w.+-]+@[\w-]+\.[\w.]+",
    "phone": r"\(\d{3}\)\s?\d{3}-\d{4}",
    "money": r"\$\s?\d[\d,]*(?:\.\d+)?",
    "percent": r"\d+(?:\.\d+)?\s?%",
    "license": r"\bCAC\d+\b",
    "number": r"(?<![\w$#])\d[\d,]*(?:\.\d+)?\+?(?![\w%])",
}
STOPWORDS = set(
    "a an the and or of to in on for with by at from is are be as it its this that "
    "these those not no yes if than then so can may will do does any all each per "
    "md cold services website page stated".split()
)


@lru_cache
def _encoder():
    # text-embedding-3-* models use cl100k_base
    return tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    return len(_encoder().encode(text))


def extract_facts(text: str) -> set[str]:
    """Exact-copy facts: URLs, emails, phones, prices, percentages, license numbers, numbers."""
    facts: set[str] = set()
    for kind, pattern in FACT_PATTERNS.items():
        for match in re.findall(pattern, text):
            value = match.rstrip(".,;:")
            if kind == "number" and len(value.rstrip("+").replace(",", "")) < 2:
                continue   # single digits are everywhere; checking them proves nothing
            if kind in ("money", "percent", "phone"):
                value = value.replace(" ", "")
            facts.add(value)
    return facts


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("**", "")).strip().lower()


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9$#@.+/'-]+", text.lower().replace("**", ""))
            if w.strip(".'-") and w.strip(".'-") not in STOPWORDS}


def _content_lines(body: str) -> list[str]:
    """Source lines that carry content (headings and table rules skipped)."""
    lines = []
    for line in body.splitlines():
        s = line.strip()
        if not s or s.startswith("#") or re.fullmatch(r"\|?[\s:|-]+\|?", s):
            continue
        if len(_words(s)) >= 4:
            lines.append(s)
    return lines


@dataclass
class DocCheck:
    source_doc: str
    missing_facts: list[str] = field(default_factory=list)
    invented_facts: list[str] = field(default_factory=list)       # not in this doc
    missing_questions: list[str] = field(default_factory=list)
    weak_lines: list[tuple[str, float]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not (self.missing_facts or self.invented_facts or self.missing_questions)

    def feedback(self) -> str:
        """Text sent back to the chunker when it needs a second attempt."""
        parts = []
        if self.missing_facts:
            parts.append("These exact values from the document are missing from every chunk; "
                         "add them, copied exactly: " + ", ".join(sorted(self.missing_facts)))
        if self.invented_facts:
            parts.append("These values are not in the document; remove them or copy the "
                         "document's exact wording: " + ", ".join(sorted(self.invented_facts)))
        if self.missing_questions:
            parts.append("These FAQ questions must each be one chunk with the exact question "
                         "text: " + " | ".join(self.missing_questions))
        if self.weak_lines:
            parts.append("These source lines are only partly covered; make sure their content "
                         "is in a chunk: " + " | ".join(line for line, _ in self.weak_lines[:15]))
        return "\n".join(f"- {p}" for p in parts)


def check_document(doc: SourceDoc, chunks: list[Chunk]) -> DocCheck:
    result = DocCheck(doc.source_doc)
    joined = "\n".join(c.text for c in chunks)

    src_facts, chunk_facts = extract_facts(doc.body), extract_facts(joined)
    result.missing_facts = sorted(src_facts - chunk_facts)
    # Facts in the header line come from metadata, not the doc; only check bodies.
    body_facts = extract_facts("\n".join(c.text.partition("\n")[2] for c in chunks))
    result.invented_facts = sorted(body_facts - src_facts)

    norm_joined = _norm(joined)
    for q in re.findall(r"^##\s*Q:\s*(.+)$", doc.body, flags=re.M):
        if _norm(q) not in norm_joined:
            result.missing_questions.append(q.strip())

    chunk_words = [_words(c.text) for c in chunks]
    for line in _content_lines(doc.body):
        words = _words(line)
        best = max((len(words & cw) / len(words) for cw in chunk_words), default=0.0)
        if best < LINE_COVERAGE_MIN:
            result.weak_lines.append((line, round(best, 2)))
    return result


@dataclass
class ValidationReport:
    docs: list[DocCheck]
    oversize: list[tuple[str, int]]
    undersize: list[tuple[str, int]]
    bad_headers: list[str]
    duplicate_ids: list[str]

    @property
    def errors(self) -> list[str]:
        out = []
        for d in self.docs:
            if d.missing_facts:
                out.append(f"{d.source_doc}: missing facts {d.missing_facts}")
            if d.invented_facts:
                out.append(f"{d.source_doc}: facts not in source {d.invented_facts}")
            if d.missing_questions:
                out.append(f"{d.source_doc}: FAQ questions not found {d.missing_questions}")
        out += [f"bad header: {i}" for i in self.bad_headers]
        out += [f"duplicate id: {i}" for i in self.duplicate_ids]
        return out


def validate(docs: list[SourceDoc], chunks: list[Chunk], business: str) -> ValidationReport:
    by_doc: dict[str, list[Chunk]] = {}
    for c in chunks:
        by_doc.setdefault(c.metadata.source_doc, []).append(c)

    oversize, undersize, bad_headers = [], [], []
    for c in chunks:
        c.metadata.token_count = count_tokens(c.text)
        if c.metadata.token_count > MAX_TOKENS:
            oversize.append((c.id, c.metadata.token_count))
        elif c.metadata.token_count < MIN_TOKENS:
            undersize.append((c.id, c.metadata.token_count))
        expected = f"[Business: {business} | Category: {c.metadata.category} | Topic: {c.metadata.topic}]"
        if c.text.partition("\n")[0] != expected:
            bad_headers.append(c.id)

    ids = [c.id for c in chunks]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    return ValidationReport(
        docs=[check_document(d, by_doc.get(d.source_doc, [])) for d in docs],
        oversize=oversize, undersize=undersize, bad_headers=bad_headers, duplicate_ids=dupes,
    )
