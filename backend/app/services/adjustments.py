"""
Adjustment Rules: the arithmetic that moves a Recurring Expense's amount.

A rent contract says "every N months, by X% / by the IPC". This is that rule
read against one month: whether the adjustment falls due, which months of the
index it needs, and what the amount becomes. Nothing here touches the database
— the index values are handed in — so the whole thing is arithmetic a test can
read at a glance.

The months an index rule compounds are the N ending with the latest month that
should already be published, which is the month before the one being proposed
for. Early in the month that value is not out yet: the Suggestion still arrives
on time, saying the adjustment is pending, rather than waiting for INDEC.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date as Date
from decimal import Decimal

from app.models import AdjustmentRule
from app.models.enums import AdjustmentKind
from app.months import add_months, months_between, months_from
from app.services.money import round_money

HUNDRED = Decimal(100)


@dataclass(frozen=True)
class Adjustment:
    """What a rule does to an amount in one month, and what it did it with."""

    amount: Decimal
    # The months of the index it compounded, empty for a percentage rule.
    months: list[Date]
    # The months whose value is not published yet. While there is one, the
    # amount is the unadjusted one: a pending adjustment changes nothing.
    pending: list[Date]
    factor: Decimal | None = None

    @property
    def is_pending(self) -> bool:
        return bool(self.pending)


def is_due(rule: AdjustmentRule, month: Date) -> bool:
    """
    Whether the adjustment falls in this month.

    Counted from the month the cycle starts from, which is not itself an
    adjustment: a contract signed in January with a period of six months moves
    in July, not in January.
    """
    since = months_between(rule.start_month, month)
    return since > 0 and since % rule.period_months == 0


def index_months(rule: AdjustmentRule, month: Date) -> list[Date]:
    """The months an index rule needs to adjust `month`, empty if it needs none."""
    if rule.kind is not AdjustmentKind.index or not is_due(rule, month):
        return []
    last = add_months(month, -1)
    return months_from(add_months(last, -(rule.period_months - 1)), last)


def adjust(
    rule: AdjustmentRule | None,
    base: Decimal,
    month: Date,
    values: Mapping[Date, Decimal],
) -> Adjustment | None:
    """
    What to propose for `month`, or None when nothing is being adjusted.

    `values` is what is known of the index, in percentage points per month; a
    month missing from it is a month that is not published yet.
    """
    if rule is None or not is_due(rule, month):
        return None
    if rule.kind is AdjustmentKind.percentage:
        factor = 1 + rule.percentage / HUNDRED
        return Adjustment(
            round_money(base * factor), months=[], pending=[], factor=factor
        )

    months = index_months(rule, month)
    pending = [one for one in months if one not in values]
    if pending:
        return Adjustment(round_money(base), months=months, pending=pending)
    factor = Decimal(1)
    for one in months:
        factor *= 1 + values[one] / HUNDRED
    return Adjustment(
        round_money(base * factor), months=months, pending=[], factor=factor
    )
