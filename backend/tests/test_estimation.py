"""A USD Transaction gets its Exchange Rate without the user looking it up."""

from app.models.enums import RateType
from tests.api import create_transaction, default_category, transaction_body
from tests.conftest import TODAY


async def test_a_usd_transaction_gets_an_estimated_rate_from_the_default_type(client):
    supermercado = await default_category(client, "Supermercado", "expense")

    created = await create_transaction(
        client,
        category_id=supermercado["id"],
        currency="USD",
        amount="100.00",
        date=TODAY.isoformat(),
    )

    assert created["exchange_rate"] == "1500.0000", "the card rate, the default"
    assert created["exchange_rate_type"] == "card"
    assert created["exchange_rate_status"] == "estimated"


async def test_the_default_rate_type_from_settings_is_the_one_estimated(client):
    await client.patch("/settings/", json={"default_rate_type": "blue"})
    supermercado = await default_category(client, "Supermercado", "expense")

    created = await create_transaction(
        client,
        category_id=supermercado["id"],
        currency="USD",
        amount="100.00",
        date=TODAY.isoformat(),
    )

    assert created["exchange_rate_type"] == "blue"
    assert created["exchange_rate"] == "1200.0000"


async def test_the_rate_type_can_be_overridden_on_one_transaction(client):
    supermercado = await default_category(client, "Supermercado", "expense")

    created = await create_transaction(
        client,
        category_id=supermercado["id"],
        currency="USD",
        amount="100.00",
        date=TODAY.isoformat(),
        exchange_rate_type="mep",
    )

    assert created["exchange_rate_type"] == "mep"
    assert created["exchange_rate"] == "1100.0000"
    assert created["exchange_rate_status"] == "estimated"


async def test_a_rate_typed_by_the_user_is_kept_as_given(client):
    supermercado = await default_category(client, "Supermercado", "expense")

    created = await create_transaction(
        client,
        category_id=supermercado["id"],
        currency="USD",
        amount="100.00",
        date=TODAY.isoformat(),
        exchange_rate="1777.00",
        exchange_rate_type="manual",
        exchange_rate_status="confirmed",
    )

    assert created["exchange_rate"] == "1777.0000"
    assert created["exchange_rate_status"] == "confirmed"


async def test_a_future_date_is_estimated_with_todays_rate(client):
    supermercado = await default_category(client, "Supermercado", "expense")

    created = await create_transaction(
        client,
        category_id=supermercado["id"],
        currency="USD",
        amount="100.00",
        date="2026-09-10",
    )

    assert created["exchange_rate"] == "1500.0000"
    assert created["exchange_rate_status"] == "estimated"


async def test_a_past_date_is_estimated_from_the_stored_snapshot(client, clock,
                                                                 rate_source):
    supermercado = await default_category(client, "Supermercado", "expense")
    clock.date = TODAY.replace(day=10)
    await client.get("/settings/rate", params={"rate_type": "card"})

    clock.date = TODAY
    rate_source.rates.pop(RateType.card), "the source no longer answers for today"

    created = await create_transaction(
        client,
        category_id=supermercado["id"],
        currency="USD",
        amount="100.00",
        date="2026-03-12",
    )

    assert created["exchange_rate"] == "1500.0000"


async def test_a_transaction_fails_when_no_rate_can_be_established(client,
                                                                   rate_source):
    supermercado = await default_category(client, "Supermercado", "expense")
    rate_source.rates.clear()

    response = await client.post(
        "/transactions/",
        json=transaction_body(
            category_id=supermercado["id"],
            currency="USD",
            amount="100.00",
            date=TODAY.isoformat(),
        ),
    )

    assert response.status_code == 422
    assert "cannot be estimated" in response.json()["detail"]
    assert (await client.get("/transactions/")).json() == [], "nothing was guessed"


async def test_a_past_date_with_no_snapshot_is_never_given_todays_rate(client):
    """Stamping an old purchase with today's rate would rewrite the past."""
    supermercado = await default_category(client, "Supermercado", "expense")

    response = await client.post(
        "/transactions/",
        json=transaction_body(
            category_id=supermercado["id"],
            currency="USD",
            amount="100.00",
            date="2026-03-10",
        ),
    )

    assert response.status_code == 422
    assert "no card rate is known for 2026-03-10" in response.json()["detail"]
    assert (await client.get("/transactions/")).json() == []


async def test_an_ars_transaction_is_never_given_a_rate(client):
    supermercado = await default_category(client, "Supermercado", "expense")

    created = await create_transaction(client, category_id=supermercado["id"])

    assert created["exchange_rate"] is None
    assert created["exchange_rate_type"] is None
