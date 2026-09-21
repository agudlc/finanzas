"""
Adjustment Rules: the rent contract that moves every N months.

TODAY is the 15th of March 2026 and the fake IPC carries November 2025 to
February 2026, so a Review of March asks for months up to February — the latest
one that should already be published — and a Review of April asks for March,
which is exactly the month that is not out yet.
"""

from tests.test_recurring_expenses import create_recurring
from tests.test_reviews import run_review, suggestions
from tests.test_suggestions import accept


def percentage_rule(**fields) -> dict:
    """Every 6 months by 10%, with a cycle whose adjustments land in March."""
    return {
        "kind": "percentage",
        "period_months": 6,
        "percentage": "10.00",
        "start_month": "2025-09-01",
        **fields,
    }


def index_rule(**fields) -> dict:
    """Every 3 months by IPC, with a cycle whose adjustments land in March."""
    return {
        "kind": "index",
        "period_months": 3,
        "index_name": "IPC",
        "start_month": "2025-12-01",
        **fields,
    }


async def proposed_amount(client) -> str:
    await run_review(client)
    [one] = await suggestions(client)
    return one["payload"]["amount"]


async def rationale(client) -> str:
    await run_review(client)
    [one] = await suggestions(client)
    return one["rationale"]


async def test_a_due_month_raises_the_amount_by_the_percentage(client):
    await create_recurring(client, adjustment=percentage_rule())

    assert await proposed_amount(client) == "495000.00"


async def test_a_month_that_is_not_due_keeps_the_amount_as_it_was(client):
    await create_recurring(client, adjustment=percentage_rule(period_months=5))

    assert await proposed_amount(client) == "450000.00", (
        "six months after September is March, five months is February"
    )


async def test_the_month_the_cycle_starts_from_is_not_an_adjustment(client):
    await create_recurring(
        client, adjustment=percentage_rule(start_month="2026-03-01")
    )

    assert await proposed_amount(client) == "450000.00"


async def test_a_month_before_the_cycle_starts_is_not_an_adjustment(client):
    await create_recurring(
        client, adjustment=percentage_rule(start_month="2026-09-01")
    )

    assert await proposed_amount(client) == "450000.00"


async def test_the_adjustment_lands_on_the_last_amount_that_was_paid(client, clock):
    clock.date = clock.date.replace(month=2)
    await create_recurring(client, adjustment=percentage_rule())
    await run_review(client)
    [february] = await suggestions(client)
    await accept(client, february["id"], amount="500000.00")

    clock.date = clock.date.replace(month=3)

    assert await proposed_amount(client) == "550000.00"


async def test_an_index_rule_compounds_the_months_of_its_period(client):
    await create_recurring(client, adjustment=index_rule())

    assert await proposed_amount(client) == "475946.65", (
        "December, January and February compound on the reference amount"
    )


async def test_an_index_rule_compounds_as_many_months_as_its_period(client):
    await create_recurring(
        client, adjustment=index_rule(period_months=4, start_month="2025-11-01")
    )

    assert await proposed_amount(client) == "487369.37"


async def test_an_index_rule_compounds_on_the_last_amount_that_was_paid(
    client, clock
):
    clock.date = clock.date.replace(month=2)
    await create_recurring(client, adjustment=index_rule())
    await run_review(client)
    [february] = await suggestions(client)
    await accept(client, february["id"], amount="500000.00")

    clock.date = clock.date.replace(month=3)

    assert await proposed_amount(client) == "528829.61"


async def test_an_index_that_is_not_out_yet_leaves_the_amount_alone(client, clock):
    # April's Review asks for March, published halfway through April.
    clock.date = clock.date.replace(month=4, day=2)
    await create_recurring(
        client, adjustment=index_rule(period_months=4, start_month="2025-12-01")
    )

    assert await proposed_amount(client) == "450000.00"


async def test_a_pending_adjustment_says_which_month_is_missing(client, clock):
    clock.date = clock.date.replace(month=4, day=2)
    await create_recurring(
        client, adjustment=index_rule(period_months=4, start_month="2025-12-01")
    )

    said = await rationale(client)
    assert "pendiente" in said
    assert "IPC" in said and "marzo de 2026" in said


async def test_a_hand_entered_value_completes_a_pending_adjustment(client, clock):
    clock.date = clock.date.replace(month=4, day=2)
    await client.put("/inflation-indexes/2026-03", json={"value": "2.400"})
    await create_recurring(
        client, adjustment=index_rule(period_months=4, start_month="2025-12-01")
    )

    assert await proposed_amount(client) == "487369.37", (
        "December, January, February and the March value typed by hand"
    )


async def test_a_percentage_adjustment_explains_its_arithmetic(client):
    await create_recurring(client, adjustment=percentage_rule())

    said = await rationale(client)
    assert "10%" in said
    assert "450.000,00" in said and "495.000,00" in said
    assert "monto de referencia" in said


async def test_an_index_adjustment_explains_its_arithmetic(client):
    await create_recurring(client, adjustment=index_rule())

    said = await rationale(client)
    assert "IPC" in said
    assert "diciembre de 2025" in said and "febrero de 2026" in said
    assert "5,77%" in said
    assert "475.946,65" in said


async def test_a_template_without_a_rule_is_proposed_as_it_always_was(client):
    await create_recurring(client)

    assert await proposed_amount(client) == "450000.00"
    assert "ajuste" not in await rationale(client)
