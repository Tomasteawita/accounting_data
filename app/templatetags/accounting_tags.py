"""
Filtros de plantilla personalizados para formateo contable argentino
(separador de miles con punto '.' y decimales con coma ',').
"""

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from django import template

register = template.Library()


@register.filter(name="ar_currency")
def ar_currency(value, decimals=2):
    """
    Formatea un monto numérico o Decimal al estándar contable argentino:
    - Separador de miles: '.'
    - Separador decimal: ','
    Ejemplo:
      1912491.32 (decimals=2) -> '1.912.491,32'
      1912491.32 (decimals=0) -> '1.912.491'
      -50000.00  (decimals=0) -> '-50.000'
    """
    try:
        dec_places = int(decimals)
    except (TypeError, ValueError):
        dec_places = 2

    try:
        num = Decimal(str(value if value is not None else "0"))
    except (InvalidOperation, TypeError, ValueError):
        num = Decimal("0")

    is_negative = num < Decimal("0")
    abs_num = abs(num)

    if dec_places <= 0:
        quantized = abs_num.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        int_part = f"{int(quantized):,}".replace(",", ".")
        formatted = int_part
    else:
        quant_str = "0." + ("0" * dec_places)
        quantized = abs_num.quantize(Decimal(quant_str), rounding=ROUND_HALF_UP)
        raw_str = f"{quantized:,.{dec_places}f}"
        int_str, frac_str = raw_str.split(".")
        int_part = int_str.replace(",", ".")
        formatted = f"{int_part},{frac_str}"

    return f"-{formatted}" if is_negative and quantized != Decimal("0") else formatted
