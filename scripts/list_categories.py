import sys
import os
import json

# Asegurar que el directorio raíz del proyecto esté en sys.path
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app import create_app, db
from app.models import Categoria, Subcategoria

app = create_app()
with app.app_context():
    cats = Categoria.query.order_by(Categoria.nombre).all()
    out = []
    for c in cats:
        subs = Subcategoria.query.filter_by(categoria_id=c.id).order_by(Subcategoria.nombre).all()
        out.append({"categoria": c.nombre, "subcategorias": [s.nombre for s in subs]})
    print(json.dumps(out, ensure_ascii=False, indent=2))
