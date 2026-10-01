.PHONY: help install token up down logs migrate api worker lint format typecheck test check build clean-data

help:
	@grep -E '^[a-z-]+:' Makefile | cut -d: -f1 | sort

install:
	uv sync

# Writes a random API_TOKEN to the git-ignored .env (kept if already present).
token:
	@if grep -qs '^API_TOKEN=' .env; then echo ".env already has an API_TOKEN"; else \
	  echo "API_TOKEN=$$(uv run python -c 'import secrets; print(secrets.token_urlsafe(32))')" >> .env; \
	  echo "wrote API_TOKEN to .env"; fi

up: token
	docker compose up --build -d

down:
	docker compose down

logs:
	docker compose logs -f api worker

# Non-docker runs; need `docker compose up -d --wait mysql` and the settings in .env.
migrate:
	uv run session-lens migrate

api:
	uv run session-lens api

worker:
	uv run session-lens worker

lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff check --fix .
	uv run ruff format .

typecheck:
	uv run mypy --strict src

test:
	uv run pytest

check: lint typecheck test

build:
	docker build -t session-lens:dev .

# Deletes all stored raw recordings (the shared data volume), after asking.
clean-data:
	@printf "Stop the stack and delete ALL raw recordings in volume session-lens-data? [y/N] "; \
	read ans; if [ "$$ans" = "y" ]; then \
	  docker compose down && docker volume rm session-lens-data; \
	else echo "aborted"; fi
