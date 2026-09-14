"""Small helpers so tests read as domain sentences, not as request plumbing."""

from httpx import AsyncClient

from tests.conftest import TODAY


async def default_category(client: AsyncClient, name: str, type: str) -> dict:
    response = await client.get("/categories/")
    response.raise_for_status()
    return next(
        category
        for category in response.json()
        if category["name"] == name and category["type"] == type
    )


async def create_category(client: AsyncClient, **fields) -> dict:
    body = {"name": "Nueva", "color": "#123456", "type": "expense", **fields}
    response = await client.post("/categories/", json=body)
    response.raise_for_status()
    return response.json()


def transaction_body(**fields) -> dict:
    return {
        "amount": "1000.00",
        "currency": "ARS",
        "type": "expense",
        "date": TODAY.isoformat(),
        **fields,
    }


async def create_transaction(client: AsyncClient, **fields) -> dict:
    response = await client.post("/transactions/", json=transaction_body(**fields))
    response.raise_for_status()
    return response.json()
