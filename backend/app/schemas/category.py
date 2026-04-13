import uuid

from pydantic import BaseModel


class CategoryBase(BaseModel):
    name: str
    color: str
    icon: str | None = None
    is_default: bool = False


class CategoryCreate(CategoryBase):
    pass


class CategoryUpdate(BaseModel):
    name: str | None = None
    color: str | None = None
    icon: str | None = None
    is_default: bool | None = None


class CategoryResponse(CategoryBase):
    id: uuid.UUID

    model_config = {"from_attributes": True}
