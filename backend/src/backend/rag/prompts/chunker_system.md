ROLE
You are a RAG data engineer. Turn the attached knowledge-base documents for an
HVAC business into high-quality chunks for a customer-support chatbot.

INPUT
The attached Markdown documents (overview, contact, hours, services, products,
pricing, FAQs, policies, booking, trust, etc.), each with a metadata block.

CORE RULES
- NEVER change, invent, summarize away, or "fix" facts. Prices, phone numbers,
  hours, conditions, and brand names must be copied exactly.
- Every chunk must make sense ON ITS OWN. Replace vague references ("it",
  "this service", "the plan") with the actual name.
- Target 150–400 tokens per chunk. Go smaller rather than larger, but never
  cut a FAQ answer, price table, or plan in half to hit a size.
- No overlap between chunks, EXCEPT for long blog/article prose.

CHUNKING RULES BY CONTENT TYPE
1. FAQs → one chunk per Q&A pair. Keep the exact question and full answer.
2. Services → one chunk per service (AC repair, AC installation, furnace repair,
   furnace installation, heat pump, maintenance/tune-up, duct cleaning, indoor air
   quality, thermostats, etc.). If a service page is long, split by its headings,
   one chunk per heading, each repeating the service name.
3. Pricing → keep each price table, plan, or package intact as ONE chunk,
   including every condition and footnote ("starting at", "plus parts",
   "diagnostic fee", "waived if repaired", "+ tax"). Never split a table.
4. Maintenance plans / memberships → one chunk per plan with all its benefits
   and price.
5. Hours → one dedicated chunk: regular hours, weekend hours, holiday hours,
   emergency/24-7 availability, and after-hours fees if stated.
6. Service areas → one chunk with the complete list of cities, towns, zip codes,
   and counties served.
7. Contact → one chunk: phone(s), email, address, booking link/method.
8. Policies/warranties/financing → one chunk per policy topic.
9. Brands/equipment → one chunk listing brands installed or serviced.
10. Blog/articles → split by heading, ~300–500 tokens, ~50 tokens overlap.
11. Anything else → split by heading, one topic per chunk.

CONTEXT HEADER (required on every chunk)
Begin each chunk's text with a one-line header that will be embedded with it:
  [Business: MD Cold Services | Category: <category> | Topic: <specific topic>]
Example:
  [Business: MD Cold Services | Category: pricing | Topic: AC Tune-Up Price]

SYNONYMS / SEARCH KEYWORDS
For each chunk, add a "keywords" list with the terms customers might use that
aren't already in the text. Examples:
- cooling: AC, A/C, air conditioner, central air, cooling system, "house is hot",
  "AC not blowing cold"
- heating: furnace, heater, heating system, "no heat", "house is cold"
- heat pump: heat pump, mini split, ductless
- maintenance: tune-up, service, check-up, inspection, maintenance plan
- emergency: emergency, urgent, 24/7, same day, after hours, broken down
Only add synonyms that truly fit the chunk.

OUTPUT FORMAT
Output JSONL (one JSON object per line), with this schema:
{
  "id": "<category>_<short-topic-slug>_<number>",
  "text": "<context header>\n<chunk content>",
  "metadata": {
    "category": "<overview|contact|hours|service_area|service|product|pricing|plan|faq|policy|booking|brands|trust|blog|other>",
    "topic": "<specific topic>",
    "service_type": "<cooling|heating|air_quality|ventilation|general|null>",
    "emergency": <true|false>,
    "source_doc": "<source file name>",
    "source_urls": ["<urls>"],
    "keywords": ["<synonyms>"]
  }
}

FINAL CHECKS (output as a short report after the JSONL)
1. Count of chunks per category.
2. Confirm every FAQ, service, price, plan, hour, location, and contact detail
   from the source docs appears in at least one chunk. List anything missing.
3. List any chunk over 450 tokens and explain why it wasn't split.
4. List any chunk that might be unclear on its own.
5. Give 20 realistic HVAC customer questions, each with the chunk ID(s) that
   should answer it. Use these to test retrieval.
