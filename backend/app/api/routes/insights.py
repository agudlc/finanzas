"""
Acting on an Insight: the only thing there is to do with one is say you read it.

It is about the Insight rather than the Inbox screen that happens to show it,
so it lives on its own path, the way acting on a Suggestion does.
"""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.review import InsightResponse
from app.services.insights import dismiss

router = APIRouter(prefix="/insights", tags=["insights"])


@router.post("/{insight_id}/dismiss", response_model=InsightResponse)
async def dismiss_insight(insight_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """"Leído": it leaves the Inbox and stays as history."""
    return await dismiss(db, insight_id)
