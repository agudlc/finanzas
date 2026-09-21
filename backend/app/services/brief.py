"""
The core brief: the month, written out for the model to read.

It is the one place that decides what a Review is allowed to know, which is
what keeps the cost of a run bounded and the answer about *this* month. It is
built from the same services the screens read, so the agent is never told
something the user cannot see for themselves.

It is written in English, like the rest of the code; what comes back is the
user's, and the system prompt is where that is asked for in Spanish.
"""

import uuid
from collections.abc import Callable
from datetime import date as Date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.clock import Clock
from app.models import Review, Suggestion
from app.models.enums import Currency, SuggestionKind
from app.months import format_month
from app.services import insights as insights_service
from app.services.budgets import budgets_in, progress_of
from app.services.categories import list_categories
from app.services.money import MoneyConverter, converter_for
from app.services.settings import get_settings
from app.services.suggestions import pending_suggestions, rejected_since
from app.services.summary import converted_totals


async def core_brief(db: AsyncSession, review: Review, clock: Clock) -> str:
    """Everything the Review is told before it says anything."""
    month = review.month
    currency = (await get_settings(db)).display_currency
    converter = await converter_for(db, clock)
    names = await _category_names(db)
    return "\n\n".join(
        [
            _header(month, clock, currency),
            await _spending(db, month, currency, converter),
            await _budgets(db, month, clock, converter, names),
            await _pending(db, names),
            await _rejections(db, month, names),
            await _insights(db, month),
        ]
    )


def _section(title: str, lines: list[str], when_empty: str) -> str:
    return "\n".join([f"## {title}", *(lines or [when_empty])])


def _figure(value: Decimal) -> str:
    """
    An amount written plainly, so there is nothing to misread.

    Not the way the app writes amounts: 45.000,00 read as a number is anyone's
    guess, and the system prompt is where the Spanish format is asked for.
    """
    return f"{value:.2f}"


async def _category_names(db: AsyncSession) -> dict[uuid.UUID, str]:
    return {one.id: one.name for one in await list_categories(db)}


def _named(names: dict[uuid.UUID, str], category_id: str | uuid.UUID) -> str:
    return names.get(uuid.UUID(str(category_id)), "an unknown Category")


def _header(month: Date, clock: Clock, currency: Currency) -> str:
    return (
        f"The month under review is {format_month(month)}. "
        f"Today is {clock.today().isoformat()}. "
        f"Every amount below is in {currency.value}, the Display Currency, "
        f"converted through each Transaction's own Exchange Rate, and written "
        f"plainly as 45000.00 — write them back the way the app does."
    )


async def _spending(
    db: AsyncSession, month: Date, currency: Currency, converter: MoneyConverter
) -> str:
    """
    What came in, what went out, and what each expense Category cost.

    The Income and the Monthly Result are here because a month read as
    spending alone invites advice the user cannot act on: whether 45000 in
    Delivery is a lot depends on what arrived that month.
    """
    income, expenses, by_category = await converted_totals(
        db, month, currency, converter
    )
    return _section(
        "This month so far",
        [
            f"- Income: {_figure(income)}",
            f"- Expenses: {_figure(expenses)}",
            f"- Monthly Result: {_figure(income - expenses)}",
            *(f"- {one.name}: {_figure(one.total)}" for one in by_category),
        ],
        "- Nothing has been recorded this month yet.",
    )


async def _budgets(
    db: AsyncSession,
    month: Date,
    clock: Clock,
    converter: MoneyConverter,
    names: dict[uuid.UUID, str],
) -> str:
    """
    Each Budget against what it has cost and against its Pace.

    It reads the Budgets the month already has rather than starting the month
    off a copy of the last one: a Review is a reader, and opening a month is a
    decision that belongs to the user pressing something.
    """
    lines = []
    for budget in await budgets_in(db, month):
        progress = await progress_of(db, budget, clock, converter)
        pace = (
            "no Pace, because the month is not the one being lived"
            if progress.pace is None
            else f"Pace says {_figure(progress.pace)} by today"
        )
        lines.append(
            f"- {_named(names, budget.category_id)}: "
            f"limit {_figure(progress.amount)} {progress.currency.value}, "
            f"spent {_figure(progress.spent)} ({_figure(progress.percentage)}%), "
            f"{pace}, state {progress.state.value}"
        )
    return _section(
        "Budgets this month", lines, "- This month has no Budgets set."
    )


def _budget_proposal(suggestion: Suggestion, category: str) -> str:
    payload = suggestion.payload
    return (
        f"set the {category} Budget for {format_month(suggestion.month)} "
        f"to {payload['amount']} {payload['currency']}"
    )


def _transaction_proposal(suggestion: Suggestion, category: str) -> str:
    payload = suggestion.payload
    return (
        f"record \"{payload['description']}\" in {category}, "
        f"{payload['amount']} {payload['currency']} on {payload['date']}"
    )


# How each kind reads in a line. A map rather than a cascade, as accepting one
# dispatches: a new kind has to say how it is written here, instead of being
# quietly described as the kind that happened to be the fallback.
PROPOSALS: dict[SuggestionKind, Callable[[Suggestion, str], str]] = {
    SuggestionKind.add_transaction: _transaction_proposal,
    SuggestionKind.set_budget: _budget_proposal,
}


def _proposal(suggestion: Suggestion, names: dict[uuid.UUID, str]) -> str:
    """One proposal in a line: what it would do, not how it is stored."""
    return PROPOSALS[suggestion.kind](
        suggestion, _named(names, suggestion.payload["category_id"])
    )


async def _pending(db: AsyncSession, names: dict[uuid.UUID, str]) -> str:
    """
    What is already waiting in the Inbox.

    The Review reads it so it does not propose what the arithmetic has already
    proposed (ADR-0003), and so an observation can point at it.
    """
    lines = [
        f"- {_proposal(one, names)}. Why: {one.rationale}"
        for one in await pending_suggestions(db)
    ]
    return _section(
        "Proposals already waiting in the Inbox",
        lines,
        "- Nothing is waiting in the Inbox.",
    )


async def _rejections(
    db: AsyncSession, month: Date, names: dict[uuid.UUID, str]
) -> str:
    """
    What the user said no to lately, and why when they said.

    A rejection means "not this month" rather than "never", so it is history
    to take into account rather than a rule: the same proposal can come back.
    """
    lines = []
    for one in await rejected_since(db, month):
        reason = (
            "no reason given"
            if one.rejection_reason is None
            else f'"{one.rejection_reason}"'
        )
        lines.append(
            f"- in {format_month(one.month)} they said no to "
            f"{_proposal(one, names)}: {reason}"
        )
    return _section(
        "Proposals the user rejected recently",
        lines,
        "- The user has not rejected anything recently.",
    )


async def _insights(db: AsyncSession, month: Date) -> str:
    lines = [
        f"- {format_month(one.month)} — {one.topic}: {one.body}"
        for one in await insights_service.recent(db, month)
    ]
    return _section(
        "Observations already recorded this month and in the two before it",
        lines,
        "- Nothing has been observed yet.",
    )
