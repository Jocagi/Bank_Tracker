"""add logo to comercios

Revision ID: a7e5c1d2b904
Revises: 0f4e1aa8d2b3
Create Date: 2026-08-02 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'a7e5c1d2b904'
down_revision = '0f4e1aa8d2b3'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('comercios', sa.Column('logo_filename', sa.String(length=255), nullable=True))


def downgrade():
    op.drop_column('comercios', 'logo_filename')
