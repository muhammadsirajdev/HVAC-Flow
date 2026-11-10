# hvacX API. Runs anywhere Docker runs (Render, Koyeb, a VM). Settings come from environment
# variables set on the host, never from .env. The server listens on $PORT (hosts like Render set it).
#
#   docker build -t hvacx-api backend
#   docker run --env-file <file with unquoted KEY=value lines> -p 7860:7860 hvacx-api

FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.12.15 /uv /usr/local/bin/uv

RUN useradd --create-home --uid 1000 user
USER user
WORKDIR /home/user/app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_HTTP_TIMEOUT=300 \
    PATH="/home/user/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PORT=7860

# Dependencies first, so code changes don't reinstall them.
COPY --chown=user pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY --chown=user src ./src
COPY --chown=user scripts/seed_demo_client.py ./scripts/
# The knowledge base: source docs plus the built Chroma index, so nothing is embedded at start-up.
COPY --chown=user knowledge ./knowledge
COPY --chown=user data/chroma ./data/chroma
RUN uv sync --frozen --no-dev

EXPOSE 7860
# Create any missing tables and open slots, then serve.
CMD ["sh", "-c", "python scripts/seed_demo_client.py && exec uvicorn backend.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
