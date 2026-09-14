import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import InstallmentPurchase, Transaction
from app.models.enums import ConfirmationStatus, Currency, TransactionType
from app.schemas.transaction import TransactionCreate, TransactionUpdate
from app.services.categories import get_category
from app.services.errors import Conflict, Invalid, NotFound

EXCHANGE_RATE_FIELDS = ("exchange_rate", "exchange_rate_type", "exchange_rate_status")


async def get_transaction(db: AsyncSession, transaction_id: uuid.UUID) -> Transaction:
    transaction = await db.get(Transaction, transaction_id)
    if transaction is None:
        raise NotFound(f"no Transaction with id {transaction_id}")
    return transaction


async def list_transactions(db: AsyncSession) -> list[Transaction]:
    result = await db.execute(
        select(Transaction).order_by(Transaction.date.desc(), Transaction.created_at)
    )
    return list(result.scalars().all())


async def create_transaction(
    db: AsyncSession, data: TransactionCreate
) -> Transaction:
    await _check_domain_rules(db, data, transaction_id=None)
    transaction = Transaction(**data.model_dump())
    db.add(transaction)
    await db.commit()
    await db.refresh(transaction)
    return transaction


async def update_transaction(
    db: AsyncSession, transaction_id: uuid.UUID, changes: TransactionUpdate
) -> Transaction:
    transaction = await get_transaction(db, transaction_id)
    changed = changes.model_dump(exclude_unset=True)

    _check_exchange_rate_is_not_rewritten(transaction, changed)
    after = TransactionCreate.model_validate(transaction).model_copy(update=changed)
    await _check_domain_rules(db, after, transaction_id=transaction_id)

    for field, value in changed.items():
        setattr(transaction, field, value)
    await db.commit()
    await db.refresh(transaction)
    return transaction


async def delete_transaction(db: AsyncSession, transaction_id: uuid.UUID) -> None:
    transaction = await get_transaction(db, transaction_id)
    await db.delete(transaction)
    await db.commit()


def _check_exchange_rate_is_not_rewritten(
    transaction: Transaction, changed: dict
) -> None:
    """A confirmed Exchange Rate never changes again (ADR-0001)."""
    if transaction.exchange_rate_status is not ConfirmationStatus.confirmed:
        return
    for field in (*EXCHANGE_RATE_FIELDS, "currency"):
        if field in changed and changed[field] != getattr(transaction, field):
            raise Conflict("a confirmed Exchange Rate cannot be changed")


async def _check_domain_rules(
    db: AsyncSession, after: TransactionCreate, transaction_id: uuid.UUID | None
) -> None:
    """Everything the Transaction must be true of once it is stored."""
    await _check_category_type_matches(db, after)
    _check_exchange_rate_matches_currency(after)
    _check_only_expenses_go_negative(after)
    await _check_refund(db, after, transaction_id)
    await _check_installment(db, after)


async def _check_category_type_matches(
    db: AsyncSession, after: TransactionCreate
) -> None:
    category = await get_category(db, after.category_id)
    if category.type is not after.type:
        raise Invalid(
            f"an {after.type.value} cannot use the {category.type.value} "
            f"Category '{category.name}'"
        )


def _check_exchange_rate_matches_currency(after: TransactionCreate) -> None:
    present = [
        field for field in EXCHANGE_RATE_FIELDS if getattr(after, field) is not None
    ]
    if after.currency is Currency.USD and len(present) < len(EXCHANGE_RATE_FIELDS):
        raise Invalid(
            "a USD Transaction needs an exchange_rate, exchange_rate_type and "
            "exchange_rate_status"
        )
    if after.currency is Currency.ARS and present:
        raise Invalid("an ARS Transaction carries no Exchange Rate")


def _check_only_expenses_go_negative(after: TransactionCreate) -> None:
    if after.amount < Decimal(0) and after.type is not TransactionType.expense:
        raise Invalid("only an Expense may have a negative amount, as a Refund")


async def _check_refund(
    db: AsyncSession, after: TransactionCreate, transaction_id: uuid.UUID | None
) -> None:
    if after.refund_of_id is None:
        return
    if after.refund_of_id == transaction_id:
        raise Invalid("a Refund cannot reverse itself")
    if after.amount >= Decimal(0):
        raise Invalid("a Refund is an Expense with a negative amount")

    original = await db.get(Transaction, after.refund_of_id)
    if original is None:
        raise NotFound(f"no Transaction with id {after.refund_of_id}")
    if original.type is not TransactionType.expense:
        raise Invalid("a Refund can only reverse an Expense")
    if original.category_id != after.category_id:
        raise Invalid("a Refund is in the same Category as the Expense it reverses")


async def _check_installment(db: AsyncSession, after: TransactionCreate) -> None:
    purchase_id = after.installment_purchase_id
    if (purchase_id is None) != (after.installment_number is None):
        raise Invalid(
            "a cuota needs both an installment_purchase_id and an installment_number"
        )
    if purchase_id is None:
        return
    if after.type is not TransactionType.expense:
        raise Invalid("only an Expense can be a cuota of an Installment Purchase")
    if await db.get(InstallmentPurchase, purchase_id) is None:
        raise NotFound(f"no Installment Purchase with id {purchase_id}")
