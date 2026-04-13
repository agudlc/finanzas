import enum


class CurrencyEnum(str, enum.Enum):
    ARS = "ARS"
    USD = "USD"


class TypeEnum(str, enum.Enum):
    expense = "expense"
    income = "income"
