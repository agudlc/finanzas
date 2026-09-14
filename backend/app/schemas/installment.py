import uuid
from datetime import date as Date
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.enums import Currency, RateType
from app.schemas.transaction import TransactionResponse


class InstallmentPurchaseCreate(BaseModel):
    """Recorded once; the cuotas are generated from it."""

    description: str = Field(min_length=1, max_length=250)
    total_amount: Decimal = Field(gt=0)
    installments: int = Field(ge=1, le=60, description="how many cuotas")
    category_id: uuid.UUID
    currency: Currency = Currency.ARS
    purchase_date: Date

    # Which dollar rate the cuotas are estimated with, when the purchase is in USD.
    exchange_rate_type: RateType | None = None


class InstallmentPurchaseResponse(BaseModel):
    id: uuid.UUID
    description: str
    total_amount: Decimal
    currency: Currency
    installments: int
    category_id: uuid.UUID
    purchase_date: Date
    created_at: datetime

    model_config = {"from_attributes": True}


class InstallmentPurchaseDetail(InstallmentPurchaseResponse):
    cuotas: list[TransactionResponse]
