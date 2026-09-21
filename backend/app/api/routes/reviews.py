import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.clock import Clock, get_clock
from app.database import get_db
from app.models.enums import MANUAL_TRIGGERS
from app.months import month_of
from app.queue import ReviewQueue, get_review_queue
from app.schemas.review import ReviewDetail, ReviewResponse, ReviewSummary
from app.services import insights as insights_service
from app.services import reviews as service
from app.services import suggestions as suggestions_service

router = APIRouter(prefix="/reviews", tags=["reviews"])

# "Revisar ahora" asks for two Reviews rather than one because a Review either
# called the model or it did not (ADR-0003). Separate is also what keeps the
# proposals coming when the model is unreachable: a failed agent Review takes
# nothing else down with it.

@router.post(
    "/", response_model=list[ReviewResponse], status_code=status.HTTP_201_CREATED
)
async def create_review(
    db: AsyncSession = Depends(get_db),
    clock: Clock = Depends(get_clock),
    queue: ReviewQueue = Depends(get_review_queue),
):
    """"Revisar ahora": the Reviews come back queued, not finished."""
    month = month_of(clock.today())
    created = []
    for trigger in MANUAL_TRIGGERS:
        review = await service.create_review(db, trigger, month)
        await queue.enqueue(review.id)
        created.append(review)
    return created


@router.get("/", response_model=list[ReviewSummary])
async def list_reviews(db: AsyncSession = Depends(get_db)):
    """The history: the most recent runs, newest first."""
    return await service.list_reviews(db)


@router.get("/{review_id}", response_model=ReviewDetail)
async def get_review(review_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """One run in full: the exchange it was, and everything it left behind."""
    review = await service.get_review(db, review_id)
    return {
        **ReviewSummary.model_validate(review).model_dump(),
        "transcript": review.transcript,
        "prompt_version": review.prompt_version,
        "suggestions": await suggestions_service.of_review(db, review.id),
        "insights": await insights_service.of_review(db, review.id),
    }
