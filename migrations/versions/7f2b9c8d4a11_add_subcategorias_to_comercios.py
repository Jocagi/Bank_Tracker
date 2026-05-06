"""add subcategorias to comercios

Revision ID: 7f2b9c8d4a11
Revises: eccc4c39b9a8
Create Date: 2026-05-05 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '7f2b9c8d4a11'
down_revision = 'eccc4c39b9a8'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'subcategorias',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('nombre', sa.String(length=100), nullable=False),
        sa.Column('categoria_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['categoria_id'], ['categorias.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('categoria_id', 'nombre', name='uq_subcategoria_categoria_nombre')
    )

    with op.batch_alter_table('comercios', schema=None) as batch_op:
        batch_op.add_column(sa.Column('subcategoria_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_comercios_subcategoria_id_subcategorias', 'subcategorias', ['subcategoria_id'], ['id'], ondelete='SET NULL')


def downgrade():
    with op.batch_alter_table('comercios', schema=None) as batch_op:
        batch_op.drop_constraint('fk_comercios_subcategoria_id_subcategorias', type_='foreignkey')
        batch_op.drop_column('subcategoria_id')

    op.drop_table('subcategorias')