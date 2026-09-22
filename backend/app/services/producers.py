"""
The producers: the arithmetic a Review runs to decide what to propose.

Each one is a plain function of a session, a Review and what lies outside the
database, so it can be read and tested without a worker anywhere near it. The
month to propose for is the Review's, not today's: a run the worker picked up
after midnight still does the month it was created for. The ARQ job is only a
wrapper that opens a session and calls these.
"""

from datetime import date as Date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.inflation import IndexProvider
from app.models import AdjustmentRule, InflationIndex, RecurringExpense, Review
from app.models.enums import AdjustmentKind, Currency, SuggestionKind
from app.months import add_months, days_in_month
from app.services.adjustments import (
    HUNDRED,
    Adjustment,
    adjust,
    index_months,
)
from app.services.budgets import budget_for, budgets_in, spent_in
from app.services.money import converter_for, round_money, round_to_thousand
from app.services.outside import Outside
from app.services.recurring_expenses import (
    last_amount_paid,
    list_recurring_expenses,
)
from app.services.suggestions import propose

MONTH_NAMES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]


def _expected_date(template: RecurringExpense, month: Date) -> Date:
    """The template's day in that month, clamped to a month too short for it."""
    return month.replace(day=min(template.expected_day, days_in_month(month)))


def _month_name(month: Date) -> str:
    return f"{MONTH_NAMES[month.month - 1]} de {month.year}"


def _amount(amount: Decimal) -> str:
    """An amount as it is written here: 475946.65 reads 475.946,65."""
    return f"{amount:,.2f}".translate(str.maketrans(",.", ".,"))


def _percentage(value: Decimal) -> str:
    """A percentage without the zeros it does not need: 10.00 reads 10."""
    written = f"{value:f}".rstrip("0").rstrip(".")
    return written.replace(".", ",")


def _adjustment_sentence(
    rule: AdjustmentRule, adjustment: Adjustment, base: Decimal
) -> str:
    """Why the amount moved this month, or why it did not move yet."""
    if adjustment.is_pending:
        missing = ", ".join(_month_name(one) for one in adjustment.pending)
        return (
            f"Este mes toca el ajuste, pero está pendiente: todavía no se "
            f"publicó el {rule.index_name} de {missing}, así que propongo el "
            f"mismo monto."
        )
    if rule.kind is AdjustmentKind.percentage:
        return (
            f"Este mes toca el ajuste: {_percentage(rule.percentage)}% sobre "
            f"{_amount(base)} da {_amount(adjustment.amount)}."
        )
    accumulated = (adjustment.factor - 1) * 100
    return (
        f"Este mes toca el ajuste: el {rule.index_name} de "
        f"{_month_name(adjustment.months[0])} a "
        f"{_month_name(adjustment.months[-1])} acumula "
        f"{_percentage(round_money(accumulated))}%, que sobre {_amount(base)} "
        f"da {_amount(adjustment.amount)}."
    )


def _rationale(
    template: RecurringExpense,
    on: Date,
    paid: Decimal | None,
    base: Decimal,
    adjustment: Adjustment | None,
) -> str:
    """
    Why this amount, on this day.

    It says where the amount came from: the last payment once there is one, and
    the template's reference amount until then, and what the Adjustment Rule
    did to it in the months it falls due.
    """
    source = (
        "por el último monto que pagaste"
        if paid is not None
        else "por el monto de referencia del gasto recurrente"
    )
    said = (
        f"{template.description} se paga todos los meses. "
        f"Lo propongo para el {on.day} de {MONTH_NAMES[on.month - 1]} "
        f"{source}."
    )
    if adjustment is None:
        return said
    return f"{said} {_adjustment_sentence(template.adjustment, adjustment, base)}"


async def _index_variations(
    indexes: IndexProvider, templates: list[RecurringExpense], month: Date
) -> dict[str, dict[Date, Decimal]]:
    """
    Everything the month's index rules need to know, read before proposing.

    Reading the index can bring the published series in and store it, which is
    a commit; doing it up front keeps that from landing in the middle of a run
    whose Suggestions a later failure should have rolled back.
    """
    wanted: dict[str, list[Date]] = {}
    for template in templates:
        rule = template.adjustment
        if rule is None:
            continue
        for needed in index_months(rule, month):
            wanted.setdefault(rule.index_name, []).append(needed)
    return {
        name: {
            value.month: value.value
            for value in await indexes.values_in(min(months), max(months), name)
        }
        for name, months in wanted.items()
    }


async def propose_recurring_expenses(
    db: AsyncSession, review: Review, outside: Outside
) -> None:
    """One `add_transaction` per active Recurring Expense, for the month."""
    month = review.month
    templates = [one for one in await list_recurring_expenses(db) if one.is_active]
    variations = await _index_variations(outside.indexes, templates, month)
    for template in templates:
        on = _expected_date(template, month)
        paid = await last_amount_paid(db, template)
        base = paid if paid is not None else template.reference_amount
        rule = template.adjustment
        known = variations.get(rule.index_name, {}) if rule is not None else {}
        adjustment = adjust(rule, base, month, known)
        await propose(
            db,
            review.id,
            kind=SuggestionKind.add_transaction,
            month=month,
            payload={
                "description": template.description,
                "category_id": str(template.category_id),
                "currency": template.currency.value,
                "amount": str(base if adjustment is None else adjustment.amount),
                "date": on.isoformat(),
                "is_fixed": template.is_fixed,
                "recurring_expense_id": str(template.id),
            },
            rationale=_rationale(template, on, paid, base, adjustment),
        )


def _budget_rationale(
    previous: Date,
    spent: Decimal,
    budget: Decimal,
    index: InflationIndex,
    proposed: Decimal,
) -> str:
    """Last month against its limit, and the index that moves it."""
    return (
        f"En {_month_name(previous)} gastaste {_amount(spent)} de un "
        f"presupuesto de {_amount(budget)}. El {index.name} de "
        f"{_month_name(index.month)} fue "
        f"{_percentage(index.value)}%, así que propongo {_amount(proposed)}."
    )


async def propose_budget_adjustments(
    db: AsyncSession, review: Review, outside: Outside
) -> None:
    """
    One `set_budget` per ARS Budget of last month, moved by the latest IPC.

    This is what "Revisar ahora" proposes, and what the month-end Review
    falls back on when the agent could not: the same shape of change, worked
    out from the one figure arithmetic can read. A blunter answer than the
    agent's — every Budget moved by the same percentage, whatever the
    Category has actually been costing — and the right one to be left
    holding, because the alternative is a month whose limits nobody moved.

    Last month's is the right base because the new month starts as a copy of
    it: what this proposes is a move of that copy, whether or not it has been
    made yet. So nothing here writes a Budget — accepting does.

    Dollars are left alone — the Argentine IPC says nothing about them — and so
    is an amount the adjustment does not actually move.
    """
    month = review.month
    previous = add_months(month, -1)
    budgets = [
        one
        for one in await budgets_in(db, previous)
        if one.currency is Currency.ARS
    ]
    if not budgets:
        return
    index = await outside.indexes.latest_published(month)
    if index is None:
        return

    converter = await converter_for(db, outside.clock)
    factor = 1 + index.value / HUNDRED
    for budget in budgets:
        proposed = round_to_thousand(budget.amount * factor)
        # What the month already has, which is last month's amount until the
        # copy is made: a proposal that changes nothing is not a proposal.
        current = await budget_for(db, budget.category_id, month)
        if proposed == (budget.amount if current is None else current.amount):
            continue
        spent = await spent_in(
            db, budget.category_id, previous, budget.currency, converter
        )
        await propose(
            db,
            review.id,
            kind=SuggestionKind.set_budget,
            month=month,
            payload={
                "category_id": str(budget.category_id),
                "month": month.isoformat(),
                "amount": str(proposed),
                "currency": budget.currency.value,
            },
            rationale=_budget_rationale(
                previous, spent, budget.amount, index, proposed
            ),
        )
