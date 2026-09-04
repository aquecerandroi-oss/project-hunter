# PROJECT HUNTER
# Thin wrapper around the canonical commands documented in CLAUDE.md.
# Windows without `make` on PATH: run the commands listed under each target directly.

.PHONY: install lint lint-strict typecheck test build dev migrate gen-types file-size

install:
	pnpm install
	uv sync --all-packages

lint:
	pnpm lint
	uv run ruff check .
	uv run ruff format --check .

# Slow, aspirational tier. CI-only, non-blocking until the violation count hits zero.
lint-strict:
	-pnpm lint:types
	-uv run ruff check --config packages/config/ruff.strict.toml .

typecheck:
	pnpm typecheck
	uv run pyright

test:
	pnpm test
	uv run pytest

build:
	pnpm build
	docker compose -f infra/docker/docker-compose.yml build

dev:
	docker compose -f infra/docker/docker-compose.yml up

migrate:
	uv run alembic -c infra/migrations/alembic.ini upgrade head

gen-types:
	pnpm gen:types

file-size:
	python infra/scripts/check_file_size.py
