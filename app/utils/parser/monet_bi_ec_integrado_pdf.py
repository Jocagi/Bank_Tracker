"""
Parser para estado de cuenta monetaria BI (formato EC integrado en PDF).

Características del formato:
- Cabecera por página con mes (ej. "ENERO - 23" o "FEBRERO 2023").
- Cabecera con número de cuenta (ej. "185-007460-8").
- Detalle por línea con columnas: Día, Documento, Descripción, Débito, Crédito, Saldo.
"""

from __future__ import annotations

import calendar
import re
from datetime import datetime

import pdfplumber

from ... import db
from ...models import Movimiento
from .cuenta_utils import get_or_create_cuenta


_MESES = {
    "ENERO": 1,
    "FEBRERO": 2,
    "MARZO": 3,
    "ABRIL": 4,
    "MAYO": 5,
    "JUNIO": 6,
    "JULIO": 7,
    "AGOSTO": 8,
    "SEPTIEMBRE": 9,
    "OCTUBRE": 10,
    "NOVIEMBRE": 11,
    "DICIEMBRE": 12,
}

_MONTH_RE = re.compile(
    r"DEL\s+MES\s+DE\s+([A-ZÁÉÍÓÚ]+)\s*-?\s*(\d{2,4})?",
    re.IGNORECASE,
)
_ACCOUNT_RE = re.compile(r"N[ÚU]MERO\s+DE\s+CUENTA\s+(\d{3}-\d{6}-\d)", re.IGNORECASE)
_SALDO_ANTERIOR_RE = re.compile(r"SALDO\s+ANTERIOR.*?(\d{1,3}(?:,\d{3})*\.\d{2})$", re.IGNORECASE)
_TX_RE = re.compile(
    r"^(?P<dia>\d{1,2})\s+"
    r"(?P<doc>\d+)\s+"
    r"(?P<desc>.+?)\s+"
    r"(?P<debito>\d{1,3}(?:,\d{3})*\.\d{2})\s+"
    r"(?P<credito>\d{1,3}(?:,\d{3})*\.\d{2})\s+"
    r"(?P<saldo>\d{1,3}(?:,\d{3})*\.\d{2})$"
)


def _to_year(year_text: str | None) -> int | None:
    if not year_text:
        return None
    raw = int(year_text)
    if len(year_text) == 2:
        return 2000 + raw if raw <= 50 else 1900 + raw
    return raw


def _to_float(amount_text: str) -> float:
    return float(amount_text.replace(",", ""))


def load_movements_monet_bi_ec_integrado_pdf(filepath, archivo_obj):
    with pdfplumber.open(filepath) as pdf:
        page_texts = [page.extract_text() or "" for page in pdf.pages]

    if not any(page_texts):
        raise ValueError("No se pudo extraer texto del PDF")

    titular = "TITULAR NO IDENTIFICADO"
    numero_cuenta = None
    current_month = None
    current_year = None

    # Extraer metadata recorriendo cabeceras de páginas.
    for text in page_texts:
        lines = text.split("\n")
        for line in lines[:8]:
            m_month = _MONTH_RE.search(line)
            if m_month:
                month_name = m_month.group(1).upper()
                parsed_month = _MESES.get(month_name)
                parsed_year = _to_year(m_month.group(2))
                if parsed_month:
                    current_month = parsed_month
                if parsed_year:
                    current_year = parsed_year

            m_account = _ACCOUNT_RE.search(line)
            if m_account:
                numero_cuenta = m_account.group(1)
                possible_name = line[: m_account.start()].strip()
                if possible_name:
                    titular = possible_name

    if not numero_cuenta:
        raise ValueError("No se pudo extraer el número de cuenta del PDF")

    if not current_month or not current_year:
        today = datetime.now()
        current_month = current_month or today.month
        current_year = current_year or today.year

    archivo_obj.banco = "BI"
    archivo_obj.tipo_cuenta = "MONET"
    archivo_obj.numero_cuenta = numero_cuenta
    archivo_obj.titular = titular
    archivo_obj.moneda = "GTQ"
    db.session.commit()

    cuenta = get_or_create_cuenta(archivo_obj)

    count = 0
    prev_balance = None

    # Parsear páginas en orden para respetar secuencia de saldos y cambios de mes.
    for text in page_texts:
        lines = text.split("\n")

        for line in lines[:8]:
            m_month = _MONTH_RE.search(line)
            if m_month:
                month_name = m_month.group(1).upper()
                parsed_month = _MESES.get(month_name)
                parsed_year = _to_year(m_month.group(2))
                if parsed_month:
                    current_month = parsed_month
                if parsed_year:
                    current_year = parsed_year

        for raw_line in lines:
            line = raw_line.strip()
            if not line:
                continue

            m_saldo_anterior = _SALDO_ANTERIOR_RE.search(line)
            if m_saldo_anterior:
                prev_balance = _to_float(m_saldo_anterior.group(1))
                continue

            m_tx = _TX_RE.match(line)
            if not m_tx:
                continue

            dia = int(m_tx.group("dia"))
            numero_doc = m_tx.group("doc")
            descripcion = m_tx.group("desc").strip()
            debito = _to_float(m_tx.group("debito"))
            credito = _to_float(m_tx.group("credito"))
            saldo = _to_float(m_tx.group("saldo"))

            if credito > 0 and debito == 0:
                tipo = "credito"
                monto = credito
            elif debito > 0 and credito == 0:
                tipo = "debito"
                monto = -debito
            elif prev_balance is not None:
                if saldo > prev_balance:
                    tipo = "credito"
                    monto = credito if credito > 0 else abs(saldo - prev_balance)
                else:
                    tipo = "debito"
                    monto = -(debito if debito > 0 else abs(saldo - prev_balance))
            else:
                tipo = "debito"
                monto = -debito if debito > 0 else -abs(credito)

            last_day = calendar.monthrange(current_year, current_month)[1]
            fecha = datetime(current_year, current_month, min(dia, last_day)).date()

            mov = Movimiento(
                fecha=fecha,
                descripcion=descripcion,
                lugar=None,
                numero_documento=numero_doc,
                monto=monto,
                moneda="GTQ",
                tipo=tipo,
                cuenta_id=cuenta.id,
                archivo_id=archivo_obj.id,
            )

            if getattr(archivo_obj, "user_id", None) is not None:
                mov.user_id = archivo_obj.user_id

            db.session.add(mov)
            count += 1
            prev_balance = saldo

    db.session.commit()
    return count
