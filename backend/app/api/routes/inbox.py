from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.review import Inbox
from app.services.reviews import waiting_reviews
from app.services.suggestions import pending_suggestions

router = APIRouter(prefix="/inbox", tags=["inbox"])


@router.get("/", response_model=Inbox)
async def read_inbox(db: AsyncSession = Depends(get_db)):
    pending = await pending_suggestions(db)
    return Inbox(
        suggestions=pending,
        pending_count=len(pending),
        reviews=await waiting_reviews(db),
    )
