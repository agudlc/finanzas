"""
Acting on a Suggestion: yes, yes-but-so, or not this month.

It is about the Suggestion rather than the Inbox screen that happens to show
it, so it lives on its own path and in its own module.
"""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.clock import Clock, get_clock
from app.database import get_db
from app.schemas.review import (
    SuggestionAccept,
    SuggestionReject,
    SuggestionResponse,
)
from app.services.money import RateEstimator, get_rate_estimator
from app.services.suggestions import accept, reject

router = APIRouter(prefix="/suggestions", tags=["suggestions"])


@router.post("/{suggestion_id}/accept", response_model=SuggestionResponse)
async def accept_suggestion(
    suggestion_id: uuid.UUID,
    body: SuggestionAccept | None = None,
    db: AsyncSession = Depends(get_db),
    estimator: RateEstimator = Depends(get_rate_estimator),
    clock: Clock = Depends(get_clock),
):
    """Record what was proposed, as it stands or with the edits in the body."""
    return await accept(
        db, suggestion_id, body.payload if body else None, estimator, clock
    )


@router.post("/{suggestion_id}/reject", response_model=SuggestionResponse)
async def reject_suggestion(
    suggestion_id: uuid.UUID,
    body: SuggestionReject | None = None,
    db: AsyncSession = Depends(get_db),
    clock: Clock = Depends(get_clock),
):
    """"No este mes": nothing is recorded, and the reason is kept if given."""
    return await reject(db, suggestion_id, body.reason if body else None, clock)
