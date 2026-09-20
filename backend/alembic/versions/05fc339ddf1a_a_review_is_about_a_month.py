"""a review is about a month

Revision ID: 05fc339ddf1a
Revises: 08132dafd8be
Create Date: 2026-09-20 18:09:18.804035

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '05fc339ddf1a'
down_revision: Union[str, Sequence[str], None] = '08132dafd8be'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # A Review already run was about the month it ran in, read in Buenos Aires
    # because that is the day the user was living.
    op.add_column('reviews', sa.Column('month', sa.Date(), nullable=True))
    op.execute(
        "UPDATE reviews SET month = date_trunc('month', "
        "created_at AT TIME ZONE 'America/Argentina/Buenos_Aires')"
    )
    op.alter_column('reviews', 'month', nullable=False)
    # One scheduled Review per trigger per month, decided by the database: a
    # cron and an Inbox read can both find the month missing its Review.
    op.create_index(
        'uq_scheduled_review_per_month',
        'reviews',
        ['trigger', 'month'],
        unique=True,
        postgresql_where=sa.text("trigger IN ('recurring_monthly')"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        'uq_scheduled_review_per_month',
        table_name='reviews',
        postgresql_where=sa.text("trigger IN ('recurring_monthly')"),
    )
    op.drop_column('reviews', 'month')
