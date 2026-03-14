"""replace raw fel with structured fields

Revision ID: d9b2f4a7c6e1
Revises: c4a9d7e21b6f
Create Date: 2026-03-14 12:15:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd9b2f4a7c6e1'
down_revision = 'c4a9d7e21b6f'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('facturas', sa.Column('emisor_afiliacion_iva', sa.String(length=20), nullable=True))
    op.add_column('facturas', sa.Column('emisor_codigo_establecimiento', sa.String(length=20), nullable=True))
    op.add_column('facturas', sa.Column('emisor_correo', sa.String(length=255), nullable=True))
    op.add_column('facturas', sa.Column('emisor_direccion', sa.Text(), nullable=True))
    op.add_column('facturas', sa.Column('emisor_codigo_postal', sa.String(length=20), nullable=True))
    op.add_column('facturas', sa.Column('emisor_municipio', sa.String(length=100), nullable=True))
    op.add_column('facturas', sa.Column('emisor_departamento', sa.String(length=100), nullable=True))
    op.add_column('facturas', sa.Column('emisor_pais', sa.String(length=5), nullable=True))

    op.add_column('facturas', sa.Column('receptor_correo', sa.String(length=255), nullable=True))
    op.add_column('facturas', sa.Column('receptor_direccion', sa.Text(), nullable=True))
    op.add_column('facturas', sa.Column('receptor_codigo_postal', sa.String(length=20), nullable=True))
    op.add_column('facturas', sa.Column('receptor_municipio', sa.String(length=100), nullable=True))
    op.add_column('facturas', sa.Column('receptor_departamento', sa.String(length=100), nullable=True))
    op.add_column('facturas', sa.Column('receptor_pais', sa.String(length=5), nullable=True))

    op.add_column('facturas', sa.Column('nit_certificador', sa.String(length=50), nullable=True))
    op.add_column('facturas', sa.Column('nombre_certificador', sa.String(length=255), nullable=True))
    op.add_column('facturas', sa.Column('frases_resumen', sa.Text(), nullable=True))
    op.add_column('facturas', sa.Column('total_impuestos_monto', sa.Float(), nullable=True))

    op.drop_column('facturas', 'totales_raw')
    op.drop_column('facturas', 'frases_raw')
    op.drop_column('facturas', 'certificacion_raw')
    op.drop_column('facturas', 'receptor_raw')
    op.drop_column('facturas', 'emisor_raw')
    op.drop_column('facturas', 'datos_generales_raw')


def downgrade():
    op.add_column('facturas', sa.Column('datos_generales_raw', sa.Text(), nullable=True))
    op.add_column('facturas', sa.Column('emisor_raw', sa.Text(), nullable=True))
    op.add_column('facturas', sa.Column('receptor_raw', sa.Text(), nullable=True))
    op.add_column('facturas', sa.Column('certificacion_raw', sa.Text(), nullable=True))
    op.add_column('facturas', sa.Column('frases_raw', sa.Text(), nullable=True))
    op.add_column('facturas', sa.Column('totales_raw', sa.Text(), nullable=True))

    op.drop_column('facturas', 'total_impuestos_monto')
    op.drop_column('facturas', 'frases_resumen')
    op.drop_column('facturas', 'nombre_certificador')
    op.drop_column('facturas', 'nit_certificador')
    op.drop_column('facturas', 'receptor_pais')
    op.drop_column('facturas', 'receptor_departamento')
    op.drop_column('facturas', 'receptor_municipio')
    op.drop_column('facturas', 'receptor_codigo_postal')
    op.drop_column('facturas', 'receptor_direccion')
    op.drop_column('facturas', 'receptor_correo')
    op.drop_column('facturas', 'emisor_pais')
    op.drop_column('facturas', 'emisor_departamento')
    op.drop_column('facturas', 'emisor_municipio')
    op.drop_column('facturas', 'emisor_codigo_postal')
    op.drop_column('facturas', 'emisor_direccion')
    op.drop_column('facturas', 'emisor_correo')
    op.drop_column('facturas', 'emisor_codigo_establecimiento')
    op.drop_column('facturas', 'emisor_afiliacion_iva')
