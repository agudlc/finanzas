"""An Installment Purchase recorded once, carried by its cuotas."""

from decimal import Decimal

from tests.api import default_category
from tests.conftest import TODAY

UNKNOWN = "00000000-0000-0000-0000-000000000000"


def purchase_body(**fields) -> dict:
    return {
        "description": "Notebook",
        "total_amount": "600000.00",
        "installments": 6,
        "purchase_date": "2026-03-10",
        **fields,
    }


async def create_purchase(client, **fields) -> dict:
    if "category_id" not in fields:
        fields["category_id"] = (
            await default_category(client, "Ocio", "expense")
        )["id"]
    response = await client.post(
        "/installment-purchases/", json=purchase_body(**fields)
    )
    response.raise_for_status()
    return response.json()


async def test_a_purchase_generates_one_expense_per_cuota(client):
    purchase = await create_purchase(client)

    assert len(purchase["cuotas"]) == 6
    assert [c["installment_number"] for c in purchase["cuotas"]] == [1, 2, 3, 4, 5, 6]
    assert all(c["type"] == "expense" for c in purchase["cuotas"])
    assert all(c["installment_purchase_id"] == purchase["id"]
               for c in purchase["cuotas"])


async def test_the_first_cuota_falls_in_the_purchase_month(client):
    purchase = await create_purchase(client)

    assert [c["date"] for c in purchase["cuotas"]] == [
        "2026-03-10", "2026-04-10", "2026-05-10",
        "2026-06-10", "2026-07-10", "2026-08-10",
    ]


async def test_a_day_a_shorter_month_does_not_have_lands_on_its_last_day(client):
    purchase = await create_purchase(
        client, purchase_date="2026-01-31", installments=3
    )

    assert [c["date"] for c in purchase["cuotas"]] == [
        "2026-01-31", "2026-02-28", "2026-03-31"
    ]


async def test_the_cuotas_add_up_to_exactly_the_total(client):
    purchase = await create_purchase(
        client, total_amount="100.00", installments=3
    )

    amounts = [Decimal(c["amount"]) for c in purchase["cuotas"]]
    assert sum(amounts) == Decimal("100.00")
    assert amounts == [Decimal("33.34"), Decimal("33.33"), Decimal("33.33")], (
        "the rounding cents ride on the first cuota"
    )


async def test_every_cuota_starts_as_an_estimate(client):
    purchase = await create_purchase(client)

    assert all(c["amount_status"] == "estimated" for c in purchase["cuotas"])


async def test_each_usd_cuota_carries_its_own_estimated_exchange_rate(client):
    purchase = await create_purchase(
        client,
        currency="USD",
        total_amount="600.00",
        installments=3,
        purchase_date=TODAY.isoformat(),
    )

    assert all(c["currency"] == "USD" for c in purchase["cuotas"])
    assert all(c["exchange_rate"] == "1500.0000" for c in purchase["cuotas"])
    assert all(c["exchange_rate_status"] == "estimated" for c in purchase["cuotas"])
    assert all(c["exchange_rate_type"] == "card" for c in purchase["cuotas"])


async def test_an_ars_purchase_gives_its_cuotas_no_exchange_rate(client):
    purchase = await create_purchase(client)

    assert all(c["exchange_rate"] is None for c in purchase["cuotas"])


async def test_editing_a_cuotas_amount_confirms_it(client):
    purchase = await create_purchase(client)
    cuota = purchase["cuotas"][0]

    response = await client.patch(
        f"/transactions/{cuota['id']}", json={"amount": "105000.00"}
    )

    assert response.status_code == 200
    assert response.json()["amount"] == "105000.00"
    assert response.json()["amount_status"] == "confirmed"


async def test_the_other_cuotas_stay_estimates_when_one_is_confirmed(client):
    purchase = await create_purchase(client)
    await client.patch(
        f"/transactions/{purchase['cuotas'][0]['id']}", json={"amount": "105000.00"}
    )

    read = (await client.get(f"/installment-purchases/{purchase['id']}")).json()

    assert [c["amount_status"] for c in read["cuotas"]] == [
        "confirmed", "estimated", "estimated", "estimated", "estimated", "estimated"
    ]


async def test_deleting_a_purchase_deletes_all_its_cuotas(client):
    purchase = await create_purchase(client)

    response = await client.delete(f"/installment-purchases/{purchase['id']}")

    assert response.status_code == 204
    assert (await client.get("/transactions/")).json() == []
    assert (
        await client.get(f"/installment-purchases/{purchase['id']}")
    ).status_code == 404


async def test_a_purchase_uses_an_expense_category(client):
    sueldo = await default_category(client, "Sueldo", "income")

    response = await client.post(
        "/installment-purchases/", json=purchase_body(category_id=sueldo["id"])
    )

    assert response.status_code == 422
    assert (await client.get("/installment-purchases/")).json() == [], (
        "the purchase is not left behind without its cuotas"
    )


async def test_a_purchase_that_does_not_exist_returns_404(client):
    assert (
        await client.get(f"/installment-purchases/{UNKNOWN}")
    ).status_code == 404
    assert (
        await client.delete(f"/installment-purchases/{UNKNOWN}")
    ).status_code == 404
