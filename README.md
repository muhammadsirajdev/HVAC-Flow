# Speed-to-Lead (hvacX)

An AI front desk for **MD Cold Services**, an HVAC contractor in South Florida. A customer can ask a
question or book a technician visit **in the website chat** or **by email**. The office follows every
booking in **Slack**. Finished jobs reported in Slack get a thank-you email, and every visit gets a
reminder the day before.

All channels share one **booking core** (customers, cases, slots, bookings in Postgres) and one
**knowledge base** (RAG over the company's own documents). The agents are **LangGraph** graphs, and
Gmail and Slack are reached through **MCP** servers. The LLM only classifies messages, extracts
details and words the answers. Code makes every decision that changes data or reaches a customer.

| | |
|---|---|
| **Live demo** | [hvac-flow-olive.vercel.app](https://hvac-flow-olive.vercel.app): chat, enquiry form and the office view ([how the public demo works](#live-demo-and-deployment)) |
| **Plan** | [docs/plan.md](docs/plan.md): full design, rules and acceptance checks |
| **Scope** | [docs/](docs/): original scope document |
| **Status** | Phase 1 complete (Runs A–D). Phase 2 (WhatsApp, Run E) and the embeddable widget are next |

---

## Contents

1. [Screenshots](#screenshots)
2. [What it does](#what-it-does)
3. [System architecture](#system-architecture)
4. [A customer's journey end to end](#a-customers-journey-end-to-end)
5. [Run A: website chat](#run-a-website-chat)
6. [Run B: email agent](#run-b-email-agent)
7. [Run C: job status from Slack](#run-c-job-status-from-slack)
8. [Run D: day-before reminders](#run-d-day-before-reminders)
9. [Knowledge base (RAG)](#knowledge-base-rag)
10. [Case lifecycle](#case-lifecycle)
11. [Guardrails](#guardrails)
12. [MCP integrations](#mcp-integrations)
13. [Data model](#data-model)
14. [Tech stack](#tech-stack)
15. [Project layout](#project-layout)
16. [Getting started](#getting-started)
17. [Live demo and deployment](#live-demo-and-deployment)
18. [Configuration](#configuration)
19. [Testing and evaluation](#testing-and-evaluation)
20. [Known limitations](#known-limitations)
21. [Roadmap](#roadmap)

---

## Screenshots

The frontend ([frontend/](frontend/)) has two pages: **Try it**, where anyone can test the agents, and
**Office**, a CRM that shows every case the agents handle. These were taken from real test runs.

**Try it.** The website chat (Run A) on the left. On the right, the enquiry form, which the email agent
(Run B) answers by email.

![Try it page: website chat and enquiry form](docs/screenshots/01-try-it.png)

**Office: cases.** The board at the top shows what needs a person and who is on the schedule. Cases can
be searched and filtered by status and channel. Each case opens as a work order.

![Office: case list and a website-form case](docs/screenshots/02-office-cases.png)

**A chat booking, then changed by email.** The customer, the visit, whether the confirmation email,
Slack post and reminder went out, and every step since. Cases from the chat and from email share one case history.

![Work order for a visit booked in the chat](docs/screenshots/03-work-order-chat-booking.png)

**The email thread.** Every email in and every AI answer out, in order. The line on the left takes
the colour of the case's status at each point.

![Journey of an email case](docs/screenshots/04-journey-email-case.png)

**Schedule.** The next seven days of slots, booked or still open for the AI to offer, in Miami time.

![Schedule of the next seven days](docs/screenshots/05-schedule.png)

**Activity.** Everything that happened across all cases, newest first.

![Activity feed](docs/screenshots/06-activity.png)

<img src="docs/screenshots/07-phone-office.png" alt="Office work order on a phone" width="300" align="right">

**On a phone.** Both pages work down to phone width. The work order stacks into one column, and the
list and the case open one at a time.

<br clear="right">

---

## What it does

| Run | Channel | Trigger | What happens |
|---|---|---|---|
| **A** | Website chat | Each visitor message (`POST /chat`) | Answers questions from the KB, collects booking details, offers open times, books after a clear "yes", sends the confirmation email, posts to Slack |
| **B** | Email | Inbox poll every 90 s | Answers enquiries from the KB, books visits, changes or cancels bookings for the customer's own address, hands anything unclear to a person |
| **C** | Slack | Every 12 h (on demand for testing) | Reads the staff `#work_status` channel. For each "case 123 status done" it sends the thank-you email and closes the case, once |
| **D** | Email | Daily at 6 PM (business time) | Reminds every customer with a visit tomorrow, once per booking. Alerts Slack about unanswered change requests |

All four runs are independent. They never call each other and share state only through the database.

---

## System architecture

```mermaid
flowchart LR
    subgraph Customers
        V["Website visitor"]
        E["Customer email"]
    end

    subgraph App["FastAPI app (backend.main)"]
        API["POST /chat"]
        SCHED["APScheduler"]
        RA["Run A<br/>chat graph"]
        RB["Run B<br/>email poller + graph"]
        RC["Run C<br/>status graph"]
        RD["Run D<br/>reminder graph"]
        TOOLS["Booking core<br/>tools/: booking, cases,<br/>customers, notify"]
        RAG["RAG retriever<br/>rag/: search_kb"]
    end

    subgraph Data
        PG[("Postgres<br/>cases, bookings, slots,<br/>messages + LangGraph checkpoints")]
        CH[("Chroma<br/>118 KB chunks")]
    end

    subgraph MCP["Klavis MCP servers"]
        GM["Gmail MCP"]
        SL["Slack MCP"]
    end

    LLM["OpenAI<br/>gpt-4.1-mini + text-embedding-3-large"]
    STAFF["Office staff in Slack"]

    V --> API --> RA
    SCHED -->|every 90 s| RB
    SCHED -->|every 12 h| RC
    SCHED -->|daily 6 PM| RD

    RA & RB --> RAG --> CH
    RA & RB --> LLM
    RAG --> LLM
    RA & RB & RC & RD --> TOOLS --> PG
    RA & RB --> PG

    RB <-->|search, read, reply, mark read| GM
    TOOLS -->|confirmations| GM
    RC & RD -->|thank-you, reminders| GM
    GM <--> E
    TOOLS -->|bookings, changes, alerts| SL
    RC -->|"read work_status channel"| SL
    SL <--> STAFF
```

**Key design choices**

- **The LLM decides wording, code decides actions.** The model returns a structured analysis
  (intent, extracted details, chosen option). Code validates it and performs every booking, status
  change, email and Slack post. Confirmation texts are templates filled in *after* the database write
  succeeded, so the model can never confirm a booking that doesn't exist.
- **Identity comes from code, never from the model.** Tools read `case_id`, `customer_id`, the
  recipient address and `verified` from graph state set by code. A fooled model can only send a bad
  reply; it can't act on another customer's case or email an address it chose.
- **One booking core for every channel.** Chat and email call the same `create_booking`,
  `change_booking` and `cancel_booking`. These run in one transaction with row locks and partial
  unique indexes, so a slot can never be booked twice.
- **Polling instead of webhooks.** Gmail and Slack are read through MCP on a timer, so the system needs
  no public URL, Slack app or Gmail push setup, and runs the same on a laptop as on a server.

---

## A customer's journey end to end

```mermaid
sequenceDiagram
    autonumber
    actor C as Customer
    participant W as Website chat (Run A)
    participant B as Email agent (Run B)
    participant DB as Postgres
    participant S as Slack
    actor O as Office staff
    participant T as Status check (Run C)
    participant R as Reminders (Run D)

    C->>W: "My AC isn't cooling, can someone come Thursday?"
    W->>C: Asks for details, offers 3 open times
    C->>W: "The second one" ... "yes"
    W->>DB: create_booking (case #1 = booked)
    W->>C: Confirmation email "[Case #1] Your AC Repair visit ..."
    W->>S: New booking - Case #1

    C->>B: Email "I want to update my booking"
    B->>DB: Find the booking by the sender's address
    B->>C: Current booking details + "what would you like to change?"
    C->>B: "Move it to Friday at 10 AM"
    B->>DB: change_booking (slot locked, old slot freed)
    B->>C: Updated booking details
    B->>S: Case #1 rescheduled: Thu 10:00 AM -> Fri 10:00 AM

    R->>DB: Visits tomorrow, not reminded
    R->>C: "[Case #1] Reminder: your visit tomorrow ..."

    O->>S: "case 1 status done" in #work_status
    T->>S: Read channel (every 12 h)
    T->>DB: Case #1 still booked?
    T->>C: "[Case #1] Thank you from MD Cold Services"
    T->>DB: Case #1 -> done -> closed
```

---

## Run A: website chat

One LangGraph thread per chat session (Postgres checkpointer), so a visitor can leave and come back.

```mermaid
flowchart TD
    IN(("message")) --> guard
    guard -->|"emergency words<br/>(gas smell, sparks, smoke, flooding...)"| respond
    guard --> classify
    classify -->|question| rag_answer
    classify -->|booking| booking_step
    classify -->|"change / payment / DIY / off-topic"| fixed_reply
    classify -->|smalltalk| smalltalk
    classify -->|model down| fallback_form
    booking_step -->|"clear yes"| create_booking
    booking_step -->|"ask a detail / offer times / summary"| respond
    create_booking --> notify
    create_booking -->|"slot just taken"| respond
    rag_answer --> respond
    fixed_reply --> respond
    smalltalk --> respond
    fallback_form --> respond
    notify --> respond
    respond --> OUT(("reply"))
```

| Node | Kind | Role |
|---|---|---|
| `guard` | Code | Emergency keywords (English and Roman Urdu) → the approved safety message + urgent Slack alert, no AI |
| `classify` | LLM | Structured `TurnAnalysis`: intent, name/phone/email/address/problem, date, time, chosen option, yes/no, a standalone search query |
| `rag_answer` | LLM + RAG | Retrieves passages and answers **only** from them, or says it doesn't know and offers a visit |
| `booking_step` | Code | Collects missing details one or two at a time, validates email and phone (E.164), offers up to 3 open times, reads back a summary |
| `create_booking` | Code | Transactional booking; a slot taken meanwhile → new times offered |
| `notify` | Code | Confirmation email (Gmail MCP) and Slack post. A failure alerts staff, never undoes the booking |
| `fixed_reply` | Code | Fixed answers: changes go by email, no payment details in chat, no DIY diagnosis |
| `fallback_form` | Code | Model unavailable → a short form that creates a `needs_person` case |

A test console at `http://localhost:8000/` (dev only) shows each turn's node path, the classifier
output, booking state, Gmail/Slack results and the database.

---

## Run B: email agent

Run B has two parts. The **poller** (plain code) decides *which* emails to handle and *who* sent them.
The **graph** reuses Run A's nodes and holds the conversation, with one LangGraph thread per case.
A customer can therefore reply days later and the conversation continues where it stopped.

```mermaid
flowchart TD
    subgraph Poller["poller.py (code only)"]
        F["fetch_new<br/>Gmail search, skip IDs already in messages"] --> FL
        FL{"filter"} -->|"auto-reply, not for the agent"| IGN["store ID as ignored"]
        FL --> M["match_case<br/>thread -> case number from its customer -><br/>sender's open case -> new case"]
        M -->|"case waiting for a person"| SIL["Slack note, no reply"]
        M -->|"plain thanks on a closed case"| IGN
        M --> V["verify_sender<br/>sender address = booking's email"]
    end

    V --> G

    subgraph G["graph.py (Run A nodes + email rules)"]
        gate{"gate"} -->|"over 5 replies/hour,<br/>or reply about a completed job"| NP["needs_person<br/>fixed acknowledgement + Slack"]
        gate --> guard2["guard -> classify"]
        guard2 -->|question| RAG2["rag_answer"]
        guard2 -->|"off-topic / unclear"| NP
        guard2 -->|"book / change"| BS["booking_step<br/>show booking -> change at once"]
        guard2 -->|"cancel (after yes)"| CB["cancel_booking"]
        BS --> CR["create_booking / change_booking"] --> NT["notify<br/>confirmation = the reply"]
    end

    G --> SEND["send reply in the same thread<br/>(retry once, else Slack: reply by hand)"]
    SEND --> REC["store messages, mark read,<br/>then Slack post for booking/change"]
```

**Rules the email agent follows**

| Situation | Behaviour |
|---|---|
| Question about services, prices, areas | Answered from the knowledge base |
| New booking | Same steps as chat. The booking always uses the sender's address, never one typed in the email |
| "I want to update my booking" | Finds the booking by the sender's address and replies with its full details |
| "Move it to Friday at 10 AM" | If that time is open, the booking moves straight away. Otherwise the 3 closest times are offered and a pick moves it. The updated details are emailed, **then** Slack is posted (old → new) |
| Cancel | Asks for a yes, then cancels, frees the slot and posts to Slack |
| Change within 2 hours of the visit | Goes to a person |
| Change from any other address | Nothing changes; the reply asks for the booking's address; Slack is told |
| Unclear or off-topic email | Case → `needs_person`; the customer gets only a fixed acknowledgement; Slack alert; the AI stays silent on that case |
| Reply to a completed job (other than "thanks") | Straight to a person (it may be a warranty callback) |
| Website enquiry-form email | Customer details parsed by code; may ask and book, never change or cancel |
| Auto-replies, newsletters, unrelated mail | Ignored. Only mail to `EMAIL_AGENT_ADDRESS`, replies on a case and mail from customers with an open booking are taken |

Every email the poller looks at is stored by Gmail message ID, so it's read once. Read/unread is not
used to find work, so staff opening the inbox can't hide an email from the agent.

---

## Run C: job status from Slack

```mermaid
flowchart LR
    S["work_status channel<br/>case 123 status done,<br/>replaced the capacitor"] --> R["read_slack<br/>case number + done word"]
    R --> C{"close_cases<br/>per case"}
    C -->|already closed| SK["skip<br/>(no second thank-you)"]
    C -->|booked| TY["thank-you email<br/>(Gmail MCP)"] --> CL["case -> done -> closed"]
    C -->|"not booked / unknown"| SK
    TY -->|send fails| RT["stays open,<br/>retried next run"]
```

Staff write in their own words. A message counts when it names a case number and a done word (done,
completed, finished, closed). "case 124 not done yet" doesn't count.

## Run D: day-before reminders

```mermaid
flowchart LR
    T["Daily 6 PM<br/>(business time)"] --> F["find_tomorrow<br/>booked, not reminded"]
    F --> S{"send_reminders<br/>per visit"}
    S -->|"change offers unanswered"| A["Slack: please call"]
    S --> E["reminder email<br/>subject: Case N Reminder"] --> M["booking.reminded = true"]
    E -->|send fails| P["Slack: remind by phone"]
```

A moved booking resets `reminded`, so the new time gets its own reminder. Replying to the reminder
reaches Run B with the case number in the subject.

---

## Knowledge base (RAG)

The knowledge base is built from MD Cold Services' own website content: 11 topic files plus one file
per service and product under `backend/knowledge/mdcold/`, with YAML front-matter (title,
category, source URLs). It's chunked by an LLM, checked by code, embedded and stored in Chroma.

### Ingestion pipeline

```mermaid
flowchart LR
    MD["knowledge/mdcold/*.md<br/>+ front-matter"] --> L["loader<br/>parse metadata,<br/>sha256 per file"]
    L --> CA{"changed since<br/>manifest.json?"}
    CA -->|no| KEEP["reuse cached chunks"]
    CA -->|yes| CK["chunking (gpt-4.1)<br/>self-contained chunks,<br/>facts copied exactly"]
    CK --> N["code normalises<br/>context header, IDs,<br/>document metadata"]
    KEEP --> VAL
    N --> VAL["validation (no LLM)<br/>every URL, phone, price, %,<br/>licence, number kept;<br/>line coverage; 40-450 tokens"]
    VAL --> REP["report (gpt-4.1)<br/>unclear chunks +<br/>20 test questions"]
    REP --> EMB["embeddings<br/>text-embedding-3-large<br/>header + text + keywords"]
    EMB --> DB[("Chroma<br/>cosine, 118 chunks")]
    REP --> OUT["build/: chunks.jsonl,<br/>report.md, eval_questions.json"]
```

- **LLM chunking with fact checks.** The chunker writes self-contained chunks, each starting with a
  context header such as `[Business: MD Cold Services | Category: pricing | Topic: Diagnostic fee]`.
  Code then checks that every price, phone number, URL, percentage, licence number and figure in the
  source appears in some chunk unchanged, and that each source line is covered.
- **Search keywords are embedded, not shown.** Each chunk carries customer phrasings ("house is hot")
  that are embedded with it, so everyday wording finds the right passage. The answer model never
  sees them.
- **Incremental.** Unchanged files are not re-chunked. Changing a chunker prompt or model changes
  `CHUNKER_VERSION` and invalidates the cache.

### Retrieval

`search_kb_multi(queries)` embeds each query with the **same** model used for ingestion, then:

1. takes the best `k × 3` candidates by cosine similarity (`KB_TOP_K` = 6);
2. drops anything below `KB_MIN_SCORE` (0.20, tuned on real vs off-topic questions);
3. keeps at most `KB_MAX_PER_SOURCE` (2) chunks per source file, so a FAQ and a service page that say
   the same thing can't fill every slot;
4. merges results across sub-queries for multi-part questions.

No passage above the threshold means **no answer**: the agent says it doesn't know and offers a
visit or the 24/7 phone line instead of guessing.

### How LangGraph talks to the RAG

RAG is not a tool the model can call freely. It's a fixed step in the graph that runs only when
the classifier routes a turn to `rag_answer`:

```mermaid
sequenceDiagram
    autonumber
    participant U as Customer message
    participant G as LangGraph (Run A / B)
    participant CL as classify node (LLM)
    participant RA as rag_answer node
    participant R as rag.retriever
    participant CH as Chroma
    participant AN as Answer LLM

    U->>G: "Do you serve Doral, and is there a warranty?"
    G->>CL: message + recent history + booking state
    CL-->>G: intent=question, search_query="Do you serve Doral?",<br/>sub_queries=["Warranty on new systems"]
    G->>RA: route on intent (code)
    RA->>R: search_kb_multi([search_query, *sub_queries])
    R->>CH: embed (text-embedding-3-large) + cosine top k*3
    CH-->>R: candidates + scores
    R-->>RA: passages >= KB_MIN_SCORE, max 2 per source
    alt no passage above threshold
        RA-->>G: "I'm not sure, I can book a visit or call ..."
    else passages found
        RA->>AN: answer.md prompt: passages + business facts + question
        AN-->>RA: answer from passages only (or NO_ANSWER)
        RA-->>G: reply
    end
    G-->>U: reply (chat) / email body (Run B)
```

- The **classifier rewrites** follow-ups into standalone queries ("how much is it?" → "How much is the
  Premium Comfort Plan?") and splits multi-part questions into up to 3 queries.
- The **answer prompt** allows only facts from the passages, copied exactly. It forbids diagnoses and
  invented prices, and returns `NO_ANSWER` when the passages don't contain the answer.
- The **same path** serves chat and email. Run B only passes `channel="email"` so the wording fits an
  email.

### Evaluation results

End-to-end on 51 labelled questions (40 answerable, 11 that the KB must refuse), through the same path
as the chat. Full report: `backend/knowledge/mdcold/build/eval_qa_report.md`.

| Metric | Score |
|---|---|
| Routing to the knowledge base | 98% |
| Retrieval: expected source in top-k | 100% |
| Retrieval: MRR | 0.846 |
| Retrieval: must-include facts in passages | 98% |
| Answer correctness (LLM judge) | 99% |
| Answer faithfulness (no claims beyond passages) | 98% |
| False "not sure" on answerable questions | 0% |
| Correct refusals on unanswerable questions | 100% |
| Invented facts on unanswerable questions | 0% |
| Latency p50 / p95 | 2.96 s / 4.49 s |

---

## Case lifecycle

Every inquiry or job is a **case** ("Case #123"). Every status change goes through
`tools/cases.transition()`, which checks an allowed-transitions table and writes an audit row
(`case_events`). The model never sets a status.

```mermaid
stateDiagram-v2
    [*] --> open: first message
    open --> booked: create_booking
    booked --> booked: change_booking
    booked --> cancelled: cancel_booking (email, after yes)
    open --> needs_person: agent can't handle it
    booked --> needs_person: unclear email / late change
    booked --> done: "case N status done" in Slack
    done --> closed: thank-you email sent
    needs_person --> [*]: the office takes over
    closed --> [*]: a later email opens a new case
    cancelled --> [*]
```

One open case per customer is enforced by a partial unique index.

---

## Guardrails

| Risk | Control |
|---|---|
| Prompt injection in a message or email | Customer text is data. No tool can forward mail or email an address the model picks; recipients are set by code |
| Model confirms something that didn't happen | Confirmations are templates rendered **after** the database write succeeds |
| Someone else changes a booking | Email: sender must be the booking's address (form emails never). Chat: only the same session, within 60 min |
| Double booking | Slot row lock + partial unique indexes (`one active booking per slot`, `one per case`) |
| Invented prices or facts | Answers only from retrieved passages; numbers in reworded replies are checked against the facts given |
| Emergencies | Code-side keyword guard before any LLM call → fixed safety text + urgent Slack alert |
| Email loops and floods | Auto-replies skipped; more than 5 AI replies per thread per hour → a person |
| Payment details | Never requested or accepted |
| Failures | Booking saved even if email or Slack fails; failed sends alert Slack ("confirm/remind by phone"); MCP connection drops are retried once when the request provably wasn't delivered |

---

## MCP integrations

Gmail and Slack are reached through **Klavis Strata MCP** servers using `langchain-mcp-adapters`.
Only the tools listed below are loaded; the rest are ignored.

| Server | Tools offered | Used | Purpose |
|---|---|---|---|
| Gmail | 10 | `gmail_send_email` | Confirmations, replies in thread (`threadId`), thank-you, reminders |
| | | `gmail_search_emails` | Find candidate inbox mail |
| | | `gmail_read_email` | Read a message's whole thread |
| | | `gmail_modify_email` | Mark handled mail as read |
| Slack | 13 | `slack_user_post_message` | Bookings, changes, cancellations, alerts |
| | | `slack_user_list_channels` | Resolve channel names to IDs |
| | | `slack_get_channel_history` | Read `#work_status` for Run C |

List them yourself with `uv run python scripts/list_mcp_tools.py -v`.

---

## Data model

| Table | Holds |
|---|---|
| `customers` | Name, email (unique), phone in E.164 (unique), address |
| `cases` | Status, channel, linked email thread, timestamps |
| `case_events` | Audit trail of every status change and its reason |
| `slots` | Bookable visit times |
| `bookings` | Slot, service, address, problem; `reminded`, confirmation/Slack sent flags, pending change offers |
| `messages` | Every email in and out, by provider message ID (dedupe and reply-rate limit) |
| LangGraph checkpoints | Conversation state per chat session (`web:<session>`) and per email case (`email:<case>`) |

Schema: [backend/src/backend/db/schema.sql](backend/src/backend/db/schema.sql) (idempotent).

---

## Tech stack

| Part | Choice |
|---|---|
| Agents | LangGraph 1.2 (`StateGraph`, `Command` routing, Postgres checkpointer) |
| LLM | OpenAI `gpt-4.1-mini` (Groq supported via `LLM_PROVIDER`), structured output with Pydantic |
| RAG | Chroma (cosine), OpenAI `text-embedding-3-large`, `gpt-4.1` chunking and review |
| API | FastAPI + Uvicorn |
| Frontend | React 18 + TypeScript + Vite, React Router, hand-written CSS (no UI kit) |
| Database | Postgres 16 (psycopg 3, connection pool) |
| Integrations | Klavis Gmail and Slack MCP servers via `langchain-mcp-adapters` |
| Scheduling | APScheduler (interval and cron jobs inside the app) |
| Templates | Jinja2 (every customer-facing confirmation, reminder and thank-you) |
| Tooling | uv, pytest |

---

## Project layout

```
hvacX/
├── docker-compose.yml                 # Postgres for local development
├── docs/plan.md                       # design, rules, acceptance checks
├── docs/screenshots/                  # README screenshots
├── frontend/                          # React app: Try it page + Office (CRM) view
│   ├── vercel.json                    # SPA rewrite for Vercel (public/_redirects for Cloudflare/Netlify)
│   └── src/                           # pages/, components/, lib/ (formatting, polling, access), styles/
└── backend/
    ├── knowledge/mdcold/              # KB source documents (+ build/: chunks, reports, evals)
    ├── Dockerfile                     # API image (Render or any Docker host)
    ├── data/chroma/                   # built knowledge-base index (committed: deployed builds need it)
    ├── scripts/                       # seed slots / demo data, copy_db, terminal chat, list MCP tools,
    │                                  #   resend notifications
    ├── tests/                         # graph tests (Runs A-D) and offline RAG tests + eval dataset
    └── src/backend/
        ├── main.py                    # FastAPI app; starts the background jobs
        ├── scheduler.py               # APScheduler: email poll, Slack status, reminders
        ├── config.py                  # settings from .env
        ├── api/                       # /chat, /forms, /crm (office), /auth, /health, dev console
        ├── core/                      # demo mode rules, privacy masking, rate limits, time, errors
        ├── graphs/
        │   ├── common/                # state types, LLM client, checkpointer
        │   ├── run_a_chat/            # chat graph, nodes, prompts
        │   ├── run_b_email/           # poller, email rules, graph (extends Run A)
        │   ├── run_c_slack_status/    # status channel -> thank-you -> close
        │   └── run_d_reminders/       # day-before reminders
        ├── rag/                       # loader, chunking, validation, report, embeddings,
        │                              #   vectorstore, ingest, retriever, evaluate, evaluate_qa
        ├── tools/                     # booking, cases, customers, notify, guardrails, validation
        ├── mcp/                       # MCP client, Gmail and Slack adapters
        ├── db/                        # schema.sql, connection pool, init, slots, demo data
        └── templates/                 # email templates, safety message
```

---

## Getting started

**Requirements:** Python 3.12+, [uv](https://docs.astral.sh/uv/), Docker (for Postgres), an OpenAI
API key, and Klavis MCP URLs for Gmail and Slack.

```bash
docker compose up -d db                              # Postgres
cd backend
cp .env.example .env                                 # fill in the keys (see Configuration)
uv sync
uv run python -m backend.db.init_db                  # tables + LangGraph checkpoint tables
uv run python scripts/seed_demo_client.py            # 14 days of demo slots
uv run python -m backend.rag.ingest                  # build the knowledge base (once, or when docs change)
uv run uvicorn backend.main:app --reload             # API + test console at http://localhost:8000/
```

**Frontend** (Node 20+), in a second terminal while the API runs:

```bash
cd frontend
npm install
npm run dev                                          # http://localhost:5173
```

- **Try it** (`/`): the website chat and an enquiry form whose answer is emailed to you.
- **Office** (`/office`): the CRM. Every case with its customer, visit, status history,
  chat and email messages, plus the week's schedule and an activity feed. It updates every few seconds.

The dev server proxies `/api` to `localhost:8000`. For a separate deployment, build with
`VITE_API_URL=https://your-api npm run build` and add that site to `WIDGET_ALLOWED_ORIGINS`.
The office view and the form need `DEV_UI=true`. On a public server, also turn on `DEMO_MODE` and set
`OFFICE_PASSWORD` (see [Live demo and deployment](#live-demo-and-deployment)).

**Background jobs** run inside the app when enabled in `.env`. Each can also be run once by hand for
testing. These commands really send email:

```bash
uv run python -m backend.graphs.run_b_email.poller          # one inbox poll
uv run python -m backend.graphs.run_c_slack_status.graph    # one status-channel check
uv run python -m backend.graphs.run_d_reminders.graph       # one reminder run
uv run python scripts/chat_cli.py                           # chat with Run A in the terminal
```

---

## Live demo and deployment

**Try it:** [hvac-flow-olive.vercel.app](https://hvac-flow-olive.vercel.app). Chat with the front
desk, book a visit, send the enquiry form, then open **Office** to see the case appear.

### What the public demo does differently

The live site runs with `DEMO_MODE=true`, so strangers can use it safely:

| | In the demo | In production |
|---|---|---|
| **Emails** (form answers, booking confirmations, reminders, thank-yous) | Written by the agent and **shown on the page and in the office, not sent**. Only addresses on `DEMO_LIVE_EMAILS` receive real mail | Sent through Gmail (MCP) |
| **Office (CRM)** | Names, phones, emails and addresses are **partly hidden** ("Maria G.", `ma•••@example.com`). Staff sign in with `OFFICE_PASSWORD` to see everything | Behind the office sign-in |
| **Limits** | 20 chat messages per 10 min and 3 forms per hour per visitor; 300 AI requests a day in total (caps the OpenAI cost) | None |
| **Data** | Seven made-up customers covering every status and channel, **reset every night** | Real cases |
| Slack posts, booking rules, the knowledge base, the email agent | Exactly as in production | |

**Why the emails appear on the page:** an open form that sends email to any address typed into it
could be used to send mail to anyone from the business account. Showing the email instead keeps the
demo safe, while everything around it (the agent writing it, the case, the booking, the office
timeline) runs for real.

**Seeing real delivery:** the email path is the same code in both modes; demo mode only skips the
final Gmail call for addresses not on the list. The owner's address is on `DEMO_LIVE_EMAILS`, so in a
live walkthrough the form is sent with that address and the answer lands in Gmail within about 30
seconds, with the case number in the subject. Replying to it gets a new answer in the same thread.
For someone else to receive real emails, their address is added to `DEMO_LIVE_EMAILS` for the session.

### How it's hosted (all free tiers)

| Part | Where | Notes |
|---|---|---|
| Frontend | **Vercel** | `frontend/`, Vite preset, `VITE_API_URL` = the API address; `vercel.json` sends every path to the app |
| API + background jobs | **Render** web service (Docker) | Root directory `backend/`, built from [backend/Dockerfile](backend/Dockerfile); health check `/health` |
| Database | **Supabase** Postgres | Use the **Session pooler** connection string (IPv4); the direct one is IPv6-only |
| Keep-alive | **cron-job.org** | Calls `/health` every 10 minutes so the free Render service never sleeps (it would after 15 idle minutes) |

The image includes the built knowledge base (`backend/data/chroma`), so nothing is re-embedded at
start-up. On every start it creates any missing tables, and `SLOTS_DAYS_AHEAD=14` keeps two weeks of
bookable slots open. Environment variables on the host must be entered **without quotes**.

**Useful scripts** (in `backend/`):

```bash
uv run python scripts/copy_db.py --to "<postgres url>"   # copy all data, e.g. local -> Supabase
uv run python scripts/seed_demo_data.py --yes            # EMPTY the database and load the demo customers
```

---

## Configuration

All settings live in `backend/.env` (template: [backend/.env.example](backend/.env.example)).

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | | Postgres connection |
| `OPENAI_API_KEY`, `LLM_PROVIDER`, `LLM_MODEL` | `openai`, `gpt-4.1-mini` | Chat model |
| `KLAVIS_GMAIL_MCP_URL`, `KLAVIS_SLACK_MCP_URL`, `KLAVIS_MCP_TOKEN` | | MCP servers |
| `BUSINESS_NAME`, `BUSINESS_PHONE`, `BUSINESS_TZ` | MD Cold Services, (786) 797-6193, America/New_York | Used in every message and for "tomorrow" |
| `SLACK_BOOKINGS_CHANNEL`, `SLACK_URGENT_CHANNEL` | | Where bookings and alerts are posted |
| `EMAIL_POLL_ENABLED`, `EMAIL_POLL_SECONDS` | `false`, `90` | Run B on a timer |
| `EMAIL_AGENT_ADDRESS` | `BUSINESS_INBOX` | New conversations are taken only from mail sent here. With a personal Gmail use a plus address such as `you+hvac@gmail.com` |
| `EMAIL_FORM_SENDERS` | | Website enquiry-form sender addresses |
| `SLACK_STATUS_CHANNEL`, `SLACK_STATUS_ENABLED`, `SLACK_STATUS_HOURS` | (set to `work_status`), `false`, `12` | Run C: the staff channel and how often it's read |
| `REMINDERS_ENABLED`, `REMINDER_HOUR` | `false`, `18` | Run D |
| `LATE_CHANGE_HOURS`, `MIN_LEAD_HOURS` | `2`, `2` | No changes within 2 h of a visit; no slot sooner than 2 h from now |
| `KB_TOP_K`, `KB_MIN_SCORE`, `KB_MAX_PER_SOURCE` | `6`, `0.20`, `2` | Retrieval tuning |
| `WIDGET_ALLOWED_ORIGINS` | `http://localhost:8000` | Sites allowed to call the API (the frontend's address) |
| `SLOTS_DAYS_AHEAD` | `0` | Keep this many days of bookable slots open (start-up + nightly); `14` on a server |
| `DEV_UI` | `true` | Office view, enquiry form and the backend test console |
| `DEMO_MODE` | `false` | Public demo: emails shown not sent, visitor limits, office details partly hidden |
| `DEMO_LIVE_EMAILS` | | Addresses that still receive real email in demo mode (comma-separated) |
| `DEMO_CHAT_PER_10MIN`, `DEMO_FORMS_PER_HOUR`, `DEMO_AI_PER_DAY` | `20`, `3`, `300` | Visitor limits and the daily AI cap |
| `DEMO_RESET_HOUR` | `-1` | 0-23: wipe and reload the demo customers daily at this hour; `-1` off |
| `OFFICE_PASSWORD` | | Staff sign-in for the office (full details); empty = no sign-in |

---

## Testing and evaluation

```bash
cd backend
uv run pytest                                # 71 tests, no network: fake LLM, DB, MCP
uv run python -m backend.rag.evaluate_qa     # end-to-end RAG eval (uses the OpenAI API)
uv run python -m backend.rag.evaluate        # retrieval only: hit@k, MRR, threshold suggestion
```

| Suite | Covers |
|---|---|
| `tests/graphs/test_run_a_chat.py` | Chat routing, booking flow, validation, slot taken, emergencies, fallback |
| `tests/graphs/test_run_b_email.py` | Email rules (auto-reply, quoted text, form parsing), show-then-change flow, exact time, unverified sender, cancel with yes, hand-off to a person |
| `tests/graphs/test_run_c_slack_status.py` | Status message parsing, thank-you once, failures stay open |
| `tests/graphs/test_run_d_reminders.py` | Tomorrow's window, mark once, failed send alert, unanswered change alert |
| `tests/test_demo.py` | Demo mode: masking, office sign-in tokens, visitor limits, emails not sent |
| `tests/rag/` | Offline pipeline checks + the 51-question eval dataset |

---

## Known limitations

- **No DKIM/DMARC check.** The Gmail MCP returns no raw headers, so email changes trust the sender
  address as shown (Gmail's spam filtering drops most forged mail). A header-returning Gmail tool
  would allow a full check.
- **No way back from `needs_person` in the app yet.** The office handles those cases by hand.
- **Polling latency.** Email replies take up to one poll interval (90 s); Slack status up to 12 h, by design.

---

## Roadmap

- **Embeddable chat widget** for the production website.
- **Run E: WhatsApp** (phase 2): same agent and tools through the WhatsApp Cloud API, with templates
  outside the 24-hour window.
- A Slack command to hand a `needs_person` case back to the AI.
