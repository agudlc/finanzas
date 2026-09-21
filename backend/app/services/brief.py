"""
The brief: the month, written out for the model to read.

It is the one place that decides what a Review is allowed to know, which is
what keeps the cost of a run bounded and the answer about *this* month. It is
built from the same services the screens read, so the agent is never told
something the user cannot see for themselves.

Every Review gets the core brief; some get more. What a run is for is the
trigger, and a Review that fires because an Import finished is being asked
about those rows in particular — so it is handed them, and the Rules that filed
them, on top of the month they landed in. One that fires because a Budget went
over is being asked about that Category, so it is handed what it was spent on
this month and what it has cost month by month.

It is written in English, like the rest of the code; what comes back is the
user's, and the system prompt is where that is asked for in Spanish.

How it writes a section, a figure, a Category name and a proposal is public,
because the read tools answer in the same words: whatever the agent reaches
for, it is reading one language and not two.
"""

import uuid
from collections.abc import Awaitable, Callable
from datetime import date as Date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clock import Clock
from app.models import Budget, Import, Review, Suggestion, Transaction
from app.models.enums import Currency, ReviewTrigger
from app.months import format_month, months_from
from app.services import insights as insights_service
from app.services.budgets import budgets_in, progress_of, spent_in
from app.services.categories import list_categories
from app.services.categorization import list_rules
from app.services.kinds import KINDS
from app.services.lookback import earliest_month_for
from app.services.money import MoneyConverter, converter_for
from app.services.settings import get_settings
from app.services.suggestions import pending_suggestions, rejected_since
from app.services.summary import converted_totals
from app.services.transactions import in_month

# How many imported Transactions the brief writes out. A statement is a few
# dozen rows and this is two months of them; past that the run is being asked
# to read a database rather than a file, and the read tools are how it digs.
IMPORTED_ROWS = 200

# How many of the Category's own Transactions the brief writes out when a
# Budget has gone over. One Category in one month is rarely near this, and a
# Category that is has a shape the totals below show better than the rows.
CATEGORY_ROWS = 100


async def brief(db: AsyncSession, review: Review, clock: Clock) -> str:
    """
    Everything this Review is told before it says anything.

    The core brief, and whatever its trigger adds to it. A trigger with nothing
    to add gets the core brief alone, which is what "the month" means.
    """
    core = await core_brief(db, review, clock)
    extra = EXTRAS.get(review.trigger)
    if extra is None:
        return core
    return "\n\n".join([core, await extra(db, review, clock)])


async def core_brief(db: AsyncSession, review: Review, clock: Clock) -> str:
    """Everything the Review is told before it says anything."""
    month = review.month
    currency = (await get_settings(db)).display_currency
    converter = await converter_for(db, clock)
    names = await _category_names(db)
    earliest = await earliest_month_for(db, month)
    return "\n\n".join(
        [
            _header(month, clock, currency, earliest),
            await _spending(db, month, currency, converter),
            await _budgets(db, month, clock, converter, names),
            await _pending(db, names),
            await _rejections(db, month, names, earliest),
            await _insights(db, month, earliest),
        ]
    )


def section(title: str, lines: list[str], when_empty: str) -> str:
    return "\n".join([f"## {title}", *(lines or [when_empty])])


def figure(value: Decimal) -> str:
    """
    An amount written plainly, so there is nothing to misread.

    Not the way the app writes amounts: 45.000,00 read as a number is anyone's
    guess, and the system prompt is where the Spanish format is asked for.
    """
    return f"{value:.2f}"


async def _category_names(db: AsyncSession) -> dict[uuid.UUID, str]:
    return {one.id: one.name for one in await list_categories(db)}


def named(names: dict[uuid.UUID, str], category_id: str | uuid.UUID) -> str:
    return names.get(uuid.UUID(str(category_id)), "an unknown Category")


def _header(
    month: Date, clock: Clock, currency: Currency, earliest: Date
) -> str:
    return (
        f"The month under review is {format_month(month)}. "
        f"Today is {clock.today().isoformat()}. "
        f"Every amount below is in {currency.value}, the Display Currency, "
        f"converted through each Transaction's own Exchange Rate, and written "
        f"plainly as 45000.00 — write them back the way the app does. "
        f"The user lets you read back as far as {format_month(earliest)} and "
        f"no further, here or through a tool."
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
    return section(
        "This month so far",
        [
            f"- Income: {figure(income)}",
            f"- Expenses: {figure(expenses)}",
            f"- Monthly Result: {figure(income - expenses)}",
            *(f"- {one.name}: {figure(one.total)}" for one in by_category),
        ],
        "- Nothing has been recorded this month yet.",
    )


async def budget_lines(
    db: AsyncSession,
    month: Date,
    clock: Clock,
    converter: MoneyConverter,
    names: dict[uuid.UUID, str],
) -> list[str]:
    """
    Each Budget of the month against what it has cost and against its Pace.

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
            else f"Pace says {figure(progress.pace)} by today"
        )
        lines.append(
            f"- {named(names, budget.category_id)}: "
            f"limit {figure(progress.amount)} {progress.currency.value}, "
            f"spent {figure(progress.spent)} ({figure(progress.percentage)}%), "
            f"{pace}, state {progress.state.value}"
        )
    return lines


async def _budgets(
    db: AsyncSession,
    month: Date,
    clock: Clock,
    converter: MoneyConverter,
    names: dict[uuid.UUID, str],
) -> str:
    return section(
        "Budgets this month",
        await budget_lines(db, month, clock, converter, names),
        "- This month has no Budgets set.",
    )


async def proposal(
    db: AsyncSession, suggestion: Suggestion, names: dict[uuid.UUID, str]
) -> str:
    """
    One proposal in a line: what it would do, not how it is stored.

    How each kind reads is the kind's own business, so a new one cannot be
    quietly described as whichever kind happened to be the fallback. Every
    payload names a Category, which is resolved here because every kind wants
    it; whatever else a kind has to look up, it looks up itself.
    """
    return await KINDS[suggestion.kind].reads(
        db, suggestion, named(names, suggestion.payload["category_id"])
    )


async def _pending(db: AsyncSession, names: dict[uuid.UUID, str]) -> str:
    """
    What is already waiting in the Inbox.

    The Review reads it so it does not propose what the arithmetic has already
    proposed (ADR-0003), and so an observation can point at it.
    """
    lines = [
        f"- {await proposal(db, one, names)}. Why: {one.rationale}"
        for one in await pending_suggestions(db)
    ]
    return section(
        "Proposals already waiting in the Inbox",
        lines,
        "- Nothing is waiting in the Inbox.",
    )


async def _rejections(
    db: AsyncSession, month: Date, names: dict[uuid.UUID, str], earliest: Date
) -> str:
    """
    What the user said no to lately, and why when they said.

    A rejection means "not this month" rather than "never", so it is history
    to take into account rather than a rule: the same proposal can come back.
    """
    lines = []
    for one in await rejected_since(db, month, earliest):
        reason = (
            "no reason given"
            if one.rejection_reason is None
            else f'"{one.rejection_reason}"'
        )
        lines.append(
            f"- in {format_month(one.month)} they said no to "
            f"{await proposal(db, one, names)}: {reason}"
        )
    return section(
        "Proposals the user rejected recently",
        lines,
        "- The user has not rejected anything recently.",
    )


async def _insights(db: AsyncSession, month: Date, earliest: Date) -> str:
    lines = [
        f"- {format_month(one.month)} — {one.topic}: {one.body}"
        for one in await insights_service.recent(db, month, earliest)
    ]
    return section(
        "Observations already recorded this month and in the two before it",
        lines,
        "- Nothing has been observed yet.",
    )


async def transaction_line(
    converter: MoneyConverter,
    currency: Currency,
    names: dict[uuid.UUID, str],
    one: Transaction,
) -> str:
    """
    One Transaction as the agent reads it: converted, and said so when it was.

    A USD Expense keeps its Original Amount next to the converted one, because
    "30 dólares" is what the user remembers spending and the pesos are what
    the month adds up to.
    """
    amount = await converter.convert(
        one.amount, one.currency, currency, one.date, one.exchange_rate
    )
    original = (
        ""
        if one.currency is currency
        else f" (originally {figure(one.amount)} {one.currency.value})"
    )
    return (
        f"- {one.date.isoformat()}, {named(names, one.category_id)}, "
        f'"{one.description or "no description"}", {one.type.value}: '
        f"{figure(amount)}{original}"
    )


async def _what_was_imported(
    db: AsyncSession, review: Review, clock: Clock
) -> str:
    """
    What the Import or Imports just brought in, and the Rules that filed them.

    This is the whole point of the run: these rows were categorised by the
    Categorization Rules and by the user working down a list, which is where a
    Category ends up wrong and where the next Rule is hiding. Both are written
    out because one without the other says nothing — a Transaction in the wrong
    place is only obviously wrong next to the rule that put it there.
    """
    records = await _imports_of(db, review)
    currency = (await get_settings(db)).display_currency
    converter = await converter_for(db, clock)
    names = await _category_names(db)
    lines = [
        await transaction_line(converter, currency, names, one)
        for one in await _imported_transactions(db, records)
    ]
    # Said outright when there were more rows than the brief writes out, so a
    # run counting what it can see knows it is not counting the file.
    heading = "The Transactions it brought in, newest first" + (
        f", the first {IMPORTED_ROWS} of them"
        if len(lines) == IMPORTED_ROWS
        else ""
    )
    return "\n\n".join(
        [
            "An Import has just finished. What follows is what it brought in "
            "and the Categorization Rules that filed it, which is what this "
            "Review is about.",
            section(
                "What was just imported",
                [
                    f"- {one.filename}: {one.imported_count} Transactions "
                    f"recorded, {one.skipped_count} rows skipped"
                    for one in records
                ],
                "- The Import it was about is gone: it was undone.",
            ),
            section(heading, lines, "- It brought in no Transactions."),
            await _rules(db, names),
        ]
    )


async def _imports_of(db: AsyncSession, review: Review) -> list[Import]:
    """The Imports this Review is about, oldest first."""
    result = await db.execute(
        select(Import)
        .where(Import.review_id == review.id)
        .order_by(Import.created_at)
    )
    return list(result.scalars().all())


async def _imported_transactions(
    db: AsyncSession, records: list[Import]
) -> list[Transaction]:
    if not records:
        return []
    result = await db.execute(
        select(Transaction)
        .where(Transaction.import_id.in_(one.id for one in records))
        .order_by(Transaction.date.desc(), Transaction.created_at.desc())
        .limit(IMPORTED_ROWS)
    )
    return list(result.scalars().all())


async def _rules(db: AsyncSession, names: dict[uuid.UUID, str]) -> str:
    """
    The Categorization Rules as they stand, so a new one is not a repeat.

    A Rule files what is imported from then on and moves nothing already
    recorded, which is why the rows above and these belong in the same brief.
    """
    return section(
        "The Categorization Rules as they stand",
        [
            f'- "{one.pattern}" -> {named(names, one.category_id)}'
            for one in await list_rules(db)
        ],
        "- There are no Categorization Rules yet.",
    )


async def _what_went_over(
    db: AsyncSession, review: Review, clock: Clock
) -> str:
    """
    The Budget that was crossed, what it was spent on, and what it usually costs.

    One Category, in three ways of looking at it. The Transactions are what the
    user actually bought, which is the only place an answer to "why" can come
    from; the months before it are what says whether this is a bad month or the
    limit having fallen behind what things cost. The rest of the month is in
    the core brief above, as context for this rather than as the subject.
    """
    budget = await _budget_of(db, review)
    if budget is None:
        # The Budget was deleted between the Review being asked for and it
        # running. There is nothing to look into, and the core brief stands.
        return "The Budget this Review was about is gone: it was deleted."

    currency = (await get_settings(db)).display_currency
    converter = await converter_for(db, clock)
    names = await _category_names(db)
    category = named(names, budget.category_id)
    progress = await progress_of(db, budget, clock, converter)
    lines = [
        await transaction_line(converter, currency, names, one)
        for one in await _spent_on(db, budget)
    ]
    return "\n\n".join(
        [
            f"{category} went over its Budget for "
            f"{format_month(budget.month)}: limit "
            f"{figure(progress.amount)} {progress.currency.value}, spent "
            f"{figure(progress.spent)} ({figure(progress.percentage)}%). "
            f"That is what this Review is about.",
            section(
                f"What {category} was spent on in "
                f"{format_month(budget.month)}, newest first",
                lines,
                "- Nothing is recorded in it, which should not be possible.",
            ),
            await _month_by_month(db, budget, currency, converter),
        ]
    )


async def _budget_of(db: AsyncSession, review: Review) -> Budget | None:
    """The Budget whose crossing asked for this Review."""
    result = await db.execute(
        select(Budget).where(Budget.exceeded_review_id == review.id)
    )
    return result.scalars().first()


async def _spent_on(db: AsyncSession, budget: Budget) -> list[Transaction]:
    """That Category's Transactions in the Budget's month, newest first."""
    result = await db.execute(
        in_month(
            select(Transaction).where(
                Transaction.category_id == budget.category_id
            ),
            budget.month,
        )
        .order_by(Transaction.date.desc(), Transaction.created_at.desc())
        .limit(CATEGORY_ROWS)
    )
    return list(result.scalars().all())


async def _month_by_month(
    db: AsyncSession,
    budget: Budget,
    currency: Currency,
    converter: MoneyConverter,
) -> str:
    """
    What the Category has cost each month, as far back as the lookback allows.

    A total per month rather than the rows: the question this answers is
    whether 125% is this month being unusual or the limit having fallen behind,
    and that is a shape, not a list of purchases.
    """
    earliest = await earliest_month_for(db, budget.month)
    lines = [
        f"- {format_month(month)}: "
        f"{figure(await spent_in(db, budget.category_id, month, currency, converter))}"
        for month in months_from(earliest, budget.month)
    ]
    return section(
        f"What it has cost month by month, in {currency.value}", lines, ""
    )


# What each trigger adds to the core brief. A trigger absent from here is a
# Review about the month and nothing more.
Extra = Callable[[AsyncSession, Review, Clock], Awaitable[str]]

EXTRAS: dict[ReviewTrigger, Extra] = {
    ReviewTrigger.import_finished: _what_was_imported,
    ReviewTrigger.budget_exceeded: _what_went_over,
}
