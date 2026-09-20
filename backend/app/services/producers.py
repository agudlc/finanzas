"""
The producers: the arithmetic a Review runs to decide what to propose.

Each one is a plain function of a session, a Review id and a clock, so it can
be read and tested without a worker anywhere near it. The ARQ job is only a
wrapper that opens a session and calls these.
"""

import uuid
from datetime import date as Date

from sqlalchemy.ext.asyncio import AsyncSession

from app.clock import Clock
from app.models import RecurringExpense
from app.models.enums import SuggestionKind
from app.months import days_in_month, format_month, month_of
from app.services.recurring_expenses import list_recurring_expenses
from app.services.suggestions import propose

MONTH_NAMES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]


def _expected_date(template: RecurringExpense, month: Date) -> Date:
    """The template's day in that month, clamped to a month too short for it."""
    return month.replace(day=min(template.expected_day, days_in_month(month)))


def _rationale(template: RecurringExpense, on: Date) -> str:
    """
    Why this amount, on this day.

    It says where the amount came from rather than what is missing, so it stays
    true when the amount starts coming from the last payment instead.
    """
    return (
        f"{template.description} se paga todos los meses. "
        f"Lo propongo para el {on.day} de {MONTH_NAMES[on.month - 1]} "
        "por el monto de referencia del gasto recurrente."
    )


async def propose_recurring_expenses(
    db: AsyncSession, review_id: uuid.UUID, clock: Clock
) -> None:
    """One `add_transaction` per active Recurring Expense, for this month."""
    month = month_of(clock.today())
    for template in await list_recurring_expenses(db):
        if not template.is_active:
            continue
        on = _expected_date(template, month)
        await propose(
            db,
            review_id,
            kind=SuggestionKind.add_transaction,
            month=month,
            dedupe_key=f"{template.id}:{format_month(month)}",
            payload={
                "description": template.description,
                "category_id": str(template.category_id),
                "currency": template.currency.value,
                "amount": str(template.reference_amount),
                "date": on.isoformat(),
                "is_fixed": template.is_fixed,
                "recurring_expense_id": str(template.id),
            },
            rationale=_rationale(template, on),
        )
