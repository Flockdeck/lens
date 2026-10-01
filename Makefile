.PHONY: help install token up down logs migrate api worker lint format typecheck test e2e e2e-browser check build clean-data smoke

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

# The whole flow through the real stack (needs `docker compose up -d --wait mysql`). `e2e-browser` drives a
# real browser too: Edge if installed, else Playwright's Chromium (`uv run playwright install chromium`).
e2e:
	uv run pytest tests/e2e -m "not browser"

e2e-browser:
	uv run pytest tests/e2e -m browser

check: lint typecheck test

build:
	docker build -t session-lens:dev .

# Deletes all stored raw recordings (the shared data volume), after asking.
clean-data:
	@printf "Stop the stack and delete ALL raw recordings in volume session-lens-data? [y/N] "; \
	read ans; if [ "$$ans" = "y" ]; then \
	  docker compose down && docker volume rm session-lens-data; \
	else echo "aborted"; fi

define SMOKE
set -eu
url=http://127.0.0.1:8000
token=$$(sed -n 's/^API_TOKEN=//p' .env)
[ -n "$$token" ] || { echo "no API_TOKEN in .env (run make token)" >&2; exit 1; }
json() { uv run python -c "import sys, json; d = json.load(sys.stdin); print($$1)"; }
up=0
for i in $$(seq 60); do
  if curl -fs "$$url/healthz" >/dev/null; then up=1; break; fi
  sleep 1
done
[ "$$up" = 1 ] || { echo "api did not come up" >&2; exit 1; }
id=$$(curl -fsS -H "Authorization: Bearer $$token" -F files=@tests/fixtures/claude_full.jsonl "$$url/batches" | json 'd["id"]')
echo "batch $$id"
state=""
for i in $$(seq 120); do
  body=$$(curl -fsS -H "Authorization: Bearer $$token" "$$url/batches/$$id")
  state=$$(echo "$$body" | json 'd["status"]')
  [ "$$state" = done ] && break
  sleep 1
done
[ "$$state" = done ] || { echo "batch not done (status: $$state)" >&2; exit 1; }
failed=$$(echo "$$body" | json 'd["counts"]["failed"]')
[ "$$failed" = 0 ] || { echo "$$failed item(s) failed" >&2; exit 1; }
total=$$(curl -fsS -H "Authorization: Bearer $$token" "$$url/sessions?limit=1" | json 'd["total"]')
echo "ok: batch done, $$total session(s)"
endef
export SMOKE

# Needs `make up` running. Uploads a fixture, waits for the batch, prints the session count.
smoke:
	@bash -c "$$SMOKE"
