# syntax=docker/dockerfile:1

FROM ghcr.io/astral-sh/uv:0.11 AS uv

FROM python:3.13-slim AS base
COPY --from=uv /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1 PATH="/app/.venv/bin:$PATH"
WORKDIR /app

FROM base AS deps
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

FROM base AS dev
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --dev
COPY . .

FROM base AS prod
COPY --from=deps /app/.venv /.venv
COPY . .
RUN rm -rf tests \
    && useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/data/research \
    && chown -R appuser:appuser /app
USER appuser
# Refuse to boot with placeholder secrets in production (see scripts/verify_config.py).
CMD ["sh", "-c", "python -m scripts.verify_config && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers"]
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request,sys;sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=3).status==200 else 1)"