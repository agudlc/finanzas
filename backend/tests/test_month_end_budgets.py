"""
The Review that keeps Budgets up with prices.

A new month still starts from a copy of the last one's Budgets; on the 1st the
`month_end` Review proposes moving each of those copies by the latest published
IPC. TODAY is the 15th of March 2026 and the fake series ends in February, so
"last month" is February and "the latest published IPC" is February's 1,659%.
"""

from tests.api import create_transaction, default_category
from tests.test_budgets import budgets_for, create_budget
from tests.test_reviews import inbox, run_review, suggestions
from tests.test_scheduled_reviews import scheduled
from tests.test_suggestions import accept


async def budget_suggestions(client) -> list[dict]:
    """What is waiting about Budgets, ignoring any Recurring Expense."""
    proposed = await suggestions(client)
    return [one for one in proposed if one["kind"] == "set_budget"]


async def last_month(client, category, amount="100000.00", **fields) -> dict:
    """A Budget for February, the month March's Review reads."""
    return await create_budget(
        client, category, amount=amount, month="2026-02-01", **fields
    )


async def proposed_for(client, category, **fields) -> dict:
    """The one proposal March's Review makes for a Category with a Budget."""
    await last_month(client, category, **fields)
    [one] = await budget_suggestions(client)
    return one


async def test_last_months_budget_is_proposed_moved_by_inflation(client):
    supermercado = await default_category(client, "Supermercado", "expense")

    proposal = await proposed_for(client, supermercado, amount="100000.00")

    assert proposal["payload"] == {
        "category_id": supermercado["id"],
        "month": "2026-03-01",
        "amount": "102000.00",
        "currency": "ARS",
    }
    assert proposal["month"] == "2026-03-01"
    assert proposal["status"] == "pending"


async def test_the_proposed_amount_is_rounded_to_the_nearest_thousand(client):
    """200.000 × 1,01659 is 203.318, and a Budget is not a multiplication."""
    supermercado = await default_category(client, "Supermercado", "expense")

    proposal = await proposed_for(client, supermercado, amount="200000.00")

    assert proposal["payload"]["amount"] == "203000.00"


async def test_a_proposal_expires_at_the_end_of_the_month_it_is_for(client):
    supermercado = await default_category(client, "Supermercado", "expense")

    proposal = await proposed_for(client, supermercado, amount="100000.00")

    assert proposal["expires_on"] == "2026-03-31"


async def test_a_usd_budget_is_never_moved_by_the_argentine_ipc(client):
    ropa = await default_category(client, "Ropa", "expense")
    await last_month(client, ropa, amount="50.00", currency="USD")

    assert await budget_suggestions(client) == []


async def test_a_month_of_inflation_too_small_to_show_proposes_nothing(client):
    """1.000 × 1,01659 rounds back to 1.000: there is nothing to accept."""
    supermercado = await default_category(client, "Supermercado", "expense")
    await last_month(client, supermercado, amount="1000.00")

    assert await budget_suggestions(client) == []


async def test_an_ipc_nobody_published_proposes_nothing(client, index_source):
    index_source.fail_with("datos.gob.ar is down")
    supermercado = await default_category(client, "Supermercado", "expense")
    await last_month(client, supermercado)

    assert await budget_suggestions(client) == []
    assert all(one["status"] == "done" for one in await scheduled(client)), (
        "an index nobody published is not a failure"
    )


async def test_the_rationale_shows_the_month_against_its_budget(client):
    supermercado = await default_category(client, "Supermercado", "expense")
    await create_transaction(
        client,
        category_id=supermercado["id"],
        amount="92000.00",
        date="2026-02-20",
    )

    proposal = await proposed_for(client, supermercado, amount="100000.00")

    assert "92.000,00" in proposal["rationale"], "what February actually cost"
    assert "100.000,00" in proposal["rationale"], "the Budget it ran against"
    assert "IPC de febrero de 2026" in proposal["rationale"]
    assert "1,659%" in proposal["rationale"]


async def test_accepting_moves_the_budget_the_copy_already_created(client):
    supermercado = await default_category(client, "Supermercado", "expense")
    proposal = await proposed_for(client, supermercado, amount="100000.00")
    [copied] = await budgets_for(client, "2026-03")

    response = await accept(client, proposal["id"])

    assert response.status_code == 200
    [march] = await budgets_for(client, "2026-03")
    assert march["id"] == copied["id"], "the Budget moved, it was not replaced"
    assert march["amount"] == "102000.00"
    assert response.json()["result_id"] == march["id"]


async def test_accepting_one_proposal_leaves_the_rest_of_the_copy(client):
    """Accepting before the month was ever opened still copies it in first."""
    supermercado = await default_category(client, "Supermercado", "expense")
    ropa = await default_category(client, "Ropa", "expense")
    await last_month(client, ropa, amount="1000.00")
    proposal = await proposed_for(client, supermercado, amount="100000.00")

    await accept(client, proposal["id"])

    march = await budgets_for(client, "2026-03")
    assert {one["category_id"]: one["amount"] for one in march} == {
        supermercado["id"]: "102000.00",
        ropa["id"]: "1000.00",
    }


async def test_an_edited_amount_is_what_gets_set(client):
    supermercado = await default_category(client, "Supermercado", "expense")
    proposal = await proposed_for(client, supermercado, amount="100000.00")

    response = await accept(client, proposal["id"], amount="110000.00")

    assert response.status_code == 200
    assert (await budgets_for(client, "2026-03"))[0]["amount"] == "110000.00"


async def test_an_amount_the_app_would_refuse_by_hand_is_refused_here(client):
    supermercado = await default_category(client, "Supermercado", "expense")
    proposal = await proposed_for(client, supermercado, amount="100000.00")

    response = await accept(client, proposal["id"], amount="0.00")

    assert response.status_code == 422
    assert (await budgets_for(client, "2026-03"))[0]["amount"] == "100000.00"


async def test_an_income_category_has_no_budget_to_set(client):
    supermercado = await default_category(client, "Supermercado", "expense")
    sueldo = await default_category(client, "Sueldo", "income")
    proposal = await proposed_for(client, supermercado, amount="100000.00")

    response = await accept(client, proposal["id"], category_id=sueldo["id"])

    assert response.status_code == 422
    assert "income Category" in response.json()["detail"]


async def test_the_month_end_review_runs_without_anybody_asking(client):
    supermercado = await default_category(client, "Supermercado", "expense")
    await last_month(client, supermercado)

    await inbox(client)

    triggers = [one["trigger"] for one in await scheduled(client)]
    assert sorted(triggers) == ["month_end", "recurring_monthly"]
    assert all(one["status"] == "done" for one in await scheduled(client))


async def test_opening_the_inbox_again_proposes_nothing_twice(client):
    supermercado = await default_category(client, "Supermercado", "expense")
    await last_month(client, supermercado)

    await inbox(client)
    await inbox(client)

    assert len(await budget_suggestions(client)) == 1
    assert len(await scheduled(client, "month_end")) == 1


async def test_a_manual_review_proposes_the_months_budgets_too(client):
    supermercado = await default_category(client, "Supermercado", "expense")
    await last_month(client, supermercado)

    await run_review(client)

    assert len(await budget_suggestions(client)) == 1, "and only once"


async def test_next_month_asks_again_from_the_month_that_ended(client, clock):
    supermercado = await default_category(client, "Supermercado", "expense")
    proposal = await proposed_for(client, supermercado, amount="100000.00")
    await accept(client, proposal["id"])

    clock.date = clock.date.replace(month=4, day=1)
    [april] = await budget_suggestions(client)

    assert april["month"] == "2026-04-01"
    assert april["payload"]["amount"] == "104000.00", (
        "102.000 moved by February's IPC, the newest the series carries"
    )


async def test_a_budget_the_user_already_moved_is_not_proposed_again(client):
    """What the month already has is the amount a proposal has to beat."""
    supermercado = await default_category(client, "Supermercado", "expense")
    await last_month(client, supermercado)
    [march] = await budgets_for(client, "2026-03")

    await client.patch(f"/budgets/{march['id']}", json={"amount": "102000.00"})

    assert await budget_suggestions(client) == []


async def test_a_dollar_expense_counts_through_its_own_exchange_rate(client):
    """A Review converts through what is stored, never through dolarapi."""
    supermercado = await default_category(client, "Supermercado", "expense")
    await create_transaction(
        client,
        category_id=supermercado["id"],
        amount="50.00",
        currency="USD",
        exchange_rate="1200.00",
        exchange_rate_type="blue",
        exchange_rate_status="estimated",
        date="2026-02-20",
    )

    proposal = await proposed_for(client, supermercado)

    assert "60.000,00" in proposal["rationale"], "50 dólares al blue de febrero"
