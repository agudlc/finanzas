import enum


class Currency(str, enum.Enum):
    ARS = "ARS"
    USD = "USD"


class TransactionType(str, enum.Enum):
    expense = "expense"
    income = "income"


class RateType(str, enum.Enum):
    """The Argentine dollar rate an Exchange Rate was taken from."""

    official = "official"
    blue = "blue"
    mep = "mep"
    ccl = "ccl"
    card = "card"
    manual = "manual"


class ConfirmationStatus(str, enum.Enum):
    """Whether a figure is still an estimate or the settled one."""

    estimated = "estimated"
    confirmed = "confirmed"


class NumberFormat(str, enum.Enum):
    """How an export writes 1234.56."""

    comma_decimal = "comma_decimal"  # 1.234,56
    dot_decimal = "dot_decimal"  # 1,234.56


class SignConvention(str, enum.Enum):
    """How an export says whether a row is an Expense or an Income."""

    negative_is_expense = "negative_is_expense"
    positive_is_expense = "positive_is_expense"
    debit_credit_columns = "debit_credit_columns"


class RuleOrigin(str, enum.Enum):
    """Where a Categorization Rule came from."""

    manual = "manual"
    suggestion = "suggestion"


class BudgetState(str, enum.Enum):
    """How a Budget's spending stands against its amount and its Pace."""

    on_pace = "on_pace"
    ahead_of_pace = "ahead_of_pace"
    warning = "warning"
    over = "over"


class ReviewTrigger(str, enum.Enum):
    """What caused a Review to run."""

    recurring_monthly = "recurring_monthly"
    month_end = "month_end"
    manual = "manual"


# The triggers that come due on their own, once each per month. The others are
# the user asking or an event that can happen any number of times in a month,
# so only these are the ones a month can be missing.
SCHEDULED_TRIGGERS = (ReviewTrigger.recurring_monthly,)


class ReviewStatus(str, enum.Enum):
    """How far a Review got. A failed one is never retried."""

    queued = "queued"
    running = "running"
    done = "done"
    failed = "failed"


class SuggestionKind(str, enum.Enum):
    """
    The shapes of change the app knows how to apply.

    Closed on purpose (ADR-0002): anything that does not fit a kind is an
    Insight instead, so nothing can be proposed that the app cannot apply.
    """

    add_transaction = "add_transaction"


class SuggestionStatus(str, enum.Enum):
    """Where a Suggestion stands with the user."""

    pending = "pending"
    accepted = "accepted"
    rejected = "rejected"
    expired = "expired"
