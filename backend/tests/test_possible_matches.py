"""
The Possible Match: "puede que ya lo hayas registrado", said next to a proposal.

Rent that came in through an Import is already recorded by the time the month's
Suggestion is read, and accepting it then would record it twice. The Inbox says
so — and only says so. The proposal stays pending whatever it finds, because a
resemblance is a guess and the app never retracts a proposal on a guess.

TODAY is the 15th of March 2026, and the template these tests use proposes
450.000 pesos of Alquiler on the 5th.
"""

from tests.api import create_category, create_transaction, default_category
from tests.api_imports import confirm_body, create_profile
from tests.test_budgets import create_budget
from tests.test_import_confirm import categorised_preview
from tests.test_recurring_expenses import create_recurring
from tests.test_reviews import run_review, suggestions
from tests.test_suggestions import accept, proposed


async def alquiler(client) -> dict:
    return await default_category(client, "Alquiler", "expense")


async def already_recorded(client, category, **fields) -> dict:
    """An Expense that reached the app on its own, e.g. through an Import."""
    return await create_transaction(
        client,
        **{
            "category_id": category["id"],
            "amount": "450000.00",
            "date": "2026-03-04",
            "description": "ALQUILER MARZO",
            **fields,
        },
    )


async def match_for(client, **fields) -> dict | None:
    """What the Inbox found next to the month's one proposal."""
    return (await proposed(client, **fields))["possible_match"]


async def test_an_expense_that_looks_like_the_payment_is_shown_next_to_it(client):
    category = await alquiler(client)
    recorded = await already_recorded(client, category)

    proposal = await proposed(client, category_id=category["id"])

    assert proposal["possible_match"] == {
        "id": recorded["id"],
        "description": "ALQUILER MARZO",
        "amount": "450000.00",
        "currency": "ARS",
        "date": "2026-03-04",
    }


async def test_an_expense_that_arrived_through_an_import_is_found_too(client):
    """The case the hint exists for: rent already in, through a bank export."""
    category = await alquiler(client)
    profile = await create_profile(client)
    seen = await categorised_preview(client, profile)
    imported = await client.post(
        "/imports/",
        json=confirm_body(
            seen,
            **{
                "Supermercado Coto": {
                    "description": "ALQUILER MARZO",
                    "date": "2026-03-04",
                    "amount": "450000.00",
                    "category_id": category["id"],
                }
            },
        ),
    )
    imported.raise_for_status()

    match = await match_for(client, category_id=category["id"])

    assert match is not None
    assert match["description"] == "ALQUILER MARZO"
    assert match["amount"] == "450000.00"


async def test_the_suggestion_stays_pending_when_a_match_is_found(client):
    category = await alquiler(client)
    await already_recorded(client, category)

    proposal = await proposed(client, category_id=category["id"])

    assert proposal["status"] == "pending", (
        "a resemblance is a hint, not a reason to withdraw the proposal"
    )


async def test_an_amount_that_is_close_enough_still_looks_like_the_payment(client):
    category = await alquiler(client)
    await already_recorded(client, category, amount="461000.00")

    match = await match_for(client, category_id=category["id"])

    assert match is not None
    assert match["amount"] == "461000.00"


async def test_an_expense_in_another_category_is_not_the_same_payment(client):
    category = await alquiler(client)
    comida = await create_category(client, name="Comida")
    await already_recorded(client, comida)

    assert await match_for(client, category_id=category["id"]) is None


async def test_an_expense_of_another_size_is_not_the_same_payment(client):
    category = await alquiler(client)
    await already_recorded(client, category, amount="520000.00")

    assert await match_for(client, category_id=category["id"]) is None


async def test_an_expense_of_another_month_is_not_the_same_payment(client):
    category = await alquiler(client)
    await already_recorded(client, category, date="2026-02-04")

    assert await match_for(client, category_id=category["id"]) is None


async def test_an_expense_in_another_currency_is_not_the_same_payment(client):
    category = await alquiler(client)
    # Dated today, which is when a USD Expense can have its rate estimated.
    await already_recorded(
        client, category, currency="USD", amount="450000.00", date="2026-03-15"
    )

    assert await match_for(client, category_id=category["id"]) is None


async def test_an_expense_already_linked_to_a_template_is_not_offered(client):
    category = await alquiler(client)
    await create_recurring(
        client, description="Alquiler", category_id=category["id"]
    )
    await create_recurring(
        client, description="Cochera", category_id=category["id"], expected_day=6
    )
    await run_review(client)
    waiting = await suggestions(client)
    cochera = next(
        one for one in waiting if one["payload"]["description"] == "Cochera"
    )
    await accept(
        client,
        next(one for one in waiting if one["payload"]["description"] == "Alquiler")[
            "id"
        ],
    )

    [still_waiting] = [
        one for one in await suggestions(client) if one["id"] == cochera["id"]
    ]
    assert still_waiting["possible_match"] is None, (
        "that Expense belongs to the other template, not to this proposal"
    )


async def test_the_closest_of_several_look_alikes_is_the_one_shown(client):
    category = await alquiler(client)
    await already_recorded(client, category, amount="470000.00")
    closest = await already_recorded(client, category, amount="452000.00")

    match = await match_for(client, category_id=category["id"])

    assert match["id"] == closest["id"]


async def test_a_proposal_with_nothing_like_it_carries_no_match(client):
    proposal = await proposed(client)

    assert proposal["possible_match"] is None
    assert proposal["status"] == "pending"


async def test_a_budget_proposal_is_never_about_a_transaction(client):
    supermercado = await default_category(client, "Supermercado", "expense")
    await create_budget(
        client, supermercado, amount="100000.00", month="2026-02-01"
    )
    await create_transaction(
        client, category_id=supermercado["id"], amount="102000.00"
    )

    await run_review(client)

    [budget] = [
        one for one in await suggestions(client) if one["kind"] == "set_budget"
    ]
    assert budget["possible_match"] is None
