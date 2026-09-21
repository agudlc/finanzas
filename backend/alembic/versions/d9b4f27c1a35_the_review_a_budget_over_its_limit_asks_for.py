"""the review a budget over its limit asks for

Revision ID: d9b4f27c1a35
Revises: a1b7c3d05e48
Create Date: 2026-09-21 19:40:12.004518

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd9b4f27c1a35'
down_revision: Union[str, Sequence[str], None] = 'a1b7c3d05e48'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # A Budget crossing 100% is now a trigger of its own. Adding the value is
    # safe inside the migration's transaction as long as nothing here writes a
    # row with it, which nothing does.
    op.execute(
        "ALTER TYPE reviewtrigger ADD VALUE IF NOT EXISTS 'budget_exceeded'"
    )

    # The Review that looked into this Budget going over. Null until it does,
    # and on every Budget that exists today: nothing is fired retroactively,
    # so a month already over waits for the next write that touches it.
    op.add_column(
        'budgets', sa.Column('exceeded_review_id', sa.Uuid(), nullable=True)
    )
    op.create_foreign_key(
        'budgets_exceeded_review_id_fkey',
        'budgets',
        'reviews',
        ['exceeded_review_id'],
        ['id'],
    )


def downgrade() -> None:
    """
    Downgrade schema.

    The enum value stays, because Postgres cannot drop one and a Review that
    ran under it is history either way.
    """
    op.drop_constraint(
        'budgets_exceeded_review_id_fkey', 'budgets', type_='foreignkey'
    )
    op.drop_column('budgets', 'exceeded_review_id')
