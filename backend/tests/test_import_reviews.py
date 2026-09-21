"""
The Review an Import asks for, and the two Imports that share one.

Confirming an Import is the user saying "look at what I just loaded", so the
run waits a couple of minutes before it starts: loading a card statement and
then a bank one is one of those moments rather than two. Here the wait is
driven through the queue fake, which holds a deferred job the way Redis does
and moves the clock to the moment each one would fire.
"""

from datetime import date, timedelta

from tests.api import default_category
from tests.api_imports import LEMON, confirm_body, create_profile, preview
from tests.test_categorization_rules import create_rule
from tests.test_import_confirm import categorised_preview
from tests.test_reviews import inbox
from tests.test_scheduled_reviews import reviews


# Long enough after the first file that the second is a second file, and well
# inside the couple of minutes the first Review is waiting out.
A_MINUTE = timedelta(minutes=1)

# Longer than the Review waits, so by the end of it the run was due and did
# not happen: what a worker that was down looks like from here.
LONG_ENOUGH_THAT_NOBODY_CAME = timedelta(minutes=10)


async def import_mercadopago(client) -> dict:
    """A statement loaded, every row filed by a Rule."""
    profile = await create_profile(client)
    seen = await categorised_preview(client, profile)
    response = await client.post("/imports/", json=confirm_body(seen))
    response.raise_for_status()
    return response.json()


async def import_lemon(client, clock) -> dict:
    """A second file, from somewhere else, loaded right after."""
    await _rates_for_the_days_it_covers(client, clock)
    profile = await create_profile(client, **LEMON)
    suscripciones = await default_category(client, "Suscripciones", "expense")
    rendimientos = await default_category(client, "Rendimientos", "income")
    await create_rule(client, "netflix", suscripciones)
    await create_rule(client, "cashback", rendimientos)
    seen = await preview(client, profile, "lemon.csv")
    response = await client.post("/imports/", json=confirm_body(seen))
    response.raise_for_status()
    return response.json()


async def _rates_for_the_days_it_covers(client, clock) -> None:
    """
    A Rate Snapshot per day the file mentions, as living those days would leave.

    Its rows are in dollars and they are in the past, so without them the
    confirm is refused for want of an Exchange Rate — which is the Import's
    own behaviour and not this file's subject.
    """
    today = clock.date
    for day in (date(2026, 3, 10), date(2026, 3, 11)):
        clock.date = day
        await client.get("/settings/rate", params={"rate_type": "card"})
    clock.date = today


async def import_reviews(client) -> list[dict]:
    """The Reviews an Import asked for, newest first."""
    return [
        one for one in await reviews(client) if one["trigger"] == "import_finished"
    ]


async def test_confirming_an_import_asks_the_agent_about_it(client, llm):
    await import_mercadopago(client)

    [review] = await import_reviews(client)
    assert review["status"] == "queued"
    assert review["used_agent"] is True
    assert llm.runs == [], "it waits, in case another file is on its way"


async def test_the_inbox_does_not_say_it_is_working_while_the_review_waits(
    client, queue
):
    await import_mercadopago(client)

    assert (await inbox(client))["reviews"] == [], (
        "nothing is running yet, and \"Revisar ahora\" is still there to press"
    )


async def test_the_review_waits_a_couple_of_minutes_before_it_starts(
    client, clock, queue
):
    confirmed = clock.now()

    await import_mercadopago(client)
    await queue.release()

    assert clock.now() - confirmed == timedelta(minutes=2), (
        "the run begins a couple of minutes after the file was loaded"
    )


async def test_the_review_runs_once_the_import_has_settled(client, queue, llm):
    llm.says(("Coto", "El súper te salió 12.500,50 este mes."))
    await import_mercadopago(client)

    await queue.release()

    [review] = await import_reviews(client)
    assert review["status"] == "done"
    assert [one["topic"] for one in (await inbox(client))["insights"]] == ["Coto"]


async def test_two_imports_inside_the_window_share_one_review(
    client, clock, queue, llm
):
    await import_mercadopago(client)
    clock.wait(A_MINUTE)
    await import_lemon(client, clock)

    assert len(await import_reviews(client)) == 1, "the second joined the first"

    await queue.release()

    [review] = await import_reviews(client)
    assert review["status"] == "done"
    assert len(llm.runs) == 1, "one run, not one per file"
    assert "mercadopago.csv" in llm.brief
    assert "lemon.csv" in llm.brief


async def test_the_second_import_pushes_the_start_back(client, clock, queue):
    await import_mercadopago(client)
    clock.wait(A_MINUTE)
    await import_lemon(client, clock)

    await queue.release(jobs=1)

    [review] = await import_reviews(client)
    assert review["status"] == "queued", (
        "the moment the first Import asked for came and the run was not due yet"
    )

    await queue.release()

    [review] = await import_reviews(client)
    assert review["status"] == "done"


async def test_an_import_does_not_join_a_review_that_was_already_due(
    client, clock, queue
):
    await import_mercadopago(client)

    clock.wait(LONG_ENOUGH_THAT_NOBODY_CAME)
    await import_lemon(client, clock)

    assert len(await import_reviews(client)) == 2, (
        "a run that should have started already is not one to pile onto"
    )


async def test_an_import_after_the_review_started_gets_a_new_one(
    client, clock, queue, llm
):
    await import_mercadopago(client)
    await queue.release()

    await import_lemon(client, clock)

    assert [one["status"] for one in await import_reviews(client)] == [
        "queued",
        "done",
    ], "the run it would have joined had already happened"

    await queue.release()

    assert [one["status"] for one in await import_reviews(client)] == [
        "done",
        "done",
    ]
    assert "mercadopago.csv" not in llm.brief, (
        "the second Review is about the second file"
    )


async def test_the_brief_is_about_the_rows_and_the_rules_that_filed_them(
    client, queue, llm
):
    await import_mercadopago(client)

    await queue.release()

    assert "mercadopago.csv: 3 Transactions recorded, 2 rows skipped" in llm.brief
    assert '"Supermercado Coto", expense: 12500.50' in llm.brief
    assert '"coto" -> Supermercado' in llm.brief, (
        "a row in the wrong place is only obviously wrong next to its Rule"
    )
    assert "The month under review is 2026-03" in llm.brief, "the core brief too"


async def test_an_import_undone_before_its_review_runs_leaves_nothing_to_read(
    client, queue, llm
):
    record = await import_mercadopago(client)
    await client.delete(f"/imports/{record['id']}")

    await queue.release()

    [review] = await import_reviews(client)
    assert review["status"] == "done"
    assert "it was undone" in llm.brief
