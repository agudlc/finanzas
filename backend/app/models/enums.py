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
