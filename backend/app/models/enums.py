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
