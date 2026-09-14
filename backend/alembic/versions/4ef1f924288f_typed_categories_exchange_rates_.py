"""typed categories, exchange rates, installments, settings and rate snapshots

Revision ID: 4ef1f924288f
Revises: 5a5b5480bb77
Create Date: 2026-09-14 10:52:25.537617

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '4ef1f924288f'
down_revision: Union[str, Sequence[str], None] = '5a5b5480bb77'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# The enum types are named after the glossary terms they hold. The two that
# already exist are renamed below; the two new ones are created once. Every
# column reuses its type rather than re-creating it.
rate_type_enum = postgresql.ENUM(
    'official', 'blue', 'mep', 'ccl', 'card', 'manual',
    name='ratetype', create_type=False,
)
status_enum = postgresql.ENUM(
    'estimated', 'confirmed', name='confirmationstatus', create_type=False,
)
currency_enum = postgresql.ENUM('ARS', 'USD', name='currency', create_type=False)
type_enum = postgresql.ENUM('expense', 'income', name='transactiontype', create_type=False)


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    op.execute('ALTER TYPE currencyenum RENAME TO currency')
    op.execute('ALTER TYPE typeenum RENAME TO transactiontype')
    rate_type_enum.create(bind, checkfirst=True)
    status_enum.create(bind, checkfirst=True)

    op.create_table(
        'rate_snapshots',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('rate_type', rate_type_enum, nullable=False),
        sa.Column('value', sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column('fetched_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('date', 'rate_type', name='rate_snapshots_date_rate_type'),
    )
    op.create_table(
        'settings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('display_currency', currency_enum, nullable=False),
        sa.Column('default_rate_type', rate_type_enum, nullable=False),
        sa.CheckConstraint('id = 1', name='settings_single_row'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'installment_purchases',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('description', sa.String(length=250), nullable=False),
        sa.Column('total_amount', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('currency', currency_enum, nullable=False),
        sa.Column('installments', sa.Integer(), nullable=False),
        sa.Column('category_id', sa.Uuid(), nullable=False),
        sa.Column('purchase_date', sa.Date(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['category_id'], ['categories.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )

    # Existing development Categories become expense Categories; the default is
    # dropped straight away so new rows must state their type.
    op.add_column('categories', sa.Column('type', type_enum, nullable=False, server_default='expense'))
    op.alter_column('categories', 'type', server_default=None)

    op.drop_column('goals', 'current_amount')

    op.add_column('transactions', sa.Column('exchange_rate', sa.Numeric(precision=18, scale=4), nullable=True))
    op.add_column('transactions', sa.Column('exchange_rate_type', rate_type_enum, nullable=True))
    op.add_column('transactions', sa.Column('exchange_rate_status', status_enum, nullable=True))
    op.add_column('transactions', sa.Column('amount_status', status_enum, nullable=False, server_default='confirmed'))
    op.alter_column('transactions', 'amount_status', server_default=None)
    op.add_column('transactions', sa.Column('refund_of_id', sa.Uuid(), nullable=True))
    op.add_column('transactions', sa.Column('installment_purchase_id', sa.Uuid(), nullable=True))
    op.add_column('transactions', sa.Column('installment_number', sa.Integer(), nullable=True))
    op.add_column('transactions', sa.Column('import_id', sa.Uuid(), nullable=True))
    op.create_foreign_key('transactions_installment_purchase_id_fkey', 'transactions', 'installment_purchases', ['installment_purchase_id'], ['id'])
    op.create_foreign_key('transactions_refund_of_id_fkey', 'transactions', 'transactions', ['refund_of_id'], ['id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('transactions_refund_of_id_fkey', 'transactions', type_='foreignkey')
    op.drop_constraint('transactions_installment_purchase_id_fkey', 'transactions', type_='foreignkey')
    op.drop_column('transactions', 'import_id')
    op.drop_column('transactions', 'installment_number')
    op.drop_column('transactions', 'installment_purchase_id')
    op.drop_column('transactions', 'refund_of_id')
    op.drop_column('transactions', 'amount_status')
    op.drop_column('transactions', 'exchange_rate_status')
    op.drop_column('transactions', 'exchange_rate')
    op.drop_column('transactions', 'exchange_rate_type')
    op.add_column('goals', sa.Column('current_amount', sa.NUMERIC(precision=12, scale=2), nullable=False, server_default='0'))
    op.drop_column('categories', 'type')
    op.drop_table('installment_purchases')
    op.drop_table('settings')
    op.drop_table('rate_snapshots')

    bind = op.get_bind()
    status_enum.drop(bind, checkfirst=True)
    rate_type_enum.drop(bind, checkfirst=True)
    op.execute('ALTER TYPE transactiontype RENAME TO typeenum')
    op.execute('ALTER TYPE currency RENAME TO currencyenum')
