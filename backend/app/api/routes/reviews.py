import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.clock import Clock, get_clock
from app.database import get_db
from app.models.enums import ReviewTrigger
from app.months import month_of
from app.queue import ReviewQueue, get_review_queue
from app.schemas.review import ReviewResponse
from app.services import reviews as service

router = APIRouter(prefix="/reviews", tags=["reviews"])


@router.post("/", response_model=ReviewResponse, status_code=status.HTTP_201_CREATED)
async def create_review(
    db: AsyncSession = Depends(get_db),
    clock: Clock = Depends(get_clock),
    queue: ReviewQueue = Depends(get_review_queue),
):
    """"Revisar ahora": the Review comes back queued, not finished."""
    review = await service.create_review(
        db, ReviewTrigger.manual, month_of(clock.today())
    )
    await queue.enqueue(review.id)
    return review


@router.get("/", response_model=list[ReviewResponse])
async def list_reviews(db: AsyncSession = Depends(get_db)):
    return await service.list_reviews(db)


@router.get("/{review_id}", response_model=ReviewResponse)
async def get_review(review_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    return await service.get_review(db, review_id)
