import uuid
from datetime import date as Date
from decimal import Decimal

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import InstallmentPurchase, RecurringExpense, Transaction
from app.models.enums import ConfirmationStatus, Currency, TransactionType
from app.months import add_months
from app.schemas.transaction import (
    RefundCreate,
    TransactionCreate,
    TransactionFilters,
    TransactionUpdate,
)
from app.services.categories import get_category
from app.services.errors import Conflict, Invalid, NotFound
from app.services.money import RateEstimator

EXCHANGE_RATE_FIELDS = ("exchange_rate", "exchange_rate_type", "exchange_rate_status")


async def get_transaction(db: AsyncSession, transaction_id: uuid.UUID) -> Transaction:
    transaction = await db.get(Transaction, transaction_id)
    if transaction is None:
        raise NotFound(f"no Transaction with id {transaction_id}")
    return transaction


def newest_first(statement: Select) -> Select:
    return statement.order_by(
        Transaction.date.desc(), Transaction.created_at.desc()
    )


def in_month(statement: Select, month: Date) -> Select:
    return statement.where(Transaction.date >= month).where(
        Transaction.date < add_months(month, 1)
    )


async def list_transactions(
    db: AsyncSession, filters: TransactionFilters | None = None
) -> list[Transaction]:
    filters = filters or TransactionFilters()
    statement = newest_first(select(Transaction))
    if filters.month is not None:
        statement = in_month(statement, filters.month)
    if filters.date is not None:
        statement = statement.where(Transaction.date == filters.date)
    if filters.type is not None:
        statement = statement.where(Transaction.type == filters.type)
    if filters.category_id is not None:
        statement = statement.where(Transaction.category_id == filters.category_id)
    if filters.currency is not None:
        statement = statement.where(Transaction.currency == filters.currency)
    if filters.limit is not None:
        statement = statement.limit(filters.limit)
    result = await db.execute(statement)
    return list(result.scalars().all())


async def build_transaction(
    db: AsyncSession, data: TransactionCreate, estimator: RateEstimator
) -> Transaction:
    """
    A checked, estimated Transaction, added to the session but not committed.

    Callers that write several Transactions at once — the cuotas of an
    Installment Purchase, the rows of an Import — build them all and commit
    once, so a failure halfway through leaves nothing behind.
    """
    data = await estimator.fill_in(data)
    await _check_domain_rules(db, data, transaction_id=None)
    transaction = Transaction(**data.model_dump())
    db.add(transaction)
    return transaction


async def create_transaction(
    db: AsyncSession, data: TransactionCreate, estimator: RateEstimator
) -> Transaction:
    transaction = await build_transaction(db, data, estimator)
    await db.commit()
    await db.refresh(transaction)
    return transaction


async def create_refund(
    db: AsyncSession,
    original_id: uuid.UUID,
    data: RefundCreate,
    estimator: RateEstimator,
) -> Transaction:
    """
    A Refund recorded against the Expense it reverses.

    It takes that Expense's Category and currency, so the Category's spending
    reflects what was really spent.
    """
    original = await get_transaction(db, original_id)
    if original.type is not TransactionType.expense:
        raise Invalid("a Refund can only reverse an Expense")
    if original.amount < Decimal(0):
        raise Invalid("a Refund cannot reverse another Refund")

    refund = TransactionCreate(
        amount=-abs(data.amount),
        currency=original.currency,
        type=TransactionType.expense,
        category_id=original.category_id,
        date=data.date,
        description=data.description or original.description,
        notes=data.notes,
        refund_of_id=original.id,
    )
    return await create_transaction(db, refund, estimator)


async def _checked(
    db: AsyncSession, transaction_id: uuid.UUID, changes: TransactionUpdate
) -> tuple[Transaction, dict]:
    """The Transaction and the fields to set on it, held to every rule first."""
    transaction = await get_transaction(db, transaction_id)
    changed = changes.model_dump(exclude_unset=True)

    _check_exchange_rate_is_not_rewritten(transaction, changed)
    _confirm_a_cuota_whose_amount_was_edited(transaction, changed)
    after = TransactionCreate.model_validate(transaction).model_copy(update=changed)
    await _check_domain_rules(db, after, transaction_id=transaction_id)
    return transaction, changed


async def check_change(
    db: AsyncSession, transaction_id: uuid.UUID, changes: TransactionUpdate
) -> None:
    """
    Everything changing it would check, without changing anything.

    What a Suggestion that proposes a change is held to before it is stored:
    a proposal the app could not apply is refused where it is made rather than
    waiting in the Inbox to fail when the user presses accept.
    """
    await _checked(db, transaction_id, changes)


async def change_transaction(
    db: AsyncSession, transaction_id: uuid.UUID, changes: TransactionUpdate
) -> Transaction:
    """
    The Transaction as the changes leave it, checked but not committed.

    The commit is the caller's, so accepting a Suggestion can write the change
    and the Suggestion it came from in one go.
    """
    transaction, changed = await _checked(db, transaction_id, changes)
    for field, value in changed.items():
        setattr(transaction, field, value)
    return transaction


async def update_transaction(
    db: AsyncSession, transaction_id: uuid.UUID, changes: TransactionUpdate
) -> Transaction:
    transaction = await change_transaction(db, transaction_id, changes)
    await db.commit()
    await db.refresh(transaction)
    return transaction


async def delete_transaction(db: AsyncSession, transaction_id: uuid.UUID) -> None:
    transaction = await get_transaction(db, transaction_id)
    await db.delete(transaction)
    await db.commit()


def _confirm_a_cuota_whose_amount_was_edited(
    transaction: Transaction, changed: dict
) -> None:
    """
    Editing a cuota's amount means the statement arrived, so it is no longer an
    estimate: interest or a USD difference is now the settled figure.
    """
    if transaction.installment_purchase_id is None:
        return
    if "amount" in changed and "amount_status" not in changed:
        changed["amount_status"] = ConfirmationStatus.confirmed


def _check_exchange_rate_is_not_rewritten(
    transaction: Transaction, changed: dict
) -> None:
    """A confirmed Exchange Rate never changes again (ADR-0001)."""
    if transaction.exchange_rate_status is not ConfirmationStatus.confirmed:
        return
    for field in (*EXCHANGE_RATE_FIELDS, "currency"):
        if field in changed and changed[field] != getattr(transaction, field):
            raise Conflict("a confirmed Exchange Rate cannot be changed")


async def check_proposed(db: AsyncSession, data: TransactionCreate) -> None:
    """Everything recording it would check, except what is not settled yet."""
    await _check_domain_rules(db, data, transaction_id=None, proposed=True)


async def _check_domain_rules(
    db: AsyncSession,
    after: TransactionCreate,
    transaction_id: uuid.UUID | None,
    proposed: bool = False,
) -> None:
    """
    Everything the Transaction must be true of once it is stored.

    One list rather than two, so a rule added here cannot be added to what is
    recorded and forgotten about what is proposed. A proposal is held to all of
    it but the Exchange Rate, which it does not carry: the estimator fills one
    in at the moment the user accepts it and the Transaction is recorded.
    """
    await _check_category_type_matches(db, after)
    if not proposed:
        _check_exchange_rate_matches_currency(after)
    _check_only_expenses_go_negative(after)
    await _check_refund(db, after, transaction_id)
    await _check_installment(db, after)
    await _check_recurring_expense(db, after)


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


async def _check_recurring_expense(db: AsyncSession, after: TransactionCreate) -> None:
    """A Transaction can only come from a Recurring Expense that exists."""
    if after.recurring_expense_id is None:
        return
    if after.type is not TransactionType.expense:
        raise Invalid("only an Expense can come from a Recurring Expense")
    if await db.get(RecurringExpense, after.recurring_expense_id) is None:
        raise NotFound(
            f"no Recurring Expense with id {after.recurring_expense_id}"
        )
