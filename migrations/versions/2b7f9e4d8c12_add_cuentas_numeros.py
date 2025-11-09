"""Add cuentas_numeros table

Revision ID: 2b7f9e4d8c12
Revises: 1cf63fe5ea2c
Create Date: 2025-11-08 23:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '2b7f9e4d8c12'
down_revision = '1cf63fe5ea2c'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'cuentas_numeros',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('cuenta_id', sa.Integer(), sa.ForeignKey('cuentas.id'), nullable=False, index=True),
        sa.Column('numero', sa.String(length=100), nullable=False, index=True),
    )


def downgrade():
    op.drop_table('cuentas_numeros')
