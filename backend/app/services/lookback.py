"""
How far back a Review is allowed to read.

The brief is about one month, but the agent can ask for more, and how much
more is the user's call: everything a tool hands over is a description of the
user's money on its way to Anthropic, so the limit is a Setting rather than a
number we chose. A quarter means the month under review and the two before it,
a year that month and the eleven before it.

Everything that reads history for the agent asks here for the floor, and
nothing below it is fetched: the brief clamps its own windows to it, and a tool
asked for an older month answers with the limit instead of the rows.
"""

from datetime import date as Date

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import LOOKBACK_MONTHS, AgentLookback
from app.months import add_months, month_of
from app.services.settings import get_settings


def earliest_month(month: Date, lookback: AgentLookback) -> Date:
    """The oldest month a Review about `month` may read, as its first day."""
    return add_months(month_of(month), -(LOOKBACK_MONTHS[lookback] - 1))


async def earliest_month_for(db: AsyncSession, month: Date) -> Date:
    """The same floor, for a Review that has only the month in hand."""
    return earliest_month(month, (await get_settings(db)).agent_lookback)
