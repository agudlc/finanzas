import uuid
from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from app.models.enums import NumberFormat, SignConvention
from app.schemas.updates import reject_blanking


class ColumnMapping(BaseModel):
    """Which column of the export holds which piece of a Transaction."""

    date: str
    description: str
    amount: str | None = None
    debit: str | None = None
    credit: str | None = None
    currency: str | None = None
    type: str | None = Field(
        default=None,
        description="a column naming the kind of movement, matched by ignore patterns",
    )


class ImportProfileBase(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    source: str = Field(min_length=1, max_length=100)
    column_mapping: ColumnMapping
    date_format: str = Field(min_length=1, max_length=50, examples=["%d/%m/%Y"])
    number_format: NumberFormat
    sign_convention: SignConvention
    ignore_patterns: list[str] = []

    @model_validator(mode="after")
    def check_the_amount_columns_match_the_sign_convention(self):
        mapping, convention = self.column_mapping, self.sign_convention
        if convention is SignConvention.debit_credit_columns:
            if not (mapping.debit and mapping.credit):
                raise ValueError(
                    "a debit/credit export needs both a debit and a credit column"
                )
        elif not mapping.amount:
            raise ValueError("an export with one amount column needs it mapped")
        return self


class ImportProfileCreate(ImportProfileBase):
    pass


class ImportProfileUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    source: str | None = Field(default=None, min_length=1, max_length=100)
    column_mapping: ColumnMapping | None = None
    date_format: str | None = Field(default=None, min_length=1, max_length=50)
    number_format: NumberFormat | None = None
    sign_convention: SignConvention | None = None
    ignore_patterns: list[str] | None = None

    _required = reject_blanking(
        "name", "source", "column_mapping", "date_format", "number_format",
        "sign_convention", "ignore_patterns",
    )


class ImportProfileResponse(ImportProfileBase):
    id: uuid.UUID
    created_at: datetime

    model_config = {"from_attributes": True}


class FileColumns(BaseModel):
    """The headings a file was found to have, offered as mapping choices."""

    filename: str
    columns: list[str]
