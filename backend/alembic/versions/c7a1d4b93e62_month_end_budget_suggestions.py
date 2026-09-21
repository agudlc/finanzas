"""month-end budget suggestions

Revision ID: c7a1d4b93e62
Revises: e0a578866323
Create Date: 2026-09-21 10:12:44.118207

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c7a1d4b93e62'
down_revision: Union[str, Sequence[str], None] = 'e0a578866323'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# The partial index that makes a scheduled Review happen once a month. It names
# the triggers it covers, so a new scheduled trigger means rebuilding it.
OLD_TRIGGERS = "trigger IN ('recurring_monthly')"
NEW_TRIGGERS = "trigger IN ('recurring_monthly', 'month_end')"


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        "ALTER TYPE suggestionkind ADD VALUE IF NOT EXISTS 'set_budget'"
    )
    _rebuild_scheduled_index(OLD_TRIGGERS, NEW_TRIGGERS)


def downgrade() -> None:
    """
    Downgrade schema.

    The index only narrows, so the rows it stops covering are left alone, and
    the enum value stays because Postgres cannot drop one. Nothing is deleted:
    a migration down is not a reason to lose what a Review proposed.
    """
    _rebuild_scheduled_index(NEW_TRIGGERS, OLD_TRIGGERS)


def _rebuild_scheduled_index(was: str, becomes: str) -> None:
    op.drop_index(
        'uq_scheduled_review_per_month',
        table_name='reviews',
        postgresql_where=sa.text(was),
    )
    op.create_index(
        'uq_scheduled_review_per_month',
        'reviews',
        ['trigger', 'month'],
        unique=True,
        postgresql_where=sa.text(becomes),
    )
