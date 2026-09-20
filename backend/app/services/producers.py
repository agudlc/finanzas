"""
The producers: the arithmetic a Review runs to decide what to propose.

Each one is a plain function of a session, a Review and a clock, so it can be
read and tested without a worker anywhere near it. The month to propose for is
the Review's, not today's: a run the worker picked up after midnight still does
the month it was created for. The ARQ job is only a wrapper that opens a
session and calls these.
"""

import uuid
from datetime import date as Date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.clock import Clock
from app.models import RecurringExpense, Review
from app.models.enums import SuggestionKind
from app.months import days_in_month, format_month
from app.services.recurring_expenses import (
    last_amount_paid,
    list_recurring_expenses,
)
from app.services.suggestions import propose

MONTH_NAMES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]


def add_transaction_key(recurring_id: uuid.UUID, month: Date) -> str:
    """
    What an `add_transaction` proposal is about: this template, this month.

    One key per template and month is what makes a rejection mean "not this
    month": the next month asks a different question.
    """
    return f"{recurring_id}:{format_month(month)}"


def _expected_date(template: RecurringExpense, month: Date) -> Date:
    """The template's day in that month, clamped to a month too short for it."""
    return month.replace(day=min(template.expected_day, days_in_month(month)))


def _rationale(template: RecurringExpense, on: Date, paid: Decimal | None) -> str:
    """
    Why this amount, on this day.

    It says where the amount came from: the last payment once there is one, and
    the template's reference amount until then.
    """
    source = (
        "por el último monto que pagaste"
        if paid is not None
        else "por el monto de referencia del gasto recurrente"
    )
    return (
        f"{template.description} se paga todos los meses. "
        f"Lo propongo para el {on.day} de {MONTH_NAMES[on.month - 1]} "
        f"{source}."
    )


async def propose_recurring_expenses(
    db: AsyncSession, review: Review, clock: Clock
) -> None:
    """One `add_transaction` per active Recurring Expense, for the month."""
    month = review.month
    for template in await list_recurring_expenses(db):
        if not template.is_active:
            continue
        on = _expected_date(template, month)
        paid = await last_amount_paid(db, template)
        await propose(
            db,
            review.id,
            kind=SuggestionKind.add_transaction,
            month=month,
            dedupe_key=add_transaction_key(template.id, month),
            payload={
                "description": template.description,
                "category_id": str(template.category_id),
                "currency": template.currency.value,
                "amount": str(paid if paid is not None else template.reference_amount),
                "date": on.isoformat(),
                "is_fixed": template.is_fixed,
                "recurring_expense_id": str(template.id),
            },
            rationale=_rationale(template, on, paid),
        )
