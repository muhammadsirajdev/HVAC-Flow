# Speed-to-Lead (hvacX)

Website chatbot, email agent and (phase 2) WhatsApp agent sharing one booking core,
built for MD Cold Services. Full plan: [plan.md](plan.md). Scope doc: [docs/](docs/).

## Layout

| Path | What |
|---|---|
| `backend/` | Python project (uv). Package in `backend/src/backend/` |
| `backend/knowledge/mdcold/` | Knowledge-base source documents (`_meta/` is not ingested) |
| `backend/migrations/` | Alembic migrations |
| `backend/tests/` | unit, graphs, rag, integration tests + fixtures |
| `backend/scripts/` | seed, reindex, demo reset, terminal chat |
| `widget/` | Embeddable website chat script + demo page |
| `mcp_servers/` | MCP servers we run ourselves (only if needed) |
| `docs/` | Scope document |

## Run locally

```bash
docker compose up -d db            # Postgres + pgvector
cd backend
cp .env.example .env               # fill in keys
uv sync
uv run uvicorn backend.main:app --reload
```

## Knowledge base (RAG)

```bash
cd backend
uv run python -m backend.rag.ingest          # chunk (LLM) -> check -> report -> embed -> Chroma
uv run python -m backend.rag.evaluate        # hit@1 / hit@k / MRR on build/eval_questions.json
uv run pytest tests/rag                      # offline tests
```

Chunks, the checks report and the test questions are written to
`backend/knowledge/mdcold/build/`; the vector store is `backend/data/chroma/` (git-ignored).
In the graph, use `backend.tools.kb.search_kb` (LangChain tool) or `backend.rag.search_kb`.

## Test console (Run A)

```bash
cd backend
uv run python scripts/seed_demo_client.py     # tables + 14 days of demo slots (once)
uv run uvicorn backend.main:app --reload      # then open http://localhost:8000/
```

Chat as a customer on the left; the right side shows each turn's node path, the
classifier output, booking state, Gmail/Slack results and the database. Disable it in
production with `DEV_UI=false`.
