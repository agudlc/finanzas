"""the agent proposes a recategorization

Revision ID: b4e7c2a19d83
Revises: a7c31e5d9b40
Create Date: 2026-09-21 12:40:11.503118

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'b4e7c2a19d83'
down_revision: Union[str, Sequence[str], None] = 'a7c31e5d9b40'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        "ALTER TYPE suggestionkind "
        "ADD VALUE IF NOT EXISTS 'recategorize_transaction'"
    )


def downgrade() -> None:
    """
    Downgrade schema.

    The value stays, because Postgres cannot drop one, and the Suggestions
    already proposed under it stay with it: a migration down is not a reason to
    lose what a Review proposed.
    """
