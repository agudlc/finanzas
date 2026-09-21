"""
The read tools, and the history cap the user sets on them.

Every test here drives one tool the way the model would: the scripted client
asks for it by name, the Review runs, and what the tool answered is read back
out of the transcript the run left on the Review. That is the whole seam — the
model asks, the app answers — so these read as the conversation a real run
would have had.
"""

from datetime import date

from app.llm import Reply, ToolCall
from tests.api import create_category, create_transaction, default_category
from tests.test_agent_reviews import agent_review, finished, insights
from tests.test_recurring_expenses import create_recurring
from tests.test_reviews import press_revisar_ahora, run_review, suggestions


async def asks(client, llm, tool: str, **arguments) -> str:
    """What one read tool answers when the model calls it, in its own words."""
    llm.will(
        Reply(tool_calls=(ToolCall(id="call-0", name=tool, arguments=arguments),)),
        Reply(text="Listo."),
    )
    review = await finished(client, await agent_review(client))
    [answer] = review["transcript"][2]["content"]
    return answer["content"]


async def widen_the_lookback(client) -> None:
    """"Un año", as the user would set it in Ajustes."""
    response = await client.patch("/settings/", json={"agent_lookback": "year"})
    response.raise_for_status()


async def test_the_brief_says_how_far_back_the_agent_may_read(client, llm):
    await press_revisar_ahora(client)

    assert "read back as far as 2026-01 and no further" in llm.brief, (
        "a quarter is the month under review and the two before it"
    )


async def test_a_year_of_lookback_is_what_the_brief_says_instead(client, llm):
    await widen_the_lookback(client)

    await press_revisar_ahora(client)

    assert "read back as far as 2025-04 and no further" in llm.brief


async def test_listing_transactions_says_what_was_bought(client, llm):
    delivery = await default_category(client, "Delivery", "expense")
    await create_transaction(
        client,
        category_id=delivery["id"],
        amount="45000.00",
        description="Pedidos Ya",
    )

    answer = await asks(
        client, llm, "list_transactions", from_month="2026-03", to_month="2026-03"
    )

    assert "2026-03-15, Delivery, \"Pedidos Ya\", expense: 45000.00" in answer


async def test_a_dollar_transaction_is_read_in_the_display_currency(client, llm):
    delivery = await default_category(client, "Delivery", "expense")
    await create_transaction(
        client,
        category_id=delivery["id"],
        currency="USD",
        amount="30.00",
        description="Spotify",
    )

    answer = await asks(
        client, llm, "list_transactions", from_month="2026-03", to_month="2026-03"
    )

    assert "45000.00 (originally 30.00 USD)" in answer, (
        "converted through the Transaction's own Exchange Rate, card at 1500"
    )


async def test_listing_transactions_can_be_asked_for_one_category(client, llm):
    delivery = await default_category(client, "Delivery", "expense")
    supermercado = await default_category(client, "Supermercado", "expense")
    await create_transaction(
        client, category_id=delivery["id"], description="Pedidos Ya"
    )
    await create_transaction(
        client, category_id=supermercado["id"], description="Coto"
    )

    answer = await asks(
        client,
        llm,
        "list_transactions",
        from_month="2026-03",
        to_month="2026-03",
        category="Delivery",
    )

    assert "Pedidos Ya" in answer
    assert "Coto" not in answer


async def test_a_category_that_does_not_exist_is_answered_rather_than_fatal(
    client, llm
):
    answer = await asks(
        client,
        llm,
        "list_transactions",
        from_month="2026-03",
        to_month="2026-03",
        category="Cripto",
    )

    assert answer == "There is no Category called 'Cripto'."


async def test_listing_transactions_honours_the_limit_it_was_given(client, llm):
    delivery = await default_category(client, "Delivery", "expense")
    for number in range(3):
        await create_transaction(
            client, category_id=delivery["id"], description=f"Pedido {number}"
        )

    answer = await asks(
        client,
        llm,
        "list_transactions",
        from_month="2026-03",
        to_month="2026-03",
        limit=1,
    )

    assert len(answer.splitlines()) == 2, "the heading and the one row asked for"


async def test_a_limit_that_cannot_be_met_is_said_rather_than_bent(client, llm):
    answer = await asks(
        client,
        llm,
        "list_transactions",
        from_month="2026-03",
        to_month="2026-03",
        limit=500,
    )

    assert answer == "A limit has to be between 1 and 200.", (
        "a list quietly cut to 200 reads as the whole of what was asked for"
    )


async def test_a_name_two_categories_share_reads_both_of_them(client, llm):
    given = await create_category(client, name="Regalos", type="expense")
    received = await create_category(client, name="Regalos", type="income")
    await create_transaction(
        client, category_id=given["id"], description="Cumpleaños de mamá"
    )
    await create_transaction(
        client,
        category_id=received["id"],
        type="income",
        description="Regalo de la abuela",
    )

    answer = await asks(
        client,
        llm,
        "list_transactions",
        from_month="2026-03",
        to_month="2026-03",
        category="Regalos",
    )

    assert "Cumpleaños de mamá" in answer
    assert "Regalo de la abuela" in answer, (
        "the model asked for a name, and both Categories answer to it"
    )


async def test_a_month_that_is_not_a_month_is_answered_rather_than_fatal(
    client, llm
):
    answer = await asks(client, llm, "category_totals", month="marzo")

    assert "is not a month of the form YYYY-MM" in answer


async def test_category_totals_read_an_earlier_month(client, llm):
    delivery = await default_category(client, "Delivery", "expense")
    sueldo = await default_category(client, "Sueldo", "income")
    await create_transaction(
        client, category_id=delivery["id"], amount="20000.00", date="2026-01-10"
    )
    await create_transaction(
        client,
        category_id=sueldo["id"],
        type="income",
        amount="800000.00",
        date="2026-01-01",
    )

    answer = await asks(client, llm, "category_totals", month="2026-01")

    assert "- Income: 800000.00" in answer
    assert "- Expenses: 20000.00" in answer
    assert "- Monthly Result: 780000.00" in answer
    assert "- Delivery: 20000.00" in answer


async def test_budgets_are_read_with_their_pace(client, llm):
    delivery = await default_category(client, "Delivery", "expense")
    await client.post(
        "/budgets/",
        json={
            "category_id": delivery["id"],
            "amount": "30000.00",
            "currency": "ARS",
            "month": "2026-03-01",
        },
    )
    await create_transaction(client, category_id=delivery["id"], amount="45000.00")

    answer = await asks(client, llm, "budgets", month="2026-03")

    assert "limit 30000.00 ARS, spent 45000.00 (150.00%)" in answer
    assert "state over" in answer


async def test_recurring_expenses_are_read_as_the_month_expects_them(client, llm):
    await create_recurring(client, description="Alquiler")

    answer = await asks(client, llm, "recurring_expenses")

    assert (
        "- Alquiler in Alquiler: 450000.00 ARS on day 5, never paid through a "
        "Suggestion yet, no Adjustment Rule" in answer
    )


async def test_what_a_recurring_expense_last_cost_is_read_with_its_currency(
    client, llm
):
    await create_recurring(client, description="Alquiler")
    await run_review(client)
    [proposed] = await suggestions(client)
    await client.post(f"/suggestions/{proposed['id']}/accept", json={})

    answer = await asks(client, llm, "recurring_expenses")

    assert "last paid 450000.00 ARS" in answer


async def test_an_adjustment_rule_is_read_with_the_recurring_expense(client, llm):
    await create_recurring(
        client,
        description="Alquiler",
        adjustment={
            "kind": "index",
            "period_months": 3,
            "index_name": "IPC",
            "start_month": "2026-01-01",
        },
    )

    answer = await asks(client, llm, "recurring_expenses")

    assert "adjusted by the IPC every 3 months from 2026-01" in answer


async def test_categories_are_read_with_the_type_they_classify(client, llm):
    answer = await asks(client, llm, "categories")

    assert "- Delivery: expense" in answer
    assert "- Sueldo: income" in answer


async def test_categorization_rules_are_read_as_pattern_and_category(client, llm):
    delivery = await default_category(client, "Delivery", "expense")
    await client.post(
        "/categorization-rules/",
        json={"pattern": "pedidos ya", "category_id": delivery["id"]},
    )

    answer = await asks(client, llm, "categorization_rules")

    assert '- "pedidos ya" -> Delivery' in answer


async def test_past_rejections_are_read_with_the_reason_given(client, llm):
    await create_recurring(client, description="Netflix")
    await run_review(client)
    [proposed] = await suggestions(client)
    await client.post(
        f"/suggestions/{proposed['id']}/reject", json={"reason": "lo di de baja"}
    )

    answer = await asks(client, llm, "past_rejections")

    assert "Netflix" in answer
    assert "lo di de baja" in answer


async def test_past_rejections_can_be_asked_for_one_kind(client, llm):
    await create_recurring(client, description="Netflix")
    await run_review(client)
    [proposed] = await suggestions(client)
    await client.post(f"/suggestions/{proposed['id']}/reject", json={})

    answer = await asks(client, llm, "past_rejections", kind="set_budget")

    assert answer.endswith("They have rejected nothing."), (
        "the Netflix rejection is an add_transaction, which was not asked for"
    )


async def test_recorded_insights_can_be_read_back(client, llm):
    llm.says(("Delivery", "Se te fue la mano con el delivery."))
    await press_revisar_ahora(client)

    answer = await asks(client, llm, "recent_insights")

    assert "2026-03 — Delivery: Se te fue la mano con el delivery." in answer


async def test_a_month_behind_the_lookback_is_refused_with_the_limit(client, llm):
    answer = await asks(client, llm, "category_totals", month="2025-12")

    assert answer == (
        "2025-12 is further back than you may read. The user lets you read "
        "from 2026-01 onwards; ask again from that month on."
    )


async def test_a_year_of_lookback_reaches_the_month_a_quarter_refused(client, llm):
    await widen_the_lookback(client)

    answer = await asks(client, llm, "category_totals", month="2025-12")

    assert "## 2025-12, in ARS" in answer
    assert "- Monthly Result: 0.00" in answer, "a quiet month, but a readable one"


async def test_even_a_year_stops_somewhere(client, llm):
    await widen_the_lookback(client)

    answer = await asks(client, llm, "category_totals", month="2025-03")

    assert "The user lets you read from 2025-04 onwards" in answer


async def test_a_range_is_refused_when_it_starts_behind_the_lookback(client, llm):
    answer = await asks(
        client, llm, "list_transactions", from_month="2025-10", to_month="2026-03"
    )

    assert "further back than you may read" in answer, (
        "the range is clamped by refusing it, not by quietly shortening it"
    )


async def test_an_older_insight_is_out_of_reach_under_a_quarter(client, llm, clock):
    clock.date = date(2025, 12, 10)
    llm.says(("Diciembre", "Las fiestas te salieron caras."))
    await press_revisar_ahora(client)
    assert len(await insights(client)) == 1
    clock.date = date(2026, 3, 15)

    answer = await asks(client, llm, "recent_insights")

    assert "Diciembre" not in answer


async def test_a_year_of_lookback_reaches_that_older_insight(client, llm, clock):
    clock.date = date(2025, 12, 10)
    llm.says(("Diciembre", "Las fiestas te salieron caras."))
    await press_revisar_ahora(client)
    clock.date = date(2026, 3, 15)
    await widen_the_lookback(client)

    answer = await asks(client, llm, "recent_insights")

    assert "2025-12 — Diciembre: Las fiestas te salieron caras." in answer


async def test_the_brief_leaves_out_a_rejection_the_lookback_does_not_cover(
    client, llm, clock
):
    clock.date = date(2025, 12, 10)
    await create_recurring(client, description="Netflix")
    await run_review(client)
    [proposed] = await suggestions(client)
    await client.post(f"/suggestions/{proposed['id']}/reject", json={})
    clock.date = date(2026, 3, 15)

    await press_revisar_ahora(client)

    assert "The user has not rejected anything recently." in llm.brief, (
        "three months of rejections, but only one quarter of them may be read"
    )


async def test_a_year_of_lookback_puts_that_rejection_back_in_the_brief(
    client, llm, clock
):
    clock.date = date(2025, 12, 10)
    await create_recurring(client, description="Netflix")
    await run_review(client)
    [proposed] = await suggestions(client)
    await client.post(f"/suggestions/{proposed['id']}/reject", json={})
    clock.date = date(2026, 3, 15)
    await widen_the_lookback(client)

    await press_revisar_ahora(client)

    assert "they said no to" in llm.brief
    assert "Netflix" in llm.brief
