"""
The Review a Budget asks for when its spending crosses 100%.

Going over a Budget is never blocked and always shown loudly, and this is the
loud part the user does not have to be looking at the screen for: the agent is
asked what happened to that Category this month.

It happens once per Budget, whichever write got the spending there. A quick
add, an edit to something recorded weeks ago, a Refund deleted, a file loaded,
a proposal accepted — they all end in the same question, so the check hangs off
the writes rather than off any one screen, and the Budget itself remembers that
the question has been asked. Spending that is already over says nothing more:
the user has been told, and a Review per purchase after that is noise.

Only the Budgets a write actually moved are looked at, each named by the
Category and the day the money moved on. Reading the whole month instead would
make an unrelated quick add fire for every Budget that has ever been over and
never been asked about, which is a Review about nothing that just happened.

A Budget is over when its spending is past the limit, the same comparison the
screens escalate on, so the month's colour and the Review can never disagree.
"""

import uuid
from dataclasses import dataclass
from datetime import date as Date

from fastapi import Depends
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.clock import Clock, get_clock
from app.models import Budget, Review
from app.models.enums import BudgetState, ReviewTrigger
from app.months import month_of
from app.queue import ReviewQueue, get_review_queue
from app.services.budgets import budget_for, progress_of
from app.services.money import MoneyConverter, get_money_converter
from app.services.reviews import build_review

# Where a write moved money: the Category it moved in and the day it moved on.
# A write hands over one per Transaction it touched, and both sides of a move —
# a Refund taken out of a Category raises what that Category cost.
Moved = tuple[uuid.UUID, Date]


@dataclass(frozen=True)
class BudgetWatch:
    """
    What the check needs from outside the database, carried as one thing.

    Every write that moves spending ends by handing this what it moved, so a
    new write path is one line rather than three more arguments threaded down
    to it.
    """

    clock: Clock
    queue: ReviewQueue
    converter: MoneyConverter

    async def after_spending_changed(
        self, db: AsyncSession, *moved: Moved
    ) -> list[Review]:
        """Fire a Review for each of those Budgets that has just gone over."""
        fired = []
        for category_id, month in _months_of(moved):
            review = await self._if_over(db, category_id, month)
            if review is not None:
                fired.append(review)
        return fired

    async def _if_over(
        self, db: AsyncSession, category_id: uuid.UUID, month: Date
    ) -> Review | None:
        budget = await budget_for(db, category_id, month)
        if budget is None or budget.exceeded_review_id is not None:
            return None
        progress = await progress_of(db, budget, self.clock, self.converter)
        if progress.state is not BudgetState.over:
            return None
        return await self._fire(db, budget)

    async def _fire(self, db: AsyncSession, budget: Budget) -> Review | None:
        """
        Ask for the Review and hang it off the Budget, if it is still this
        write's to ask for.

        The Review and the link are written together, and the link is taken in
        one statement the way a Review is claimed to be run: two writes that
        cross the limit at the same moment both find the Budget over, and only
        the one that writes the link gets to ask. The other leaves nothing
        behind, not even the Review it was about to ask for.
        """
        review = await build_review(
            db, ReviewTrigger.budget_exceeded, budget.month
        )
        linked = await db.execute(
            update(Budget)
            .where(Budget.id == budget.id)
            .where(Budget.exceeded_review_id.is_(None))
            .values(exceeded_review_id=review.id)
            .returning(Budget.id)
        )
        if linked.scalars().first() is None:
            await db.rollback()
            return None
        await db.commit()
        await self.queue.enqueue(review.id)
        return review


def _months_of(moved: tuple[Moved, ...]) -> list[Moved]:
    """
    The Budgets to look at: one per Category and month the write touched.

    A file of two hundred rows is a handful of Categories in one or two months,
    and the same Budget is only worth reading once however many rows landed in
    it.
    """
    return sorted(
        {(category_id, month_of(day)) for category_id, day in moved},
        key=lambda pair: (pair[1], str(pair[0])),
    )


def get_budget_watch(
    clock: Clock = Depends(get_clock),
    queue: ReviewQueue = Depends(get_review_queue),
    converter: MoneyConverter = Depends(get_money_converter),
) -> BudgetWatch:
    return BudgetWatch(clock=clock, queue=queue, converter=converter)
