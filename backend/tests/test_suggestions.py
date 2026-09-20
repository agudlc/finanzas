"""
Acting on what the Inbox proposes: accepting it as it stands, accepting it after
changing something, or saying "not this month".

Accepting goes through the same service the Transactions routes use, so a
Suggestion cannot record anything the user could not have recorded by hand — an
income Category is refused here exactly as it is there.
"""

from tests.api import create_category, default_category
from tests.test_recurring_expenses import create_recurring
from tests.test_reviews import inbox, run_review, suggestions

UNKNOWN = "00000000-0000-0000-0000-000000000000"


async def proposed(client, **fields) -> dict:
    """The one Suggestion a Review makes for a template, waiting in the Inbox."""
    await create_recurring(client, **fields)
    await run_review(client)
    [one] = await suggestions(client)
    return one


async def accept(client, suggestion_id: str, **edits):
    body = {"payload": edits} if edits else {}
    return await client.post(f"/suggestions/{suggestion_id}/accept", json=body)


async def reject(client, suggestion_id: str, reason: str | None = None):
    return await client.post(
        f"/suggestions/{suggestion_id}/reject", json={"reason": reason}
    )


async def transactions(client) -> list[dict]:
    response = await client.get("/transactions/")
    response.raise_for_status()
    return response.json()


async def test_accepting_a_suggestion_records_the_expense_it_proposed(client):
    alquiler = await default_category(client, "Alquiler", "expense")
    suggestion = await proposed(
        client, category_id=alquiler["id"], reference_amount="450000.00"
    )

    response = await accept(client, suggestion["id"])

    assert response.status_code == 200
    [recorded] = await transactions(client)
    assert recorded["amount"] == "450000.00"
    assert recorded["currency"] == "ARS"
    assert recorded["type"] == "expense"
    assert recorded["category_id"] == alquiler["id"]
    assert recorded["date"] == "2026-03-05"
    assert recorded["description"] == "Alquiler"
    assert recorded["is_fixed"] is True


async def test_the_recorded_expense_stays_linked_to_its_recurring_expense(client):
    template = await create_recurring(client)
    await run_review(client)
    [suggestion] = await suggestions(client)

    await accept(client, suggestion["id"])

    [recorded] = await transactions(client)
    assert recorded["recurring_expense_id"] == template["id"]


async def test_an_accepted_suggestion_says_what_it_created_and_when(client):
    suggestion = await proposed(client)

    accepted = (await accept(client, suggestion["id"])).json()

    [recorded] = await transactions(client)
    assert accepted["status"] == "accepted"
    assert accepted["result_id"] == recorded["id"]
    assert accepted["resolved_at"] is not None
    assert accepted["rejection_reason"] is None


async def test_an_accepted_suggestion_leaves_the_inbox(client):
    suggestion = await proposed(client)

    await accept(client, suggestion["id"])

    assert await suggestions(client) == []
    assert (await inbox(client))["pending_count"] == 0


async def test_a_suggestion_can_be_edited_before_being_accepted(client):
    comida = await create_category(client, name="Comida")
    suggestion = await proposed(client)

    await accept(
        client,
        suggestion["id"],
        amount="475000.00",
        date="2026-03-08",
        category_id=comida["id"],
        description="Alquiler con expensas",
        is_fixed=False,
    )

    [recorded] = await transactions(client)
    assert recorded["amount"] == "475000.00"
    assert recorded["date"] == "2026-03-08"
    assert recorded["category_id"] == comida["id"]
    assert recorded["description"] == "Alquiler con expensas"
    assert recorded["is_fixed"] is False


async def test_an_edit_is_checked_against_the_kind_before_anything_is_recorded(
    client,
):
    suggestion = await proposed(client)

    response = await accept(client, suggestion["id"], amount="0.00")

    assert response.status_code == 422
    assert await transactions(client) == []
    assert (await suggestions(client))[0]["status"] == "pending"


async def test_an_edit_the_kind_does_not_know_about_is_refused(client):
    suggestion = await proposed(client)

    response = await accept(client, suggestion["id"], type="income")

    assert response.status_code == 422
    assert await transactions(client) == []


async def test_an_edited_category_still_obeys_the_domain_rules(client):
    sueldo = await default_category(client, "Sueldo", "income")
    suggestion = await proposed(client)

    response = await accept(client, suggestion["id"], category_id=sueldo["id"])

    assert response.status_code == 422
    assert "income Category" in response.json()["detail"]
    assert await transactions(client) == []
    assert (await suggestions(client))[0]["status"] == "pending", (
        "a Suggestion that could not be applied is still waiting"
    )


async def test_a_usd_suggestion_gets_an_estimated_exchange_rate(client):
    # A day still to come, so the rate is estimated from the source exactly as
    # it is for a USD Transaction typed in by hand.
    suggestion = await proposed(
        client, currency="USD", reference_amount="120.00", expected_day=20
    )

    await accept(client, suggestion["id"])

    [recorded] = await transactions(client)
    assert recorded["currency"] == "USD"
    assert recorded["exchange_rate"] == "1500.0000"
    assert recorded["exchange_rate_type"] == "card"
    assert recorded["exchange_rate_status"] == "estimated"


async def test_accepting_a_suggestion_twice_is_a_conflict(client):
    suggestion = await proposed(client)
    await accept(client, suggestion["id"])

    response = await accept(client, suggestion["id"])

    assert response.status_code == 409
    assert len(await transactions(client)) == 1


async def test_a_suggestion_that_does_not_exist_cannot_be_accepted(client):
    assert (await accept(client, UNKNOWN)).status_code == 404
    assert (await reject(client, UNKNOWN)).status_code == 404


async def test_rejecting_a_suggestion_records_nothing_and_keeps_the_reason(client):
    suggestion = await proposed(client)

    rejected = (await reject(client, suggestion["id"], "este mes lo pagó mi hermana")).json()

    assert rejected["status"] == "rejected"
    assert rejected["rejection_reason"] == "este mes lo pagó mi hermana"
    assert rejected["resolved_at"] is not None
    assert rejected["result_id"] is None
    assert await transactions(client) == []
    assert await suggestions(client) == []


async def test_a_reason_is_optional(client):
    suggestion = await proposed(client)

    rejected = (await reject(client, suggestion["id"])).json()

    assert rejected["status"] == "rejected"
    assert rejected["rejection_reason"] is None


async def test_rejecting_a_suggestion_twice_is_a_conflict(client):
    suggestion = await proposed(client)
    await reject(client, suggestion["id"])

    assert (await reject(client, suggestion["id"])).status_code == 409
    assert (await accept(client, suggestion["id"])).status_code == 409


async def test_a_resolved_suggestion_is_not_proposed_again_the_same_month(client):
    suggestion = await proposed(client)
    await reject(client, suggestion["id"])

    await run_review(client)

    assert await suggestions(client) == [], (
        "rejecting means 'not this month', and this is still that month"
    )


async def test_a_rejection_blocks_only_its_own_month(client, clock):
    suggestion = await proposed(client)
    await reject(client, suggestion["id"], "no lo pagué")

    clock.date = clock.date.replace(month=4)
    await run_review(client)

    [again] = await suggestions(client)
    assert again["month"] == "2026-04-01"
    assert again["payload"]["amount"] == "450000.00", (
        "nothing was paid, so the reference amount still stands in"
    )


async def test_the_next_month_proposes_the_last_amount_that_was_paid(client, clock):
    suggestion = await proposed(client)
    await accept(client, suggestion["id"], amount="475000.00")

    clock.date = clock.date.replace(month=4)
    await run_review(client)

    [next_month] = await suggestions(client)
    assert next_month["payload"]["amount"] == "475000.00"
    assert "último monto" in next_month["rationale"]


async def test_a_transaction_of_another_template_is_not_taken_as_the_last_paid(
    client, clock
):
    luz = await create_category(client, name="Luz")
    other = await proposed(client, description="Luz", category_id=luz["id"])
    await accept(client, other["id"], amount="90000.00")
    await create_recurring(client, description="Alquiler", expected_day=5)

    clock.date = clock.date.replace(month=4)
    await run_review(client)

    alquiler = next(
        one
        for one in await suggestions(client)
        if one["payload"]["description"] == "Alquiler"
    )
    assert alquiler["payload"]["amount"] == "450000.00"
    assert "monto de referencia" in alquiler["rationale"]


async def test_an_accepted_month_is_not_proposed_again_either(client):
    suggestion = await proposed(client)
    await accept(client, suggestion["id"])

    await run_review(client)

    assert await suggestions(client) == [], (
        "the Expense is already recorded, so there is nothing left to propose"
    )
    assert len(await transactions(client)) == 1


async def test_a_payment_in_another_currency_is_not_the_last_amount_paid(
    client, clock
):
    suggestion = await proposed(client, expected_day=20)
    # Paid in dollars this once; the template still describes a pesos Expense.
    await accept(client, suggestion["id"], currency="USD", amount="400.00")

    clock.date = clock.date.replace(month=4)
    await run_review(client)

    [next_month] = await suggestions(client)
    assert next_month["payload"]["currency"] == "ARS"
    assert next_month["payload"]["amount"] == "450000.00", (
        "400 dollars says nothing about what the next month costs in pesos"
    )
