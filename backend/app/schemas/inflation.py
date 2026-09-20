import uuid
from datetime import date as Date
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.inflation import IPC
from app.models.enums import IndexOrigin


class InflationIndexResponse(BaseModel):
    """A month's value, in percentage points: 1.659 means prices moved 1.659%."""

    id: uuid.UUID
    name: str
    # The month it describes, as its first day.
    month: Date
    value: Decimal
    source: IndexOrigin
    updated_at: datetime

    model_config = {"from_attributes": True}


class InflationIndexUpsert(BaseModel):
    """A value typed by hand, replacing whatever the month held."""

    value: Decimal = Field(
        ge=-100,
        le=1000,
        description="percentage points: 1.659 means 1.659%",
    )
    name: str = Field(default=IPC, min_length=1, max_length=50)
