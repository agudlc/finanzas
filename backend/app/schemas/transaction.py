import uuid
from datetime import date, datetime
from datetime import date as Date
from decimal import Decimal

from pydantic import BaseModel

from app.models.enums import CurrencyEnum, TypeEnum


class TransactionBase(BaseModel):
    amount: Decimal
    currency: CurrencyEnum
    type: TypeEnum
    category_id: uuid.UUID
    description: str | None = None
    notes: str | None = None
    is_fixed: bool = False
    date: date


class TransactionCreate(TransactionBase):
    pass


class TransactionUpdate(BaseModel):
    amount: Decimal | None = None
    currency: CurrencyEnum | None = None
    type: TypeEnum | None = None
    category_id: uuid.UUID | None = None
    description: str | None = None
    notes: str | None = None
    is_fixed: bool | None = False
    date: Date | None = None


class TransactionResponse(TransactionBase):
    id: uuid.UUID
    created_at: datetime

    model_config = {"from_attributes": True}
