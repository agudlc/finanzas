"""
The saved settings for reading one source's exports.

Neither Mercado Pago nor Lemon documents its export format, so the columns,
date and number formats are described by the user with a real file in front of
them rather than hard-coded here.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Import, ImportProfile
from app.schemas.import_profile import ImportProfileCreate, ImportProfileUpdate
from app.services.errors import Conflict, NotFound


async def get_profile(db: AsyncSession, profile_id: uuid.UUID) -> ImportProfile:
    profile = await db.get(ImportProfile, profile_id)
    if profile is None:
        raise NotFound(f"no Import Profile with id {profile_id}")
    return profile


async def list_profiles(db: AsyncSession) -> list[ImportProfile]:
    result = await db.execute(select(ImportProfile).order_by(ImportProfile.name))
    return list(result.scalars().all())


async def create_profile(
    db: AsyncSession, data: ImportProfileCreate
) -> ImportProfile:
    profile = ImportProfile(
        **{**data.model_dump(), "column_mapping": data.column_mapping.model_dump()}
    )
    db.add(profile)
    try:
        await db.commit()
    except IntegrityError as error:
        await db.rollback()
        raise Conflict(f"an Import Profile named '{data.name}' already exists") from error
    await db.refresh(profile)
    return profile


async def update_profile(
    db: AsyncSession, profile_id: uuid.UUID, changes: ImportProfileUpdate
) -> ImportProfile:
    profile = await get_profile(db, profile_id)
    changed = changes.model_dump(exclude_unset=True)
    for field, value in changed.items():
        setattr(profile, field, value)
    await db.commit()
    await db.refresh(profile)
    return profile


async def delete_profile(db: AsyncSession, profile_id: uuid.UUID) -> None:
    profile = await get_profile(db, profile_id)
    used_by = (
        await db.execute(select(Import.id).where(Import.profile_id == profile_id))
    ).scalars().first()
    if used_by is not None:
        raise Conflict(
            "an Import Profile that already read a file cannot be deleted"
        )
    await db.delete(profile)
    await db.commit()
