"""
The read tools: how the agent digs past the brief, and how far it may go.

The brief is one month written out in full, which is enough for most of what a
Review has to say; these are for the rest. Every one of them is a read — there
is no write path at all (ADR-0002) — and every one of them answers in the same
words the brief is written in, so the agent reads one language and not two.

Two things are true of all of them. Amounts come back in the Display Currency,
converted through each Transaction's own stored Exchange Rate, because a total
that mixed pesos and dollars would be a number the user has never seen. And
nothing older than the lookback is fetched: a tool asked for a month behind the
floor answers with the limit instead of the rows, which is a thing the model
can correct within the run rather than a run that falls over.
"""

import uuid
from dataclasses import dataclass, field
from datetime import date as Date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clock import Clock
from app.models import Category, Review, Transaction
from app.models.enums import Currency, SuggestionKind
from app.months import add_months, format_month, parse_month
from app.services import insights as insights_service
from app.services.brief import budget_lines, figure, named, proposal, section
from app.services.categories import list_categories
from app.services.categorization import list_rules
from app.services.lookback import earliest_month
from app.services.money import MoneyConverter, converter_for
from app.services.recurring_expenses import (
    last_amount_paid,
    list_recurring_expenses,
)
from app.services.settings import get_settings
from app.services.suggestions import rejected_between
from app.services.summary import converted_totals

# How many Transactions one call may hand back. A month of someone's spending
# is a few dozen rows, so this is generous for a question worth asking and far
# short of a run that reads the whole database into its own context.
DEFAULT_ROWS = 50
MAX_ROWS = 200


class OutOfReach(Exception):
    """The tool was asked for something the lookback does not cover."""


@dataclass(frozen=True)
class Reading:
    """
    Everything a read tool needs, worked out once per run.

    The Display Currency, the converter and the Category names are the same
    ones the brief was built from, so a total read through a tool and the same
    total in the brief can never disagree.
    """

    db: AsyncSession
    clock: Clock
    # The month under review: what "this month" means to every tool here.
    month: Date
    currency: Currency
    converter: MoneyConverter
    categories: list[Category]
    # The oldest month the user lets this run read, as its first day.
    earliest: Date
    names: dict[uuid.UUID, str] = field(default_factory=dict)

    @classmethod
    async def of(cls, db: AsyncSession, review: Review, clock: Clock) -> "Reading":
        settings = await get_settings(db)
        categories = await list_categories(db)
        return cls(
            db=db,
            clock=clock,
            month=review.month,
            currency=settings.display_currency,
            converter=await converter_for(db, clock),
            categories=categories,
            earliest=earliest_month(review.month, settings.agent_lookback),
            names={one.id: one.name for one in categories},
        )


MONTH = {"type": "string", "description": 'A month, written "YYYY-MM".'}

TOOLS = [
    {
        "name": "list_transactions",
        "description": (
            "The Transactions of a range of months, newest first, in the "
            "Display Currency. Use it when a Category total raises a question "
            "the total cannot answer: what was actually bought."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "from_month": MONTH,
                "to_month": MONTH,
                "category": {
                    "type": "string",
                    "description": (
                        "The name of a Category, to read only its "
                        "Transactions. Omit for every Category."
                    ),
                },
                "limit": {
                    "type": "integer",
                    "description": (
                        f"How many at most, {MAX_ROWS} at the very most. "
                        f"Defaults to {DEFAULT_ROWS}."
                    ),
                },
            },
            "required": ["from_month", "to_month"],
        },
    },
    {
        "name": "category_totals",
        "description": (
            "One month's Income, Expenses and Monthly Result, and what each "
            "expense Category cost, in the Display Currency. Use it to hold "
            "the month under review against an earlier one."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"month": MONTH},
            "required": ["month"],
        },
    },
    {
        "name": "budgets",
        "description": (
            "One month's Budgets, each against what it cost and against its "
            "Pace."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"month": MONTH},
            "required": ["month"],
        },
    },
    {
        "name": "recurring_expenses",
        "description": (
            "The Recurring Expense templates: what is expected every month, "
            "on what day, for how much, and how its amount is adjusted."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "categories",
        "description": (
            "Every Category, with the type of Transaction it classifies."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "categorization_rules",
        "description": (
            "The Categorization Rules: which description sends an imported "
            "Transaction to which Category."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "past_rejections",
        "description": (
            "What the user turned down, as far back as you may read, and of "
            "one kind if you ask for one. A rejection means \"not this "
            "month\", so it is history to weigh rather than a rule."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "kind": {
                    "type": "string",
                    "enum": [one.value for one in SuggestionKind],
                    "description": "Only rejections of this kind. Omit for all.",
                }
            },
        },
    },
    {
        "name": "recent_insights",
        "description": (
            "The observations already recorded, as far back as you may read. "
            "Use it to tell whether something has been said before."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
]

async def read(reading: Reading, name: str, arguments: dict) -> str:
    """
    Run one read tool and write its answer out, or say why it was not run.

    Everything that can go wrong with a call — a tool that does not exist, a
    month that is not a month, a Category that does not exist, a month behind
    the lookback — comes back as the answer to the call, because the model
    asking for the wrong thing is something to correct inside the run.
    """
    if name not in _READERS:
        return f"There is no tool called {name}."
    try:
        return await _READERS[name](reading, arguments)
    except (OutOfReach, ValueError) as error:
        return str(error)


def _month(reading: Reading, written: str) -> Date:
    """A month the tool was given, checked against the lookback."""
    month = parse_month(str(written))
    if month < reading.earliest:
        raise OutOfReach(
            f"{format_month(month)} is further back than you may read. The "
            f"user lets you read from {format_month(reading.earliest)} "
            f"onwards; ask again from that month on."
        )
    return month


def _categories_named(reading: Reading, name: str) -> list[Category]:
    """
    Every Category of that name, which can be two.

    An expense and an income Category may share a name — "Regalos" given and
    "Regalos" received — and the model asked for the name, so both are what it
    asked for. Picking one of them would be picking the wrong one half the time.
    """
    wanted = name.strip().casefold()
    found = [one for one in reading.categories if one.name.casefold() == wanted]
    if not found:
        raise ValueError(f"There is no Category called '{name}'.")
    return found


def _rows(arguments: dict) -> int:
    """
    How many rows to hand back, or a refusal to hand back that many.

    A limit out of range is answered rather than bent, for the reason the
    lookback is: a model told 200 when it asked for 500 has no way of knowing
    the list it is reading is not the whole of what it asked for.
    """
    asked = arguments.get("limit")
    if asked is None:
        return DEFAULT_ROWS
    if not 1 <= int(asked) <= MAX_ROWS:
        raise ValueError(f"A limit has to be between 1 and {MAX_ROWS}.")
    return int(asked)


async def _list_transactions(reading: Reading, arguments: dict) -> str:
    first = _month(reading, arguments["from_month"])
    last = _month(reading, arguments["to_month"])
    if last < first:
        raise ValueError(
            f"{format_month(last)} is before {format_month(first)}, so that "
            f"range holds no months."
        )
    statement = (
        select(Transaction)
        .where(Transaction.date >= first)
        .where(Transaction.date < add_months(last, 1))
        .order_by(Transaction.date.desc(), Transaction.created_at.desc())
        .limit(_rows(arguments))
    )
    named_category = arguments.get("category")
    if named_category:
        statement = statement.where(
            Transaction.category_id.in_(
                one.id for one in _categories_named(reading, named_category)
            )
        )

    lines = [
        await _transaction_line(reading, one)
        for one in (await reading.db.execute(statement)).scalars().all()
    ]
    return section(
        f"Transactions from {format_month(first)} to {format_month(last)}"
        + (f", in {named_category}" if named_category else ""),
        lines,
        "- Nothing was recorded in those months.",
    )


async def _transaction_line(reading: Reading, one: Transaction) -> str:
    """
    One Transaction as the agent reads it: converted, and said so when it was.

    A USD Expense keeps its Original Amount next to the converted one, because
    "30 dólares" is what the user remembers spending and the pesos are what
    the month adds up to.
    """
    amount = await reading.converter.convert(
        one.amount, one.currency, reading.currency, one.date, one.exchange_rate
    )
    original = (
        ""
        if one.currency is reading.currency
        else f" (originally {figure(one.amount)} {one.currency.value})"
    )
    return (
        f"- {one.date.isoformat()}, {named(reading.names, one.category_id)}, "
        f'"{one.description or "no description"}", {one.type.value}: '
        f"{figure(amount)}{original}"
    )


async def _category_totals(reading: Reading, arguments: dict) -> str:
    month = _month(reading, arguments["month"])
    income, expenses, by_category = await converted_totals(
        reading.db, month, reading.currency, reading.converter
    )
    # A month with nothing in it says so in its zeros, so there is no empty
    # case here: the three totals are always worth writing.
    return section(
        f"{format_month(month)}, in {reading.currency.value}",
        [
            f"- Income: {figure(income)}",
            f"- Expenses: {figure(expenses)}",
            f"- Monthly Result: {figure(income - expenses)}",
            *(f"- {one.name}: {figure(one.total)}" for one in by_category),
        ],
        "",
    )


async def _budgets(reading: Reading, arguments: dict) -> str:
    month = _month(reading, arguments["month"])
    return section(
        f"Budgets in {format_month(month)}",
        await budget_lines(
            reading.db, month, reading.clock, reading.converter, reading.names
        ),
        "- That month has no Budgets set.",
    )


async def _recurring_expenses(reading: Reading, arguments: dict) -> str:
    lines = []
    for template in await list_recurring_expenses(reading.db):
        paid = await last_amount_paid(reading.db, template)
        lines.append(
            f"- {template.description} in "
            f"{named(reading.names, template.category_id)}: "
            f"{figure(template.reference_amount)} "
            f"{template.currency.value} on day {template.expected_day}, "
            f"{_last_paid(paid, template.currency)}, "
            f"{_adjustment(template.adjustment)}"
            + ("" if template.is_active else ", paused")
        )
    return section(
        "Recurring Expenses", lines, "- There are no Recurring Expenses."
    )


def _last_paid(paid: Decimal | None, currency: Currency) -> str:
    """
    What was last actually paid, in the template's own currency.

    Not the Display Currency: a template's amounts are the ones the next
    Suggestion will be in, and converting them would answer a question about
    the past with a rate from today.
    """
    return (
        "never paid through a Suggestion yet"
        if paid is None
        else f"last paid {figure(paid)} {currency.value}"
    )


def _adjustment(rule) -> str:
    """The Adjustment Rule in a clause, in the words the templates use."""
    if rule is None:
        return "no Adjustment Rule"
    every = (
        f"every {rule.period_months} months from {format_month(rule.start_month)}"
    )
    if rule.index_name is not None:
        return f"adjusted by the {rule.index_name} {every}"
    return f"adjusted by {figure(rule.percentage)}% {every}"


async def _categories(reading: Reading, arguments: dict) -> str:
    return section(
        "Categories",
        [f"- {one.name}: {one.type.value}" for one in reading.categories],
        "- There are no Categories.",
    )


async def _categorization_rules(reading: Reading, arguments: dict) -> str:
    return section(
        "Categorization Rules",
        [
            f'- "{one.pattern}" -> {named(reading.names, one.category_id)}'
            for one in await list_rules(reading.db)
        ],
        "- There are no Categorization Rules.",
    )


async def _past_rejections(reading: Reading, arguments: dict) -> str:
    asked = arguments.get("kind")
    kind = SuggestionKind(asked) if asked else None
    lines = []
    for one in await rejected_between(
        reading.db, reading.earliest, reading.month, kind
    ):
        reason = (
            "no reason given"
            if one.rejection_reason is None
            else f'"{one.rejection_reason}"'
        )
        lines.append(
            f"- in {format_month(one.month)} they said no to "
            f"{await proposal(reading.db, one, reading.names)}: {reason}"
        )
    return section(
        "Proposals the user rejected", lines, "- They have rejected nothing."
    )


async def _recent_insights(reading: Reading, arguments: dict) -> str:
    lines = [
        f"- {format_month(one.month)} — {one.topic}: {one.body}"
        for one in await insights_service.between(
            reading.db, reading.earliest, reading.month
        )
    ]
    return section(
        "Observations already recorded", lines, "- Nothing has been observed yet."
    )


# One reader per tool, under the name the model is offered. A map rather than
# a cascade: adding a tool is adding an entry here and its schema above, and a
# name in one without the other answers "there is no tool called that".
_READERS = {
    "list_transactions": _list_transactions,
    "category_totals": _category_totals,
    "budgets": _budgets,
    "recurring_expenses": _recurring_expenses,
    "categories": _categories,
    "categorization_rules": _categorization_rules,
    "past_rejections": _past_rejections,
    "recent_insights": _recent_insights,
}
