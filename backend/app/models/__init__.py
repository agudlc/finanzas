import uuid
from dataclasses import dataclass
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
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.enums import (
    SCHEDULED_TRIGGERS,
    AdjustmentKind,
    AgentLookback,
    ConfirmationStatus,
    Currency,
    IndexOrigin,
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


@dataclass(frozen=True)
class AdjustmentRule:
    """
    How a Recurring Expense's amount changes over time, as a rent contract says.

    It is the template's adjustment columns read as one thing, because they
    only mean anything together: a period without a percentage or an index name
    adjusts by nothing.
    """

    kind: AdjustmentKind
    period_months: int
    start_month: Date
    percentage: Decimal | None = None
    index_name: str | None = None


# The shape the adjustment columns take when a template has no rule at all.
NO_ADJUSTMENT = {
    "adjustment_kind": AdjustmentKind.none,
    "adjustment_period_months": None,
    "adjustment_percentage": None,
    "adjustment_index_name": None,
    "adjustment_start_month": None,
}

# Each kind fills its own columns and leaves the others null, so a half-written
# rule cannot reach the database from anywhere.
ADJUSTMENT_IS_COHERENT = """
    (adjustment_kind = 'none'
        AND adjustment_period_months IS NULL
        AND adjustment_start_month IS NULL
        AND adjustment_percentage IS NULL
        AND adjustment_index_name IS NULL)
    OR (adjustment_kind = 'percentage'
        AND adjustment_period_months IS NOT NULL
        AND adjustment_start_month IS NOT NULL
        AND adjustment_percentage IS NOT NULL
        AND adjustment_index_name IS NULL)
    OR (adjustment_kind = 'index'
        AND adjustment_period_months IS NOT NULL
        AND adjustment_start_month IS NOT NULL
        AND adjustment_index_name IS NOT NULL
        AND adjustment_percentage IS NULL)
"""


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
        CheckConstraint(
            "adjustment_period_months IS NULL OR adjustment_period_months >= 1",
            name="recurring_expenses_adjustment_period",
        ),
        CheckConstraint(ADJUSTMENT_IS_COHERENT, name="recurring_expenses_adjustment"),
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

    # The Adjustment Rule, spread over columns; `adjustment` reads it as one.
    adjustment_kind: Mapped[AdjustmentKind] = mapped_column(
        Enum(AdjustmentKind), default=AdjustmentKind.none
    )
    # Every how many months the adjustment falls due, counted from its start.
    adjustment_period_months: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    # Percentage points: 10.00 raises the amount by 10%.
    adjustment_percentage: Mapped[Decimal | None] = mapped_column(
        Numeric(8, 2), nullable=True
    )
    adjustment_index_name: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )
    # The month the cycle counts from, stored as its first day. The cycle's own
    # month is not an adjustment: the first one falls a period after it.
    adjustment_start_month: Mapped[Date | None] = mapped_column(
        DateColumn, nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    @property
    def adjustment(self) -> AdjustmentRule | None:
        """The rule this template carries, or None when it carries none."""
        if self.adjustment_kind is AdjustmentKind.none:
            return None
        return AdjustmentRule(
            kind=self.adjustment_kind,
            period_months=self.adjustment_period_months,
            start_month=self.adjustment_start_month,
            percentage=self.adjustment_percentage,
            index_name=self.adjustment_index_name,
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

    # The Recurring Expense this came from, when it was recorded by accepting
    # its Suggestion. It is what makes "the last amount actually paid" exact.
    recurring_expense_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("recurring_expenses.id"), nullable=True
    )

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
    # How far back a Review may read. It is here rather than in the code
    # because it is the user's call how much of their history is worth sending
    # to a model, and they are told as much where they set it.
    agent_lookback: Mapped[AgentLookback] = mapped_column(
        Enum(AgentLookback), default=AgentLookback.quarter
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


class InflationIndex(Base):
    """
    How much prices moved in one month, as a percentage.

    The value is in percentage points, so 1.659 means 1.659%. A month has at
    most one value per index name, and `source` says whether it came from the
    official series or from the user; a hand-entered value is never overwritten
    by a later fetch, the same way a confirmed Exchange Rate never moves.
    """

    __tablename__ = "inflation_indexes"
    __table_args__ = (
        UniqueConstraint("name", "month", name="inflation_indexes_name_month"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # The published name of the index, e.g. "IPC".
    name: Mapped[str] = mapped_column(String(50))
    # The month it describes, stored as its first day.
    month: Mapped[Date] = mapped_column(DateColumn)
    value: Mapped[Decimal] = mapped_column(Numeric(8, 3))
    source: Mapped[IndexOrigin] = mapped_column(Enum(IndexOrigin))

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    def __repr__(self):
        return f"<InflationIndex {self.name} {self.month:%Y-%m}>"


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
    # A scheduled Review happens once per month, and the database is what says
    # so: the cron and a user opening the Inbox can both decide it is missing
    # at the same moment, and only one of them gets to create it. Only the
    # scheduled triggers are covered — the user can ask as often as they like,
    # and an event can happen as often as it happens.
    __table_args__ = (
        Index(
            "uq_scheduled_review_per_month",
            "trigger",
            "month",
            unique=True,
            postgresql_where=text(
                "trigger IN ("
                + ", ".join(f"'{one.value}'" for one in SCHEDULED_TRIGGERS)
                + ")"
            ),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    trigger: Mapped[ReviewTrigger] = mapped_column(Enum(ReviewTrigger))
    # The month the run is about, stored as its first day.
    month: Mapped[Date] = mapped_column(DateColumn)
    status: Mapped[ReviewStatus] = mapped_column(
        Enum(ReviewStatus), default=ReviewStatus.queued
    )
    # Whether the run called the model. Deterministic and agent work never
    # share a Review, so the trigger alone answers this.
    used_agent: Mapped[bool] = mapped_column(Boolean, default=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str | None] = mapped_column(String(250), nullable=True)

    # What the agent run was: the whole exchange as it happened, what it cost,
    # and which prompt asked for it. Null on a deterministic Review, because
    # there was nothing to say to anyone. The transcript is kept so a strange
    # Insight can be read back to where it came from.
    transcript: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(50), nullable=True)

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


class Insight(Base):
    """
    A read-only observation the agent produced during a Review.

    It changes no data, which is why it is not a Suggestion: anything that does
    not fit a Suggestion kind is said here instead (ADR-0002). It belongs to
    the month it was produced in and only waits in the Inbox during that month,
    dismissed or not; afterwards it stays as history later Reviews can read,
    which is why dismissing it is a timestamp and never a delete.
    """

    __tablename__ = "insights"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    review_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("reviews.id"))
    # The month it is about, stored as its first day.
    month: Mapped[Date] = mapped_column(DateColumn)
    # A few words naming what it is about, so the Inbox can be skimmed.
    topic: Mapped[str] = mapped_column(String(100))
    body: Mapped[str] = mapped_column(Text)

    dismissed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    def __repr__(self):
        return f"<Insight {self.topic}>"
