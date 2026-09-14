"""Helpers for the Import tests: a Profile, a fixture file, a preview."""

from pathlib import Path

from httpx import AsyncClient

FIXTURES = Path(__file__).parent / "fixtures"

MERCADO_PAGO = {
    "name": "Mercado Pago",
    "source": "mercadopago",
    "column_mapping": {
        "date": "Fecha",
        "description": "Descripción",
        "type": "Tipo",
        "debit": "Débito",
        "credit": "Crédito",
    },
    "date_format": "%d/%m/%Y",
    "number_format": "comma_decimal",
    "sign_convention": "debit_credit_columns",
    "ignore_patterns": ["Transferencia", "Cripto"],
}

LEMON = {
    "name": "Lemon",
    "source": "lemon",
    "column_mapping": {
        "date": "fecha",
        "description": "detalle",
        "amount": "monto",
        "currency": "moneda",
    },
    "date_format": "%d/%m/%Y",
    "number_format": "dot_decimal",
    "sign_convention": "negative_is_expense",
    "ignore_patterns": [],
}


async def create_profile(client: AsyncClient, **overrides) -> dict:
    response = await client.post("/import-profiles/", json={**MERCADO_PAGO, **overrides})
    response.raise_for_status()
    return response.json()


async def preview(client: AsyncClient, profile: dict, fixture: str) -> dict:
    response = await client.post(
        "/imports/preview",
        data={"profile_id": profile["id"]},
        files={"file": (fixture, (FIXTURES / fixture).read_bytes())},
    )
    response.raise_for_status()
    return response.json()


def row_named(preview: dict, description: str) -> dict:
    return next(row for row in preview["rows"] if row["description"] == description)


def confirm_body(preview: dict, **per_row) -> dict:
    """The preview handed straight back, skipping what it flagged."""
    return {
        "profile_id": preview["profile_id"],
        "filename": preview["filename"],
        "rows": [
            {
                "date": row["date"],
                "description": row["description"],
                "amount": row["amount"],
                "currency": row["currency"],
                "type": row["type"],
                "category_id": row["category_id"],
                "skip": row["status"] in ("ignored", "duplicate"),
                **per_row.get(row["description"], {}),
            }
            for row in preview["rows"]
        ],
    }
