"""the agent lookback

Revision ID: a7c31e5d9b40
Revises: d3f8a1c46b92
Create Date: 2026-09-21 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7c31e5d9b40'
down_revision: Union[str, Sequence[str], None] = 'd3f8a1c46b92'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

LOOKBACK = sa.Enum('quarter', 'year', name='agentlookback')


def upgrade() -> None:
    """Upgrade schema."""
    # How far back a Review may read. An installation that has never been asked
    # reads a quarter, which is the smaller of the two: the history that leaves
    # the app is the user's to widen, not ours to assume.
    LOOKBACK.create(op.get_bind())
    op.add_column(
        'settings',
        sa.Column(
            'agent_lookback',
            LOOKBACK,
            nullable=False,
            server_default='quarter',
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('settings', 'agent_lookback')
    LOOKBACK.drop(op.get_bind())
