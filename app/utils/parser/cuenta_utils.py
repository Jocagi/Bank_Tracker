import re
from ... import db
from ...models import Cuenta, CuentaNumero
from sqlalchemy.exc import IntegrityError


def get_or_create_cuenta(archivo_obj, preferred_tipo=None, create=True):
    """Localiza una `Cuenta` existente usando número principal o números alternativos.

    Flujo:
    1. Intentar `Cuenta.find_by_numero(archivo_obj.numero_cuenta)` (usa CuentaNumero internamente).
    2. Validar que la cuenta encontrada pertenezca al mismo banco y tipo (o empiece por el tipo).
    3. Si no hay match, buscar por versión "limpia" (sin caracteres) entre cuentas del mismo banco/tipo.
    4. Si no hay cuenta y `create` es True -> crear la cuenta, proteger contra IntegrityError y reintentar buscar.

    Retorna la instancia `Cuenta` o None.
    """
    numero = (getattr(archivo_obj, 'numero_cuenta', '') or '').strip()
    tipo = (getattr(archivo_obj, 'tipo_cuenta', '') or '')
    banco = getattr(archivo_obj, 'banco', None)

    # 1) Intentar match por número (incluye números alternativos mediante el helper del modelo)
    cuenta = None
    if numero:
        try:
            cuenta = Cuenta.find_by_numero(numero)
        except Exception:
            cuenta = None

    # 2) Validar banco/tipo
    if cuenta:
        try:
            if banco and cuenta.banco != banco:
                cuenta = None
            elif tipo and not (cuenta.tipo_cuenta or '').startswith(tipo):
                cuenta = None
        except Exception:
            cuenta = None

    # 3) Buscar por versión limpia entre cuentas del mismo banco/tipo
    if not cuenta and numero:
        numero_clean = re.sub(r"[^A-Za-z0-9]", "", numero)
        if numero_clean:
            q = Cuenta.query
            if banco:
                q = q.filter(Cuenta.banco == banco)
            if tipo:
                q = q.filter(Cuenta.tipo_cuenta.like(f"{tipo}%"))
            posibles = q.all()
            for pc in posibles:
                try:
                    if re.sub(r"[^A-Za-z0-9]", "", (pc.numero_cuenta or '')) == numero_clean:
                        cuenta = pc
                        break
                except Exception:
                    continue

    # 4) Crear si está permitido
    if not cuenta and create:
        nueva = Cuenta(
            banco=banco,
            tipo_cuenta=tipo or preferred_tipo or '',
            numero_cuenta=numero,
            titular=getattr(archivo_obj, 'titular', None),
            moneda=getattr(archivo_obj, 'moneda', None)
        )
        if getattr(archivo_obj, 'user_id', None) is not None:
            nueva.user_id = archivo_obj.user_id
        db.session.add(nueva)
        try:
            db.session.commit()
            return nueva
        except IntegrityError:
            db.session.rollback()
            # Otro proceso pudo crear la cuenta; intentar recuperar por numero
            if numero:
                cuenta = Cuenta.query.filter_by(numero_cuenta=numero).first()
            # último recurso: volver a intentar la búsqueda limpia
            if not cuenta and numero:
                numero_clean = re.sub(r"[^A-Za-z0-9]", "", numero)
                q = Cuenta.query
                if banco:
                    q = q.filter(Cuenta.banco == banco)
                if tipo:
                    q = q.filter(Cuenta.tipo_cuenta.like(f"{tipo}%"))
                posibles = q.all()
                for pc in posibles:
                    try:
                        if re.sub(r"[^A-Za-z0-9]", "", (pc.numero_cuenta or '')) == numero_clean:
                            cuenta = pc
                            break
                    except Exception:
                        continue

    return cuenta
