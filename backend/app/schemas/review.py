import uuid
from datetime import date as Date
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.enums import (
    Currency,
    ReviewStatus,
    ReviewTrigger,
    SuggestionKind,
    SuggestionStatus,
)


class ReviewResponse(BaseModel):
    id: uuid.UUID
    trigger: ReviewTrigger
    # The month the run is about, stored as its first day. A scheduled Review
    # happens once per month; a manual one is about the month it was asked in.
    month: Date
    status: ReviewStatus
    used_agent: bool
    error: str | None
    note: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None

    model_config = {"from_attributes": True}


class ReviewSummary(ReviewResponse):
    """
    One Review in the history: how the run went, and what it cost.

    The tokens are here and the transcript is not. Two numbers are what the
    list is for — a run that cost ten times the others is worth opening — and
    the exchange itself is megabytes nobody reads a page of.
    """

    input_tokens: int | None
    output_tokens: int | None


class AddTransactionPayload(BaseModel):
    """
    What an `add_transaction` Suggestion would record.

    This is the kind's schema, and accepting goes through it: the payload, with
    whatever the user edited merged over it, is checked against this before
    anything is recorded, so an edited proposal can be no looser than a proposed
    one. Anything it does not name is not a field of this kind.
    """

    description: str = Field(
        min_length=1,
        max_length=250,
        description="What the Expense is, as it would read in the list.",
    )
    category_id: uuid.UUID = Field(
        description="The expense Category it goes in."
    )
    currency: Currency = Field(description="ARS or USD.")
    amount: Decimal = Field(gt=0, description="How much, as a positive figure.")
    date: Date = Field(description='The day it falls on, written "YYYY-MM-DD".')
    is_fixed: bool = Field(
        default=False,
        description="Whether the user would call this Expense unavoidable.",
    )
    # Which Recurring Expense this came from. Null is a proposal from somewhere
    # else, which is what one made by the agent rather than by a template is.
    recurring_expense_id: uuid.UUID | None = Field(
        default=None,
        description=(
            "The Recurring Expense this is the month's payment of, if it is "
            "one. Omit it otherwise."
        ),
    )

    model_config = {"extra": "forbid"}


class SetBudgetPayload(BaseModel):
    """
    What a `set_budget` Suggestion would set.

    The month is the one the Budget is for, stored as its first day like every
    other month in the app. Accepting sets that Category's Budget whether or
    not the month's copy already made one, so "there is one already" is the
    case this kind exists for, not an error.
    """

    category_id: uuid.UUID = Field(
        description="The expense Category whose Budget this is."
    )
    month: Date = Field(
        description='The month the Budget is for, as its first day: "2026-03-01".'
    )
    amount: Decimal = Field(gt=0, description="The limit, as a positive figure.")
    currency: Currency = Field(description="ARS or USD.")

    model_config = {"extra": "forbid"}


class RecategorizeTransactionPayload(BaseModel):
    """
    What a `recategorize_transaction` Suggestion would move.

    The smallest kind there is: one Transaction, one Category to file it under
    instead. Nothing else about the Transaction changes, and the Category has
    to be of the Transaction's own type — an Expense cannot be filed under an
    income Category — which is checked when it is proposed and again when it is
    accepted, because the user may have edited it in between.
    """

    transaction_id: uuid.UUID = Field(
        description="The Transaction that is filed in the wrong Category."
    )
    category_id: uuid.UUID = Field(
        description=(
            "The Category it should be in instead, of the same type as the "
            "Transaction: an expense Category for an Expense."
        )
    )

    model_config = {"extra": "forbid"}


class AddCategorizationRulePayload(BaseModel):
    """
    What an `add_categorization_rule` Suggestion would learn.

    A rule is "description contains this -> that Category" and nothing else.
    Accepting one changes no Transaction already recorded: a rule only applies
    to what an Import brings in after it exists, and a Transaction already
    filed in the wrong place is a recategorization, which is its own kind
    (ADR-0004).
    """

    pattern: str = Field(
        min_length=1,
        max_length=250,
        description=(
            "The text to look for in an imported Transaction's description. "
            "Case does not matter, and the longest matching pattern wins, so "
            'prefer the merchant over a word it shares: "mercado libre" '
            'rather than "mercado".'
        ),
    )
    category_id: uuid.UUID = Field(
        description=(
            "The Category those Transactions should go in, of the type they "
            "are: an expense Category for Expenses."
        )
    )

    model_config = {"extra": "forbid"}


class AddRecurringExpensePayload(BaseModel):
    """
    What an `add_recurring_expense` Suggestion would set up.

    The template's own fields, and not its Adjustment Rule: how a rent moves
    every six months is written in a contract the agent has never read, and a
    template the user accepts can be given a rule afterwards like any other.
    The template records nothing by itself — each month it produces a
    Suggestion — so accepting this proposes rather than spends.
    """

    description: str = Field(
        min_length=1,
        max_length=250,
        description="What the Expense is, as it would read every month.",
    )
    category_id: uuid.UUID = Field(
        description="The expense Category its payments go in."
    )
    currency: Currency = Field(description="ARS or USD.")
    reference_amount: Decimal = Field(
        gt=0,
        description=(
            "What to expect it to cost, until a payment of its own says "
            "otherwise."
        ),
    )
    expected_day: int = Field(
        ge=1, le=31, description="The day of the month it falls on."
    )
    is_fixed: bool = Field(
        default=False,
        description="Whether the user would call this Expense unavoidable.",
    )

    model_config = {"extra": "forbid"}


class SuggestionResponse(BaseModel):
    """
    What is being proposed, and why — and, once resolved, what came of it.

    The payload is left as the kind wrote it: the Inbox reads it to show what
    would change, and accepting it validates it against the kind again.
    """

    id: uuid.UUID
    review_id: uuid.UUID
    kind: SuggestionKind
    month: Date
    payload: dict
    rationale: str
    status: SuggestionStatus
    rejection_reason: str | None
    # What accepting it created, e.g. the Transaction.
    result_id: uuid.UUID | None
    expires_on: Date
    resolved_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class PossibleMatch(BaseModel):
    """
    A Transaction that may already be the payment a Suggestion proposes.

    Enough of it to recognise the payment and no more: the Inbox shows it so
    the user can tell "that is the rent, already recorded" from "that is
    something else that happens to cost the same".
    """

    id: uuid.UUID
    description: str | None
    amount: Decimal
    currency: Currency
    date: Date

    model_config = {"from_attributes": True}


class InboxSuggestion(SuggestionResponse):
    """
    A pending proposal as the Inbox hands it over, with its Possible Match.

    Only the Inbox answers this, because the match is about the Transactions of
    the moment it was read; accepting and rejecting hand back the proposal
    alone. It is a hint either way: the proposal is pending whether or not one
    was found.
    """

    possible_match: PossibleMatch | None = None


class SuggestionAccept(BaseModel):
    """
    "Sí, pero así": the fields of the payload the user changed, if any.

    Only what is given is changed, so a client that only moved the amount does
    not have to send the rest back.
    """

    payload: dict | None = None


class SuggestionReject(BaseModel):
    """"No este mes", and optionally why."""

    reason: str | None = Field(default=None, max_length=250)


class InsightResponse(BaseModel):
    """
    A read-only observation, as the Inbox hands it over.

    There is nothing to accept: the only thing the user does with one is read
    it and say so, which is what `dismissed_at` records.
    """

    id: uuid.UUID
    review_id: uuid.UUID
    # The month it is about, stored as its first day.
    month: Date
    topic: str
    body: str
    dismissed_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ReviewDetail(ReviewSummary):
    """
    One Review read in full: the whole exchange, and what came out of it.

    This is the only place the transcript is served, because it is the only
    question it answers — a Suggestion that reads oddly or an Insight that
    seems to come from nowhere can be traced to the turn that produced it.
    The proposals are here whatever became of them, and so are the Insights
    whatever month it is now: this is history, not the Inbox. All of the
    agent's own fields are null on a deterministic Review, which talked to
    nobody.
    """

    transcript: list | None
    prompt_version: str | None
    suggestions: list[SuggestionResponse]
    insights: list[InsightResponse]


class Inbox(BaseModel):
    """Everything the Inbox screen needs in one read."""

    suggestions: list[InboxSuggestion]
    pending_count: int
    # This month's observations the user has not dismissed. An Insight from an
    # earlier month is history, so it is not here however undismissed it is.
    insights: list[InsightResponse]
    # The Reviews queued or running right now, so the screen can say "buscando"
    # and poll faster until they finish.
    reviews: list[ReviewResponse]
