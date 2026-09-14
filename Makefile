# Development entry points. Everything runs against the Postgres in Compose.

DEV_DATABASE_URL  ?= postgresql+asyncpg://agudlc:finagudlc@localhost:5432/finagudlc
TEST_DATABASE_URL ?= postgresql+asyncpg://agudlc:finagudlc@localhost:5432/finanzas_test
VENV              := backend/.venv
PYTHON            := $(VENV)/bin/python

.PHONY: help dev down install db test migrate migration

help:
	@echo "make dev        start the database, the backend and the frontend"
	@echo "make test       run the API test suite against a disposable database"
	@echo "make migrate    apply migrations to the development database"
	@echo "make migration  create a migration (make migration m=\"what changed\")"
	@echo "make down       stop everything"

dev:
	docker compose up --build

down:
	docker compose down

# The backend virtualenv, used by the test suite and the migration commands.
install $(VENV):
	cd backend && uv venv && VIRTUAL_ENV=.venv uv pip install -e ".[dev]"

# The database on its own, waited for, so host-side commands can reach it.
db:
	docker compose up -d --wait db

test: $(VENV) db
	cd backend && TEST_DATABASE_URL=$(TEST_DATABASE_URL) ../$(PYTHON) -m pytest

migrate: $(VENV) db
	cd backend && DATABASE_URL=$(DEV_DATABASE_URL) ../$(PYTHON) -m alembic upgrade head

migration: $(VENV) db
	@test -n "$(m)" || (echo 'usage: make migration m="what changed"'; exit 1)
	cd backend && DATABASE_URL=$(DEV_DATABASE_URL) ../$(PYTHON) -m alembic revision --autogenerate -m "$(m)"
