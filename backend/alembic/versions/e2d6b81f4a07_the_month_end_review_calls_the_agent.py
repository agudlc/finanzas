"""the month-end review calls the agent

Revision ID: e2d6b81f4a07
Revises: d9b4f27c1a35
Create Date: 2026-09-21 21:05:33.512904

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e2d6b81f4a07'
down_revision: Union[str, Sequence[str], None] = 'd9b4f27c1a35'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# The partial index that makes a scheduled Review happen once a month. The
# triggers it covers do not change here; what it is keyed by does.
SCHEDULED = "trigger IN ('recurring_monthly', 'month_end')"

WAS = ['trigger', 'month']
BECOMES = ['trigger', 'month', 'used_agent']


def upgrade() -> None:
    """
    Upgrade schema.

    The month-end Review now calls the model, and when it cannot, a second one
    of the same trigger runs the arithmetic instead. Those are two rows for one
    month, so `used_agent` joins the key: still once each, never two of either.
    """
    _rekey(BECOMES)


def downgrade() -> None:
    """
    Downgrade schema.

    Narrowing the key back can find a month that already has both rows, which
    is a month whose agent Review failed. The failed one is what goes: nothing
    a Review proposed is lost by it, because a run that failed rolled back
    everything it had, and the arithmetic row beside it is the one the user is
    actually holding proposals from.
    """
    op.execute(
        sa.text(
            "DELETE FROM reviews a WHERE a.used_agent AND a.trigger = 'month_end'"
            " AND EXISTS (SELECT 1 FROM reviews b WHERE b.trigger = a.trigger"
            " AND b.month = a.month AND NOT b.used_agent)"
        )
    )
    _rekey(WAS)


def _rekey(columns: list[str]) -> None:
    op.drop_index(
        'uq_scheduled_review_per_month',
        table_name='reviews',
        postgresql_where=sa.text(SCHEDULED),
    )
    op.create_index(
        'uq_scheduled_review_per_month',
        'reviews',
        columns,
        unique=True,
        postgresql_where=sa.text(SCHEDULED),
    )
