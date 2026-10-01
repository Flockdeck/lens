IMAGE ?= ghcr.io/jmwri/session-lens
TAG ?= dev

.PHONY: help install db db-down migrate api worker lint format typecheck test check build up down

help:
	@grep -E '^[a-z-]+:' Makefile | cut -d: -f1 | sort

install:
	uv sync

db:
	docker compose up -d --wait mysql

db-down:
	docker compose down

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
	uv run mypy src

test:
	uv run pytest

check: lint typecheck test

build:
	docker build -t $(IMAGE):$(TAG) .

up:
	docker compose up --build -d

down:
	docker compose down
