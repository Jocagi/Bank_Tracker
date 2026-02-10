"""Add excluir_dashboard to movimientos

Revision ID: 6d3f9b0b2c7a
Revises: 2b7f9e4d8c12
Create Date: 2026-02-10 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '6d3f9b0b2c7a'
down_revision = '2b7f9e4d8c12'
branch_labels = None
depends_on = None


def upgrade():
    # Add column with default False
    op.add_column(
        'movimientos',
        sa.Column('excluir_dashboard', sa.Boolean(), nullable=False, server_default=sa.false())
    )
    # Remove server_default to rely on application defaults afterwards (optional)
    with op.get_context().autocommit_block():
        pass


def downgrade():
    op.drop_column('movimientos', 'excluir_dashboard')
