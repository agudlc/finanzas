import uuid

from pydantic import BaseModel, Field

from app.schemas.updates import reject_blanking

from app.models.enums import TransactionType


class CategoryBase(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    color: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    type: TransactionType
    icon: str | None = None
    is_default: bool = False


class CategoryCreate(CategoryBase):
    pass


class CategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    color: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    type: TransactionType | None = None
    icon: str | None = None
    is_default: bool | None = None

    _required = reject_blanking("name", "color", "type", "is_default")


class CategoryResponse(CategoryBase):
    id: uuid.UUID

    model_config = {"from_attributes": True}
