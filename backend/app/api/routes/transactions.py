from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import uuid

from app.database import get_db
from app.models import Transaction
from app.schemas.transaction import TransactionCreate, TransactionResponse, TransactionUpdate

router = APIRouter(prefix="/transactions", tags=["transactions"])

@router.get("/", response_model=list[TransactionResponse])
async def get_transactions(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Transaction))
    transactions = result.scalars().all()
    return transactions

@router.post("/", response_model=TransactionResponse)
async def create_transaction(transaction: TransactionCreate, db: AsyncSession = Depends(get_db)):
    db_transaction = Transaction(**transaction.model_dump())
    db.add(db_transaction)
    await db.commit()
    await db.refresh(db_transaction)
    return db_transaction

@router.patch("/{transaction_id}", response_model=TransactionResponse)
async def update_transaction(transaction_id: uuid.UUID, transaction: TransactionUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Transaction).where(Transaction.id == transaction_id))
    db_transaction = result.scalars().first()
    update_data = transaction.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_transaction, field, value)
    await db.commit()
    await db.refresh(db_transaction)
    return db_transaction

@router.delete("/{transaction_id}")
async def delete_transaction(transaction_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Transaction).where(Transaction.id == transaction_id))
    db_transaction = result.scalars().first()
    await db.delete(db_transaction)
    await db.commit()
    return {"ok": True}