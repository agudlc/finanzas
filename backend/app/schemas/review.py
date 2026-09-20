import uuid
from datetime import date as Date
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.enums import (
    Currency,
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


class AddTransactionPayload(BaseModel):
    """
    What an `add_transaction` Suggestion would record.

    This is the kind's schema, and accepting goes through it: the payload, with
    whatever the user edited merged over it, is checked against this before
    anything is recorded, so an edited proposal can be no looser than a proposed
    one. Anything it does not name is not a field of this kind.
    """

    description: str = Field(min_length=1, max_length=250)
    category_id: uuid.UUID
    currency: Currency
    amount: Decimal = Field(gt=0)
    date: Date
    is_fixed: bool = False
    # Which Recurring Expense this came from. Null would mean a proposal from
    # somewhere else, which no producer makes yet.
    recurring_expense_id: uuid.UUID | None = None

    model_config = {"extra": "forbid"}


class SuggestionResponse(BaseModel):
    """
    What is being proposed, and why — and, once resolved, what came of it.

    The payload is left as the kind wrote it: the Inbox reads it to show what
    would change, and accepting it validates it against the kind again.
    """

    id: uuid.UUID
    review_id: uuid.UUID
    kind: SuggestionKind
    month: Date
    payload: dict
    rationale: str
    status: SuggestionStatus
    rejection_reason: str | None
    # What accepting it created, e.g. the Transaction.
    result_id: uuid.UUID | None
    expires_on: Date
    resolved_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class SuggestionAccept(BaseModel):
    """
    "Sí, pero así": the fields of the payload the user changed, if any.

    Only what is given is changed, so a client that only moved the amount does
    not have to send the rest back.
    """

    payload: dict | None = None


class SuggestionReject(BaseModel):
    """"No este mes", and optionally why."""

    reason: str | None = Field(default=None, max_length=250)


class Inbox(BaseModel):
    """Everything the Inbox screen needs in one read."""

    suggestions: list[SuggestionResponse]
    pending_count: int
    # The Reviews queued or running right now, so the screen can say "buscando"
    # and poll faster until they finish.
    reviews: list[ReviewResponse]
