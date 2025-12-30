from app import create_app, db
from app.models import PresupuestoPlan, PresupuestoRegla, Movimiento, TipoCambio, Comercio
from datetime import date
from calendar import monthrange

app = create_app()
app.app_context().push()

uid = 2  # example user (adjust if needed)
plans = PresupuestoPlan.query.filter_by(user_id=uid).order_by(PresupuestoPlan.fecha_inicio).all()
print('Found plans for user', uid, len(plans))
if not plans:
    raise SystemExit(0)

earliest = min(p.fecha_inicio for p in plans)
today = date.today()
months = []
cursor = date(earliest.year, earliest.month, 1)
while cursor <= date(today.year, today.month, 1):
    months.append(cursor.strftime('%Y-%m'))
    year = cursor.year + (cursor.month // 12)
    month = (cursor.month % 12) + 1
    cursor = date(year, month, 1)

print('Months from', months[0], 'to', months[-1], '->', len(months))

for plan in plans:
    print('\nPlan:', plan.id, plan.nombre, 'start', plan.fecha_inicio)
    actuals = []
    budgets = []
    for m in months:
        y, mo = m.split('-')
        y = int(y); mo = int(mo)
        month_start = date(y, mo, 1)
        last_day = monthrange(y, mo)[1]
        month_end = date(y, mo, last_day)
        if month_start < plan.fecha_inicio:
            actuals.append(None); budgets.append(None); continue
        # actual
        total = db.session.query(db.func.sum(Movimiento.monto * TipoCambio.valor)).join(TipoCambio, TipoCambio.moneda == Movimiento.moneda).join(Comercio, Movimiento.comercio_id == Comercio.id).filter(Comercio.tipo_contabilizacion == 'gastos').filter(Movimiento.user_id == uid).filter(Movimiento.fecha >= month_start).filter(Movimiento.fecha <= month_end).scalar() or 0
        actuals.append(abs(total))
        # budget
        reglas_sum = db.session.query(db.func.sum(PresupuestoRegla.monto)).filter(PresupuestoRegla.presupuesto_id == plan.id, PresupuestoRegla.fecha_inicio <= month_start).scalar() or 0
        budgets.append(float(reglas_sum))
    print('months:', months)
    print('actuals:', actuals)
    print('budgets:', budgets)
