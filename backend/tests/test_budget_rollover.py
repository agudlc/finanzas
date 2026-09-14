"""A new month starts from the last month that had Budgets."""

from tests.test_budgets import budgets_for, create_budget

from tests.api import default_category


async def test_a_month_with_no_budgets_copies_the_previous_months(client):
    supermercado = await default_category(client, "Supermercado", "expense")
    ropa = await default_category(client, "Ropa", "expense")
    await create_budget(client, supermercado, amount="100000.00",
                        month="2026-02-01")
    await create_budget(client, ropa, amount="50.00", currency="USD",
                        month="2026-02-01")

    march = await budgets_for(client, "2026-03")

    assert {(b["category_id"], b["amount"], b["currency"]) for b in march} == {
        (supermercado["id"], "100000.00", "ARS"),
        (ropa["id"], "50.00", "USD"),
    }
    assert all(b["month"] == "2026-03-01" for b in march)


async def test_the_copies_are_budgets_of_their_own_month(client):
    supermercado = await default_category(client, "Supermercado", "expense")
    february = await create_budget(client, supermercado, month="2026-02-01")

    [march] = await budgets_for(client, "2026-03")

    assert march["id"] != february["id"]
    assert (await budgets_for(client, "2026-02"))[0]["id"] == february["id"]


async def test_the_copy_happens_once_and_is_then_the_users_own(client):
    supermercado = await default_category(client, "Supermercado", "expense")
    await create_budget(client, supermercado, amount="100000.00",
                        month="2026-02-01")
    [march] = await budgets_for(client, "2026-03")

    await client.patch(f"/budgets/{march['id']}", json={"amount": "120000.00"})
    again = await budgets_for(client, "2026-03")

    assert len(again) == 1
    assert again[0]["amount"] == "120000.00"


async def test_a_month_that_still_has_budgets_is_never_added_to(client):
    supermercado = await default_category(client, "Supermercado", "expense")
    ropa = await default_category(client, "Ropa", "expense")
    await create_budget(client, supermercado, month="2026-02-01")
    await create_budget(client, ropa, month="2026-02-01")
    await create_budget(client, supermercado, month="2026-03-01")

    march = await budgets_for(client, "2026-03")

    assert [b["category_id"] for b in march] == [supermercado["id"]]


async def test_the_latest_earlier_month_with_budgets_is_the_one_copied(client):
    supermercado = await default_category(client, "Supermercado", "expense")
    await create_budget(client, supermercado, amount="80000.00",
                        month="2025-12-01")
    await create_budget(client, supermercado, amount="100000.00",
                        month="2026-02-01")

    [march] = await budgets_for(client, "2026-03")

    assert march["amount"] == "100000.00"


async def test_a_future_month_is_not_copied_into_until_it_begins(client, clock):
    supermercado = await default_category(client, "Supermercado", "expense")
    await create_budget(client, supermercado, month="2026-03-01")

    assert await budgets_for(client, "2026-04") == []

    clock.date = clock.date.replace(month=4, day=1)
    assert len(await budgets_for(client, "2026-04")) == 1


async def test_a_month_with_nothing_before_it_stays_empty(client):
    assert await budgets_for(client, "2026-03") == []


async def test_the_month_defaults_to_the_one_being_lived(client):
    supermercado = await default_category(client, "Supermercado", "expense")
    await create_budget(client, supermercado, month="2026-03-01")

    [budget] = await budgets_for(client)

    assert budget["month"] == "2026-03-01"


async def test_emptying_a_month_is_a_decision_not_an_invitation_to_copy(client):
    """Once a month has been started, nothing is ever copied into it again."""
    supermercado = await default_category(client, "Supermercado", "expense")
    await create_budget(client, supermercado, month="2026-02-01")
    [march] = await budgets_for(client, "2026-03")

    await client.delete(f"/budgets/{march['id']}")

    assert await budgets_for(client, "2026-03") == []


async def test_a_budget_set_by_hand_starts_the_month_on_its_own(client):
    """A month the user opened themselves is never topped up from the last one."""
    supermercado = await default_category(client, "Supermercado", "expense")
    ropa = await default_category(client, "Ropa", "expense")
    await create_budget(client, supermercado, month="2026-02-01")
    await create_budget(client, ropa, month="2026-02-01")

    await create_budget(client, supermercado, amount="70000.00", month="2026-03-01")
    march = await budgets_for(client, "2026-03")

    assert [b["category_id"] for b in march] == [supermercado["id"]]
    assert march[0]["amount"] == "70000.00"
