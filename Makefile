.PHONY: help web-dev api-dev db-local db-stop db-reset db-migrate test test-api test-rls test-web lint fmt

help:
	@echo "Targets:"
	@echo "  web-dev     Run the Next.js app (http://localhost:3100)"
	@echo "  api-dev     Run the FastAPI service (http://localhost:8100)"
	@echo "  db-local    Start a local PostgreSQL 16 cluster on port 54329 and apply migrations"
	@echo "  db-migrate  Apply pending migrations to the local cluster"
	@echo "  db-reset    Drop and recreate the local database, then migrate"
	@echo "  db-stop     Stop the local cluster"
	@echo "  test        Run API tests, RLS tests, and web lint and unit tests"
	@echo "  lint        Lint api (ruff) and web (eslint)"

web-dev:
	cd web && pnpm dev

api-dev:
	cd api && . .venv/bin/activate && uvicorn app.main:app --reload --port 8100

db-local:
	./scripts/db_local.sh start
	./scripts/db_local.sh migrate

db-migrate:
	./scripts/db_local.sh migrate

db-reset:
	./scripts/db_local.sh reset

db-stop:
	./scripts/db_local.sh stop

test: test-api test-rls test-web

test-api:
	cd api && . .venv/bin/activate && pytest -q -m "not db"

test-rls:
	cd api && . .venv/bin/activate && pytest -q -m db

test-web:
	cd web && pnpm lint && pnpm test

lint:
	cd api && . .venv/bin/activate && ruff check . && ruff format --check .
	cd web && pnpm lint

fmt:
	cd api && . .venv/bin/activate && ruff format . && ruff check --fix .
	cd web && pnpm exec prettier --write "src/**/*.{ts,tsx,css}"
