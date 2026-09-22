"""
What a run produced, written out for a person to judge.

The same three things for every trigger: what the model observed, what it
proposed, and what the conversation cost. The proposals are written the way
the brief writes them, so what is printed here is what the next Review would
read back — a proposal that looks odd in the Inbox looks odd here too.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Insight, Review, Suggestion
from app.services.brief import proposal
from app.services.categories import list_categories

RULE = "=" * 72


async def of(db: AsyncSession, review: Review) -> str:
    """One Review, as `make eval` prints it."""
    return "\n".join(
        [
            RULE,
            f"{review.trigger.value} — {review.month:%Y-%m}",
            RULE,
            _how_it_went(review),
            "",
            *await _insights(db, review),
            "",
            *await _suggestions(db, review),
        ]
    )


def _how_it_went(review: Review) -> str:
    """
    How the run went, saying only what there is to say.

    A failed run kept none of what it was doing — the whole run is rolled back
    with it, tokens and all — so a line about its prompt and its turns would be
    a row of nulls where the error belongs. What it spent is still said, as
    zero, because the total at the end counts it the same way.
    """
    lines = [
        f"status: {review.status.value}"
        f" · {review.input_tokens or 0} in"
        f" / {review.output_tokens or 0} out tokens"
    ]
    if review.prompt_version is not None:
        lines[0] += f" · prompt {review.prompt_version} · {_turns(review)} turns"
    if review.note is not None:
        lines.append(f"note: {review.note}")
    if review.error is not None:
        lines.append(f"error: {review.error}")
    return "\n".join(lines)


def _turns(review: Review) -> int:
    """How many times the model answered, which is what the run cost."""
    return sum(
        1 for turn in review.transcript or [] if turn["role"] == "assistant"
    )


async def _insights(db: AsyncSession, review: Review) -> list[str]:
    result = await db.execute(
        select(Insight)
        .where(Insight.review_id == review.id)
        .order_by(Insight.created_at)
    )
    insights = list(result.scalars().all())
    if not insights:
        return ["Insights: none."]
    return [
        "Insights:",
        *(f"  - {one.topic}\n    {one.body}" for one in insights),
    ]


async def _suggestions(db: AsyncSession, review: Review) -> list[str]:
    result = await db.execute(
        select(Suggestion)
        .where(Suggestion.review_id == review.id)
        .order_by(Suggestion.created_at)
    )
    suggestions = list(result.scalars().all())
    if not suggestions:
        return ["Suggestions: none."]
    names = {one.id: one.name for one in await list_categories(db)}
    lines = ["Suggestions:"]
    for one in suggestions:
        lines.append(f"  - [{one.kind.value}] {await proposal(db, one, names)}")
        lines.append(f"    why: {one.rationale}")
    return lines
