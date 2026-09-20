"""
Recurring Expenses: the templates for the Expenses expected every month.

A template produces nothing on its own — each month a Review turns it into a
Suggestion — so the only rule here is the one that keeps it capable of
producing a valid Expense: an expense Category. Deactivating is how a template
is paused, so nothing is ever deleted just to stop being reminded of it.
"""

import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import RecurringExpense, Transaction
from app.models.enums import TransactionType
from app.schemas.recurring_expense import (
    RecurringExpenseCreate,
    RecurringExpenseUpdate,
)
from app.services.categories import get_category
from app.services.errors import Invalid, NotFound


async def _require_expense_category(db: AsyncSession, category_id: uuid.UUID) -> None:
    """An unknown Category is a 404; an income one is a broken domain rule."""
    category = await get_category(db, category_id)
    if category.type is not TransactionType.expense:
        raise Invalid(
            f"'{category.name}' is an income Category, which no Recurring "
            "Expense can use"
        )


async def get_recurring_expense(
    db: AsyncSession, recurring_id: uuid.UUID
) -> RecurringExpense:
    template = await db.get(RecurringExpense, recurring_id)
    if template is None:
        raise NotFound(f"no Recurring Expense with id {recurring_id}")
    return template


async def list_recurring_expenses(db: AsyncSession) -> list[RecurringExpense]:
    """In the order the month pays them, so the list reads as a calendar."""
    result = await db.execute(
        select(RecurringExpense).order_by(
            RecurringExpense.expected_day, RecurringExpense.description
        )
    )
    return list(result.scalars().all())


async def last_amount_paid(
    db: AsyncSession, template: RecurringExpense
) -> Decimal | None:
    """
    What was last actually paid for this template, or None before anything was.

    Only a Transaction linked to the template counts — which is what accepting
    one of its Suggestions records — so this is exact rather than a guess from
    descriptions that happen to match. A payment in another currency is not an
    answer either: an amount only means something next to its own currency, and
    the template's is the one the next Suggestion will be in.
    """
    result = await db.execute(
        select(Transaction.amount)
        .where(Transaction.recurring_expense_id == template.id)
        .where(Transaction.currency == template.currency)
        .order_by(Transaction.date.desc(), Transaction.created_at.desc())
        .limit(1)
    )
    return result.scalars().first()


async def create_recurring_expense(
    db: AsyncSession, data: RecurringExpenseCreate
) -> RecurringExpense:
    await _require_expense_category(db, data.category_id)
    template = RecurringExpense(**data.model_dump())
    db.add(template)
    await db.commit()
    await db.refresh(template)
    return template


async def update_recurring_expense(
    db: AsyncSession, recurring_id: uuid.UUID, changes: RecurringExpenseUpdate
) -> RecurringExpense:
    template = await get_recurring_expense(db, recurring_id)
    changed = changes.model_dump(exclude_unset=True)
    if "category_id" in changed:
        await _require_expense_category(db, changed["category_id"])
    for field, value in changed.items():
        setattr(template, field, value)
    await db.commit()
    await db.refresh(template)
    return template


async def delete_recurring_expense(db: AsyncSession, recurring_id: uuid.UUID) -> None:
    await db.delete(await get_recurring_expense(db, recurring_id))
    await db.commit()
