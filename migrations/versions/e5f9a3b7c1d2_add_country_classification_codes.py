"""add configurable country classification codes

Revision ID: e5f9a3b7c1d2
Revises: d4e8f2a3b5c6
Create Date: 2026-08-02 00:00:00.000000

"""
from alembic import op
import pycountry
import sqlalchemy as sa


revision = 'e5f9a3b7c1d2'
down_revision = 'd4e8f2a3b5c6'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'codigos_pais',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('codigo', sa.String(length=3), nullable=False),
        sa.Column('digitos', sa.Integer(), nullable=False),
        sa.Column('pais_id', sa.Integer(), nullable=False),
        sa.Column('activo', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.ForeignKeyConstraint(['pais_id'], ['paises.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('codigo'),
    )
    op.create_index('ix_codigos_pais_codigo', 'codigos_pais', ['codigo'], unique=False)
    op.create_index('ix_codigos_pais_pais_id', 'codigos_pais', ['pais_id'], unique=False)

    connection = op.get_bind()
    paises = connection.execute(sa.text('SELECT id, codigo_iso FROM paises')).mappings().all()
    rows = []
    for pais in paises:
        alpha2 = (pais['codigo_iso'] or '').upper()
        if len(alpha2) != 2:
            continue
        rows.append({
            'codigo': alpha2,
            'digitos': 2,
            'pais_id': pais['id'],
            'activo': True,
        })
        country = pycountry.countries.get(alpha_2=alpha2)
        if country and getattr(country, 'alpha_3', None):
            rows.append({
                'codigo': country.alpha_3.upper(),
                'digitos': 3,
                'pais_id': pais['id'],
                'activo': True,
            })
    connection.execute(sa.text(
        'INSERT INTO codigos_pais (codigo, digitos, pais_id, activo) '
        'VALUES (:codigo, :digitos, :pais_id, :activo)'
    ), rows)


def downgrade():
    op.drop_index('ix_codigos_pais_pais_id', table_name='codigos_pais')
    op.drop_index('ix_codigos_pais_codigo', table_name='codigos_pais')
    op.drop_table('codigos_pais')
