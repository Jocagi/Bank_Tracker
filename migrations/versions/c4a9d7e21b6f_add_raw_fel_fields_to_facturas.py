"""add raw fel fields to facturas

Revision ID: c4a9d7e21b6f
Revises: 8e5d1f2a91c3
Create Date: 2026-03-14 11:05:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c4a9d7e21b6f'
down_revision = '8e5d1f2a91c3'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('facturas', sa.Column('datos_generales_raw', sa.Text(), nullable=True))
    op.add_column('facturas', sa.Column('emisor_raw', sa.Text(), nullable=True))
    op.add_column('facturas', sa.Column('receptor_raw', sa.Text(), nullable=True))
    op.add_column('facturas', sa.Column('certificacion_raw', sa.Text(), nullable=True))
    op.add_column('facturas', sa.Column('frases_raw', sa.Text(), nullable=True))
    op.add_column('facturas', sa.Column('totales_raw', sa.Text(), nullable=True))


def downgrade():
    op.drop_column('facturas', 'totales_raw')
    op.drop_column('facturas', 'frases_raw')
    op.drop_column('facturas', 'certificacion_raw')
    op.drop_column('facturas', 'receptor_raw')
    op.drop_column('facturas', 'emisor_raw')
    op.drop_column('facturas', 'datos_generales_raw')
