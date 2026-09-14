import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import RuleOrigin
from app.schemas.updates import reject_blanking


class CategorizationRuleCreate(BaseModel):
    pattern: str = Field(min_length=1, max_length=250)
    category_id: uuid.UUID
    origin: RuleOrigin = RuleOrigin.manual


class CategorizationRuleUpdate(BaseModel):
    pattern: str | None = Field(default=None, min_length=1, max_length=250)
    category_id: uuid.UUID | None = None

    _required = reject_blanking("pattern", "category_id")


class CategorizationRuleResponse(BaseModel):
    id: uuid.UUID
    pattern: str
    category_id: uuid.UUID
    origin: RuleOrigin
    created_at: datetime

    model_config = {"from_attributes": True}
