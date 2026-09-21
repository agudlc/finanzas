"""
The first Review that calls the model, and the Insights it leaves behind.

The model is faked at the edge, the way the dollar rates and the IPC are: the
scripted client answers with exactly the turns a test wants and keeps whatever
it was sent, so what these tests read back through the API is what a real run
would have left, and what they assert about the brief is what Claude would
actually have been told.
"""

from datetime import date

from app.llm import Reply, ToolCall
from tests.api import create_transaction, default_category
from tests.test_recurring_expenses import create_recurring
from tests.test_reviews import inbox, press_revisar_ahora, run_review, suggestions


async def agent_review(client) -> dict:
    """"Revisar ahora", and the half of it that calls the model."""
    [asked] = [
        one
        for one in await press_revisar_ahora(client)
        if one["trigger"] == "manual_agent"
    ]
    return asked


async def insights(client) -> list[dict]:
    return (await inbox(client))["insights"]


async def finished(client, review: dict) -> dict:
    response = await client.get(f"/reviews/{review['id']}")
    response.raise_for_status()
    return response.json()


async def test_revisar_ahora_asks_for_the_arithmetic_and_the_agent(client):
    asked = await press_revisar_ahora(client)

    assert [one["trigger"] for one in asked] == ["manual", "manual_agent"]
    assert [one["used_agent"] for one in asked] == [False, True], (
        "the trigger alone says whether a Review called the model (ADR-0003)"
    )


async def test_an_insight_the_agent_recorded_waits_in_the_inbox(client, llm):
    llm.says(("Delivery", "Gastaste 45.000 en Delivery, el doble que en febrero."))

    await press_revisar_ahora(client)

    [insight] = await insights(client)
    assert insight["topic"] == "Delivery"
    assert "45.000" in insight["body"]
    assert insight["month"] == "2026-03-01"
    assert insight["dismissed_at"] is None


async def test_the_agent_can_record_more_than_one_insight_in_a_run(client, llm):
    llm.says(
        ("Delivery", "Se te fue la mano con el delivery."),
        ("Supermercado", "El súper viene igual que el mes pasado."),
    )

    await press_revisar_ahora(client)

    assert {one["topic"] for one in await insights(client)} == {
        "Delivery",
        "Supermercado",
    }


async def test_a_dismissed_insight_leaves_the_inbox(client, llm):
    llm.says(("Delivery", "Se te fue la mano con el delivery."))
    await press_revisar_ahora(client)
    [insight] = await insights(client)

    response = await client.post(f"/insights/{insight['id']}/dismiss")

    assert response.status_code == 200
    assert response.json()["dismissed_at"] is not None
    assert await insights(client) == [], "dismissing is reading, not deleting"


async def test_an_insight_that_does_not_exist_returns_404(client):
    unknown = "00000000-0000-0000-0000-000000000000"

    assert (await client.post(f"/insights/{unknown}/dismiss")).status_code == 404


async def test_last_months_insight_is_no_longer_in_the_inbox(client, clock, llm):
    clock.date = date(2026, 2, 10)
    llm.says(("Delivery", "Febrero te salió caro en delivery."))
    await press_revisar_ahora(client)
    assert len(await insights(client)) == 1

    clock.date = date(2026, 3, 15)

    assert await insights(client) == [], (
        "an Insight waits during its month and is history afterwards"
    )


async def test_an_agent_review_records_what_the_run_was(client, llm):
    llm.says(("Delivery", "Se te fue la mano con el delivery."))

    review = await finished(client, await agent_review(client))

    assert review["status"] == "done"
    assert review["used_agent"] is True
    assert review["prompt_version"]
    assert review["input_tokens"] == 2600, "both turns, added up"
    assert review["output_tokens"] == 320
    assert [turn["role"] for turn in review["transcript"]] == [
        "user",
        "assistant",
        "user",
        "assistant",
    ], "the brief, the tool call, its result, and the answer"


async def test_a_deterministic_review_keeps_its_transcript_empty(client):
    review = await finished(client, await run_review(client))

    assert review["transcript"] is None
    assert review["input_tokens"] is None
    assert review["prompt_version"] is None


async def test_a_model_that_cannot_be_reached_leaves_only_that_review_failed(
    client, llm
):
    llm.fail_with("no hay API key")
    await create_recurring(client, description="Alquiler")

    asked = await press_revisar_ahora(client)
    deterministic, agent = [await finished(client, one) for one in asked]

    assert deterministic["status"] == "done"
    assert agent["status"] == "failed"
    assert "no hay API key" in agent["error"]
    assert [one["payload"]["description"] for one in await suggestions(client)] == [
        "Alquiler"
    ], "the arithmetic still reached the Inbox"


async def test_nothing_the_agent_said_survives_a_run_that_fell_over(client, llm):
    llm.will(
        Reply(
            tool_calls=(
                ToolCall(
                    id="call-0",
                    name="record_insight",
                    arguments={"topic": "Delivery", "body": "Mucho delivery."},
                ),
            )
        ),
    )
    llm.fail_with("se cortó a mitad de camino", after=1)

    review = await finished(client, await agent_review(client))

    assert review["status"] == "failed"
    assert await insights(client) == [], (
        "the Insight the first turn recorded went with the run that failed"
    )


async def test_a_model_that_never_stops_is_cut_off_and_says_so(client, llm):
    llm.will(
        Reply(
            tool_calls=(
                ToolCall(
                    id="call-0",
                    name="record_insight",
                    arguments={"topic": "Otra vez", "body": "Lo mismo de antes."},
                ),
            )
        )
    )

    review = await finished(client, await agent_review(client))

    assert review["status"] == "done", "what it recorded before the cap stands"
    assert review["note"] == "hit the iteration cap"
    assert len(await insights(client)) == 10


async def test_a_tool_that_does_not_exist_is_answered_rather_than_fatal(client, llm):
    llm.will(
        Reply(tool_calls=(ToolCall(id="call-0", name="delete_everything"),)),
        Reply(text="Listo."),
    )

    review = await finished(client, await agent_review(client))

    assert review["status"] == "done"
    assert await insights(client) == []
    [answer] = review["transcript"][2]["content"]
    assert "no tool called delete_everything" in answer["content"]


async def test_the_model_is_told_to_answer_in_spanish(client, llm):
    await press_revisar_ahora(client)

    assert "rioplatense" in llm.systems[-1].lower()


async def test_the_brief_carries_how_the_month_is_going(client, llm):
    delivery = await default_category(client, "Delivery", "expense")
    sueldo = await default_category(client, "Sueldo", "income")
    await create_transaction(client, category_id=delivery["id"], amount="45000.00")
    await create_transaction(
        client, category_id=sueldo["id"], type="income", amount="800000.00"
    )

    await press_revisar_ahora(client)

    assert "Delivery: 45000.00" in llm.brief
    assert "Income: 800000.00" in llm.brief
    assert "Monthly Result: 755000.00" in llm.brief, (
        "spending alone invites advice the user cannot act on"
    )


async def test_the_brief_carries_each_budget_against_its_pace(client, llm):
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

    await press_revisar_ahora(client)

    assert "limit 30000.00 ARS, spent 45000.00 (150.00%)" in llm.brief
    assert "Pace says 14516.13 by today" in llm.brief
    assert "state over" in llm.brief


async def test_the_brief_carries_what_is_already_waiting_in_the_inbox(client, llm):
    await create_recurring(client, description="Alquiler")

    await press_revisar_ahora(client)

    assert "Alquiler" in llm.brief, (
        "the agent reads the arithmetic's proposals so it does not repeat them"
    )


async def test_the_brief_carries_a_rejection_and_the_reason_given(client, llm):
    await create_recurring(client, description="Netflix")
    await run_review(client)
    [proposed] = await suggestions(client)
    await client.post(
        f"/suggestions/{proposed['id']}/reject", json={"reason": "lo di de baja"}
    )

    await press_revisar_ahora(client)

    assert "they said no to" in llm.brief
    assert "Netflix" in llm.brief
    assert "lo di de baja" in llm.brief


async def test_the_brief_carries_what_the_agent_already_said_this_month(client, llm):
    llm.says(("Delivery", "Se te fue la mano con el delivery."))
    await press_revisar_ahora(client)

    await press_revisar_ahora(client)

    assert "Delivery: Se te fue la mano con el delivery." in llm.brief, (
        "it is told what it has already said so it does not say it again"
    )


async def test_a_busy_api_is_asked_again_and_the_run_finishes(client, llm, sleeper):
    llm.is_busy(2)
    llm.says(("Delivery", "Se te fue la mano con el delivery."))

    review = await finished(client, await agent_review(client))

    assert review["status"] == "done"
    assert [one["topic"] for one in await insights(client)] == ["Delivery"]
    assert sleeper.waited == [1.0, 4.0], "it waited longer each time before asking"


async def test_an_api_that_stays_busy_leaves_the_review_failed(client, llm, sleeper):
    llm.is_busy(3)
    llm.says(("Delivery", "Se te fue la mano con el delivery."))

    review = await finished(client, await agent_review(client))

    assert review["status"] == "failed"
    assert "overloaded" in review["error"]
    assert sleeper.waited == [1.0, 4.0], "three asks, and it gave up rather than loop"


async def test_an_error_that_is_not_the_api_being_busy_is_not_retried(
    client, llm, sleeper
):
    llm.fail_with("the model did not answer: invalid request")

    review = await finished(client, await agent_review(client))

    assert review["status"] == "failed"
    assert "invalid request" in review["error"]
    assert len(llm.runs) == 1, "asking again would have been refused again"
    assert sleeper.waited == []


async def test_without_an_api_key_the_agent_review_fails_at_once(
    client, llm, sleeper
):
    llm.without_key()

    review = await finished(client, await agent_review(client))

    assert review["status"] == "failed"
    assert "ANTHROPIC_API_KEY is not set" in review["error"]
    assert len(llm.runs) == 1, "there is nothing to wait for"
    assert sleeper.waited == []


async def test_a_run_that_was_cut_off_keeps_what_it_proposed(client, llm):
    supermercado = await default_category(client, "Supermercado", "expense")
    delivery = await default_category(client, "Delivery", "expense")
    expense = await create_transaction(
        client,
        category_id=supermercado["id"],
        amount="45000.00",
        description="Pedidos Ya",
    )
    llm.will(
        Reply(
            tool_calls=(
                ToolCall(
                    id="call-0",
                    name="propose_recategorize_transaction",
                    arguments={
                        "transaction_id": expense["id"],
                        "category_id": delivery["id"],
                        "rationale": "Pedidos Ya es delivery, no supermercado.",
                    },
                ),
            )
        )
    )

    review = await finished(client, await agent_review(client))

    assert review["note"] == "hit the iteration cap"
    assert [one["kind"] for one in await suggestions(client)] == [
        "recategorize_transaction"
    ], "the proposal the first turn made outlived the cap"
