"""RAG pipeline tests that need no network: loading, normalisation, checks, metadata."""

from pathlib import Path

from backend.config import get_settings
from backend.rag.chunking import assign_ids, slugify, strip_header, to_chunk
from backend.rag.loader import load_documents, parse_front_matter
from backend.rag.schema import LLMChunk, SourceDoc
from backend.rag.validation import check_document, extract_facts, validate
from backend.rag.vectorstore import from_chroma_metadata, to_chroma_metadata

BUSINESS = "MD Cold Services"


def make_doc(body: str) -> SourceDoc:
    return SourceDoc("05_pricing.md", "Prices", "pricing", ["https://x.test/p"], "2026-10-14", body, "h")


def make_chunk(doc: SourceDoc, text: str, category="pricing", topic="AC Diagnostic Price"):
    raw = LLMChunk(category=category, topic=topic, text=text, service_type="cooling",
                   emergency=False, keywords=["AC", "AC", " a/c "])
    return to_chunk(raw, doc, BUSINESS)


def test_front_matter_parsed():
    meta, body = parse_front_matter(
        "---\ntitle: T\ncategory: faq\nsource_urls: [https://a.test/x/, https://b.test/]\n"
        "last_scraped: 2026-10-14\n---\n\n# Body\n")
    assert meta["title"] == "T" and meta["category"] == "faq"
    assert meta["source_urls"] == ["https://a.test/x/", "https://b.test/"]
    assert body.startswith("# Body")


def test_real_kb_loads_and_skips_meta():
    docs = load_documents(get_settings().kb_dir)
    names = [d.source_doc for d in docs]
    assert "03_services/ac-repair.md" in names
    assert not any(n.startswith(("_meta/", "build/")) for n in names)
    assert all(d.title and d.source_urls and d.last_scraped for d in docs)


def test_header_is_canonical_and_keywords_deduped():
    doc = make_doc("x")
    c = make_chunk(doc, "[Business: wrong | Category: x | Topic: y]\nThe diagnostic is $99.")
    assert c.text == ("[Business: MD Cold Services | Category: pricing | Topic: AC Diagnostic Price]\n"
                      "The diagnostic is $99.")
    assert c.metadata.keywords == ["AC", "a/c"]
    assert c.metadata.source_doc == "05_pricing.md" and c.metadata.source_urls == ["https://x.test/p"]
    assert strip_header("no header\nline") == "no header\nline"


def test_ids_are_deterministic_and_unique():
    doc = make_doc("x")
    chunks = assign_ids([make_chunk(doc, "a"), make_chunk(doc, "b"), make_chunk(doc, "c", topic="Elite Plan")])
    assert [c.id for c in chunks] == [
        "pricing_ac-diagnostic-price_1", "pricing_ac-diagnostic-price_2", "pricing_elite-plan_1"]
    assert slugify("AC Installation & Replacement!") == "ac-installation-replacement"


def test_fact_extraction():
    facts = extract_facts("Call (786) 797-6193, $99 (was $129), 10% off, 16+ years, "
                          "License #CAC1824837, see https://a.test/x/. Email me@a.com")
    assert {"(786)797-6193", "$99", "$129", "10%", "16+", "CAC1824837",
            "https://a.test/x/", "me@a.com"} <= facts


def test_missing_and_invented_facts_detected():
    doc = make_doc("## Price\nThe diagnostic is $99, waived if repaired. Regular price $129.\n"
                   "## Q: How much is the diagnostic?\nA: $99.")
    good = make_chunk(doc, "Q: How much is the diagnostic? The diagnostic is $99, waived if "
                           "repaired. Regular price $129.")
    assert check_document(doc, [good]).ok

    bad = make_chunk(doc, "The diagnostic is $89, waived if repaired.")
    check = check_document(doc, [bad])
    assert "$129" in check.missing_facts and "$99" in check.missing_facts
    assert check.invented_facts == ["$89"]
    assert check.missing_questions == ["How much is the diagnostic?"]
    assert "$129" in check.feedback()


def test_validate_flags_bad_header_and_duplicates():
    doc = make_doc("The diagnostic is $99.")
    a, b = make_chunk(doc, "The diagnostic is $99."), make_chunk(doc, "The diagnostic is $99.")
    a.id = b.id = "dup"
    b.text = "no header\n" + b.text
    report = validate([doc], [a, b], BUSINESS)
    assert report.duplicate_ids == ["dup"]
    assert report.bad_headers == ["dup"]
    assert a.metadata.token_count > 0


def test_chroma_metadata_round_trip():
    doc = make_doc("x")
    c = make_chunk(doc, "text")
    c.metadata.service_type = None
    meta = to_chroma_metadata(c, "hash")
    assert all(isinstance(v, (str, int, float, bool)) for v in meta.values())
    back = from_chroma_metadata(meta)
    assert back["keywords"] == ["AC", "a/c"]
    assert back["source_urls"] == ["https://x.test/p"]
    assert back["service_type"] is None


def test_prompts_exist():
    prompts = Path(__file__).resolve().parents[2] / "src" / "backend" / "rag" / "prompts"
    assert (prompts / "chunker_system.md").read_text(encoding="utf-8").startswith("ROLE")
    assert "{body}" in (prompts / "chunker_user.md").read_text(encoding="utf-8")
