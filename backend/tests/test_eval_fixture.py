"""
The eval's dataset, checked without spending a token.

`make eval` is the one thing here that talks to the real API, so what this
covers is everything about it that can be wrong for free: that the fixture
seeds a coherent month, that each trigger's Review is wired to what it is
supposed to be about, and that what the run prints is what a run produced.
Whether the answers are any good is the eval's question, and a person's.
"""

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models import Review
from app.models.enums import AGENT_TRIGGERS, ReviewStatus, ReviewTrigger
from app.services.reviews import run_review
from evals import report
from evals.fixture import CASES, Case, seed
from evals.run import FixedIndexSource, NoQueue, PinnedClock


@pytest.fixture
def sessions(clean_database, engine):
    return async_sessionmaker(engine, expire_on_commit=False)


async def run_case(sessions, case: Case, llm) -> tuple[Review, str]:
    """
    One eval case, run against a scripted model instead of the API.

    Everything else is what `make eval` uses — the fixture, the pinned day, the
    IPC it publishes — so what this covers is the run itself and not a
    rehearsal of it.
    """
    async with sessions() as db:
        await seed(db)
        review = await case.review(db)
    async with sessions() as db:
        finished = await run_review(
            db,
            review.id,
            PinnedClock(),
            index_source=FixedIndexSource(),
            llm=llm,
            queue=NoQueue(),
        )
        return finished, await report.of(db, finished)


CASE_BY_TRIGGER = {case.trigger: case for case in CASES}


async def test_there_is_a_case_for_every_trigger_the_agent_serves():
    assert set(CASE_BY_TRIGGER) == set(AGENT_TRIGGERS)


@pytest.mark.parametrize(
    "trigger", list(CASE_BY_TRIGGER), ids=lambda one: one.value
)
async def test_each_case_runs_the_agent_over_the_seeded_month(
    sessions, llm, trigger
):
    llm.says(("Delivery", "Gastaste de más en Delivery."))
    review, _ = await run_case(sessions, CASE_BY_TRIGGER[trigger], llm)

    assert review.status is ReviewStatus.done, review.error
    assert review.used_agent
    assert "The month under review is 2026-03" in llm.brief


async def test_the_import_case_is_about_what_was_imported(sessions, llm):
    await run_case(sessions, CASE_BY_TRIGGER[ReviewTrigger.import_finished], llm)

    assert "An Import has just finished" in llm.brief
    assert "RAPPI*RESTAURANTES" in llm.brief
    assert "FARMACITY SUC 45" in llm.brief


async def test_the_budget_case_is_about_the_Budget_that_broke(sessions, llm):
    await run_case(sessions, CASE_BY_TRIGGER[ReviewTrigger.budget_exceeded], llm)

    assert "Delivery went over its Budget for 2026-03" in llm.brief


async def test_the_month_end_case_is_about_the_month_that_ended(sessions, llm):
    await run_case(sessions, CASE_BY_TRIGGER[ReviewTrigger.month_end], llm)

    assert "2026-02 has ended and 2026-03 has begun" in llm.brief
    assert "IPC for 2026-02" in llm.brief


async def test_the_month_has_history_to_compare_against(sessions, llm):
    """Three months of it, which is the whole of the default lookback."""
    await run_case(sessions, CASE_BY_TRIGGER[ReviewTrigger.month_end], llm)

    for month in ("2026-01", "2026-02"):
        assert month in llm.brief


async def test_the_report_says_what_the_run_produced(sessions, llm):
    llm.says(("Delivery", "Gastaste 96.500 en Delivery, 61% más que el límite."))
    _, printed = await run_case(
        sessions, CASE_BY_TRIGGER[ReviewTrigger.manual_agent], llm
    )

    assert "manual_agent" in printed
    assert "Delivery" in printed
    assert "Gastaste 96.500 en Delivery" in printed
    # The tokens the scripted model reported for its two turns.
    assert "2600 in" in printed
    assert "320 out" in printed
