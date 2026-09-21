"""
The first Review: pressing "Revisar ahora" and finding the month's Recurring
Expenses waiting in the Inbox.

The worker is faked at the edge, as the dollar rates are: the queue runs the
Review in-process instead of handing it to Redis, so what these tests read back
through the API is exactly what a real worker would have left behind.
"""

from tests.api import default_category
from tests.test_recurring_expenses import create_recurring


async def run_review(client) -> dict:
    """"Revisar ahora", and the deterministic half of what it asked for."""
    [deterministic] = [
        one for one in await press_revisar_ahora(client) if one["trigger"] == "manual"
    ]
    return deterministic


async def press_revisar_ahora(client) -> list[dict]:
    """Both Reviews the button asks for: the arithmetic and the agent."""
    response = await client.post("/reviews/")
    response.raise_for_status()
    return response.json()


async def inbox(client) -> dict:
    response = await client.get("/inbox/")
    response.raise_for_status()
    return response.json()


async def suggestions(client) -> list[dict]:
    return (await inbox(client))["suggestions"]


async def test_a_manual_review_proposes_each_active_recurring_expense(client):
    await create_recurring(client, description="Alquiler")
    await create_recurring(client, description="Netflix", expected_day=12)

    await run_review(client)

    proposed = await suggestions(client)
    assert {one["payload"]["description"] for one in proposed} == {
        "Alquiler",
        "Netflix",
    }
    assert all(one["kind"] == "add_transaction" for one in proposed)
    assert all(one["status"] == "pending" for one in proposed)


async def test_a_suggestion_carries_the_templates_expense(client):
    alquiler = await default_category(client, "Alquiler", "expense")
    template = await create_recurring(
        client, category_id=alquiler["id"], reference_amount="450000.00"
    )

    await run_review(client)

    [proposed] = await suggestions(client)
    assert proposed["payload"] == {
        "description": "Alquiler",
        "category_id": alquiler["id"],
        "currency": "ARS",
        "amount": "450000.00",
        "date": "2026-03-05",
        "is_fixed": True,
        "recurring_expense_id": template["id"],
    }
    assert proposed["month"] == "2026-03-01"


async def test_a_suggestion_says_why_it_is_being_proposed(client):
    await create_recurring(client, description="Alquiler")

    await run_review(client)

    [proposed] = await suggestions(client)
    assert "Alquiler" in proposed["rationale"]
    assert "monto de referencia" in proposed["rationale"]


async def test_an_expected_day_the_month_is_too_short_for_lands_on_its_last(
    client, clock
):
    clock.date = clock.date.replace(month=2, day=1)
    await create_recurring(client, expected_day=31)

    await run_review(client)

    [proposed] = await suggestions(client)
    assert proposed["payload"]["date"] == "2026-02-28"


async def test_a_paused_template_proposes_nothing(client):
    template = await create_recurring(client)
    await client.patch(
        f"/recurring-expenses/{template['id']}", json={"is_active": False}
    )

    await run_review(client)

    assert await suggestions(client) == []


async def test_running_a_review_again_proposes_nothing_twice(client):
    await create_recurring(client)

    await run_review(client)
    await run_review(client)

    assert len(await suggestions(client)) == 1


async def test_a_review_that_ran_is_done(client):
    await create_recurring(client)

    review = await run_review(client)

    assert review["status"] == "queued", "the Review is handed to the worker"
    finished = (await client.get(f"/reviews/{review['id']}")).json()
    assert finished["status"] == "done"
    assert finished["trigger"] == "manual"
    assert finished["used_agent"] is False
    assert finished["error"] is None
    assert finished["started_at"] and finished["finished_at"]


async def test_a_review_that_raises_is_left_failed_with_its_error(client, queue):
    queue.break_with("el productor explotó")
    await create_recurring(client)

    review = await run_review(client)

    failed = (await client.get(f"/reviews/{review['id']}")).json()
    assert failed["status"] == "failed"
    assert failed["error"] and "el productor explotó" in failed["error"]
    assert await suggestions(client) == []


async def test_recent_reviews_are_listed_newest_first(client):
    first = await run_review(client)
    second = await run_review(client)

    listed = (await client.get("/reviews/")).json()

    asked_for = [one["id"] for one in listed if one["trigger"] == "manual"]
    assert asked_for == [second["id"], first["id"]]


async def test_a_review_that_does_not_exist_returns_404(client):
    unknown = "00000000-0000-0000-0000-000000000000"

    assert (await client.get(f"/reviews/{unknown}")).status_code == 404


async def test_the_inbox_counts_what_is_pending(client):
    # Read before there is anything to propose: this month's own Review runs
    # on the first read, and would otherwise propose the templates below.
    assert (await inbox(client))["pending_count"] == 0

    await create_recurring(client, description="Alquiler")
    await create_recurring(client, description="Netflix", expected_day=12)
    await run_review(client)

    assert (await inbox(client))["pending_count"] == 2


async def test_the_inbox_shows_a_review_that_is_still_waiting(client, queue):
    queue.hold()
    review = await run_review(client)

    waiting = await inbox(client)

    assert {one["trigger"] for one in waiting["reviews"]} == {
        "recurring_monthly",
        "month_end",
        "manual",
        "manual_agent",
    }, "the month's own Reviews are caught up on by the read, and held too"
    assert review["id"] in [one["id"] for one in waiting["reviews"]]
    assert all(one["status"] == "queued" for one in waiting["reviews"])
    assert waiting["suggestions"] == []


async def test_the_inbox_is_clear_once_the_review_has_finished(client):
    await create_recurring(client)

    await run_review(client)

    assert (await inbox(client))["reviews"] == [], (
        "a Review that is done is history, not something to wait for"
    )
