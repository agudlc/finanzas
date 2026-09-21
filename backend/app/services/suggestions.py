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
from decimal import Decimal

from pydantic import BaseModel, ValidationError
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.clock import Clock
from app.models import Suggestion, Transaction
from app.models.enums import SuggestionKind, SuggestionStatus, TransactionType
from app.months import add_months, last_day_of_month, month_of
from app.schemas.budget import BudgetCreate
from app.schemas.review import (
    AddTransactionPayload,
    PossibleMatch,
    SetBudgetPayload,
)
from app.schemas.transaction import TransactionCreate
from app.services.budgets import set_budget
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


async def expire_overdue_suggestions(db: AsyncSession, clock: Clock) -> None:
    """
    Stop offering what the month has taken care of.

    Expiry is lazy on purpose: it happens when the Inbox is read, so there is
    no sweeper job to be down. Nothing depends on the sweep having run, though
    — accepting checks the date too — so the worst a long silence costs is rows
    that say pending a little longer than they mean it.
    """
    await db.execute(
        update(Suggestion)
        .where(Suggestion.status == SuggestionStatus.pending)
        .where(Suggestion.expires_on < clock.today())
        .values(status=SuggestionStatus.expired, resolved_at=datetime.now(UTC))
    )
    await db.commit()


async def pending_suggestions(db: AsyncSession) -> list[Suggestion]:
    """What is waiting, newest first."""
    result = await db.execute(
        select(Suggestion)
        .where(Suggestion.status == SuggestionStatus.pending)
        .order_by(Suggestion.month.desc(), Suggestion.created_at.desc())
    )
    return list(result.scalars().all())


# How far back "the user already said no to this" reaches. Longer than the
# Insight window, because a rejection is a standing instruction of sorts:
# three months of them is what keeps a Review from asking the same question
# over and over. A no from last summer says little about this month's rent.
REJECTION_MONTHS = 3


async def rejected_between(
    db: AsyncSession,
    first_month: Date,
    month: Date,
    kind: SuggestionKind | None = None,
) -> list[Suggestion]:
    """
    Every rejection from `first_month` to `month`, newest first.

    Rejections are kept and fed back into later Reviews (ADR-0002), so this is
    what "remember what I turned down" reads.
    """
    statement = (
        select(Suggestion)
        .where(Suggestion.status == SuggestionStatus.rejected)
        .where(Suggestion.month >= month_of(first_month))
        .where(Suggestion.month <= month_of(month))
        .order_by(Suggestion.month.desc(), Suggestion.resolved_at.desc())
    )
    if kind is not None:
        statement = statement.where(Suggestion.kind == kind)
    result = await db.execute(statement)
    return list(result.scalars().all())


async def rejected_since(
    db: AsyncSession, month: Date, earliest: Date
) -> list[Suggestion]:
    """
    What the user said no to lately, which is what the brief carries.

    `earliest` is the lookback floor, so the window is the shorter of the two:
    a Review reading a quarter is never told about the month before it.
    """
    month = month_of(month)
    return await rejected_between(
        db, max(add_months(month, -REJECTION_MONTHS), earliest), month
    )


# How far an already recorded amount may sit from the proposed one and still
# be taken for the same payment, as a share of what was proposed. Rent that
# arrives through an Import rarely lands on the peso the template expected, and
# a tenth is loose enough for that while staying well short of the month's
# other expenses.
SIMILAR_AMOUNT_MARGIN = Decimal("0.10")


async def possible_matches(
    db: AsyncSession, suggestions: list[Suggestion]
) -> dict[uuid.UUID, PossibleMatch]:
    """
    The Possible Match of each proposal that has one, by Suggestion id.

    This is worked out on every read rather than stored, because it is an
    answer about the Transactions there are right now: a proposal made on the
    1st should mention the rent an Import brought in on the 12th. It stays a
    hint — nothing here resolves anything — so the worst a wrong guess costs is
    a sentence the user ignores.

    Only an `add_transaction` proposes a payment, so only one of those can have
    a Possible Match; a Budget is not something an Import can have recorded.
    """
    matches = {}
    for suggestion in suggestions:
        if suggestion.kind is not SuggestionKind.add_transaction:
            continue
        found = await _possible_match(db, suggestion)
        if found is not None:
            matches[suggestion.id] = PossibleMatch.model_validate(found)
    return matches


async def _possible_match(
    db: AsyncSession, suggestion: Suggestion
) -> Transaction | None:
    """
    The Expense of the month that most looks like the one being proposed.

    Same Category — which settles that it is an Expense, since a Category can
    only classify its own type — same month, same currency and about the same
    amount, and not already linked to a Recurring Expense, because such an
    Expense is another template's payment, or this template's for a month
    already dealt with, and either way not the one waiting here. When several
    fit, the closest amount is the likeliest to be it.
    """
    proposed = _validated(AddTransactionPayload, suggestion.payload)
    month = month_of(suggestion.month)
    distance = func.abs(Transaction.amount - proposed.amount)
    result = await db.execute(
        select(Transaction)
        .where(Transaction.category_id == proposed.category_id)
        .where(Transaction.currency == proposed.currency)
        .where(Transaction.date.between(month, last_day_of_month(month)))
        .where(Transaction.recurring_expense_id.is_(None))
        .where(distance <= proposed.amount * SIMILAR_AMOUNT_MARGIN)
        .order_by(distance)
        .limit(1)
    )
    return result.scalars().first()


async def get_suggestion(db: AsyncSession, suggestion_id: uuid.UUID) -> Suggestion:
    suggestion = await db.get(Suggestion, suggestion_id)
    if suggestion is None:
        raise NotFound(f"no Suggestion with id {suggestion_id}")
    return suggestion


async def _apply_add_transaction(
    db: AsyncSession, payload: dict, estimator: RateEstimator, clock: Clock
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


async def _apply_set_budget(
    db: AsyncSession, payload: dict, estimator: RateEstimator, clock: Clock
) -> uuid.UUID:
    """Set the proposed Budget, as if the user had set it themselves."""
    proposed = _validated(SetBudgetPayload, payload)
    budget = await set_budget(
        db,
        BudgetCreate(
            category_id=proposed.category_id,
            amount=proposed.amount,
            currency=proposed.currency,
            month=proposed.month,
        ),
        clock,
    )
    return budget.id


# What accepting a Suggestion of each kind does, and what it leaves behind.
Applier = Callable[
    [AsyncSession, dict, RateEstimator, Clock], Awaitable[uuid.UUID]
]

APPLIERS: dict[SuggestionKind, Applier] = {
    SuggestionKind.add_transaction: _apply_add_transaction,
    SuggestionKind.set_budget: _apply_set_budget,
}


async def accept(
    db: AsyncSession,
    suggestion_id: uuid.UUID,
    edits: dict | None,
    estimator: RateEstimator,
    clock: Clock,
) -> Suggestion:
    """Apply what was proposed, with the user's edits merged over it."""
    suggestion = await get_suggestion(db, suggestion_id)
    await _require_open(db, suggestion, clock)
    suggestion.result_id = await APPLIERS[suggestion.kind](
        db, {**suggestion.payload, **(edits or {})}, estimator, clock
    )
    return await _resolve(db, suggestion, SuggestionStatus.accepted)


async def reject(
    db: AsyncSession, suggestion_id: uuid.UUID, reason: str | None, clock: Clock
) -> Suggestion:
    """
    "Not this month", optionally with a reason.

    The Suggestion stays on record, and its dedupe key keeps this month from
    being proposed again; next month asks a different question.
    """
    suggestion = await get_suggestion(db, suggestion_id)
    await _require_open(db, suggestion, clock)
    suggestion.rejection_reason = reason
    return await _resolve(db, suggestion, SuggestionStatus.rejected)


async def _require_open(
    db: AsyncSession, suggestion: Suggestion, clock: Clock
) -> None:
    """
    Only a Suggestion still waiting can be acted on, and only once.

    A pending one whose month is over is expired here and now rather than
    applied: the Inbox read that would have swept it may not have happened, and
    a proposal for a month that is over is no longer a proposal.
    """
    if suggestion.status is SuggestionStatus.pending and (
        suggestion.expires_on < clock.today()
    ):
        await _resolve(db, suggestion, SuggestionStatus.expired)
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
