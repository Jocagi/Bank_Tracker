import sqlite3
from pathlib import Path

root_db = Path(__file__).resolve().parents[1] / 'movimientos.db'
instance_db = Path(__file__).resolve().parents[1] / 'instance' / 'movimientos.db'

def check(dbpath):
    if not dbpath.exists():
        print('Database file not found at', dbpath)
        return
    conn = sqlite3.connect(str(dbpath))
    cur = conn.cursor()
    def safe_count(query):
        try:
            return cur.execute(query).fetchone()[0]
        except Exception as e:
            return 'ERROR: ' + str(e)

    print('\nDatabase:', dbpath)
    print('presupuesto_planes count ->', safe_count('SELECT COUNT(*) FROM presupuesto_planes'))
    print('presupuestos total        ->', safe_count('SELECT COUNT(*) FROM presupuestos'))
    print('presupuestos assigned     ->', safe_count('SELECT COUNT(*) FROM presupuestos WHERE presupuesto_id IS NOT NULL'))
    conn.close()

check(root_db)
check(instance_db)

