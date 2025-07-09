from datetime import datetime
from . import db


class Categoria(db.Model):
    __tablename__ = 'categorias'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False, unique=True)
    comercios = db.relationship('Comercio', backref='categoria', lazy=True)

class Comercio(db.Model):
    __tablename__ = 'comercios'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False, unique=True)
    categoria_id = db.Column(db.Integer, db.ForeignKey('categorias.id'), nullable=False)
    tipo_contabilizacion = db.Column(db.String(20), nullable=False, default='gastos') # Indica si es ingreso, gasto o transferencia
    reglas = db.relationship('Regla', backref='comercio', lazy=True)

class Regla(db.Model):
    __tablename__ = 'reglas'
    id = db.Column(db.Integer, primary_key=True)
    comercio_id = db.Column(db.Integer, db.ForeignKey('comercios.id'), nullable=False)
    descripcion = db.Column(db.String(200), nullable=False)
    tipo = db.Column(db.String(50), nullable=False)  # 'incluir' o 'excluir'
    criterio = db.Column(db.String(200), nullable=False)  # Regex o texto a buscar

class Movimiento(db.Model):
    __tablename__ = 'movimientos'
    id = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.Date)
    cuenta_id = db.Column(db.Integer, db.ForeignKey('cuentas.id'), nullable=False)
    descripcion = db.Column(db.String(200))
    lugar = db.Column(db.String(200), nullable=True)
    numero_documento = db.Column(db.String(100), nullable=True)
    monto = db.Column(db.Float)
    moneda = db.Column(db.String(10))
    tipo = db.Column(db.String(10))  # 'debito' o 'credito'
    archivo_id = db.Column(db.Integer, db.ForeignKey('archivos.id'), nullable=False)
    comercio_id = db.Column(db.Integer, db.ForeignKey('comercios.id'), nullable=True)
    # Relaciones
    comercio = db.relationship(
        'Comercio',
        backref=db.backref('movimientos', lazy=True),
        foreign_keys=[comercio_id]
    )
    cuenta   = db.relationship(
        'Cuenta',
        backref=db.backref('movimientos', lazy=True),
        foreign_keys=[cuenta_id]
    )
    archivo  = db.relationship(
        'Archivo',
        backref=db.backref('movimientos', lazy=True),
        foreign_keys=[archivo_id]
    )

class Cuenta(db.Model):
    __tablename__ = 'cuentas'
    id = db.Column(db.Integer, primary_key=True)
    banco = db.Column(db.String(50), nullable=False)
    tipo_cuenta = db.Column(db.String(50), nullable=False)
    numero_cuenta = db.Column(db.String(100), nullable=False, unique=True)
    titular = db.Column(db.String(200), nullable=False)
    moneda = db.Column(db.String(10), nullable=False)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)

class Archivo(db.Model):
    __tablename__ = 'archivos'
    id = db.Column(db.Integer, primary_key=True)
    tipo_archivo = db.Column(db.String(50), nullable=False)
    filename = db.Column(db.String(200), nullable=False)
    upload_date = db.Column(db.DateTime, default=datetime.utcnow)
    file_hash = db.Column(db.String(64), unique=True, nullable=False)

class TipoCambio(db.Model):
    __tablename__ = 'tipos_cambio'
    id         = db.Column(db.Integer, primary_key=True)
    moneda     = db.Column(db.String(10), nullable=False, unique=True)  # p.e. "USD", "EUR"
    valor      = db.Column(db.Float,    nullable=False)                 # cuántos GTQ vale 1 unidad de esta moneda
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

