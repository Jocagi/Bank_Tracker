"""add flags to countries

Revision ID: d4e8f2a3b5c6
Revises: c9d7e1f2a3b4
Create Date: 2026-08-02 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'd4e8f2a3b5c6'
down_revision = 'c9d7e1f2a3b4'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('paises', sa.Column('logo_filename', sa.String(length=255), nullable=True))


def downgrade():
    op.drop_column('paises', 'logo_filename')