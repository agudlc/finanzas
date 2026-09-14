"""Budgets, judged against Pace, loud when they break."""

from tests.api import create_transaction, default_category
from tests.conftest import TODAY

UNKNOWN = "00000000-0000-0000-0000-000000000000"


async def create_budget(client, category, amount="100000.00", month="2026-03-01",
                        currency="ARS") -> dict:
    response = await client.post(
        "/budgets/",
        json={
            "category_id": category["id"],
            "amount": amount,
            "currency": currency,
            "month": month,
        },
    )
    response.raise_for_status()
    return response.json()


async def budgets_for(client, month: str | None = None) -> list[dict]:
    params = {"month": month} if month else {}
    response = await client.get("/budgets/", params=params)
    response.raise_for_status()
    return response.json()


async def test_a_budget_is_set_for_a_category_and_a_month(client):
    supermercado = await default_category(client, "Supermercado", "expense")

    budget = await create_budget(client, supermercado)

    assert budget["category_id"] == supermercado["id"]
    assert budget["amount"] == "100000.00"
    assert budget["month"] == "2026-03-01"


async def test_a_month_is_stored_as_its_first_day_whichever_day_is_given(client):
    supermercado = await default_category(client, "Supermercado", "expense")

    budget = await create_budget(client, supermercado, month="2026-03-27")

    assert budget["month"] == "2026-03-01"


async def test_a_category_has_only_one_budget_per_month(client):
    supermercado = await default_category(client, "Supermercado", "expense")
    await create_budget(client, supermercado)

    response = await client.post(
        "/budgets/",
        json={
            "category_id": supermercado["id"],
            "amount": "50000.00",
            "currency": "ARS",
            "month": "2026-03-01",
        },
    )

    assert response.status_code == 409
    assert len(await budgets_for(client, "2026-03")) == 1


async def test_the_same_category_can_be_budgeted_in_another_month(client):
    supermercado = await default_category(client, "Supermercado", "expense")
    await create_budget(client, supermercado, month="2026-03-01")

    budget = await create_budget(client, supermercado, month="2026-04-01")

    assert budget["month"] == "2026-04-01"


async def test_an_income_category_has_no_budget(client):
    sueldo = await default_category(client, "Sueldo", "income")

    response = await client.post(
        "/budgets/",
        json={
            "category_id": sueldo["id"],
            "amount": "100000.00",
            "currency": "ARS",
            "month": "2026-03-01",
        },
    )

    assert response.status_code == 422


async def test_a_budget_is_edited_and_removed(client):
    supermercado = await default_category(client, "Supermercado", "expense")
    budget = await create_budget(client, supermercado)

    edited = await client.patch(
        f"/budgets/{budget['id']}", json={"amount": "150000.00"}
    )
    assert edited.status_code == 200
    assert edited.json()["amount"] == "150000.00"

    assert (await client.delete(f"/budgets/{budget['id']}")).status_code == 204
    assert await budgets_for(client, "2026-03") == []


async def test_a_budget_that_does_not_exist_returns_404(client):
    assert (
        await client.patch(f"/budgets/{UNKNOWN}", json={"amount": "1.00"})
    ).status_code == 404
    assert (await client.delete(f"/budgets/{UNKNOWN}")).status_code == 404


async def test_progress_counts_the_months_spending_in_that_category(client):
    supermercado = await default_category(client, "Supermercado", "expense")
    ropa = await default_category(client, "Ropa", "expense")
    await create_budget(client, supermercado)
    await create_transaction(client, category_id=supermercado["id"],
                             amount="30000.00", date="2026-03-05")
    await create_transaction(client, category_id=supermercado["id"],
                             amount="10000.00", date="2026-03-06")
    await create_transaction(client, category_id=ropa["id"], amount="90000.00",
                             date="2026-03-06")
    await create_transaction(client, category_id=supermercado["id"],
                             amount="70000.00", date="2026-04-01")

    [budget] = [b for b in await budgets_for(client, "2026-03")
                if b["category_id"] == supermercado["id"]]

    assert budget["spent"] == "40000.00"
    assert budget["percentage"] == "40.00"


async def test_a_refund_is_subtracted_from_what_the_category_cost(client):
    supermercado = await default_category(client, "Supermercado", "expense")
    await create_budget(client, supermercado)
    purchase = await create_transaction(client, category_id=supermercado["id"],
                                        amount="30000.00", date="2026-03-05")
    await client.post(
        f"/transactions/{purchase['id']}/refund",
        json={"amount": "5000.00", "date": "2026-03-07"},
    )

    [budget] = await budgets_for(client, "2026-03")

    assert budget["spent"] == "25000.00"


async def test_usd_spending_is_converted_into_the_budgets_currency(client):
    ropa = await default_category(client, "Ropa", "expense")
    await create_budget(client, ropa, amount="300000.00")
    await create_transaction(client, category_id=ropa["id"], currency="USD",
                             amount="100.00", date=TODAY.isoformat())

    [budget] = await budgets_for(client, "2026-03")

    assert budget["spent"] == "150000.00", "100 USD at the stored card rate"
    assert budget["percentage"] == "50.00"


async def test_ars_spending_is_converted_into_a_usd_budget(client):
    ropa = await default_category(client, "Ropa", "expense")
    await create_budget(client, ropa, amount="200.00", currency="USD")
    await create_transaction(client, category_id=ropa["id"], amount="150000.00",
                             date="2026-03-05")

    [budget] = await budgets_for(client, "2026-03")

    assert budget["spent"] == "100.00", "150.000 ARS at the default card rate"


async def test_pace_is_the_share_of_the_budget_that_today_has_earned(client, clock):
    supermercado = await default_category(client, "Supermercado", "expense")
    await create_budget(client, supermercado, amount="310000.00")

    [budget] = await budgets_for(client, "2026-03")

    assert budget["pace"] == "150000.00", "the 15th of a 31-day month"


async def test_a_past_month_has_no_pace(client):
    supermercado = await default_category(client, "Supermercado", "expense")
    await create_budget(client, supermercado, month="2026-02-01")

    [budget] = await budgets_for(client, "2026-02")

    assert budget["pace"] is None


async def test_a_future_month_has_no_pace(client):
    supermercado = await default_category(client, "Supermercado", "expense")
    await create_budget(client, supermercado, month="2026-04-01")

    [budget] = await budgets_for(client, "2026-04")

    assert budget["pace"] is None


async def test_a_budget_within_its_pace_is_on_pace(client):
    supermercado = await default_category(client, "Supermercado", "expense")
    await create_budget(client, supermercado, amount="310000.00")
    await create_transaction(client, category_id=supermercado["id"],
                             amount="100000.00", date="2026-03-05")

    [budget] = await budgets_for(client, "2026-03")

    assert budget["state"] == "on_pace"


async def test_a_budget_spent_faster_than_its_pace_is_ahead_of_pace(client):
    supermercado = await default_category(client, "Supermercado", "expense")
    await create_budget(client, supermercado, amount="310000.00")
    await create_transaction(client, category_id=supermercado["id"],
                             amount="200000.00", date="2026-03-05")

    [budget] = await budgets_for(client, "2026-03")

    assert budget["state"] == "ahead_of_pace", "200k spent against a 150k Pace"


async def test_a_budget_at_eighty_percent_is_a_warning(client):
    supermercado = await default_category(client, "Supermercado", "expense")
    await create_budget(client, supermercado, amount="100000.00")
    await create_transaction(client, category_id=supermercado["id"],
                             amount="80000.00", date="2026-03-05")

    [budget] = await budgets_for(client, "2026-03")

    assert budget["state"] == "warning"


async def test_a_budget_spent_past_its_amount_is_over(client):
    supermercado = await default_category(client, "Supermercado", "expense")
    await create_budget(client, supermercado, amount="100000.00")
    await create_transaction(client, category_id=supermercado["id"],
                             amount="120000.00", date="2026-03-05")

    [budget] = await budgets_for(client, "2026-03")

    assert budget["state"] == "over"
    assert budget["percentage"] == "120.00", "never capped at a hundred"


async def test_going_over_a_budget_never_blocks_the_expense(client):
    supermercado = await default_category(client, "Supermercado", "expense")
    await create_budget(client, supermercado, amount="1000.00")

    response = await client.post(
        "/transactions/",
        json={
            "amount": "999999.00",
            "currency": "ARS",
            "type": "expense",
            "category_id": supermercado["id"],
            "date": "2026-03-05",
        },
    )

    assert response.status_code == 201, "shame, not blocking"


async def test_a_past_month_is_judged_on_what_it_finally_cost(client):
    supermercado = await default_category(client, "Supermercado", "expense")
    await create_budget(client, supermercado, amount="100000.00",
                        month="2026-02-01")
    await create_transaction(client, category_id=supermercado["id"],
                             amount="20000.00", date="2026-02-03")

    [budget] = await budgets_for(client, "2026-02")

    assert budget["state"] == "on_pace", "a fifth spent, and the month is closed"
