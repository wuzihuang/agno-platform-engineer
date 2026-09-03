.PHONY: install test lint run compose-up compose-down

install:
	uv sync --extra dev

run:
	uv run agno-app

test:
	uv run pytest

lint:
	uv run ruff check .
	uv run ruff format --check .

compose-up:
	docker compose up --build

compose-down:
	docker compose down
