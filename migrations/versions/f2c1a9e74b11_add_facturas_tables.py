"""add facturas tables

Revision ID: f2c1a9e74b11
Revises: eccc4c39b9a8
Create Date: 2026-03-13 15:10:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f2c1a9e74b11'
down_revision = 'eccc4c39b9a8'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'facturas',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('uuid', sa.String(length=100), nullable=False),
        sa.Column('serie', sa.String(length=50), nullable=True),
        sa.Column('numero_autorizacion', sa.String(length=100), nullable=True),
        sa.Column('tipo_documento', sa.String(length=20), nullable=True),
        sa.Column('fecha_emision', sa.DateTime(), nullable=True),
        sa.Column('fecha_certificacion', sa.DateTime(), nullable=True),
        sa.Column('moneda', sa.String(length=10), nullable=True),
        sa.Column('emisor_nit', sa.String(length=50), nullable=True),
        sa.Column('emisor_nombre', sa.String(length=255), nullable=True),
        sa.Column('receptor_id', sa.String(length=50), nullable=True),
        sa.Column('receptor_nombre', sa.String(length=255), nullable=True),
        sa.Column('gran_total', sa.Float(), nullable=True),
        sa.Column('total_impuesto_iva', sa.Float(), nullable=True),
        sa.Column('retencion_isr', sa.Float(), nullable=True),
        sa.Column('retencion_iva', sa.Float(), nullable=True),
        sa.Column('total_menos_retenciones', sa.Float(), nullable=True),
        sa.Column('archivo_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['archivo_id'], ['archivos.id']),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('uuid')
    )
    op.create_index(op.f('ix_facturas_archivo_id'), 'facturas', ['archivo_id'], unique=False)
    op.create_index(op.f('ix_facturas_user_id'), 'facturas', ['user_id'], unique=False)
    op.create_index(op.f('ix_facturas_uuid'), 'facturas', ['uuid'], unique=False)

    op.create_table(
        'facturas_detalle',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('factura_id', sa.Integer(), nullable=False),
        sa.Column('numero_linea', sa.String(length=20), nullable=True),
        sa.Column('descripcion', sa.Text(), nullable=True),
        sa.Column('cantidad', sa.Float(), nullable=True),
        sa.Column('unidad_medida', sa.String(length=20), nullable=True),
        sa.Column('precio_unitario', sa.Float(), nullable=True),
        sa.Column('total_linea', sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(['factura_id'], ['facturas.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_facturas_detalle_factura_id'), 'facturas_detalle', ['factura_id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_facturas_detalle_factura_id'), table_name='facturas_detalle')
    op.drop_table('facturas_detalle')

    op.drop_index(op.f('ix_facturas_uuid'), table_name='facturas')
    op.drop_index(op.f('ix_facturas_user_id'), table_name='facturas')
    op.drop_index(op.f('ix_facturas_archivo_id'), table_name='facturas')
    op.drop_table('facturas')
