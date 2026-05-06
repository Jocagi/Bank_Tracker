"""add activa and saldo to cuentas

Revision ID: b7c9d4e2a610
Revises: c1e7d2a4f901
Create Date: 2026-05-05 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b7c9d4e2a610'
down_revision = 'c1e7d2a4f901'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('cuentas', schema=None) as batch_op:
        batch_op.add_column(sa.Column('activa', sa.Boolean(), nullable=False, server_default=sa.text('1')))
        batch_op.add_column(sa.Column('saldo', sa.Float(), nullable=False, server_default=sa.text('0')))


def downgrade():
    with op.batch_alter_table('cuentas', schema=None) as batch_op:
        batch_op.drop_column('saldo')
        batch_op.drop_column('activa')