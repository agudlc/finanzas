"""the agent review and its insights

Revision ID: d3f8a1c46b92
Revises: c7a1d4b93e62
Create Date: 2026-09-21 16:03:11.402118

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'd3f8a1c46b92'
down_revision: Union[str, Sequence[str], None] = 'c7a1d4b93e62'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # "Revisar ahora" now asks for two Reviews, and this is the agent's half.
    # Adding the value is safe inside the migration's transaction as long as
    # nothing here writes a row with it, which nothing does.
    op.execute(
        "ALTER TYPE reviewtrigger ADD VALUE IF NOT EXISTS 'manual_agent'"
    )

    # What the agent run was. Null on a deterministic Review: there was nobody
    # to talk to, so there is no transcript and nothing was spent.
    op.add_column(
        'reviews',
        sa.Column('transcript', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column('reviews', sa.Column('input_tokens', sa.Integer(), nullable=True))
    op.add_column('reviews', sa.Column('output_tokens', sa.Integer(), nullable=True))
    op.add_column(
        'reviews', sa.Column('prompt_version', sa.String(length=50), nullable=True)
    )

    op.create_table(
        'insights',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('review_id', sa.Uuid(), nullable=False),
        sa.Column('month', sa.Date(), nullable=False),
        sa.Column('topic', sa.String(length=100), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('dismissed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['review_id'], ['reviews.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    # The Inbox asks for one month's Insights on every read, and so does the
    # brief for the two months before it.
    op.create_index('ix_insights_month', 'insights', ['month'])


def downgrade() -> None:
    """
    Downgrade schema.

    The Insights go, because the table does; the enum value stays, because
    Postgres cannot drop one and a Review that ran is history either way.
    """
    op.drop_index('ix_insights_month', table_name='insights')
    op.drop_table('insights')
    op.drop_column('reviews', 'prompt_version')
    op.drop_column('reviews', 'output_tokens')
    op.drop_column('reviews', 'input_tokens')
    op.drop_column('reviews', 'transcript')
