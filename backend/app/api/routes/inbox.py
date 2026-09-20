"""
The Inbox: one read that also keeps the schedule honest.

Reading it is when the month's own Reviews are caught up on and when proposals
whose month is over stop being offered. Both are cheap, and doing them here is
what lets the app have no sweeper job and survive a worker that was down.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.clock import Clock, get_clock
from app.database import get_db
from app.queue import ReviewQueue, get_review_queue
from app.schemas.review import Inbox
from app.services.reviews import ensure_scheduled_reviews, waiting_reviews
from app.services.suggestions import (
    expire_overdue_suggestions,
    pending_suggestions,
)

router = APIRouter(prefix="/inbox", tags=["inbox"])


@router.get("/", response_model=Inbox)
async def read_inbox(
    db: AsyncSession = Depends(get_db),
    clock: Clock = Depends(get_clock),
    queue: ReviewQueue = Depends(get_review_queue),
):
    await expire_overdue_suggestions(db, clock)
    await ensure_scheduled_reviews(db, clock, queue)
    pending = await pending_suggestions(db)
    return Inbox(
        suggestions=pending,
        pending_count=len(pending),
        reviews=await waiting_reviews(db),
    )
