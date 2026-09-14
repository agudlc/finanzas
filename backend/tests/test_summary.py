"""The dashboard's month, in one read."""

from tests.api import create_transaction, default_category
from tests.conftest import TODAY
from tests.test_budgets import create_budget


async def test_the_monthly_result_is_income_minus_expenses(client):
    sueldo = await default_category(client, "Sueldo", "income")
    supermercado = await default_category(client, "Supermercado", "expense")
    await create_transaction(client, type="income", category_id=sueldo["id"],
                             amount="1000000.00", date="2026-03-01")
    await create_transaction(client, category_id=supermercado["id"],
                             amount="300000.00", date="2026-03-05")

    summary = (await client.get("/summary/", params={"month": "2026-03"})).json()

    assert summary["total_income"] == "1000000.00"
    assert summary["total_expenses"] == "300000.00"
    assert summary["monthly_result"] == "700000.00"
    assert summary["currency"] == "ARS"


async def test_the_monthly_result_can_be_negative(client):
    supermercado = await default_category(client, "Supermercado", "expense")
    await create_transaction(client, category_id=supermercado["id"],
                             amount="300000.00", date="2026-03-05")

    summary = (await client.get("/summary/", params={"month": "2026-03"})).json()

    assert summary["monthly_result"] == "-300000.00"


async def test_only_the_months_own_transactions_are_counted(client):
    supermercado = await default_category(client, "Supermercado", "expense")
    await create_transaction(client, category_id=supermercado["id"],
                             amount="300000.00", date="2026-02-28")
    await create_transaction(client, category_id=supermercado["id"],
                             amount="100000.00", date="2026-03-01")

    summary = (await client.get("/summary/", params={"month": "2026-03"})).json()

    assert summary["total_expenses"] == "100000.00"


async def test_usd_transactions_are_converted_into_the_display_currency(client):
    ropa = await default_category(client, "Ropa", "expense")
    await create_transaction(client, category_id=ropa["id"], currency="USD",
                             amount="100.00", date=TODAY.isoformat())

    summary = (await client.get("/summary/", params={"month": "2026-03"})).json()

    assert summary["total_expenses"] == "150000.00", "at the stored card rate"


async def test_the_dashboard_can_be_read_in_dollars_instead(client):
    sueldo = await default_category(client, "Sueldo", "income")
    ropa = await default_category(client, "Ropa", "expense")
    await client.patch("/settings/", json={"display_currency": "USD"})
    await create_transaction(client, type="income", category_id=sueldo["id"],
                             amount="1500000.00", date="2026-03-01")
    await create_transaction(client, category_id=ropa["id"], currency="USD",
                             amount="200.00", date=TODAY.isoformat())

    summary = (await client.get("/summary/", params={"month": "2026-03"})).json()

    assert summary["currency"] == "USD"
    assert summary["total_income"] == "1000.00", "1.5M ARS at the card rate"
    assert summary["total_expenses"] == "200.00", "already dollars"
    assert summary["monthly_result"] == "800.00"


async def test_spending_is_broken_down_by_category_biggest_first(client):
    supermercado = await default_category(client, "Supermercado", "expense")
    ropa = await default_category(client, "Ropa", "expense")
    await create_transaction(client, category_id=supermercado["id"],
                             amount="30000.00", date="2026-03-05")
    await create_transaction(client, category_id=supermercado["id"],
                             amount="20000.00", date="2026-03-06")
    await create_transaction(client, category_id=ropa["id"], amount="90000.00",
                             date="2026-03-07")

    summary = (await client.get("/summary/", params={"month": "2026-03"})).json()

    assert [(s["name"], s["total"]) for s in summary["by_category"]] == [
        ("Ropa", "90000.00"),
        ("Supermercado", "50000.00"),
    ]
    assert summary["by_category"][0]["color"] == ropa["color"]


async def test_income_is_not_a_slice_of_the_spending_donut(client):
    sueldo = await default_category(client, "Sueldo", "income")
    await create_transaction(client, type="income", category_id=sueldo["id"],
                             amount="1000000.00", date="2026-03-01")

    summary = (await client.get("/summary/", params={"month": "2026-03"})).json()

    assert summary["by_category"] == []


async def test_a_refund_takes_itself_off_its_category(client):
    supermercado = await default_category(client, "Supermercado", "expense")
    purchase = await create_transaction(client, category_id=supermercado["id"],
                                        amount="30000.00", date="2026-03-05")
    await client.post(
        f"/transactions/{purchase['id']}/refund",
        json={"amount": "10000.00", "date": "2026-03-07"},
    )

    summary = (await client.get("/summary/", params={"month": "2026-03"})).json()

    assert summary["by_category"][0]["total"] == "20000.00"
    assert summary["total_expenses"] == "20000.00"


async def test_the_dashboard_carries_this_months_budgets(client):
    supermercado = await default_category(client, "Supermercado", "expense")
    await create_budget(client, supermercado, amount="100000.00")
    await create_transaction(client, category_id=supermercado["id"],
                             amount="90000.00", date="2026-03-05")

    summary = (await client.get("/summary/", params={"month": "2026-03"})).json()

    [budget] = summary["budgets"]
    assert budget["spent"] == "90000.00"
    assert budget["state"] == "warning"
    assert budget["pace"] is not None


async def test_the_dashboard_carries_the_most_recent_activity(client):
    supermercado = await default_category(client, "Supermercado", "expense")
    for day in range(1, 13):
        await create_transaction(client, category_id=supermercado["id"],
                                 date=f"2026-03-{day:02d}")

    summary = (await client.get("/summary/", params={"month": "2026-03"})).json()

    assert len(summary["recent"]) == 10
    assert summary["recent"][0]["date"] == "2026-03-12", "newest first"


async def test_the_donut_looks_back_on_its_own(client):
    supermercado = await default_category(client, "Supermercado", "expense")
    await create_transaction(client, category_id=supermercado["id"],
                             amount="70000.00", date="2026-01-20")

    donut = (
        await client.get("/summary/by-category", params={"month": "2026-01"})
    ).json()

    assert donut["month"] == "2026-01-01"
    assert [(s["name"], s["total"]) for s in donut["categories"]] == [
        ("Supermercado", "70000.00")
    ]


async def test_the_summary_defaults_to_the_month_being_lived(client):
    summary = (await client.get("/summary/")).json()

    assert summary["month"] == "2026-03-01"
