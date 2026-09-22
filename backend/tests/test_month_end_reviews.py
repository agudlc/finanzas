"""
The month-end Review: the agent deciding next month's Budgets, and what runs
when it cannot.

On the 1st the user is owed one thing — the limits the new month should run on
— and the agent is who works them out, from what last month's Budgets actually
held, the IPC that came out and what each Category has been costing. TODAY is
the 15th of March 2026, so the month under review is March and the month that
ended is February.

The other half is what happens when the model is not there. A failed agent Review
asks for a deterministic Review of the same trigger, which proposes the same
shape of change by arithmetic; what that proposes is `test_month_end_budgets`.
Here the point is that it happens at all, and only when the agent did not
deliver — the user never ends up holding two sets of Budget proposals.
"""

from app.llm import Reply, ToolCall
from tests.api import create_transaction, default_category
from tests.api_imports import confirm_body, create_profile
from tests.test_agent_tools import widen_the_lookback
from tests.test_budgets import create_budget
from tests.test_import_confirm import categorised_preview
from tests.test_month_end_budgets import budget_suggestions, last_month
from tests.test_reviews import inbox
from tests.test_scheduled_reviews import reviews


async def month_end_reviews(client) -> list[dict]:
    """The month-end Reviews there have been, newest first."""
    return [one for one in await reviews(client) if one["trigger"] == "month_end"]


async def ran(client) -> list[dict]:
    """Open the Inbox, which is what catches the month's Reviews up."""
    await inbox(client)
    return await month_end_reviews(client)


def proposes_a_budget(llm, category, amount="130000.00") -> None:
    """The model asking for next month's limit, and then stopping."""
    llm.will(
        Reply(
            tool_calls=(
                ToolCall(
                    id="call-0",
                    name="propose_set_budget",
                    arguments={
                        "category_id": category["id"],
                        "month": "2026-03-01",
                        "amount": amount,
                        "currency": "ARS",
                        "rationale": (
                            "En febrero gastaste 120.000,00 de un límite de "
                            "100.000,00 y el IPC fue 1,659%."
                        ),
                    },
                ),
            )
        ),
        Reply(text="Listo."),
    )


async def test_the_month_end_review_is_the_agents(client):
    [review] = await ran(client)

    assert review["used_agent"] is True
    assert review["status"] == "done"
    assert review["month"] == "2026-03-01"


async def test_the_agent_proposes_next_months_budgets(client, llm):
    supermercado = await default_category(client, "Supermercado", "expense")
    await last_month(client, supermercado)
    proposes_a_budget(llm, supermercado)

    [review] = await ran(client)

    [proposal] = await budget_suggestions(client)
    assert proposal["review_id"] == review["id"]
    assert proposal["payload"] == {
        "category_id": supermercado["id"],
        "month": "2026-03-01",
        "amount": "130000.00",
        "currency": "ARS",
    }
    assert "1,659%" in proposal["rationale"]


async def test_the_brief_holds_last_months_budgets_against_what_was_spent(
    client, llm
):
    supermercado = await default_category(client, "Supermercado", "expense")
    await last_month(client, supermercado, amount="100000.00")
    await create_transaction(
        client,
        category_id=supermercado["id"],
        amount="120000.00",
        date="2026-02-20",
    )

    await ran(client)

    assert "2026-02 has ended and 2026-03 has begun" in llm.brief
    assert (
        "- Supermercado: limit 100000.00 ARS, spent 120000.00 (120.00%)"
        in llm.brief
    )
    assert "no Pace, because the month is not the one being lived" in llm.brief
    assert "The month under review is 2026-03" in llm.brief, "the core brief too"


async def test_the_brief_says_which_month_the_latest_index_is_for(client, llm):
    await ran(client)

    assert "IPC for 2026-02: 1.659%" in llm.brief, (
        "February's is the newest out by the 1st of March"
    )


async def test_an_index_nobody_published_is_said_to_be_missing(
    client, llm, index_source
):
    index_source.fail_with("datos.gob.ar is down")

    await ran(client)

    assert "Nothing has been published that is recent enough" in llm.brief


async def test_the_brief_holds_what_each_category_has_cost_month_by_month(
    client, llm
):
    supermercado = await default_category(client, "Supermercado", "expense")
    ropa = await default_category(client, "Ropa", "expense")
    await create_transaction(
        client,
        category_id=supermercado["id"],
        amount="80000.00",
        date="2026-01-10",
    )
    await create_transaction(
        client,
        category_id=supermercado["id"],
        amount="120000.00",
        date="2026-02-20",
    )

    await ran(client)

    assert "- Supermercado: 2026-01: 80000.00, 2026-02: 120000.00" in llm.brief
    assert "- Ropa:" not in llm.brief, (
        "a Category nothing was ever spent in is not a row of zeros"
    )
    assert "2026-03:" not in llm.brief.split("month by month")[1], (
        "the month that has barely started would read as a collapse"
    )


async def test_a_wider_lookback_reaches_further_back(client, llm):
    supermercado = await default_category(client, "Supermercado", "expense")
    await create_transaction(
        client,
        category_id=supermercado["id"],
        amount="60000.00",
        date="2025-06-10",
    )
    await widen_the_lookback(client)

    await ran(client)

    assert "2025-06: 60000.00" in llm.brief, "a year reaches back to 2025-04"


async def test_a_failed_agent_review_is_stood_in_for_by_the_arithmetic(client, llm):
    supermercado = await default_category(client, "Supermercado", "expense")
    await last_month(client, supermercado)
    llm.fail_with("the model did not answer: 500 internal error")

    [stand_in, agent] = await ran(client)

    assert agent["used_agent"] is True
    assert agent["status"] == "failed"
    assert "500 internal error" in agent["error"]
    assert stand_in["used_agent"] is False
    assert stand_in["status"] == "done"
    assert stand_in["month"] == agent["month"]
    [proposal] = await budget_suggestions(client)
    assert proposal["review_id"] == stand_in["id"]
    assert proposal["payload"]["amount"] == "102000.00", "100.000 by the IPC"


async def test_an_installation_without_a_key_still_gets_its_proposals(
    client, llm
):
    supermercado = await default_category(client, "Supermercado", "expense")
    await last_month(client, supermercado)
    llm.without_key()

    [stand_in, agent] = await ran(client)

    assert agent["status"] == "failed"
    assert "ANTHROPIC_API_KEY is not set" in agent["error"]
    assert stand_in["status"] == "done"
    assert len(await budget_suggestions(client)) == 1


async def test_a_run_the_agent_finished_is_not_stood_in_for(client, llm):
    supermercado = await default_category(client, "Supermercado", "expense")
    await last_month(client, supermercado)
    proposes_a_budget(llm, supermercado)

    reviewed = await ran(client)

    assert len(reviewed) == 1, "the agent delivered; nothing stands in for it"
    [proposal] = await budget_suggestions(client)
    assert proposal["payload"]["amount"] == "130000.00", (
        "the agent's figure, not the arithmetic's 102.000"
    )


async def test_an_agent_review_that_proposed_nothing_is_not_stood_in_for(
    client, llm
):
    """Silence is an answer: the agent read the month and left the limits be."""
    supermercado = await default_category(client, "Supermercado", "expense")
    await last_month(client, supermercado)

    reviewed = await ran(client)

    assert len(reviewed) == 1
    assert await budget_suggestions(client) == []


async def test_the_stand_in_is_asked_for_once(client, llm):
    supermercado = await default_category(client, "Supermercado", "expense")
    await last_month(client, supermercado)
    llm.without_key()

    await ran(client)
    reviewed = await ran(client)

    assert [one["used_agent"] for one in reviewed] == [False, True]
    assert len(await budget_suggestions(client)) == 1


async def test_next_month_asks_the_agent_again(client, llm, clock):
    llm.without_key()
    await ran(client)

    clock.date = clock.date.replace(month=4, day=1)
    reviewed = await ran(client)

    assert [(one["month"], one["used_agent"]) for one in reviewed] == [
        ("2026-04-01", False),
        ("2026-04-01", True),
        ("2026-03-01", False),
        ("2026-03-01", True),
    ], "April asks the agent of its own accord, and stands in for it again"


async def test_an_import_review_that_fails_is_not_stood_in_for(client, llm, queue):
    """There is no arithmetic that could say what the agent was going to."""
    llm.without_key()
    profile = await create_profile(client)
    seen = await categorised_preview(client, profile)

    response = await client.post("/imports/", json=confirm_body(seen))
    response.raise_for_status()
    await queue.release()

    asked = [
        one for one in await reviews(client) if one["trigger"] == "import_finished"
    ]
    assert [one["status"] for one in asked] == ["failed"]


async def test_a_budget_exceeded_review_that_fails_is_not_stood_in_for(
    client, llm
):
    llm.without_key()
    supermercado = await default_category(client, "Supermercado", "expense")
    await create_budget(client, supermercado, amount="10000.00")

    await create_transaction(
        client, amount="12500.50", category_id=supermercado["id"]
    )

    asked = [
        one for one in await reviews(client) if one["trigger"] == "budget_exceeded"
    ]
    assert [one["status"] for one in asked] == ["failed"]
