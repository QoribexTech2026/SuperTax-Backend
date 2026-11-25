"""
Índice de periodo (Opción C — historial automático).

De un PLE de ventas extrae lo MÍNIMO que necesitan los cruces entre periodos (ver
`cruce_periodos`), para persistirlo y que las futuras conciliaciones crucen contra
él sin que el usuario re-suba los PLE:

  - `claves`: conjunto de (tipo, serie, número) de tipos != 03 → duplicidad.
  - `serie_max`: último número por (tipo, serie) de 01/03/07, usando el número
    final del rango si existe → correlatividad.

Dos entradas equivalentes:
  - `construir_indice(filas)`: desde las filas ya parseadas (lo usa el worker, que
    de todos modos parsea el PLE).
  - `escanear_indice(contenido)`: lectura liviana en streaming desde los bytes (lo
    usa el proceso principal, que necesita las claves sin construir todas las filas).

Ambas comparten `_acumular`, y un test de equivalencia verifica que dan lo mismo.
La normalización de la clave es la MISMA del cruce en memoria
(`cruce_periodos.normalizar_clave`), para que el cruce desde BD coincida carácter a
carácter con el cruce desde archivos.
"""
from src.modules.sire.infrastructure.reconciliation.cruce_periodos import (
    _a_entero,
    normalizar_clave,
)
from src.modules.sire.infrastructure.reconciliation.ple_ventas import (
    IDX,
    MIN_CAMPOS,
    FilaPLE,
    decodificar,
)

# Boletas (03) no entran en la duplicidad cruzada → no se indexan sus claves.
_TIPOS_EXCLUIDOS_DUP = {"03"}
# Correlatividad: facturas, boletas y notas de crédito.
_TIPOS_CORRELATIVIDAD = {"01", "03", "07"}


def _acumular(
    claves: set[tuple[str, str, str]],
    serie_max: dict[tuple[str, str], int],
    tipo: str,
    serie: str,
    numero: str,
    numero_final: str,
) -> None:
    """Suma un comprobante al índice en curso (normalizando la clave)."""
    tipo, serie, numero = normalizar_clave(tipo, serie, numero)
    if tipo not in _TIPOS_EXCLUIDOS_DUP:
        claves.add((tipo, serie, numero))
    if tipo in _TIPOS_CORRELATIVIDAD:
        n = _a_entero(numero_final) or _a_entero(numero)
        if n is not None:
            serie_max[(tipo, serie)] = max(serie_max.get((tipo, serie), n), n)


def _serializar(
    claves: set[tuple[str, str, str]], serie_max: dict[tuple[str, str], int]
) -> dict:
    """Estructura serializable (listas) para cruzar el subproceso y persistir."""
    return {
        "claves": [list(clave) for clave in claves],
        "serie_max": [[tipo, serie, n] for (tipo, serie), n in serie_max.items()],
    }


def construir_indice(filas: list[FilaPLE]) -> dict:
    """Índice del periodo desde las filas ya parseadas."""
    claves: set[tuple[str, str, str]] = set()
    serie_max: dict[tuple[str, str], int] = {}
    for fila in filas:
        _acumular(claves, serie_max, fila.tipo, fila.serie, fila.numero, fila.numero_final)
    return _serializar(claves, serie_max)


def escanear_indice(contenido: bytes) -> dict:
    """Índice del periodo leyendo los bytes del PLE en streaming (sin construir
    todas las filas). Replica el barrido de `parse_ple_ventas` para dar un resultado
    idéntico a `construir_indice(parse_ple_ventas(contenido))`."""
    claves: set[tuple[str, str, str]] = set()
    serie_max: dict[tuple[str, str], int] = {}
    for linea in decodificar(contenido).splitlines():
        if not linea.strip():
            continue
        campos = linea.split("|")
        if len(campos) < MIN_CAMPOS:
            continue
        _acumular(
            claves, serie_max,
            campos[IDX["tipo"]], campos[IDX["serie"]],
            campos[IDX["numero"]], campos[IDX["numero_final"]],
        )
    return _serializar(claves, serie_max)
