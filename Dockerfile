# syntax=docker/dockerfile:1
FROM python:3.12-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app

# Dependencies first so this layer is cached until the lockfile changes.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-dev --frozen --no-install-project

COPY README.md alembic.ini ./
COPY alembic ./alembic
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-dev --frozen --no-editable

FROM python:3.12-slim
RUN groupadd --system --gid 65532 app \
    && useradd --system --uid 65532 --gid app --no-create-home app
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
# alembic is run from /app by `session-lens migrate`.
COPY --from=builder /app/alembic.ini /app/alembic.ini
COPY --from=builder /app/alembic /app/alembic
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
USER 65532:65532
EXPOSE 8000
# Default is the API; the worker Deployment overrides the command.
CMD ["session-lens", "api"]
