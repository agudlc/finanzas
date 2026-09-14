"""
Bulk-loading Transactions from an export, with the user in control throughout.

Nothing is saved from a preview: the file is parsed, each row is judged against
the Categorization Rules and against what is already recorded, and the answer
goes back for review. Only a confirm writes, and it writes everything at once so
a half-loaded file is never left behind. An Import can be undone.
"""

import uuid
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CategorizationRule, Import, ImportProfile, Transaction
from app.models.enums import RuleOrigin
from app.schemas.categorization import CategorizationRuleCreate
from app.schemas.imports import (
    ConfirmRow,
    ImportConfirm,
    ImportPreview,
    PreviewRow,
    RowStatus,
)
from app.schemas.transaction import TransactionCreate
from app.services import categorization
from app.services.errors import Invalid, NotFound
from app.services.import_profiles import get_profile
from app.services.money import RateEstimator
from app.services.parsing import ParsedRow, parse_rows, read_table
from app.services.transactions import build_transaction


async def get_import(db: AsyncSession, import_id: uuid.UUID) -> Import:
    record = await db.get(Import, import_id)
    if record is None:
        raise NotFound(f"no Import with id {import_id}")
    return record


async def list_imports(db: AsyncSession) -> list[Import]:
    result = await db.execute(select(Import).order_by(Import.created_at.desc()))
    return list(result.scalars().all())


async def is_already_recorded(db: AsyncSession, row: ParsedRow) -> bool:
    """
    Whether the same movement is already in the data.

    Two rows are the same movement when their date, amount, currency and
    description agree, the description compared without case or surrounding
    whitespace — re-importing overlapping periods has to be safe.

    The amount is compared as it is stored, sign and all, so a Refund of 5.000
    already recorded is not mistaken for a 5.000 purchase arriving now.
    """
    existing = await db.execute(
        select(Transaction.id)
        .where(Transaction.date == row.date)
        .where(Transaction.amount == row.amount)
        .where(Transaction.currency == row.currency)
        .where(
            func.lower(func.btrim(func.coalesce(Transaction.description, "")))
            == row.description.strip().casefold()
        )
        .limit(1)
    )
    return existing.scalars().first() is not None


async def preview(
    db: AsyncSession, profile_id: uuid.UUID, filename: str, content: bytes
) -> ImportPreview:
    profile: ImportProfile = await get_profile(db, profile_id)
    rules: list[CategorizationRule] = await categorization.list_rules(db)

    rows = []
    for parsed in parse_rows(read_table(filename, content), profile):
        category_id = categorization.match(rules, parsed.description)
        rows.append(
            PreviewRow(
                number=parsed.number,
                date=parsed.date,
                description=parsed.description,
                amount=parsed.amount,
                currency=parsed.currency,
                type=parsed.type,
                category_id=category_id,
                status=await _status_of(db, parsed, category_id),
            )
        )
    return ImportPreview(profile_id=profile_id, filename=filename, rows=rows)


async def _status_of(
    db: AsyncSession, parsed: ParsedRow, category_id: uuid.UUID | None
) -> RowStatus:
    if parsed.ignored:
        return RowStatus.ignored
    if await is_already_recorded(db, parsed):
        return RowStatus.duplicate
    if category_id is None:
        return RowStatus.needs_category
    return RowStatus.new


def _every_row_categorised(
    rows: list[ConfirmRow],
) -> list[tuple[ConfirmRow, uuid.UUID]]:
    """
    The rows being imported, each paired with the Category it was given.

    Phase 1 has no uncategorized Transactions, so a row on its way in without a
    Category stops the whole import rather than being quietly filed somewhere.
    """
    missing = [row.description for row in rows if row.category_id is None]
    if missing:
        raise Invalid(
            "every row that is being imported needs a Category: "
            + ", ".join(repr(description) for description in missing[:5])
        )
    return [(row, row.category_id) for row in rows if row.category_id is not None]


def _signed(row: ConfirmRow) -> Decimal:
    """A Refund is an Expense with a negative amount; everything else is positive."""
    return -row.amount if row.is_refund else row.amount


async def confirm(
    db: AsyncSession, data: ImportConfirm, estimator: RateEstimator
) -> Import:
    profile = await get_profile(db, data.profile_id)
    keeping = _every_row_categorised([row for row in data.rows if not row.skip])
    record = Import(
        profile_id=profile.id,
        filename=data.filename,
        imported_count=len(keeping),
        skipped_count=len(data.rows) - len(keeping),
    )
    db.add(record)
    await db.flush()

    for row, category_id in keeping:
        await build_transaction(
            db,
            TransactionCreate(
                amount=_signed(row),
                currency=row.currency,
                type=row.type,
                category_id=category_id,
                date=row.date,
                description=row.description or None,
                import_id=record.id,
            ),
            estimator,
        )

    await _remember(db, keeping)
    await db.commit()
    await db.refresh(record)
    return record


async def _remember(
    db: AsyncSession, rows: list[tuple[ConfirmRow, uuid.UUID]]
) -> None:
    """The Categories the user chose by hand, so the next import needs no work."""
    known = {
        rule.pattern.casefold() for rule in await categorization.list_rules(db)
    }
    for row, category_id in rows:
        if row.remember is None:
            continue
        pattern = row.remember.pattern.strip()
        if not pattern or pattern.casefold() in known:
            continue
        known.add(pattern.casefold())
        db.add(
            CategorizationRule(
                **CategorizationRuleCreate(
                    pattern=pattern,
                    category_id=category_id,
                    origin=RuleOrigin.manual,
                ).model_dump()
            )
        )


async def undo(db: AsyncSession, import_id: uuid.UUID) -> None:
    """A bad import is reversible: its Transactions go with it."""
    record = await get_import(db, import_id)
    transactions = (
        await db.execute(
            select(Transaction).where(Transaction.import_id == import_id)
        )
    ).scalars().all()
    for transaction in transactions:
        await db.delete(transaction)
    # The Transactions have to be gone before the row they point at.
    await db.flush()
    await db.delete(record)
    await db.commit()
