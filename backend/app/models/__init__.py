import uuid
from datetime import date as Date
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date as DateColumn,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.enums import (
    ConfirmationStatus,
    Currency,
    NumberFormat,
    RateType,
    ReviewStatus,
    ReviewTrigger,
    RuleOrigin,
    SignConvention,
    SuggestionKind,
    SuggestionStatus,
    TransactionType,
)


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100))
    color: Mapped[str] = mapped_column(String(7))
    icon: Mapped[str | None] = mapped_column(String(50), nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    type: Mapped[TransactionType] = mapped_column(Enum(TransactionType))

    def __repr__(self):
        return f"<Category {self.name}>"


class Budget(Base):
    """A spending limit for one expense Category in one month."""

    __tablename__ = "budgets"
    __table_args__ = (
        UniqueConstraint("category_id", "month", name="budgets_category_month"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    category_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("categories.id"))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[Currency] = mapped_column(Enum(Currency))
    month: Mapped[Date] = mapped_column(DateColumn)


class BudgetMonth(Base):
    """
    A month whose Budgets have been started.

    Rollover copies the previous month's Budgets into a month exactly once, and
    this is how "once" is remembered: without it, deleting every Budget of a
    month would make the next read quietly put them all back.
    """

    __tablename__ = "budget_months"

    month: Mapped[Date] = mapped_column(DateColumn, primary_key=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Goal(Base):
    __tablename__ = "goals"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100))
    target_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[Currency] = mapped_column(Enum(Currency))
    deadline: Mapped[Date | None] = mapped_column(DateColumn, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class InstallmentPurchase(Base):
    """A purchase paid in cuotas. Its cuota Expenses point back at it."""

    __tablename__ = "installment_purchases"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    description: Mapped[str] = mapped_column(String(250))
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[Currency] = mapped_column(Enum(Currency))
    installments: Mapped[int] = mapped_column(Integer)
    category_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("categories.id"))
    purchase_date: Mapped[Date] = mapped_column(DateColumn)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class RecurringExpense(Base):
    """
    A template for an Expense expected every month.

    It never creates Transactions itself: each month a Review turns it into a
    Suggestion. Deactivating it stops those Suggestions without losing the
    template or anything it has produced.
    """

    __tablename__ = "recurring_expenses"
    __table_args__ = (
        CheckConstraint(
            "expected_day BETWEEN 1 AND 31", name="recurring_expenses_expected_day"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    description: Mapped[str] = mapped_column(String(250))
    category_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("categories.id"))
    currency: Mapped[Currency] = mapped_column(Enum(Currency))
    # What the Expense is expected to cost, until a Transaction says otherwise.
    reference_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    # The day of the month it falls on; a shorter month clamps it to its last.
    expected_day: Mapped[int] = mapped_column(Integer)
    is_fixed: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    def __repr__(self):
        return f"<RecurringExpense {self.description}>"


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[Currency] = mapped_column(Enum(Currency))
    type: Mapped[TransactionType] = mapped_column(Enum(TransactionType))
    category_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("categories.id"))
    description: Mapped[str | None] = mapped_column(String(250), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(250), nullable=True)
    is_fixed: Mapped[bool] = mapped_column(Boolean, default=False)
    date: Mapped[Date] = mapped_column(DateColumn)

    # Exchange Rate: ARS per USD, fixed on the Transaction (ADR-0001).
    exchange_rate: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    exchange_rate_type: Mapped[RateType | None] = mapped_column(
        Enum(RateType), nullable=True
    )
    exchange_rate_status: Mapped[ConfirmationStatus | None] = mapped_column(
        Enum(ConfirmationStatus), nullable=True
    )

    amount_status: Mapped[ConfirmationStatus] = mapped_column(
        Enum(ConfirmationStatus), default=ConfirmationStatus.confirmed
    )

    refund_of_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("transactions.id"), nullable=True
    )
    installment_purchase_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("installment_purchases.id"), nullable=True
    )
    installment_number: Mapped[int | None] = mapped_column(Integer, nullable=True)

    import_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("imports.id"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Settings(Base):
    """The single Settings record. Its id is pinned to 1."""

    __tablename__ = "settings"
    __table_args__ = (CheckConstraint("id = 1", name="settings_single_row"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    display_currency: Mapped[Currency] = mapped_column(
        Enum(Currency), default=Currency.ARS
    )
    default_rate_type: Mapped[RateType] = mapped_column(
        Enum(RateType), default=RateType.card
    )


class RateSnapshot(Base):
    """A dollar rate as it stood on one date, kept so past dates convert stably."""

    __tablename__ = "rate_snapshots"
    __table_args__ = (
        UniqueConstraint("date", "rate_type", name="rate_snapshots_date_rate_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    date: Mapped[Date] = mapped_column(DateColumn)
    rate_type: Mapped[RateType] = mapped_column(Enum(RateType))
    value: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ImportProfile(Base):
    """The saved settings for reading exports from one source."""

    __tablename__ = "import_profiles"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    source: Mapped[str] = mapped_column(String(100))

    # {"date": "Fecha", "description": "Descripción", "amount": "Monto",
    #  "debit": ..., "credit": ..., "currency": ..., "type": ...}
    column_mapping: Mapped[dict] = mapped_column(JSONB)
    date_format: Mapped[str] = mapped_column(String(50))
    number_format: Mapped[NumberFormat] = mapped_column(Enum(NumberFormat))
    sign_convention: Mapped[SignConvention] = mapped_column(Enum(SignConvention))

    # Descriptions or type values whose rows are skipped: transfers between the
    # user's own accounts, crypto operations, card payments.
    ignore_patterns: Mapped[list] = mapped_column(JSONB, default=list)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    def __repr__(self):
        return f"<ImportProfile {self.name}>"


class Import(Base):
    """One confirmed bulk load, kept so it can be undone."""

    __tablename__ = "imports"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("import_profiles.id"))
    filename: Mapped[str] = mapped_column(String(250))
    imported_count: Mapped[int] = mapped_column(Integer)
    skipped_count: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class CategorizationRule(Base):
    """"description contains pattern -> Category". The longest pattern wins."""

    __tablename__ = "categorization_rules"
    __table_args__ = (
        UniqueConstraint("pattern", name="categorization_rules_pattern"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    pattern: Mapped[str] = mapped_column(String(250))
    category_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("categories.id"))
    origin: Mapped[RuleOrigin] = mapped_column(
        Enum(RuleOrigin), default=RuleOrigin.manual
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Review(Base):
    """
    One run that produces Suggestions, with the trigger saying what caused it.

    Every Suggestion belongs to one (ADR-0003), including the deterministic
    ones, so "what was proposed, when and why" has a single history. A Review
    that fails keeps its error and is never retried, so bugs stay visible.
    """

    __tablename__ = "reviews"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    trigger: Mapped[ReviewTrigger] = mapped_column(Enum(ReviewTrigger))
    status: Mapped[ReviewStatus] = mapped_column(
        Enum(ReviewStatus), default=ReviewStatus.queued
    )
    # Whether the run called the model. Deterministic and agent work never
    # share a Review, so the trigger alone answers this.
    used_agent: Mapped[bool] = mapped_column(Boolean, default=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str | None] = mapped_column(String(250), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def __repr__(self):
        return f"<Review {self.trigger.value} {self.status.value}>"


class Suggestion(Base):
    """
    A change a Review proposes, waiting in the Inbox.

    The payload holds the proposed change in the shape its kind defines; the
    dedupe key says what it is about ("this template, this month"), so running
    the Reviews again proposes nothing twice. Expiry is a date because a
    Suggestion stops making sense at the end of a month, not at an instant.
    """

    __tablename__ = "suggestions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    review_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("reviews.id"))
    kind: Mapped[SuggestionKind] = mapped_column(Enum(SuggestionKind))
    # The month the Suggestion is about, stored as its first day.
    month: Mapped[Date] = mapped_column(DateColumn)
    dedupe_key: Mapped[str] = mapped_column(String(250))
    payload: Mapped[dict] = mapped_column(JSONB)
    rationale: Mapped[str] = mapped_column(Text)

    status: Mapped[SuggestionStatus] = mapped_column(
        Enum(SuggestionStatus), default=SuggestionStatus.pending
    )
    rejection_reason: Mapped[str | None] = mapped_column(String(250), nullable=True)
    # What accepting it created, e.g. the Transaction. Kept without a foreign
    # key because each kind creates something of its own.
    result_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)

    expires_on: Mapped[Date] = mapped_column(DateColumn)
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    def __repr__(self):
        return f"<Suggestion {self.kind.value} {self.dedupe_key}>"
