import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Category, Transaction
from app.schemas.category import CategoryCreate, CategoryUpdate
from app.services.errors import Conflict, NotFound


async def get_category(db: AsyncSession, category_id: uuid.UUID) -> Category:
    category = await db.get(Category, category_id)
    if category is None:
        raise NotFound(f"no Category with id {category_id}")
    return category


async def list_categories(db: AsyncSession) -> list[Category]:
    result = await db.execute(select(Category).order_by(Category.name))
    return list(result.scalars().all())


async def count_transactions_in(db: AsyncSession, category_id: uuid.UUID) -> int:
    result = await db.execute(
        select(func.count())
        .select_from(Transaction)
        .where(Transaction.category_id == category_id)
    )
    return result.scalar_one()


async def create_category(db: AsyncSession, data: CategoryCreate) -> Category:
    category = Category(**data.model_dump())
    db.add(category)
    await db.commit()
    await db.refresh(category)
    return category


async def update_category(
    db: AsyncSession, category_id: uuid.UUID, changes: CategoryUpdate
) -> Category:
    category = await get_category(db, category_id)
    changed = changes.model_dump(exclude_unset=True)

    new_type = changed.get("type")
    if new_type is not None and new_type != category.type:
        if await count_transactions_in(db, category_id):
            raise Conflict(
                "a Category that already classifies Transactions cannot change type"
            )

    for field, value in changed.items():
        setattr(category, field, value)
    await db.commit()
    await db.refresh(category)
    return category


async def delete_category(db: AsyncSession, category_id: uuid.UUID) -> None:
    category = await get_category(db, category_id)
    if await count_transactions_in(db, category_id):
        raise Conflict(
            "a Category that still classifies Transactions cannot be deleted"
        )
    await db.delete(category)
    await db.commit()
