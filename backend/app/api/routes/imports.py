import uuid

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.categorization import (
    CategorizationRuleCreate,
    CategorizationRuleResponse,
    CategorizationRuleUpdate,
)
from app.schemas.import_profile import (
    FileColumns,
    ImportProfileCreate,
    ImportProfileResponse,
    ImportProfileUpdate,
)
from app.schemas.imports import ImportConfirm, ImportPreview, ImportResponse
from app.services import (
    categorization,
    import_profiles,
    imports as service,
    parsing,
)
from app.services.money import RateEstimator, get_rate_estimator

profiles_router = APIRouter(prefix="/import-profiles", tags=["import profiles"])
rules_router = APIRouter(
    prefix="/categorization-rules", tags=["categorization rules"]
)
router = APIRouter(prefix="/imports", tags=["imports"])


@profiles_router.get("/", response_model=list[ImportProfileResponse])
async def list_profiles(db: AsyncSession = Depends(get_db)):
    return await import_profiles.list_profiles(db)


@profiles_router.post(
    "/", response_model=ImportProfileResponse, status_code=status.HTTP_201_CREATED
)
async def create_profile(
    profile: ImportProfileCreate, db: AsyncSession = Depends(get_db)
):
    return await import_profiles.create_profile(db, profile)


@profiles_router.post("/columns", response_model=FileColumns)
async def read_columns(file: UploadFile = File()):
    """
    The column names of an uploaded export.

    A Profile is written the first time with a real file in front of the user,
    so the columns are offered rather than typed from memory. Nothing is saved.
    """
    filename = file.filename or ""
    return FileColumns(
        filename=filename, columns=parsing.read_columns(filename, await file.read())
    )


@profiles_router.get("/{profile_id}", response_model=ImportProfileResponse)
async def get_profile(profile_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    return await import_profiles.get_profile(db, profile_id)


@profiles_router.patch("/{profile_id}", response_model=ImportProfileResponse)
async def update_profile(
    profile_id: uuid.UUID,
    changes: ImportProfileUpdate,
    db: AsyncSession = Depends(get_db),
):
    return await import_profiles.update_profile(db, profile_id, changes)


@profiles_router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_profile(profile_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    await import_profiles.delete_profile(db, profile_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@rules_router.get("/", response_model=list[CategorizationRuleResponse])
async def list_rules(db: AsyncSession = Depends(get_db)):
    return await categorization.list_rules(db)


@rules_router.post(
    "/",
    response_model=CategorizationRuleResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_rule(
    rule: CategorizationRuleCreate, db: AsyncSession = Depends(get_db)
):
    return await categorization.create_rule(db, rule)


@rules_router.patch("/{rule_id}", response_model=CategorizationRuleResponse)
async def update_rule(
    rule_id: uuid.UUID,
    changes: CategorizationRuleUpdate,
    db: AsyncSession = Depends(get_db),
):
    return await categorization.update_rule(db, rule_id, changes)


@rules_router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rule(rule_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    await categorization.delete_rule(db, rule_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/preview", response_model=ImportPreview)
async def preview_import(
    profile_id: uuid.UUID = Form(),
    file: UploadFile = File(),
    db: AsyncSession = Depends(get_db),
):
    """Reads the file and says what would happen. Nothing is saved."""
    return await service.preview(
        db, profile_id, file.filename or "", await file.read()
    )


@router.get("/", response_model=list[ImportResponse])
async def list_imports(db: AsyncSession = Depends(get_db)):
    return await service.list_imports(db)


@router.post("/", response_model=ImportResponse, status_code=status.HTTP_201_CREATED)
async def confirm_import(
    confirmation: ImportConfirm,
    db: AsyncSession = Depends(get_db),
    estimator: RateEstimator = Depends(get_rate_estimator),
):
    return await service.confirm(db, confirmation, estimator)


@router.delete("/{import_id}", status_code=status.HTTP_204_NO_CONTENT)
async def undo_import(import_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    await service.undo(db, import_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
