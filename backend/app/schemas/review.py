import uuid
from datetime import date as Date
from datetime import datetime

from pydantic import BaseModel

from app.models.enums import (
    ReviewStatus,
    ReviewTrigger,
    SuggestionKind,
    SuggestionStatus,
)


class ReviewResponse(BaseModel):
    id: uuid.UUID
    trigger: ReviewTrigger
    status: ReviewStatus
    used_agent: bool
    error: str | None
    note: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None

    model_config = {"from_attributes": True}


class SuggestionResponse(BaseModel):
    """
    What is being proposed, and why.

    The payload is left as the kind wrote it: the Inbox reads it to show what
    would change, and accepting it (next) validates it against the kind.
    """

    id: uuid.UUID
    review_id: uuid.UUID
    kind: SuggestionKind
    month: Date
    payload: dict
    rationale: str
    status: SuggestionStatus
    expires_on: Date
    created_at: datetime

    model_config = {"from_attributes": True}


class Inbox(BaseModel):
    """Everything the Inbox screen needs in one read."""

    suggestions: list[SuggestionResponse]
    pending_count: int
    # The Reviews queued or running right now, so the screen can say "buscando"
    # and poll faster until they finish.
    reviews: list[ReviewResponse]
