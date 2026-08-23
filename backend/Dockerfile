# syntax=docker/dockerfile:1.7
#
# Bhopal news backend. Runs on Render (or any container host).
#
# Uses uv for reproducible installs from the committed uv.lock, so the built
# image always matches what we develop against. Python 3.13 is a hard project
# requirement (pyproject.toml: requires-python = ">=3.13"), which is why we
# don't rely on the host platform's default Python.

FROM python:3.13-slim-bookworm AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH=/opt/venv/bin:$PATH

# curl only for the runtime healthcheck; the rest is uv from its own image.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /uvx /usr/local/bin/

WORKDIR /app

# Install dependencies first, in their own layer, so code edits don't rebuild
# the whole environment.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

COPY app ./app
COPY scripts ./scripts

# Non-root runtime. Render doesn't require it, but running as root in a
# public container is asking for trouble later.
RUN groupadd --system app && useradd --system --gid app --home /app app \
    && chown -R app:app /app
USER app

EXPOSE 8000

# Render (and most PaaS) inject $PORT. Fall back to 8000 for local runs.
ENV PORT=8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${PORT}/health" >/dev/null || exit 1

CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
