"""
Índice de periodo (Opción C — historial automático).

De las filas de un PLE de ventas ya parseado extrae lo MÍNIMO que necesitan los
cruces entre periodos (ver `cruce_periodos`), para persistirlo y que las futuras
conciliaciones crucen contra él sin que el usuario re-suba los PLE:

  - `claves`: conjunto de (tipo, serie, número) de tipos != 03 → duplicidad.
  - `serie_max`: último número por (tipo, serie) de 01/03/07, usando el número
    final del rango si existe → correlatividad.

La normalización de la clave es la MISMA que usa el cruce en memoria
(`cruce_periodos.normalizar_clave`), así el cruce desde la BD da exactamente el
mismo resultado que el cruce desde archivos (lo verifica el test de equivalencia).
"""
from src.modules.sire.infrastructure.reconciliation.cruce_periodos import (
    _a_entero,
    normalizar_clave,
)
from src.modules.sire.infrastructure.reconciliation.ple_ventas import FilaPLE

# Boletas (03) no entran en la duplicidad cruzada → no se indexan sus claves.
_TIPOS_EXCLUIDOS_DUP = {"03"}
# Correlatividad: facturas, boletas y notas de crédito.
_TIPOS_CORRELATIVIDAD = {"01", "03", "07"}


def construir_indice(filas: list[FilaPLE]) -> dict:
    """Índice serializable de un periodo listo para cruzar el subproceso y persistir.

    Devuelve ``{"claves": [[tipo, serie, numero], ...],
                "serie_max": [[tipo, serie, numero_max], ...]}`` (listas, no sets ni
    tuplas, para no depender de pickle entre procesos)."""
    claves: set[tuple[str, str, str]] = set()
    serie_max: dict[tuple[str, str], int] = {}
    for fila in filas:
        tipo, serie, numero = normalizar_clave(fila.tipo, fila.serie, fila.numero)
        if tipo not in _TIPOS_EXCLUIDOS_DUP:
            claves.add((tipo, serie, numero))
        if tipo in _TIPOS_CORRELATIVIDAD:
            n = _a_entero(fila.numero_final) or _a_entero(fila.numero)
            if n is not None:
                serie_max[(tipo, serie)] = max(serie_max.get((tipo, serie), n), n)
    return {
        "claves": [list(clave) for clave in claves],
        "serie_max": [[tipo, serie, n] for (tipo, serie), n in serie_max.items()],
    }
