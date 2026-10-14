PIPELINE NOTE (how this run differs from the OUTPUT FORMAT above)
- You receive ONE document per call. Return only that document's chunks, in the
  structured response format. Do not write JSONL text and do not write the
  FINAL CHECKS report; the pipeline produces both in later steps.
- The pipeline fills in "id", "source_doc" and "source_urls" from the document's
  metadata block. You provide: category, topic, text, service_type, emergency,
  keywords.
- Start "text" with the context header line exactly as specified, using the same
  category and topic you return.
- A chunk's category describes the chunk, not the document: the contact document
  can produce "contact" and "service_area" chunks, the pricing document can
  produce "pricing" and "plan" chunks, and so on.
- Statements such as "Not stated on website" are facts too: keep them, so the
  chatbot knows the information is not available.
- References to other knowledge-base files (for example "see 05_pricing.md") mean
  nothing to a customer. Drop the file name but keep every fact around it.
- Every price, phone number, email, URL, license number, percentage, count and
  list item in the document must appear in at least one chunk, copied exactly.
- Do not add any fact, number or URL that is not in this document.
{feedback}
DOCUMENT METADATA
source_doc: {source_doc}
title: {title}
document category: {doc_category}
source_urls: {source_urls}
last_scraped: {last_scraped}

<document>
{body}
</document>
