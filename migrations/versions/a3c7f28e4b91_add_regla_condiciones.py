"""add regla_condiciones for flexible rule matching

Revision ID: a3c7f28e4b91
Revises: e5f9a3b7c1d2
Create Date: 2026-10-24 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a3c7f28e4b91'
down_revision = 'e5f9a3b7c1d2'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'regla_condiciones',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('regla_id', sa.Integer(), nullable=False),
        sa.Column('orden', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('conector', sa.String(length=3), nullable=False, server_default='AND'),
        sa.Column('negar', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('campo', sa.String(length=30), nullable=False),
        sa.Column('operador', sa.String(length=20), nullable=False),
        sa.Column('valor', sa.String(length=200), nullable=True),
        sa.Column('valor2', sa.String(length=200), nullable=True),
        sa.ForeignKeyConstraint(['regla_id'], ['reglas.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_regla_condiciones_regla_id'), 'regla_condiciones', ['regla_id'], unique=False)

    # Migrar cada regla existente (criterio + comodín/'=') a una condición
    # equivalente sobre el campo 'descripcion', preservando el comportamiento.
    bind = op.get_bind()
    reglas = bind.execute(sa.text('SELECT id, criterio FROM reglas')).fetchall()
    for regla_id, criterio in reglas:
        raw = (criterio or '').strip()
        if raw.startswith('='):
            operador = 'igual'
            valor = raw[1:].strip()
        else:
            operador = 'comodin'
            valor = raw
        bind.execute(
            sa.text(
                "INSERT INTO regla_condiciones "
                "(regla_id, orden, conector, negar, campo, operador, valor, valor2) "
                "VALUES (:regla_id, 0, 'AND', 0, 'descripcion', :operador, :valor, NULL)"
            ),
            {'regla_id': regla_id, 'operador': operador, 'valor': valor},
        )

    op.drop_column('reglas', 'criterio')


def downgrade():
    op.add_column('reglas', sa.Column('criterio', sa.String(length=200), nullable=True))

    bind = op.get_bind()
    condiciones = bind.execute(
        sa.text(
            "SELECT regla_id, operador, valor FROM regla_condiciones "
            "WHERE campo = 'descripcion' ORDER BY regla_id, orden"
        )
    ).fetchall()
    vistos = set()
    for regla_id, operador, valor in condiciones:
        if regla_id in vistos:
            continue
        vistos.add(regla_id)
        if operador == 'igual':
            criterio = f"={valor or ''}"
        else:
            criterio = valor or ''
        bind.execute(
            sa.text('UPDATE reglas SET criterio = :criterio WHERE id = :regla_id'),
            {'criterio': criterio, 'regla_id': regla_id},
        )

    bind.execute(sa.text("UPDATE reglas SET criterio = '' WHERE criterio IS NULL"))
    op.alter_column('reglas', 'criterio', nullable=False)
    op.drop_table('regla_condiciones')
