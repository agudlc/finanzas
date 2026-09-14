from datetime import date as Date
from decimal import Decimal

from pydantic import BaseModel

from app.schemas.updates import reject_blanking

from app.models.enums import Currency, RateType


class SettingsResponse(BaseModel):
    display_currency: Currency
    default_rate_type: RateType

    model_config = {"from_attributes": True}


class SettingsUpdate(BaseModel):
    display_currency: Currency | None = None
    default_rate_type: RateType | None = None

    _required = reject_blanking("display_currency", "default_rate_type")


class RateResponse(BaseModel):
    """A rate as it stood on `date`, which may be earlier than the date asked for."""

    rate_type: RateType
    date: Date
    value: Decimal

    model_config = {"from_attributes": True}
