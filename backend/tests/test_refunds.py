"""A Refund is a negative Expense, never an Income."""

from tests.api import create_transaction, default_category
from tests.conftest import TODAY

UNKNOWN = "00000000-0000-0000-0000-000000000000"


async def test_a_refund_against_an_expense_takes_its_category_and_currency(client):
    ropa = await default_category(client, "Ropa", "expense")
    purchase = await create_transaction(
        client, category_id=ropa["id"], currency="USD", amount="80.00"
    )

    response = await client.post(
        f"/transactions/{purchase['id']}/refund",
        json={"amount": "30.00", "date": TODAY.isoformat()},
    )

    assert response.status_code == 201
    refund = response.json()
    assert refund["amount"] == "-30.00"
    assert refund["category_id"] == ropa["id"]
    assert refund["currency"] == "USD"
    assert refund["refund_of_id"] == purchase["id"]


async def test_a_refund_of_a_usd_expense_carries_its_own_estimated_rate(client):
    ropa = await default_category(client, "Ropa", "expense")
    purchase = await create_transaction(
        client, category_id=ropa["id"], currency="USD", amount="80.00"
    )

    refund = (
        await client.post(
            f"/transactions/{purchase['id']}/refund",
            json={"amount": "30.00", "date": TODAY.isoformat()},
        )
    ).json()

    assert refund["exchange_rate"] == "1500.0000"
    assert refund["exchange_rate_status"] == "estimated"


async def test_a_refund_without_an_original_only_needs_a_category(client):
    """Refunds for old or unrecorded purchases still have to count."""
    ropa = await default_category(client, "Ropa", "expense")

    refund = await create_transaction(
        client, category_id=ropa["id"], amount="-2500.00"
    )

    assert refund["amount"] == "-2500.00"
    assert refund["refund_of_id"] is None
    assert refund["type"] == "expense"


async def test_a_refund_cannot_reverse_an_income(client):
    sueldo = await default_category(client, "Sueldo", "income")
    salary = await create_transaction(
        client, type="income", category_id=sueldo["id"]
    )

    response = await client.post(
        f"/transactions/{salary['id']}/refund",
        json={"amount": "100.00", "date": TODAY.isoformat()},
    )

    assert response.status_code == 422


async def test_a_refund_cannot_reverse_another_refund(client):
    ropa = await default_category(client, "Ropa", "expense")
    refund = await create_transaction(
        client, category_id=ropa["id"], amount="-500.00"
    )

    response = await client.post(
        f"/transactions/{refund['id']}/refund",
        json={"amount": "100.00", "date": TODAY.isoformat()},
    )

    assert response.status_code == 422


async def test_a_refund_of_an_expense_that_does_not_exist_returns_404(client):
    response = await client.post(
        f"/transactions/{UNKNOWN}/refund",
        json={"amount": "100.00", "date": TODAY.isoformat()},
    )

    assert response.status_code == 404


async def test_the_original_expense_is_never_deleted_by_a_refund(client):
    ropa = await default_category(client, "Ropa", "expense")
    purchase = await create_transaction(client, category_id=ropa["id"])

    await client.post(
        f"/transactions/{purchase['id']}/refund",
        json={"amount": "250.00", "date": TODAY.isoformat()},
    )

    assert (await client.get(f"/transactions/{purchase['id']}")).status_code == 200
