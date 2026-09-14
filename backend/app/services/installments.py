"""
An Installment Purchase and the cuotas it generates.

The purchase is recorded once and produces one estimated Expense per cuota, so
every month carries its share and the remaining cuotas stand as future
commitments. Editing the purchase is not supported: delete it and record it
again.
"""

import uuid
from decimal import ROUND_DOWN, Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import InstallmentPurchase, Transaction
from app.models.enums import ConfirmationStatus, Currency, TransactionType
from app.months import add_months
from app.schemas.installment import InstallmentPurchaseCreate
from app.schemas.transaction import TransactionCreate
from app.services.errors import NotFound
from app.services.money import CENTS, RateEstimator
from app.services.transactions import build_transaction


def split_evenly(total: Decimal, installments: int) -> list[Decimal]:
    """
    The total divided evenly, with the rounding cents on the first cuota.

    Dividing by hand leaves cents unaccounted for; putting them on the first
    cuota keeps the cuotas adding up to exactly what was spent.
    """
    each = (total / installments).quantize(CENTS, rounding=ROUND_DOWN)
    amounts = [each] * installments
    amounts[0] += total.quantize(CENTS) - each * installments
    return amounts


async def get_purchase(
    db: AsyncSession, purchase_id: uuid.UUID
) -> InstallmentPurchase:
    purchase = await db.get(InstallmentPurchase, purchase_id)
    if purchase is None:
        raise NotFound(f"no Installment Purchase with id {purchase_id}")
    return purchase


async def list_purchases(db: AsyncSession) -> list[InstallmentPurchase]:
    result = await db.execute(
        select(InstallmentPurchase).order_by(InstallmentPurchase.purchase_date.desc())
    )
    return list(result.scalars().all())


async def cuotas_of(
    db: AsyncSession, purchase_id: uuid.UUID
) -> list[Transaction]:
    result = await db.execute(
        select(Transaction)
        .where(Transaction.installment_purchase_id == purchase_id)
        .order_by(Transaction.installment_number)
    )
    return list(result.scalars().all())


async def create_purchase(
    db: AsyncSession, data: InstallmentPurchaseCreate, estimator: RateEstimator
) -> InstallmentPurchase:
    purchase = InstallmentPurchase(
        **data.model_dump(exclude={"exchange_rate_type"})
    )
    db.add(purchase)
    await db.flush()

    in_usd = data.currency is Currency.USD
    for number, amount in enumerate(
        split_evenly(data.total_amount, data.installments), start=1
    ):
        await build_transaction(
            db,
            TransactionCreate(
                amount=amount,
                currency=data.currency,
                type=TransactionType.expense,
                category_id=data.category_id,
                # The first cuota falls in the purchase month and one in each
                # month after, on the same day or the month's last day.
                date=add_months(data.purchase_date, number - 1),
                description=data.description,
                # Both the amount and, in USD, the rate are estimates until the
                # statement arrives.
                amount_status=ConfirmationStatus.estimated,
                exchange_rate_type=data.exchange_rate_type if in_usd else None,
                installment_purchase_id=purchase.id,
                installment_number=number,
            ),
            estimator,
        )

    await db.commit()
    await db.refresh(purchase)
    return purchase


async def delete_purchase(db: AsyncSession, purchase_id: uuid.UUID) -> None:
    """Undoing a mistake in one step: the purchase takes its cuotas with it."""
    purchase = await get_purchase(db, purchase_id)
    for cuota in await cuotas_of(db, purchase_id):
        await db.delete(cuota)
    # The cuotas have to be gone before the row they point at.
    await db.flush()
    await db.delete(purchase)
    await db.commit()
