FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .

RUN pip install uv && uv pip install --system -r pyproject.toml

COPY alembic.ini .
COPY alembic/ ./alembic/
COPY app/ ./app/

# Migrations run on every start, so a fresh database comes up with the schema
# and the Default Categories already in place.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"]
