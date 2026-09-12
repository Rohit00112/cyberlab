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
RUN rm -rf tests
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]