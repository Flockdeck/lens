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
# --reinstall-package: uv would otherwise reuse the wheel it cached for this project (the version has not
# changed) and ship the previous source. Only the project is rebuilt; the dependencies stay cached.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-dev --frozen --no-editable --reinstall-package session-lens

FROM python:3.12-slim
RUN groupadd --system --gid 65532 app \
    && useradd --system --uid 65532 --gid app --no-create-home app
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
# alembic is run from /app by `session-lens migrate`.
COPY --from=builder /app/alembic.ini /app/alembic.ini
COPY --from=builder /app/alembic /app/alembic
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
# Filesystem store for raw recordings; owned by the non-root user so a fresh named volume is writable.
RUN mkdir /data && chown 65532:65532 /data
ENV DATA_DIR=/data
VOLUME /data
USER 65532:65532
EXPOSE 8000
# Default is the API. It must bind 0.0.0.0 inside the container to be reachable through a
# published port (publish to 127.0.0.1 on the host to keep it local). The worker overrides this.
CMD ["session-lens", "api", "--host", "0.0.0.0"]
