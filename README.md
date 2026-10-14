# Speed-to-Lead (hvacX)

Website chatbot, email agent and (phase 2) WhatsApp agent sharing one booking core,
built for MD Cold Services. Full plan: [docs/plan.md](docs/plan.md). Scope doc: [docs/](docs/).

## Status

| Run | What | Status |
|---|---|---|
| A | Website chat: RAG answers, booking, confirmation email (Gmail MCP), Slack post | built |
| B | Email agent: inbox poll, RAG answers, booking, verified change/cancel, needs-person hand-off | built |
| C, D, E | Slack status, reminders, WhatsApp | planned |

## Layout

| Path | What |
|---|---|
| `backend/src/backend/` | Python package: `api/`, `graphs/`, `tools/`, `rag/`, `mcp/`, `db/`, `templates/` |
| `backend/knowledge/mdcold/` | Knowledge-base source documents (`_meta/` is not ingested, `build/` is generated) |
| `backend/tests/` | Graph tests (Runs A, B) and offline RAG tests + eval dataset |
| `backend/scripts/` | Seed demo slots, terminal chat, list MCP tools, resend pending notifications |
| `docs/` | Plan and scope document |

## Run locally

```bash
docker compose up -d db            # Postgres
cd backend
cp .env.example .env               # fill in keys
uv sync
uv run python scripts/seed_demo_client.py     # tables + 14 days of demo slots (once)
uv run uvicorn backend.main:app --reload      # test console at http://localhost:8000/
```

## Email agent (Run B)

Set in `backend/.env`: `EMAIL_POLL_ENABLED=true` and `EMAIL_AGENT_ADDRESS` (new conversations are
only taken from mail sent to it; with a personal Gmail use a plus address like `you+hvac@gmail.com`).
Replies in a case's thread are always taken; everything else in the mailbox is ignored.

```bash
cd backend
uv run python -m backend.graphs.run_b_email.poller   # one poll by hand (it really replies)
```

## Knowledge base (RAG)

```bash
cd backend
uv run python -m backend.rag.ingest          # chunk (LLM) -> check -> report -> embed -> Chroma
uv run python -m backend.rag.evaluate_qa     # end-to-end eval on tests/rag/dataset_eval.json
uv run python -m backend.rag.evaluate        # retrieval-only: hit@k / MRR on build/eval_questions.json
```

Chunks and reports are written to `backend/knowledge/mdcold/build/`; the vector store is
`backend/data/chroma/` (git-ignored).

## Tests

```bash
cd backend
uv run pytest                                # graph + offline RAG tests, no network
```

## Test console (Run A)

Chat as a customer on the left; the right side shows each turn's node path, the
classifier output, booking state, Gmail/Slack results and the database. Disable it in
production with `DEV_UI=false`.
