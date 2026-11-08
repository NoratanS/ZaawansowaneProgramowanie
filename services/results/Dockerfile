# syntax=docker/dockerfile:1
# Build with the repo root as context:
#   docker build -f services/results/Dockerfile .
FROM ghcr.io/astral-sh/uv:python3.15-trixie-slim

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_DEV=1

WORKDIR /app

# Dependencies first, so code changes don't reinstall them. uv needs every
# workspace member's pyproject.toml to read the lockfile.
COPY pyproject.toml uv.lock ./
COPY services/analysis/pyproject.toml services/analysis/
COPY services/results/pyproject.toml services/results/
RUN uv sync --frozen --no-install-workspace --package results-service

COPY services/results services/results
RUN uv sync --frozen --package results-service

ENV PATH="/app/.venv/bin:$PATH"

# One replica, so migrating at start is safe. exec hands uvicorn PID 1, so
# `docker compose stop` reaches it as SIGTERM.
CMD ["sh", "-c", "alembic -c services/results/alembic.ini upgrade head && exec python -m results_service.app"]
