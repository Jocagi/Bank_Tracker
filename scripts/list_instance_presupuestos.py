import sqlite3
from pathlib import Path

db = Path(__file__).resolve().parents[1] / 'instance' / 'movimientos.db'
if not db.exists():
    print('Instance DB not found at', db)
    raise SystemExit(1)

conn = sqlite3.connect(str(db))
cur = conn.cursor()

print('DB:', db)
print('\nPresupuesto Plans:')
for row in cur.execute('SELECT id, user_id, nombre, fecha_inicio, active, created_at FROM presupuesto_planes ORDER BY id'):
    print(row)

print('\nPresupuesto Reglas (sample):')
for row in cur.execute('SELECT id, presupuesto_id, user_id, categoria_id, tipo, monto, fecha_inicio, created_at FROM presupuestos ORDER BY id'):
    print(row)

conn.close()
