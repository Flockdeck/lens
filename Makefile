.PHONY: help install run lint format typecheck test e2e e2e-browser check binary smoke clean

help:
	@grep -E '^[a-z-]+:' Makefile | cut -d: -f1 | sort

install:
	uv sync

# The whole service in one process: http://127.0.0.1:8000
run:
	uv run lens serve --open

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

# The end-to-end tests: real app, worker, database and storage.
e2e:
	uv run pytest tests/e2e -m "not browser"

# The same flows in a real browser (needs Edge, or `uv run playwright install chromium`).
e2e-browser:
	uv run pytest tests/e2e -m browser

check: lint typecheck test

# Build the single program for this machine, then use it like a person would.
binary:
	uv run pyinstaller packaging/lens.spec --noconfirm --distpath dist --workpath build

smoke: binary
	uv run python packaging/smoke.py dist/lens

clean:
	rm -rf dist build
