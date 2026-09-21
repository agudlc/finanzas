"""the agent proposes a rule and a template

Revision ID: c5d9e1f37a20
Revises: b4e7c2a19d83
Create Date: 2026-09-21 15:02:44.118902

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'c5d9e1f37a20'
down_revision: Union[str, Sequence[str], None] = 'b4e7c2a19d83'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        "ALTER TYPE suggestionkind "
        "ADD VALUE IF NOT EXISTS 'add_categorization_rule'"
    )
    op.execute(
        "ALTER TYPE suggestionkind "
        "ADD VALUE IF NOT EXISTS 'add_recurring_expense'"
    )


def downgrade() -> None:
    """
    Downgrade schema.

    The values stay, because Postgres cannot drop one, and the Suggestions
    already proposed under them stay with them: a migration down is not a
    reason to lose what a Review proposed.
    """
