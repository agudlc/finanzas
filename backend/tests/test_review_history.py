"""
The Reviews history: every run the app has made, and what each one was.

A run happens in the worker, out of sight, and the only thing the Inbox shows
of it is what it proposed. These tests are the other half: the list says how
each run went and what it cost, and the detail says what the run actually was,
down to the exchange with the model. That is what makes a strange proposal
answerable — it came from this turn, of this run, under this prompt.
"""

from app.llm import Reply, ToolCall
from tests.test_agent_proposals import misfiled
from tests.test_agent_reviews import agent_review, finished
from tests.test_recurring_expenses import create_recurring
from tests.test_reviews import press_revisar_ahora, run_review

UNKNOWN = "00000000-0000-0000-0000-000000000000"


async def history(client) -> list[dict]:
    response = await client.get("/reviews/")
    response.raise_for_status()
    return response.json()


async def test_the_history_shows_every_run_and_how_it_went(client, llm):
    llm.says(("Delivery", "Se te fue la mano con el delivery."))

    await press_revisar_ahora(client)

    listed = await history(client)
    assert {one["trigger"] for one in listed} == {"manual", "manual_agent"}
    assert [one["used_agent"] for one in listed].count(True) == 1
    assert all(one["status"] == "done" for one in listed)
    assert [one["created_at"] for one in listed] == sorted(
        [one["created_at"] for one in listed], reverse=True
    ), "newest first, because the run being asked about is usually the last one"


async def test_the_history_says_what_an_agent_run_cost(client, llm):
    llm.says(("Delivery", "Se te fue la mano con el delivery."))

    await press_revisar_ahora(client)

    [agent] = [one for one in await history(client) if one["used_agent"]]
    assert agent["input_tokens"] == 2600
    assert agent["output_tokens"] == 320


async def test_a_run_that_called_nobody_has_no_tokens_to_show(client):
    await run_review(client)

    [arithmetic] = [one for one in await history(client) if not one["used_agent"]]
    assert arithmetic["input_tokens"] is None
    assert arithmetic["output_tokens"] is None


async def test_the_history_carries_the_note_of_a_run_that_hit_the_cap(client, llm):
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

    await agent_review(client)

    [agent] = [one for one in await history(client) if one["used_agent"]]
    assert agent["status"] == "done"
    assert agent["note"] == "hit the iteration cap"


async def test_the_history_carries_the_error_of_a_failed_run(client, llm):
    llm.without_key()

    await agent_review(client)

    [agent] = [one for one in await history(client) if one["used_agent"]]
    assert agent["status"] == "failed"
    assert "ANTHROPIC_API_KEY is not set" in agent["error"]


async def test_the_list_leaves_the_exchange_out(client, llm):
    llm.says(("Delivery", "Se te fue la mano con el delivery."))
    await press_revisar_ahora(client)

    [agent] = [one for one in await history(client) if one["used_agent"]]

    assert "transcript" not in agent, (
        "the list is polled and read as a list; megabytes of exchange are not"
    )


async def test_the_detail_adds_the_exchange_and_the_prompt_behind_it(client, llm):
    llm.says(("Delivery", "Se te fue la mano con el delivery."))

    review = await finished(client, await agent_review(client))

    assert review["prompt_version"]
    assert [turn["role"] for turn in review["transcript"]] == [
        "user",
        "assistant",
        "user",
        "assistant",
    ]


async def test_the_detail_carries_what_the_run_produced(client, llm):
    expense, delivery = await misfiled(client)
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
                ToolCall(
                    id="call-1",
                    name="record_insight",
                    arguments={"topic": "Delivery", "body": "Mucho delivery."},
                ),
            )
        ),
        Reply(text="Listo."),
    )

    review = await finished(client, await agent_review(client))

    assert [one["kind"] for one in review["suggestions"]] == [
        "recategorize_transaction"
    ]
    assert [one["topic"] for one in review["insights"]] == ["Delivery"]


async def test_a_deterministic_runs_detail_carries_its_proposals(client):
    await create_recurring(client, description="Alquiler")

    review = await finished(client, await run_review(client))

    assert [one["payload"]["description"] for one in review["suggestions"]] == [
        "Alquiler"
    ]
    assert review["insights"] == [], "the arithmetic observes nothing"
    assert review["transcript"] is None


async def test_a_review_that_does_not_exist_returns_404(client):
    assert (await client.get(f"/reviews/{UNKNOWN}")).status_code == 404
