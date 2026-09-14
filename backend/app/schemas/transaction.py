import uuid
from datetime import date as Date
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.schemas.updates import reject_blanking

from app.models.enums import Currency, RateType, ConfirmationStatus, TransactionType


class TransactionBase(BaseModel):
    amount: Decimal
    currency: Currency
    type: TransactionType
    category_id: uuid.UUID
    date: Date
    description: str | None = None
    notes: str | None = None
    is_fixed: bool = False

    exchange_rate: Decimal | None = Field(default=None, gt=0)
    exchange_rate_type: RateType | None = None
    exchange_rate_status: ConfirmationStatus | None = None

    amount_status: ConfirmationStatus = ConfirmationStatus.confirmed

    refund_of_id: uuid.UUID | None = None
    installment_purchase_id: uuid.UUID | None = None
    installment_number: int | None = Field(default=None, ge=1)
    import_id: uuid.UUID | None = None

    # Lets a stored Transaction be read back into this shape, so an update can
    # be checked as the Transaction it would become.
    model_config = {"from_attributes": True}


class TransactionCreate(TransactionBase):
    pass


class TransactionUpdate(BaseModel):
    amount: Decimal | None = None
    currency: Currency | None = None
    type: TransactionType | None = None
    category_id: uuid.UUID | None = None
    date: Date | None = None
    description: str | None = None
    notes: str | None = None
    is_fixed: bool | None = None

    exchange_rate: Decimal | None = Field(default=None, gt=0)
    exchange_rate_type: RateType | None = None
    exchange_rate_status: ConfirmationStatus | None = None

    amount_status: ConfirmationStatus | None = None

    refund_of_id: uuid.UUID | None = None
    installment_purchase_id: uuid.UUID | None = None
    installment_number: int | None = Field(default=None, ge=1)

    _required = reject_blanking(
        "amount", "currency", "type", "category_id", "date", "is_fixed",
        "amount_status",
    )


class TransactionResponse(TransactionBase):
    id: uuid.UUID
    created_at: datetime
