"""a review of what an import brought in

Revision ID: a1b7c3d05e48
Revises: c5d9e1f37a20
Create Date: 2026-09-21 18:20:05.118431

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b7c3d05e48'
down_revision: Union[str, Sequence[str], None] = 'c5d9e1f37a20'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Confirming an Import is now a trigger of its own. Adding the value is
    # safe inside the migration's transaction as long as nothing here writes a
    # row with it, which nothing does.
    op.execute(
        "ALTER TYPE reviewtrigger ADD VALUE IF NOT EXISTS 'import_finished'"
    )

    # When the run may begin. Null on every Review that starts as soon as the
    # worker reaches it, which is all of them but this one.
    op.add_column(
        'reviews',
        sa.Column('start_after', sa.DateTime(timezone=True), nullable=True),
    )

    # The Review an Import is waiting for. Several Imports confirmed close
    # together point at the same one.
    op.add_column('imports', sa.Column('review_id', sa.Uuid(), nullable=True))
    op.create_foreign_key(
        'imports_review_id_fkey', 'imports', 'reviews', ['review_id'], ['id']
    )


def downgrade() -> None:
    """
    Downgrade schema.

    The enum value stays, because Postgres cannot drop one and a Review that
    ran under it is history either way.
    """
    op.drop_constraint('imports_review_id_fkey', 'imports', type_='foreignkey')
    op.drop_column('imports', 'review_id')
    op.drop_column('reviews', 'start_after')
