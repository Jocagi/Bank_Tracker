"""add logos to categorias and subcategorias

Revision ID: b8f6e2d3c5a1
Revises: a7e5c1d2b904
Create Date: 2026-08-02 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'b8f6e2d3c5a1'
down_revision = 'a7e5c1d2b904'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('categorias', sa.Column('logo_filename', sa.String(length=255), nullable=True))
    op.add_column('subcategorias', sa.Column('logo_filename', sa.String(length=255), nullable=True))


def downgrade():
    op.drop_column('subcategorias', 'logo_filename')
    op.drop_column('categorias', 'logo_filename')
