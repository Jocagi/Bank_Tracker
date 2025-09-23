"""Add excluir_clasificacion to movimientos

Revision ID: a1f3d9c4b2e4
Revises: bbd021643d51
Create Date: 2025-09-23 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1f3d9c4b2e4'
down_revision = '9600d46315de'
branch_labels = None
depends_on = None


def upgrade():
    # Add column with default False
    op.add_column('movimientos', sa.Column('excluir_clasificacion', sa.Boolean(), nullable=False, server_default=sa.false()))
    # Remove server_default to rely on application defaults afterwards (optional)
    with op.get_context().autocommit_block():
        pass


def downgrade():
    op.drop_column('movimientos', 'excluir_clasificacion')
