"""
The Review a Budget asks for when its spending goes past the limit.

Going over is shown loudly and never blocked, and this is the loudest part of
it: the agent is asked what happened to that Category. It fires once per
Budget, whichever write pushed the spending over — a quick add, an edit to
something already recorded, a file loaded, a proposal accepted — and the
spending after it is already over says nothing more.
"""

from tests.api import create_transaction, default_category
from tests.api_imports import confirm_body, create_profile
from tests.test_budgets import create_budget
from tests.test_import_confirm import categorised_preview
from tests.test_installments import create_purchase
from tests.test_reviews import inbox
from tests.test_scheduled_reviews import reviews
from tests.test_suggestions import accept, proposed


async def exceeded_reviews(client) -> list[dict]:
    """The Reviews a Budget over its limit asked for, newest first."""
    return [
        one for one in await reviews(client) if one["trigger"] == "budget_exceeded"
    ]


async def tight_budget(client, amount="10000.00") -> dict:
    """A Supermercado Budget one ordinary purchase would break."""
    supermercado = await default_category(client, "Supermercado", "expense")
    await create_budget(client, supermercado, amount=amount)
    return supermercado


async def test_going_over_by_quick_add_asks_the_agent_what_happened(client, llm):
    supermercado = await tight_budget(client)
    llm.says(("Supermercado", "Te pasaste del límite de Supermercado."))

    await create_transaction(
        client, amount="12500.50", category_id=supermercado["id"]
    )

    [review] = await exceeded_reviews(client)
    assert review["status"] == "done"
    assert review["used_agent"] is True
    assert review["month"] == "2026-03-01"
    assert [one["topic"] for one in (await inbox(client))["insights"]] == [
        "Supermercado"
    ]


async def test_spending_that_stays_under_the_limit_asks_for_nothing(client):
    supermercado = await tight_budget(client)

    await create_transaction(
        client, amount="9000.00", category_id=supermercado["id"]
    )

    assert await exceeded_reviews(client) == []


async def test_spending_exactly_the_limit_is_not_over_it(client):
    supermercado = await tight_budget(client)

    await create_transaction(
        client, amount="10000.00", category_id=supermercado["id"]
    )

    assert await exceeded_reviews(client) == [], "100% is the limit, not past it"


async def test_a_category_without_a_budget_asks_for_nothing(client):
    ocio = await default_category(client, "Ocio", "expense")

    await create_transaction(client, amount="500000.00", category_id=ocio["id"])

    assert await exceeded_reviews(client) == []


async def test_going_over_by_editing_something_already_recorded(client):
    supermercado = await tight_budget(client)
    recorded = await create_transaction(
        client, amount="9000.00", category_id=supermercado["id"]
    )
    assert await exceeded_reviews(client) == []

    response = await client.patch(
        f"/transactions/{recorded['id']}", json={"amount": "11000.00"}
    )
    response.raise_for_status()

    assert len(await exceeded_reviews(client)) == 1


async def test_a_transaction_moved_into_the_category_takes_it_over(client):
    supermercado = await tight_budget(client)
    ocio = await default_category(client, "Ocio", "expense")
    recorded = await create_transaction(
        client, amount="11000.00", category_id=ocio["id"]
    )

    response = await client.patch(
        f"/transactions/{recorded['id']}", json={"category_id": supermercado["id"]}
    )
    response.raise_for_status()

    assert len(await exceeded_reviews(client)) == 1


async def test_going_over_by_confirming_an_import(client):
    await tight_budget(client)
    profile = await create_profile(client)
    seen = await categorised_preview(client, profile)

    response = await client.post("/imports/", json=confirm_body(seen))
    response.raise_for_status()

    assert len(await exceeded_reviews(client)) == 1, (
        "the file brought in 12.500,50 of Supermercado against a 10.000 limit"
    )


async def test_deleting_a_refund_can_take_a_budget_over(client):
    supermercado = await tight_budget(client)
    spent = await create_transaction(
        client, amount="8000.00", category_id=supermercado["id"]
    )
    refund = (
        await client.post(
            f"/transactions/{spent['id']}/refund",
            json={"amount": "3000.00", "date": "2026-03-15"},
        )
    ).json()
    await create_transaction(
        client, amount="4000.00", category_id=supermercado["id"]
    )
    assert await exceeded_reviews(client) == [], "the Refund kept it under"

    response = await client.delete(f"/transactions/{refund['id']}")
    response.raise_for_status()

    assert len(await exceeded_reviews(client)) == 1


async def test_it_fires_once_per_budget_however_much_more_is_spent(client):
    supermercado = await tight_budget(client)
    await create_transaction(
        client, amount="12500.50", category_id=supermercado["id"]
    )

    await create_transaction(
        client, amount="30000.00", category_id=supermercado["id"]
    )
    await create_transaction(
        client, amount="40000.00", category_id=supermercado["id"]
    )

    assert len(await exceeded_reviews(client)) == 1, (
        "the user has been told; the second time is not news"
    )


async def test_next_months_budget_fires_on_its_own(client, clock):
    supermercado = await tight_budget(client)
    await create_transaction(
        client, amount="12500.50", category_id=supermercado["id"]
    )

    await create_budget(
        client, supermercado, amount="10000.00", month="2026-04-01"
    )
    await create_transaction(
        client,
        amount="12500.50",
        category_id=supermercado["id"],
        date="2026-04-02",
    )

    assert [one["month"] for one in await exceeded_reviews(client)] == [
        "2026-04-01",
        "2026-03-01",
    ], "it is once per Budget, and April's is another Budget"


async def test_the_brief_is_about_that_category_and_its_history(client, llm):
    supermercado = await tight_budget(client)
    await create_transaction(
        client,
        amount="8000.00",
        category_id=supermercado["id"],
        date="2026-02-10",
        description="Coto de febrero",
    )
    ocio = await default_category(client, "Ocio", "expense")
    await create_transaction(client, amount="3000.00", category_id=ocio["id"])

    await create_transaction(
        client,
        amount="12500.50",
        category_id=supermercado["id"],
        description="Supermercado Coto",
    )

    assert "Supermercado went over its Budget" in llm.brief
    assert '"Supermercado Coto", expense: 12500.50' in llm.brief
    assert "2026-02: 8000.00" in llm.brief, "the Category's recent history"
    assert "The month under review is 2026-03" in llm.brief, "the core brief too"
    assert "Coto de febrero" not in llm.brief, (
        "the history is what it cost per month, not every row of it"
    )


async def test_accepting_a_proposal_that_breaks_the_budget_fires_it(client):
    supermercado = await tight_budget(client)
    suggestion = await proposed(
        client,
        description="Verdulería",
        category_id=supermercado["id"],
        reference_amount="12500.50",
    )

    response = await accept(client, suggestion["id"])
    response.raise_for_status()

    assert len(await exceeded_reviews(client)) == 1, (
        "accepting is the user recording it, Review and all"
    )


async def test_a_cuota_can_break_a_budget(client):
    ocio = await default_category(client, "Ocio", "expense")
    await create_budget(client, ocio, amount="50000.00")

    await create_purchase(client, category_id=ocio["id"])

    assert [one["month"] for one in await exceeded_reviews(client)] == [
        "2026-03-01"
    ], "only the month whose Budget the first cuota broke"


async def test_a_budget_the_write_did_not_touch_is_left_alone(client):
    """A Budget already over is not news because something else was recorded."""
    ocio = await default_category(client, "Ocio", "expense")
    await create_transaction(client, amount="5000.00", category_id=ocio["id"])
    await create_budget(client, ocio, amount="1000.00")
    assert await exceeded_reviews(client) == [], "setting a Budget fires nothing"

    supermercado = await tight_budget(client, amount="100000.00")
    await create_transaction(
        client, amount="500.00", category_id=supermercado["id"]
    )

    assert await exceeded_reviews(client) == [], (
        "Ocio is over, and nothing just happened to it"
    )
