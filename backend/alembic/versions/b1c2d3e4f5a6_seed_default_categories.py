"""seed the default categories and the settings record

Revision ID: b1c2d3e4f5a6
Revises: 4ef1f924288f
Create Date: 2026-09-14 11:05:00.000000

"""
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b1c2d3e4f5a6'
down_revision: Union[str, Sequence[str], None] = '4ef1f924288f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# The Categories a fresh installation ships with. The user may rename, recolor
# or delete any of them like any other Category.
DEFAULT_CATEGORIES = [
    ("Supermercado", "expense", "#22C55E"),
    ("Delivery", "expense", "#F97316"),
    ("Alquiler", "expense", "#6366F1"),
    ("Servicios", "expense", "#0EA5E9"),
    ("Transporte", "expense", "#14B8A6"),
    ("Salud", "expense", "#EF4444"),
    ("Suscripciones", "expense", "#A855F7"),
    ("Ocio", "expense", "#EC4899"),
    ("Ropa", "expense", "#F59E0B"),
    ("Educación", "expense", "#3B82F6"),
    ("Impuestos", "expense", "#64748B"),
    ("Otros", "expense", "#94A3B8"),
    ("Sueldo", "income", "#16A34A"),
    ("Freelance", "income", "#0D9488"),
    ("Rendimientos", "income", "#65A30D"),
    ("Otros", "income", "#94A3B8"),
]

settings = sa.table(
    "settings",
    sa.column("id", sa.Integer),
    sa.column("display_currency", sa.Enum(name="currency")),
    sa.column("default_rate_type", sa.Enum(name="ratetype")),
)

categories = sa.table(
    "categories",
    sa.column("id", sa.Uuid),
    sa.column("name", sa.String),
    sa.column("color", sa.String),
    sa.column("icon", sa.String),
    sa.column("is_default", sa.Boolean),
    sa.column("type", sa.Enum(name="transactiontype")),
)


def upgrade() -> None:
    op.bulk_insert(
        categories,
        [
            {
                "id": uuid.uuid4(),
                "name": name,
                "color": color,
                "icon": None,
                "is_default": True,
                "type": category_type,
            }
            for name, category_type, color in DEFAULT_CATEGORIES
        ],
    )
    # The single Settings record: ARS is shown by default, and estimates use
    # the card rate.
    op.bulk_insert(
        settings,
        [{"id": 1, "display_currency": "ARS", "default_rate_type": "card"}],
    )


def downgrade() -> None:
    op.execute(settings.delete())
    op.execute(categories.delete().where(categories.c.is_default.is_(True)))
