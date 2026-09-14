"""
What the dashboard shows for one month.

Everything here is converted into the Display Currency through each
Transaction's own stored Exchange Rate, so ARS and USD are never added up as if
they were the same thing.
"""

from datetime import date as Date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clock import Clock
from app.models import Category, Transaction
from app.models.enums import Currency, TransactionType
from app.months import month_of
from app.schemas.budget import BudgetProgress
from app.schemas.summary import CategorySpending, MonthlySpending, MonthlySummary
from app.schemas.transaction import TransactionFilters, TransactionResponse
from app.services.budgets import list_progress
from app.services.money import MoneyConverter, round_money
from app.services.transactions import in_month, list_transactions

RECENT_TRANSACTIONS = 10


async def _converted_totals(
    db: AsyncSession, month: Date, currency: Currency, converter: MoneyConverter
) -> tuple[Decimal, Decimal, dict[str, CategorySpending]]:
    """The month's Income, its Expenses, and what each Category cost."""
    statement = in_month(
        select(Transaction, Category).join(
            Category, Category.id == Transaction.category_id
        ),
        month,
    )
    income = Decimal(0)
    expenses = Decimal(0)
    per_category: dict[str, CategorySpending] = {}

    for transaction, category in await db.execute(statement):
        amount = await converter.convert(
            transaction.amount,
            transaction.currency,
            currency,
            transaction.date,
            transaction.exchange_rate,
        )
        if transaction.type is TransactionType.income:
            income += amount
            continue
        expenses += amount
        # A Refund is a negative Expense, so it takes itself off its Category.
        slice_ = per_category.get(str(category.id))
        if slice_ is None:
            per_category[str(category.id)] = CategorySpending(
                category_id=category.id,
                name=category.name,
                color=category.color,
                total=amount,
            )
        else:
            slice_.total += amount

    return round_money(income), round_money(expenses), per_category


def _biggest_first(
    per_category: dict[str, CategorySpending],
) -> list[CategorySpending]:
    return sorted(
        (
            slice_.model_copy(update={"total": round_money(slice_.total)})
            for slice_ in per_category.values()
        ),
        key=lambda slice_: slice_.total,
        reverse=True,
    )


async def spending_by_category(
    db: AsyncSession, month: Date, currency: Currency, converter: MoneyConverter
) -> MonthlySpending:
    month = month_of(month)
    _, _, per_category = await _converted_totals(db, month, currency, converter)
    return MonthlySpending(
        month=month, currency=currency, categories=_biggest_first(per_category)
    )


async def summarise_month(
    db: AsyncSession,
    month: Date,
    currency: Currency,
    clock: Clock,
    converter: MoneyConverter,
) -> MonthlySummary:
    month = month_of(month)
    income, expenses, per_category = await _converted_totals(
        db, month, currency, converter
    )
    budgets: list[BudgetProgress] = await list_progress(db, month, clock, converter)
    recent = await list_transactions(
        db, TransactionFilters(month=month, limit=RECENT_TRANSACTIONS)
    )
    return MonthlySummary(
        month=month,
        currency=currency,
        total_income=income,
        total_expenses=expenses,
        monthly_result=round_money(income - expenses),
        by_category=_biggest_first(per_category),
        budgets=budgets,
        recent=[TransactionResponse.model_validate(t) for t in recent],
    )
