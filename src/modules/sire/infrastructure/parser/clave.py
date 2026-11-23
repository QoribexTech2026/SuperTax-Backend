"""
Llave de emparejamiento de comprobantes para el cruce empresa ↔ SUNAT.

La clave por defecto es (RUC, tipo, serie, número). Excepción: las DUA (tipo 50)
se cruzan SIN RUC, porque en el archivo de la empresa figura el RUC del operador
logístico y en la propuesta de SUNAT el del proveedor real; serie + número
identifican el documento y el IGV se valida aparte con su tolerancia. Así una DUA
que coincide en todo salvo el RUC deja de observarse como "solo en tu archivo".

Única fuente de verdad: EmpresaRecord y SunatRecord construyen su llave aquí, para
que ambos lados del cruce no puedan divergir.
"""

# Tipos cuyo RUC en el archivo no es el del emisor real → se cruzan sin RUC.
_TIPOS_SIN_RUC = {"50"}


def clave_comprobante(ruc: str, tipo: str, serie: str, numero: str) -> tuple:
    """(RUC, tipo, serie, número) normalizados; sin RUC para los tipos de `_TIPOS_SIN_RUC`."""
    t = str(tipo).strip().upper()
    s = str(serie).strip().upper()
    n = str(numero).strip().lstrip("0") or "0"
    r = "" if t in _TIPOS_SIN_RUC else str(ruc).strip()
    return (r, t, s, n)
