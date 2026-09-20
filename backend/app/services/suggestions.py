"""
Suggestions: what a Review leaves for the user in the Inbox, and what the user
does about it.

Producers never write Suggestions themselves; they call `propose`, which is
where "do not propose this twice" lives. A proposal is identified by its kind
and its dedupe key ("this template, this month"), so pressing "Revisar ahora"
twice is harmless, and so is a scheduled Review that runs after a manual one.

Accepting is the other half: the payload — as proposed, or with the user's edits
merged in — is checked against its kind and then applied through the very
service the HTTP routes use, so nothing can be recorded by accepting that the
user could not have recorded by hand (ADR-0002). The Suggestion and what it
created are written in one commit, so a proposal is never marked accepted
without its Transaction, nor the other way round.
"""

import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, date as Date, datetime

from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Suggestion
from app.models.enums import SuggestionKind, SuggestionStatus, TransactionType
from app.months import last_day_of_month, month_of
from app.schemas.review import AddTransactionPayload
from app.schemas.transaction import TransactionCreate
from app.services.errors import Conflict, Invalid, NotFound
from app.services.money import RateEstimator
from app.services.transactions import build_transaction

# An expired proposal does not block a new one: the month it was about is over,
# and the same proposal may well make sense again.
BLOCKING = (
    SuggestionStatus.pending,
    SuggestionStatus.accepted,
    SuggestionStatus.rejected,
)


async def propose(
    db: AsyncSession,
    review_id: uuid.UUID,
    kind: SuggestionKind,
    month: Date,
    dedupe_key: str,
    payload: dict,
    rationale: str,
) -> Suggestion | None:
    """The Suggestion, or None when this proposal has already been made."""
    month = month_of(month)
    if await _already_proposed(db, kind, dedupe_key):
        return None
    suggestion = Suggestion(
        review_id=review_id,
        kind=kind,
        month=month,
        dedupe_key=dedupe_key,
        payload=payload,
        rationale=rationale,
        expires_on=last_day_of_month(month),
    )
    db.add(suggestion)
    return suggestion


async def _already_proposed(
    db: AsyncSession, kind: SuggestionKind, dedupe_key: str
) -> bool:
    result = await db.execute(
        select(Suggestion.id)
        .where(Suggestion.kind == kind)
        .where(Suggestion.dedupe_key == dedupe_key)
        .where(Suggestion.status.in_(BLOCKING))
        .limit(1)
    )
    return result.scalars().first() is not None


async def pending_suggestions(db: AsyncSession) -> list[Suggestion]:
    """What is waiting, newest first."""
    result = await db.execute(
        select(Suggestion)
        .where(Suggestion.status == SuggestionStatus.pending)
        .order_by(Suggestion.month.desc(), Suggestion.created_at.desc())
    )
    return list(result.scalars().all())


async def get_suggestion(db: AsyncSession, suggestion_id: uuid.UUID) -> Suggestion:
    suggestion = await db.get(Suggestion, suggestion_id)
    if suggestion is None:
        raise NotFound(f"no Suggestion with id {suggestion_id}")
    return suggestion


async def _apply_add_transaction(
    db: AsyncSession, payload: dict, estimator: RateEstimator
) -> uuid.UUID:
    """Record the proposed Expense, as if the user had typed it in themselves."""
    proposed = _validated(AddTransactionPayload, payload)
    transaction = await build_transaction(
        db,
        TransactionCreate(
            amount=proposed.amount,
            currency=proposed.currency,
            type=TransactionType.expense,
            category_id=proposed.category_id,
            date=proposed.date,
            description=proposed.description,
            is_fixed=proposed.is_fixed,
            recurring_expense_id=proposed.recurring_expense_id,
        ),
        estimator,
    )
    # The id is the column default, which only exists once the row is flushed.
    await db.flush()
    return transaction.id


# What accepting a Suggestion of each kind does, and what it leaves behind.
Applier = Callable[[AsyncSession, dict, RateEstimator], Awaitable[uuid.UUID]]

APPLIERS: dict[SuggestionKind, Applier] = {
    SuggestionKind.add_transaction: _apply_add_transaction,
}


async def accept(
    db: AsyncSession,
    suggestion_id: uuid.UUID,
    edits: dict | None,
    estimator: RateEstimator,
) -> Suggestion:
    """Apply what was proposed, with the user's edits merged over it."""
    suggestion = await get_suggestion(db, suggestion_id)
    _require_pending(suggestion)
    suggestion.result_id = await APPLIERS[suggestion.kind](
        db, {**suggestion.payload, **(edits or {})}, estimator
    )
    return await _resolve(db, suggestion, SuggestionStatus.accepted)


async def reject(
    db: AsyncSession, suggestion_id: uuid.UUID, reason: str | None
) -> Suggestion:
    """
    "Not this month", optionally with a reason.

    The Suggestion stays on record, and its dedupe key keeps this month from
    being proposed again; next month asks a different question.
    """
    suggestion = await get_suggestion(db, suggestion_id)
    _require_pending(suggestion)
    suggestion.rejection_reason = reason
    return await _resolve(db, suggestion, SuggestionStatus.rejected)


def _require_pending(suggestion: Suggestion) -> None:
    """Only a Suggestion still waiting can be acted on, and only once."""
    if suggestion.status is not SuggestionStatus.pending:
        raise Conflict(
            f"this Suggestion is already {suggestion.status.value}, "
            "so it cannot be resolved again"
        )


async def _resolve(
    db: AsyncSession, suggestion: Suggestion, status: SuggestionStatus
) -> Suggestion:
    suggestion.status = status
    suggestion.resolved_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(suggestion)
    return suggestion


def _validated[Payload: BaseModel](kind: type[Payload], payload: dict) -> Payload:
    """The payload as its kind defines it, or a 422 saying what is wrong."""
    try:
        return kind.model_validate(payload)
    except ValidationError as error:
        problems = "; ".join(
            f"{'.'.join(str(part) for part in problem['loc'])}: {problem['msg']}"
            for problem in error.errors()
        )
        raise Invalid(f"this is not a valid {kind.__name__}: {problems}") from error
