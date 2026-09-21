"""
Budgets, and how the month is going against them.

A Budget is never a blocker: going over it is shown loudly and that is all
(shame over blocking). What this module produces is the honest number — spending
converted into the Budget's own currency, Refunds subtracted — and the state the
UI escalates on.
"""

import uuid
from datetime import date as Date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.clock import Clock
from app.models import Budget, BudgetMonth, Transaction
from app.models.enums import BudgetState, Currency, TransactionType
from app.months import days_in_month, month_of
from app.schemas.budget import BudgetCreate, BudgetProgress, BudgetUpdate
from app.services.categories import get_category
from app.services.errors import Conflict, Invalid, NotFound
from app.services.money import MoneyConverter, round_money
from app.services.transactions import in_month

WARNING_SHARE = Decimal("0.80")


async def get_budget(db: AsyncSession, budget_id: uuid.UUID) -> Budget:
    budget = await db.get(Budget, budget_id)
    if budget is None:
        raise NotFound(f"no Budget with id {budget_id}")
    return budget


async def budgets_in(db: AsyncSession, month: Date) -> list[Budget]:
    result = await db.execute(select(Budget).where(Budget.month == month))
    return list(result.scalars().all())


async def create_budget(db: AsyncSession, data: BudgetCreate) -> Budget:
    category = await _expense_category(db, data.category_id)
    name = category.name  # read before the rollback below expires the row
    month = month_of(data.month)
    # Setting a Budget by hand starts the month too, so rollover never arrives
    # afterwards and adds last month's on top. Marked before the Budget is
    # added, so the lookup cannot flush a clashing row and raise early.
    await _mark_started(db, month)
    budget = Budget(**{**data.model_dump(), "month": month})
    db.add(budget)
    try:
        await db.commit()
    except IntegrityError as error:
        await db.rollback()
        raise Conflict(f"'{name}' already has a Budget for that month") from error
    await db.refresh(budget)
    return budget


async def set_budget(
    db: AsyncSession, data: BudgetCreate, clock: Clock
) -> Budget:
    """
    The Category's Budget for a month, whether or not it already has one.

    What accepting a `set_budget` Suggestion does. It is `create_budget` and
    `update_budget` in one, choosing between them the way the user would: the
    month's copy is usually what it moves, and "that month already has one" is
    the case this exists for rather than the conflict it is over there. It is
    no shortcut past the rules, only past the extra request (ADR-0002).

    A month nobody has opened yet is started first, because starting it with
    this one Budget alone would leave every other Category's behind: the copy
    is the base, and this only moves one of the amounts on it. The commit is
    the caller's — here and in the copy — so the Suggestion, the month and the
    Budget it set all land together.
    """
    await _expense_category(db, data.category_id)
    month = month_of(data.month)
    await start_month(db, month, clock)
    # A month too far ahead to be started is still opened by the Budget being
    # set in it, exactly as setting one by hand opens it.
    await _mark_started(db, month)
    budget = await budget_for(db, data.category_id, month)
    if budget is None:
        budget = Budget(**{**data.model_dump(), "month": month})
        db.add(budget)
    else:
        budget.amount = data.amount
        budget.currency = data.currency
    # The id is the column default, which only exists once the row is flushed.
    await db.flush()
    return budget


async def check_budget(db: AsyncSession, data: BudgetCreate) -> None:
    """Everything setting it would check, without setting anything."""
    await _expense_category(db, data.category_id)


async def _expense_category(db: AsyncSession, category_id: uuid.UUID):
    """The Category a Budget is allowed to be for."""
    category = await get_category(db, category_id)
    if category.type is not TransactionType.expense:
        raise Invalid(
            f"'{category.name}' is an income Category, which has no Budget"
        )
    return category


async def budget_for(
    db: AsyncSession, category_id: uuid.UUID, month: Date
) -> Budget | None:
    """That Category's Budget for that month, if it has one."""
    result = await db.execute(
        select(Budget)
        .where(Budget.category_id == category_id)
        .where(Budget.month == month_of(month))
    )
    return result.scalars().first()


async def update_budget(
    db: AsyncSession, budget_id: uuid.UUID, changes: BudgetUpdate
) -> Budget:
    budget = await get_budget(db, budget_id)
    for field, value in changes.model_dump(exclude_unset=True).items():
        setattr(budget, field, value)
    await db.commit()
    await db.refresh(budget)
    return budget


async def delete_budget(db: AsyncSession, budget_id: uuid.UUID) -> None:
    await db.delete(await get_budget(db, budget_id))
    await db.commit()


async def list_progress(
    db: AsyncSession, month: Date, clock: Clock, converter: MoneyConverter
) -> list[BudgetProgress]:
    month = month_of(month)
    budgets = await roll_over_into(db, month, clock)
    return [await progress_of(db, budget, clock, converter) for budget in budgets]


async def roll_over_into(
    db: AsyncSession, month: Date, clock: Clock
) -> list[Budget]:
    """The month, started if it had not been, and the Budgets it now has."""
    await start_month(db, month, clock)
    await db.commit()
    return await budgets_in(db, month)


async def start_month(db: AsyncSession, month: Date, clock: Clock) -> None:
    """
    Opening a month with no Budgets starts it from the last month that had any.

    It happens exactly once per month. Afterwards the month's Budgets are the
    user's own: emptying it is a decision, not an invitation to copy last
    month's in again. A month that has not begun yet is left alone, so next
    month's Budgets are not set before the user has seen how this one ended.

    The commit is the caller's, so a month opened by accepting a Suggestion is
    written in the same breath as the Suggestion that opened it.
    """
    if await db.get(BudgetMonth, month) is not None:
        return
    if month > month_of(clock.today()):
        return

    previous = (
        await db.execute(
            select(Budget.month)
            .where(Budget.month < month)
            .order_by(Budget.month.desc())
            .limit(1)
        )
    ).scalars().first()

    for earlier in [] if previous is None else await budgets_in(db, previous):
        db.add(
            Budget(
                category_id=earlier.category_id,
                amount=earlier.amount,
                currency=earlier.currency,
                month=month,
            )
        )
    await _mark_started(db, month)


async def _mark_started(db: AsyncSession, month: Date) -> None:
    if await db.get(BudgetMonth, month) is None:
        db.add(BudgetMonth(month=month))


async def spent_in(
    db: AsyncSession,
    category_id: uuid.UUID,
    month: Date,
    currency: Currency,
    converter: MoneyConverter,
) -> Decimal:
    """
    What a Category cost in a month, in one currency.

    Refunds are Expenses with a negative amount, so they subtract themselves.
    It takes the Category and the month rather than a Budget because a month
    that has been spent is worth reading where no Budget was set for it too —
    which is what the month-end Review does with the month that just ended.
    """
    statement = in_month(
        select(Transaction)
        .where(Transaction.category_id == category_id)
        .where(Transaction.type == TransactionType.expense),
        month_of(month),
    )
    total = Decimal(0)
    for transaction in (await db.execute(statement)).scalars():
        total += await converter.convert(
            transaction.amount,
            transaction.currency,
            currency,
            transaction.date,
            transaction.exchange_rate,
        )
    return round_money(total)


def pace_of(budget: Budget, today: Date) -> Decimal | None:
    """
    The share of the Budget that should be spent by today.

    Only the running month has a Pace: a past month is judged on what it
    finally cost, and a month that has not started has nothing to be behind on.
    """
    if month_of(today) != budget.month:
        return None
    return round_money(budget.amount * today.day / days_in_month(budget.month))


def state_of(budget: Budget, spent: Decimal, pace: Decimal | None) -> BudgetState:
    if spent > budget.amount:
        return BudgetState.over
    if spent >= budget.amount * WARNING_SHARE:
        return BudgetState.warning
    if pace is not None and spent > pace:
        return BudgetState.ahead_of_pace
    return BudgetState.on_pace


async def progress_of(
    db: AsyncSession, budget: Budget, clock: Clock, converter: MoneyConverter
) -> BudgetProgress:
    spent = await spent_in(
        db, budget.category_id, budget.month, budget.currency, converter
    )
    pace = pace_of(budget, clock.today())
    return BudgetProgress(
        id=budget.id,
        category_id=budget.category_id,
        amount=budget.amount,
        currency=budget.currency,
        month=budget.month,
        spent=spent,
        percentage=round_money(spent / budget.amount * 100),
        pace=pace,
        state=state_of(budget, spent, pace),
    )
