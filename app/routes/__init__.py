from flask import Blueprint

bp = Blueprint('main', __name__)

# Import submodules so their routes are registered on the blueprint
from . import index, upload, comercios, categorias, sin_clasificar, archivos, tipos_cambio, dashboard, data_tools, cuentas, users, presupuestos
