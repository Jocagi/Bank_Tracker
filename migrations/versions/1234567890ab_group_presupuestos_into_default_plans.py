"""group existing presupuesto reglas into per-user Default plans

Revision ID: 1234567890ab
Revises: 00e56665d3ad
Create Date: 2025-11-09 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from datetime import date, datetime


# revision identifiers, used by Alembic.
revision = '1234567890ab'
down_revision = '00e56665d3ad'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    conn = bind

    # Find distinct user_ids that have presupuesto reglas
    result = conn.execute(sa.text("SELECT DISTINCT user_id FROM presupuestos WHERE user_id IS NOT NULL"))
    users = [r[0] for r in result.fetchall()]

    for uid in users:
        # Check if a Default plan already exists for this user
        existing = conn.execute(sa.text("SELECT id FROM presupuesto_planes WHERE user_id = :uid AND nombre = :name LIMIT 1"), {"uid": uid, "name": "Default"}).fetchone()
        if existing:
            plan_id = existing[0]
        else:
            # determine a sensible fecha_inicio: earliest regla fecha_inicio for that user or first day of current month
            r = conn.execute(sa.text("SELECT MIN(fecha_inicio) FROM presupuestos WHERE user_id = :uid"), {"uid": uid}).fetchone()
            min_date = r[0]
            if min_date is None:
                today = date.today()
                min_date = date(today.year, today.month, 1).isoformat()
            else:
                # If the returned value is a date/datetime, convert to isoformat string; otherwise assume it's already a string
                try:
                    min_date = min_date.isoformat()
                except Exception:
                    min_date = str(min_date)

            # Insert Default plan for user
            conn.execute(sa.text(
                "INSERT INTO presupuesto_planes (user_id, nombre, fecha_inicio, active, created_at) VALUES (:uid, :name, :fecha_inicio, :active, :created_at)"
            ), {"uid": uid, "name": "Default", "fecha_inicio": min_date, "active": 1, "created_at": datetime.utcnow().isoformat()})

            # Fetch the plan id we just created
            plan_id = conn.execute(sa.text("SELECT id FROM presupuesto_planes WHERE user_id = :uid AND nombre = :name ORDER BY id DESC LIMIT 1"), {"uid": uid, "name": "Default"}).fetchone()[0]

        # Assign existing reglas for this user to the Default plan if not already assigned
        conn.execute(sa.text("UPDATE presupuestos SET presupuesto_id = :plan_id WHERE user_id = :uid AND (presupuesto_id IS NULL)"), {"plan_id": plan_id, "uid": uid})


def downgrade():
    bind = op.get_bind()
    conn = bind

    # For safety on downgrade: unassign presupuesto_id for reglas pointing to plans named 'Default' and remove those plans
    plans = conn.execute(sa.text("SELECT id FROM presupuesto_planes WHERE nombre = :name"), {"name": "Default"}).fetchall()
    plan_ids = [p[0] for p in plans]

    for pid in plan_ids:
        conn.execute(sa.text("UPDATE presupuestos SET presupuesto_id = NULL WHERE presupuesto_id = :pid"), {"pid": pid})
        conn.execute(sa.text("DELETE FROM presupuesto_planes WHERE id = :pid"), {"pid": pid})
