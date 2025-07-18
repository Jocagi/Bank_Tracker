"""Initial migration

Revision ID: bbd021643d51
Revises: 
Create Date: 2025-07-07 14:45:12.409885

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'bbd021643d51'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('archivos',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tipo_archivo', sa.String(length=50), nullable=False),
    sa.Column('filename', sa.String(length=200), nullable=False),
    sa.Column('upload_date', sa.DateTime(), nullable=True),
    sa.Column('file_hash', sa.String(length=64), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('file_hash')
    )
    op.create_table('categorias',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('nombre', sa.String(length=100), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('nombre')
    )
    op.create_table('cuentas',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('banco', sa.String(length=50), nullable=False),
    sa.Column('tipo_cuenta', sa.String(length=50), nullable=False),
    sa.Column('numero_cuenta', sa.String(length=100), nullable=False),
    sa.Column('titular', sa.String(length=200), nullable=False),
    sa.Column('moneda', sa.String(length=10), nullable=False),
    sa.Column('fecha_creacion', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('numero_cuenta')
    )
    op.create_table('comercios',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('nombre', sa.String(length=100), nullable=False),
    sa.Column('categoria_id', sa.Integer(), nullable=False),
    sa.Column('tipo_contabilizacion', sa.String(length=20), nullable=False),
    sa.ForeignKeyConstraint(['categoria_id'], ['categorias.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('nombre')
    )
    op.create_table('movimientos',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('fecha', sa.Date(), nullable=True),
    sa.Column('cuenta_id', sa.Integer(), nullable=False),
    sa.Column('descripcion', sa.String(length=200), nullable=True),
    sa.Column('lugar', sa.String(length=200), nullable=True),
    sa.Column('numero_documento', sa.String(length=100), nullable=True),
    sa.Column('monto', sa.Float(), nullable=True),
    sa.Column('moneda', sa.String(length=10), nullable=True),
    sa.Column('tipo', sa.String(length=10), nullable=True),
    sa.Column('archivo_id', sa.Integer(), nullable=False),
    sa.Column('comercio_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['archivo_id'], ['archivos.id'], ),
    sa.ForeignKeyConstraint(['comercio_id'], ['comercios.id'], ),
    sa.ForeignKeyConstraint(['cuenta_id'], ['cuentas.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('reglas',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('comercio_id', sa.Integer(), nullable=False),
    sa.Column('descripcion', sa.String(length=200), nullable=False),
    sa.Column('tipo', sa.String(length=50), nullable=False),
    sa.Column('criterio', sa.String(length=200), nullable=False),
    sa.ForeignKeyConstraint(['comercio_id'], ['comercios.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('reglas')
    op.drop_table('movimientos')
    op.drop_table('comercios')
    op.drop_table('cuentas')
    op.drop_table('categorias')
    op.drop_table('archivos')
    # ### end Alembic commands ###
