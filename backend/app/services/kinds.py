"""
The Suggestion kinds: one place that says what each shape of change is.

The list is closed (ADR-0002): a Review can only propose something the app
already knows how to apply, and anything that does not fit a kind is an Insight
instead. This is where that list lives, and everything the rest of the app asks
about a kind it asks here — what its payload looks like, what it is about, what
has to be true of it, what accepting it does, and how it reads in a line.

Keeping every piece of a kind in one record is the point. A new kind is one
entry, and an entry missing a piece does not compile into a half-supported kind
that can be proposed but not applied, or applied but not read back to the model.
"""

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date as Date

from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.clock import Clock
from app.models import Suggestion, Transaction
from app.models.enums import RuleOrigin, SuggestionKind, TransactionType
from app.months import format_month
from app.schemas.budget import BudgetCreate
from app.schemas.categorization import CategorizationRuleCreate
from app.schemas.recurring_expense import RecurringExpenseCreate
from app.schemas.review import (
    AddCategorizationRulePayload,
    AddRecurringExpensePayload,
    AddTransactionPayload,
    RecategorizeTransactionPayload,
    SetBudgetPayload,
)
from app.schemas.transaction import TransactionCreate, TransactionUpdate
from app.services.budgets import check_budget, set_budget
from app.services.categorization import build_rule, check_rule
from app.services.errors import Invalid
from app.services.money import RateEstimator
from app.services.recurring_expenses import (
    build_recurring_expense,
    check_proposed as check_proposed_template,
)
from app.services.transactions import (
    build_transaction,
    change_transaction,
    check_change,
    check_proposed,
)


@dataclass(frozen=True)
class Kind:
    """
    Everything one shape of change is, in the order it is used.

    `key` is what the proposal is about, and two proposals about the same thing
    are the same proposal however differently they are worded: it is what makes
    a rejection mean "not this month" rather than an invitation to ask again.
    `check` is the domain rules `apply` would raise on, asked before anything
    is stored. `reads` is the one line the brief and the read tools write the
    proposal out as, so the model meets it in the same words either way; it is
    given the session because a payload holds ids, and a line the model is
    meant to recognise a proposal by has to name what those ids point at.
    """

    payload: type[BaseModel]
    purpose: str
    key: Callable[[BaseModel, Date], str]
    check: Callable[[AsyncSession, BaseModel], Awaitable[None]]
    # Every applier is handed the estimator and the clock whether it wants them
    # or not: what a kind needs to apply itself is its own business, and one
    # signature is what lets `accept` dispatch without asking which kind it has.
    apply: Callable[
        [AsyncSession, BaseModel, RateEstimator, Clock], Awaitable[uuid.UUID]
    ]
    reads: Callable[[AsyncSession, Suggestion, str], Awaitable[str]]


def validated[Payload: BaseModel](kind: type[Payload], payload: dict) -> Payload:
    """The payload as its kind defines it, or a 422 saying what is wrong."""
    try:
        return kind.model_validate(payload)
    except ValidationError as error:
        problems = "; ".join(
            f"{'.'.join(str(part) for part in problem['loc'])}: {problem['msg']}"
            for problem in error.errors()
        )
        raise Invalid(f"this is not a valid {kind.__name__}: {problems}") from error


# --- add_transaction -------------------------------------------------------


def _transaction_from(proposed: AddTransactionPayload) -> TransactionCreate:
    """The Expense the proposal would record. Only Expenses are proposed."""
    return TransactionCreate(
        amount=proposed.amount,
        currency=proposed.currency,
        type=TransactionType.expense,
        category_id=proposed.category_id,
        date=proposed.date,
        description=proposed.description,
        is_fixed=proposed.is_fixed,
        recurring_expense_id=proposed.recurring_expense_id,
    )


def _add_transaction_key(proposed: AddTransactionPayload, month: Date) -> str:
    """
    What an `add_transaction` proposal is about: this payment, this month.

    A template's month is the template, so a Recurring Expense is proposed once
    per month whoever proposes it. One that comes from nowhere in particular
    has only its description to be recognised by, which is enough to keep the
    same rent from being proposed twice in the same month under two rationales.
    """
    about = proposed.recurring_expense_id or proposed.description
    return f"{about}:{format_month(month)}"


async def _check_add_transaction(
    db: AsyncSession, proposed: AddTransactionPayload
) -> None:
    await check_proposed(db, _transaction_from(proposed))


async def _apply_add_transaction(
    db: AsyncSession,
    proposed: AddTransactionPayload,
    estimator: RateEstimator,
    clock: Clock,
) -> uuid.UUID:
    """Record the proposed Expense, as if the user had typed it in themselves."""
    transaction = await build_transaction(
        db, _transaction_from(proposed), estimator
    )
    # The id is the column default, which only exists once the row is flushed.
    await db.flush()
    return transaction.id


async def _reads_add_transaction(
    db: AsyncSession, suggestion: Suggestion, category: str
) -> str:
    payload = suggestion.payload
    return (
        f"record \"{payload['description']}\" in {category}, "
        f"{payload['amount']} {payload['currency']} on {payload['date']}"
    )


# --- set_budget ------------------------------------------------------------


def _budget_from(proposed: SetBudgetPayload) -> BudgetCreate:
    return BudgetCreate(
        category_id=proposed.category_id,
        amount=proposed.amount,
        currency=proposed.currency,
        month=proposed.month,
    )


def _set_budget_key(proposed: SetBudgetPayload, month: Date) -> str:
    """
    What a `set_budget` proposal is about: this Category, this Budget's month.

    The payload's month rather than the Review's, which are the same month when
    the arithmetic proposes one and need not be when the agent does: a proposal
    about April is not the proposal about March, however they were arrived at.
    """
    return f"{proposed.category_id}:{format_month(proposed.month)}"


async def _check_set_budget(db: AsyncSession, proposed: SetBudgetPayload) -> None:
    await check_budget(db, _budget_from(proposed))


async def _apply_set_budget(
    db: AsyncSession,
    proposed: SetBudgetPayload,
    estimator: RateEstimator,
    clock: Clock,
) -> uuid.UUID:
    """Set the proposed Budget, as if the user had set it themselves."""
    budget = await set_budget(db, _budget_from(proposed), clock)
    return budget.id


async def _reads_set_budget(
    db: AsyncSession, suggestion: Suggestion, category: str
) -> str:
    payload = suggestion.payload
    return (
        f"set the {category} Budget for {format_month(suggestion.month)} "
        f"to {payload['amount']} {payload['currency']}"
    )


# --- recategorize_transaction ----------------------------------------------


def _moved(proposed: RecategorizeTransactionPayload) -> TransactionUpdate:
    return TransactionUpdate(category_id=proposed.category_id)


def _recategorize_key(
    proposed: RecategorizeTransactionPayload, month: Date
) -> str:
    """
    What a recategorization is about: this Transaction, this Category.

    Not the month, unlike the other two. A Transaction is filed where it is
    filed, so "move that one to Delivery" is the same proposal whenever it is
    made, and a user who said no to it does not want it back in four weeks.
    """
    return f"{proposed.transaction_id}:{proposed.category_id}"


async def _check_recategorize(
    db: AsyncSession, proposed: RecategorizeTransactionPayload
) -> None:
    await check_change(db, proposed.transaction_id, _moved(proposed))


async def _apply_recategorize(
    db: AsyncSession,
    proposed: RecategorizeTransactionPayload,
    estimator: RateEstimator,
    clock: Clock,
) -> uuid.UUID:
    """
    File the Transaction under the proposed Category instead.

    Through the transaction service, so the Category's type is checked against
    the Transaction's exactly as it would be from the screen (ADR-0002). The
    Transaction is the one thing that changes: its amount, its date and its
    Exchange Rate are none of this kind's business.
    """
    transaction = await change_transaction(
        db, proposed.transaction_id, _moved(proposed)
    )
    return transaction.id


async def _reads_recategorize(
    db: AsyncSession, suggestion: Suggestion, category: str
) -> str:
    """
    Which Transaction is being moved, and where to.

    It says the Transaction out loud — its description and its date — because
    the payload is two ids and "move a Transaction into Delivery" is the same
    sentence for every misfiled Transaction there is. The model is asked not to
    restate what is already waiting and to take past rejections seriously, and
    it can do neither if two proposals read alike.
    """
    moving = await db.get(
        Transaction, uuid.UUID(str(suggestion.payload["transaction_id"]))
    )
    if moving is None:
        return f"move a Transaction into {category}"
    return (
        f"move \"{moving.description or 'no description'}\" of "
        f"{moving.date.isoformat()} into {category}"
    )


# --- add_categorization_rule -----------------------------------------------


def _rule_from(proposed: AddCategorizationRulePayload) -> CategorizationRuleCreate:
    """
    The rule the proposal would learn, marked as having come from one.

    The origin is not the agent's to state: a rule the user accepts came from
    a Suggestion whatever the payload says, and the payload does not say.
    """
    return CategorizationRuleCreate(
        pattern=proposed.pattern,
        category_id=proposed.category_id,
        origin=RuleOrigin.suggestion,
    )


def _add_categorization_rule_key(
    proposed: AddCategorizationRulePayload, month: Date
) -> str:
    """
    What the proposal is about: this pattern, whatever its case.

    Not the Category and not the month. A pattern can only be mapped once, so
    "send pedidosya somewhere" is one question however it is answered, and a
    user who said no to learning it does not want it back in four weeks.
    """
    return proposed.pattern.strip().casefold()


async def _check_add_categorization_rule(
    db: AsyncSession, proposed: AddCategorizationRulePayload
) -> None:
    await check_rule(db, _rule_from(proposed))


async def _apply_add_categorization_rule(
    db: AsyncSession,
    proposed: AddCategorizationRulePayload,
    estimator: RateEstimator,
    clock: Clock,
) -> uuid.UUID:
    """
    Learn the rule, and leave every Transaction where it is.

    A rule only applies to what an Import brings in after it exists (ADR-0004),
    and nothing here reaches for a Transaction, so that holds by construction
    rather than by care.
    """
    rule = await build_rule(db, _rule_from(proposed))
    return rule.id


async def _reads_add_categorization_rule(
    db: AsyncSession, suggestion: Suggestion, category: str
) -> str:
    payload = suggestion.payload
    return (
        f"send imported Transactions saying \"{payload['pattern']}\" "
        f"to {category} from now on"
    )


# --- add_recurring_expense -------------------------------------------------


def _template_from(proposed: AddRecurringExpensePayload) -> RecurringExpenseCreate:
    """
    The template the proposal would set up, without an Adjustment Rule.

    A rule is added afterwards if the user has one; this kind does not propose
    one, so there is nothing to carry across.
    """
    return RecurringExpenseCreate(
        description=proposed.description,
        category_id=proposed.category_id,
        currency=proposed.currency,
        reference_amount=proposed.reference_amount,
        expected_day=proposed.expected_day,
        is_fixed=proposed.is_fixed,
    )


def _add_recurring_expense_key(
    proposed: AddRecurringExpensePayload, month: Date
) -> str:
    """
    What the proposal is about: this charge, in this Category.

    A template is not about a month — it is about every month — so the Review's
    month is no part of it, and neither is the amount: "Netflix in Ocio" is the
    same template proposed at 7.999 or at 9.499.
    """
    return f"{proposed.description.strip().casefold()}:{proposed.category_id}"


async def _check_add_recurring_expense(
    db: AsyncSession, proposed: AddRecurringExpensePayload
) -> None:
    await check_proposed_template(db, _template_from(proposed))


async def _apply_add_recurring_expense(
    db: AsyncSession,
    proposed: AddRecurringExpensePayload,
    estimator: RateEstimator,
    clock: Clock,
) -> uuid.UUID:
    """
    Set up the template, which records nothing by itself.

    From next month on it produces a Suggestion, the way one set up from the
    screen does; accepting this spends nothing.
    """
    template = await build_recurring_expense(db, _template_from(proposed))
    return template.id


async def _reads_add_recurring_expense(
    db: AsyncSession, suggestion: Suggestion, category: str
) -> str:
    payload = suggestion.payload
    return (
        f"expect \"{payload['description']}\" in {category} every month, "
        f"{payload['reference_amount']} {payload['currency']} "
        f"on day {payload['expected_day']}"
    )


KINDS: dict[SuggestionKind, Kind] = {
    SuggestionKind.add_transaction: Kind(
        payload=AddTransactionPayload,
        purpose=(
            "Propose recording an Expense the user has not recorded yet. "
            "Accepting it records the Expense."
        ),
        key=_add_transaction_key,
        check=_check_add_transaction,
        apply=_apply_add_transaction,
        reads=_reads_add_transaction,
    ),
    SuggestionKind.set_budget: Kind(
        payload=SetBudgetPayload,
        purpose=(
            "Propose what one expense Category's Budget should be for a "
            "month. Accepting it sets that Budget, whether or not the month "
            "already has one."
        ),
        key=_set_budget_key,
        check=_check_set_budget,
        apply=_apply_set_budget,
        reads=_reads_set_budget,
    ),
    SuggestionKind.recategorize_transaction: Kind(
        payload=RecategorizeTransactionPayload,
        purpose=(
            "Propose filing a Transaction under a different Category, when "
            "the one it is in is plainly wrong for what it says it is. "
            "Accepting it moves the Transaction and changes nothing else."
        ),
        key=_recategorize_key,
        check=_check_recategorize,
        apply=_apply_recategorize,
        reads=_reads_recategorize,
    ),
    SuggestionKind.add_categorization_rule: Kind(
        payload=AddCategorizationRulePayload,
        purpose=(
            "Propose learning a Categorization Rule, when the same kind of "
            "description keeps arriving and the user keeps filing it by hand. "
            "Accepting it files Transactions imported from then on, and "
            "changes nothing already recorded."
        ),
        key=_add_categorization_rule_key,
        check=_check_add_categorization_rule,
        apply=_apply_add_categorization_rule,
        reads=_reads_add_categorization_rule,
    ),
    SuggestionKind.add_recurring_expense: Kind(
        payload=AddRecurringExpensePayload,
        purpose=(
            "Propose a Recurring Expense template, when the same charge "
            "arrives every month and no template covers it. Accepting it sets "
            "the template up; it records no Expense by itself, it only makes "
            "each month propose one."
        ),
        key=_add_recurring_expense_key,
        check=_check_add_recurring_expense,
        apply=_apply_add_recurring_expense,
        reads=_reads_add_recurring_expense,
    ),
}
