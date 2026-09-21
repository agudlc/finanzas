"""
The Reviews nobody presses a button for, and the Suggestions that leave on
their own.

The month's Recurring Expenses are proposed by a Review that runs on the 1st
without being asked. Here that schedule is driven the way the Inbox drives it:
opening the Inbox catches up on whatever the worker did not run, so a worker
that was down costs nothing but a slower first read. Moving the fixed clock is
what makes a month pass.
"""

from app.models.enums import MANUAL_TRIGGERS
from tests.test_recurring_expenses import create_recurring
from tests.test_reviews import inbox, run_review, suggestions

# What "Revisar ahora" creates, which is the opposite of scheduled.
ASKED_FOR = [one.value for one in MANUAL_TRIGGERS]


async def reviews(client) -> list[dict]:
    response = await client.get("/reviews/")
    response.raise_for_status()
    return response.json()


async def scheduled(client, trigger: str | None = None) -> list[dict]:
    """The Reviews nobody asked for: all of them, or those of one trigger."""
    return [
        one
        for one in await reviews(client)
        if one["trigger"] not in ASKED_FOR and trigger in (None, one["trigger"])
    ]


async def test_opening_the_inbox_runs_this_months_scheduled_review(client):
    await create_recurring(client, description="Alquiler")

    proposed = await suggestions(client)

    assert [one["payload"]["description"] for one in proposed] == ["Alquiler"], (
        "nobody pressed Revisar ahora: the month's Review caught up on its own"
    )
    [review] = await scheduled(client, "recurring_monthly")
    assert review["status"] == "done"


async def test_opening_the_inbox_again_runs_nothing_more(client):
    await create_recurring(client)

    await inbox(client)
    await inbox(client)

    assert sorted(one["trigger"] for one in await scheduled(client)) == [
        "month_end",
        "recurring_monthly",
    ]
    assert len(await suggestions(client)) == 1


async def test_a_manual_review_does_not_replace_the_scheduled_one(client):
    await create_recurring(client)

    await run_review(client)

    assert len(await suggestions(client)) == 1, "the proposal is not made twice"
    assert len(await scheduled(client, "recurring_monthly")) == 1, (
        "the month's Review still happened"
    )


async def test_each_month_gets_its_own_scheduled_review(client, clock):
    await create_recurring(client, expected_day=5)
    await inbox(client)

    clock.date = clock.date.replace(month=4, day=2)
    proposed = await suggestions(client)

    assert len(await scheduled(client, "recurring_monthly")) == 2
    assert [one["payload"]["date"] for one in proposed] == ["2026-04-05"], (
        "March's proposal is gone and April's is waiting"
    )


async def test_a_suggestion_expires_at_the_end_of_its_month(client, clock):
    await create_recurring(client)
    [march] = await suggestions(client)
    assert march["expires_on"] == "2026-03-31"

    clock.date = clock.date.replace(month=4, day=1)
    [april] = await suggestions(client)

    assert april["id"] != march["id"]
    assert april["month"] == "2026-04-01", (
        "an expired proposal does not block the same one next month"
    )
    stale = await client.post(f"/suggestions/{march['id']}/accept", json={})
    assert stale.status_code == 409
    assert "expired" in stale.json()["detail"]


async def test_a_suggestion_lasts_until_its_month_is_over(client, clock):
    await create_recurring(client)
    [march] = await suggestions(client)

    clock.date = clock.date.replace(day=31)

    assert [one["id"] for one in await suggestions(client)] == [march["id"]]


async def test_a_proposal_cannot_be_accepted_once_its_month_is_over(client, clock):
    """Expiry does not wait for the Inbox to be read to be true."""
    await create_recurring(client)
    [march] = await suggestions(client)

    clock.date = clock.date.replace(month=4, day=1)
    stale = await client.post(f"/suggestions/{march['id']}/accept", json={})

    assert stale.status_code == 409
    assert "expired" in stale.json()["detail"]
    assert (await client.get("/transactions/")).json() == []
