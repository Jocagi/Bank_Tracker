"""add ultima_carga_estado_cuenta to cuentas

Revision ID: 0f4e1aa8d2b3
Revises: b7c9d4e2a610
Create Date: 2026-05-07 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0f4e1aa8d2b3'
down_revision = 'b7c9d4e2a610'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('cuentas', sa.Column('ultima_carga_estado_cuenta', sa.DateTime(), nullable=True))
    op.create_index(
        op.f('ix_cuentas_ultima_carga_estado_cuenta'),
        'cuentas',
        ['ultima_carga_estado_cuenta'],
        unique=False,
    )


def downgrade():
    op.drop_index(op.f('ix_cuentas_ultima_carga_estado_cuenta'), table_name='cuentas')
    op.drop_column('cuentas', 'ultima_carga_estado_cuenta')
