import uuid

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.installment import (
    InstallmentPurchaseCreate,
    InstallmentPurchaseDetail,
    InstallmentPurchaseResponse,
)
from app.services import installments as service
from app.services.money import RateEstimator, get_rate_estimator

router = APIRouter(prefix="/installment-purchases", tags=["installment purchases"])


async def _with_cuotas(db: AsyncSession, purchase) -> dict:
    return {
        **InstallmentPurchaseResponse.model_validate(purchase).model_dump(),
        "cuotas": await service.cuotas_of(db, purchase.id),
    }


@router.get("/", response_model=list[InstallmentPurchaseResponse])
async def list_purchases(db: AsyncSession = Depends(get_db)):
    return await service.list_purchases(db)


@router.post(
    "/", response_model=InstallmentPurchaseDetail, status_code=status.HTTP_201_CREATED
)
async def create_purchase(
    purchase: InstallmentPurchaseCreate,
    db: AsyncSession = Depends(get_db),
    estimator: RateEstimator = Depends(get_rate_estimator),
):
    created = await service.create_purchase(db, purchase, estimator)
    return await _with_cuotas(db, created)


@router.get("/{purchase_id}", response_model=InstallmentPurchaseDetail)
async def get_purchase(purchase_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    return await _with_cuotas(db, await service.get_purchase(db, purchase_id))


@router.delete("/{purchase_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_purchase(purchase_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    await service.delete_purchase(db, purchase_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
