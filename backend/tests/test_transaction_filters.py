"""The Transactions list, narrowed down to what the screen is showing."""

from tests.api import create_transaction, default_category


async def test_transactions_are_listed_newest_first(client):
    supermercado = await default_category(client, "Supermercado", "expense")
    older = await create_transaction(client, category_id=supermercado["id"],
                                     date="2026-03-01")
    newer = await create_transaction(client, category_id=supermercado["id"],
                                     date="2026-03-14")

    listed = (await client.get("/transactions/")).json()

    assert [t["id"] for t in listed] == [newer["id"], older["id"]]


async def test_a_month_holds_only_its_own_transactions(client):
    supermercado = await default_category(client, "Supermercado", "expense")
    march = await create_transaction(client, category_id=supermercado["id"],
                                     date="2026-03-31")
    await create_transaction(client, category_id=supermercado["id"],
                             date="2026-04-01")
    await create_transaction(client, category_id=supermercado["id"],
                             date="2026-02-28")

    listed = (await client.get("/transactions/", params={"month": "2026-03"})).json()

    assert [t["id"] for t in listed] == [march["id"]]


async def test_a_month_must_be_written_as_year_and_month(client):
    response = await client.get("/transactions/", params={"month": "marzo"})

    assert response.status_code == 422


async def test_todays_transactions_are_asked_for_by_date(client):
    supermercado = await default_category(client, "Supermercado", "expense")
    today = await create_transaction(client, category_id=supermercado["id"],
                                     date="2026-03-15")
    await create_transaction(client, category_id=supermercado["id"],
                             date="2026-03-14")

    listed = (
        await client.get("/transactions/", params={"date": "2026-03-15"})
    ).json()

    assert [t["id"] for t in listed] == [today["id"]]


async def test_the_list_is_filtered_by_type_category_and_currency(client):
    supermercado = await default_category(client, "Supermercado", "expense")
    ropa = await default_category(client, "Ropa", "expense")
    sueldo = await default_category(client, "Sueldo", "income")
    salary = await create_transaction(client, category_id=sueldo["id"],
                                      type="income")
    in_pesos = await create_transaction(client, category_id=supermercado["id"])
    in_dollars = await create_transaction(client, category_id=ropa["id"],
                                          currency="USD", amount="50.00")

    by_type = (await client.get("/transactions/", params={"type": "expense"})).json()
    assert {t["id"] for t in by_type} == {in_pesos["id"], in_dollars["id"]}

    by_category = (
        await client.get("/transactions/", params={"category_id": ropa["id"]})
    ).json()
    assert [t["id"] for t in by_category] == [in_dollars["id"]]

    by_currency = (
        await client.get("/transactions/", params={"currency": "ARS"})
    ).json()
    assert {t["id"] for t in by_currency} == {in_pesos["id"], salary["id"]}


async def test_the_recent_activity_list_can_be_cut_short(client):
    supermercado = await default_category(client, "Supermercado", "expense")
    for day in range(1, 6):
        await create_transaction(client, category_id=supermercado["id"],
                                 date=f"2026-03-0{day}")

    listed = (await client.get("/transactions/", params={"limit": 3})).json()

    assert len(listed) == 3
    assert [t["date"] for t in listed] == ["2026-03-05", "2026-03-04", "2026-03-03"]
