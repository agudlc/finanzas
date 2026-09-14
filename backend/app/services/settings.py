from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Settings
from app.schemas.settings import SettingsUpdate

SETTINGS_ID = 1


async def get_settings(db: AsyncSession) -> Settings:
    """The single Settings record, created with its defaults on first read."""
    settings = await db.get(Settings, SETTINGS_ID)
    if settings is None:
        settings = Settings(id=SETTINGS_ID)
        db.add(settings)
        await db.commit()
        await db.refresh(settings)
    return settings


async def update_settings(db: AsyncSession, changes: SettingsUpdate) -> Settings:
    settings = await get_settings(db)
    for field, value in changes.model_dump(exclude_unset=True).items():
        setattr(settings, field, value)
    await db.commit()
    await db.refresh(settings)
    return settings
