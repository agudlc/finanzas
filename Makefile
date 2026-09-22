# Development entry points. Everything runs against the Postgres in Compose.

DEV_DATABASE_URL  ?= postgresql+asyncpg://agudlc:finagudlc@localhost:5432/finagudlc
TEST_DATABASE_URL ?= postgresql+asyncpg://agudlc:finagudlc@localhost:5432/finanzas_test
EVAL_DATABASE_URL ?= postgresql+asyncpg://agudlc:finagudlc@localhost:5432/finanzas_eval
VENV              := backend/.venv
PYTHON            := $(VENV)/bin/python

.PHONY: help dev down install db test eval migrate migration

help:
	@echo "make dev        start the database, the backend and the frontend"
	@echo "make test       run the API test suite against a disposable database"
	@echo "make eval       ask the real model about one fixed month, and print what it says"
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

# The agent, asked about one fixed month by the real Claude: four Reviews,
# one per trigger, on a database of its own. It costs tokens and it says
# something a little different every time, which is why it is not `make test`.
eval: $(VENV) db
	cd backend && EVAL_DATABASE_URL=$(EVAL_DATABASE_URL) ../$(PYTHON) -m evals

migrate: $(VENV) db
	cd backend && DATABASE_URL=$(DEV_DATABASE_URL) ../$(PYTHON) -m alembic upgrade head

migration: $(VENV) db
	@test -n "$(m)" || (echo 'usage: make migration m="what changed"'; exit 1)
	cd backend && DATABASE_URL=$(DEV_DATABASE_URL) ../$(PYTHON) -m alembic revision --autogenerate -m "$(m)"
