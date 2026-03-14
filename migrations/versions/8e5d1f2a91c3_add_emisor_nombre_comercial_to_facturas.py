"""add emisor_nombre_comercial to facturas

Revision ID: 8e5d1f2a91c3
Revises: f2c1a9e74b11
Create Date: 2026-03-14 10:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '8e5d1f2a91c3'
down_revision = 'f2c1a9e74b11'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('facturas', sa.Column('emisor_nombre_comercial', sa.String(length=255), nullable=True))


def downgrade():
    op.drop_column('facturas', 'emisor_nombre_comercial')
