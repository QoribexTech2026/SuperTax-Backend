"""
Opción C (historial automático) — Fase 1: construcción del índice del periodo y
su persistencia idempotente. Los tests de unidad no tocan BD; los de integración
usan Postgres (en CI).
"""
from decimal import Decimal

from sqlalchemy import select

from src.modules.sire.infrastructure.models import PeriodClaveModel
from src.modules.sire.infrastructure.reconciliation import cruce_periodos as cruce
from src.modules.sire.infrastructure.reconciliation.cruce_periodos import _clave
from src.modules.sire.infrastructure.reconciliation.period_index import (
    construir_indice,
    escanear_indice,
)
from src.modules.sire.infrastructure.reconciliation.ple_ventas import (
    FilaPLE,
    parse_ple_ventas,
)
from src.modules.sire.infrastructure.repositories import SqlReconciliationRepository
from src.platform.tenancy.models import Company


def _linea_ple(tipo, serie, numero, numero_final="", periodo="20261000"):
    """Una línea cruda de PLE 14.1 (36 campos) con lo mínimo para las validaciones."""
    campos = [""] * 36
    campos[0], campos[1], campos[3] = periodo, "1", "01/10/2026"
    campos[5], campos[6], campos[7], campos[8] = tipo, serie, numero, numero_final
    campos[11], campos[24], campos[25], campos[26] = "RAZON", "100.00", "PEN", "1.000"
    return "|".join(campos)


def _ple_bytes(lineas) -> bytes:
    return ("\n".join(lineas) + "\n").encode("latin-1")


def _fila(tipo, serie, numero, numero_final=""):
    return FilaPLE(
        periodo="202610", cuo="1", fecha_emi=None, fecha_doc_mod=None,
        tipo=tipo, serie=serie, numero=numero, numero_final=numero_final,
        razon_social="X", base_imponible=Decimal(0), igv=Decimal(0),
        total=Decimal(0), moneda="PEN", tc=None,
    )


# ── construir_indice (unidad) ───────────────────────────────────────────
def test_construir_indice_excluye_boletas_de_claves():
    indice = construir_indice([
        _fila("01", "F201", "00005685"),
        _fila("07", "B224", "00001823"),
        _fila("03", "0889", "00000007", "00000015"),  # boleta → NO entra en claves
    ])
    claves = {tuple(c) for c in indice["claves"]}
    assert ("01", "F201", "5685") in claves
    assert ("07", "B224", "1823") in claves
    assert not any(c[0] == "03" for c in claves)


def test_construir_indice_claves_coinciden_con_el_cruce_en_memoria():
    # La normalización del índice es la MISMA que la del cruce (normalizar_clave).
    filas = [_fila("01", "f201", " 00005685 "), _fila("07", "B224", "1823")]
    claves = {tuple(c) for c in construir_indice(filas)["claves"]}
    assert claves == {_clave(f) for f in filas if f.tipo != "03"}


def test_construir_indice_serie_max_usa_numero_final_del_rango():
    serie_max = {
        (t, s): n
        for t, s, n in construir_indice([
            _fila("03", "0889", "00000007", "00000015"),   # rango → 15
            _fila("03", "0889", "00000016", "00000025"),   # rango → 25
            _fila("01", "F201", "00005685"),               # suelto → 5685
        ])["serie_max"]
    }
    assert serie_max[("03", "0889")] == 25
    assert serie_max[("01", "F201")] == 5685


def test_construir_indice_vacio():
    assert construir_indice([]) == {"claves": [], "serie_max": []}


# ── upsert_period_index (integración, BD) ───────────────────────────────
def test_upsert_period_index_idempotente_y_aislado(db_session):
    empresa = Company(ruc="20100000009", razon_social="Estudio Z")
    otra = Company(ruc="20100000010", razon_social="Otra")
    db_session.add_all([empresa, otra])
    db_session.flush()
    repo = SqlReconciliationRepository(db_session)

    repo.upsert_period_index(
        empresa.id, "ventas", "202610",
        claves=[("01", "F201", "5685"), ("07", "B224", "1823")],
        serie_max=[("01", "F201", 5685)],
    )
    assert repo.periodos_con_indice(empresa.id, "ventas") == ["202610"]

    # Re-UPSERT del mismo periodo: reemplaza, no acumula.
    repo.upsert_period_index(
        empresa.id, "ventas", "202610",
        claves=[("01", "F201", "5999")],
        serie_max=[("01", "F201", 5999)],
    )
    numeros = db_session.scalars(
        select(PeriodClaveModel.numero).where(
            PeriodClaveModel.company_id == empresa.id,
            PeriodClaveModel.periodo == "202610",
        )
    ).all()
    assert numeros == ["5999"]  # reemplazó (1 fila), no acumuló (3)

    # Otro periodo coexiste; otra empresa no ve nada (aislamiento por company_id).
    repo.upsert_period_index(
        empresa.id, "ventas", "202609",
        claves=[("01", "F100", "1")], serie_max=[],
    )
    assert repo.periodos_con_indice(empresa.id, "ventas") == ["202609", "202610"]
    assert repo.periodos_con_indice(otra.id, "ventas") == []


# ── Fase 2: equivalencia de los dos scanners y merges (unidad) ──────────
def test_escanear_indice_equivale_a_construir_indice():
    contenido = _ple_bytes([
        _linea_ple("01", "F201", "00005685"),
        _linea_ple("07", "B224", "00001823"),
        _linea_ple("03", "0889", "00000007", "00000015"),
        "linea|corta|invalida",   # < 36 campos → ignorada por ambos
        "",                       # vacía → ignorada
    ])
    por_bytes = escanear_indice(contenido)
    por_filas = construir_indice(parse_ple_ventas(contenido))
    assert sorted(map(tuple, por_bytes["claves"])) == sorted(map(tuple, por_filas["claves"]))
    assert sorted(map(tuple, por_bytes["serie_max"])) == sorted(map(tuple, por_filas["serie_max"]))


def test_merge_ultimos_toma_el_periodo_mas_reciente():
    files = {("07", "B1"): ("202608", 100)}
    store = {("07", "B1"): ("202609", 120), ("07", "B2"): ("202609", 5)}
    assert cruce.merge_ultimos(files, store) == {("07", "B1"): 120, ("07", "B2"): 5}


def test_merge_origen_une_periodos():
    files = {("01", "F1", "5"): ["202608"]}
    store = {("01", "F1", "5"): ["202609"], ("07", "B1", "3"): ["202609"]}
    r = cruce.merge_origen(files, store)
    assert r[("01", "F1", "5")] == ["202608", "202609"]
    assert r[("07", "B1", "3")] == ["202609"]


# ── Fase 2: TEST DE ORO — cruce desde BD == cruce desde archivos (BD) ────
def test_cruce_desde_store_igual_que_desde_archivos(db_session):
    empresa = Company(ruc="20100000011", razon_social="E")
    db_session.add(empresa)
    db_session.flush()
    repo = SqlReconciliationRepository(db_session)

    # Previo 202609 y actual 202610: un duplicado inter-periodo (F201-5) y un corte
    # de correlatividad (NC B1: previo llega a 10, actual arranca en 13 → faltan 11,12).
    prev = parse_ple_ventas(_ple_bytes([
        _linea_ple("01", "F201", "00000005", periodo="20260900"),
        _linea_ple("07", "B1", "00000010", periodo="20260900"),
    ]))
    actual = parse_ple_ventas(_ple_bytes([
        _linea_ple("01", "F201", "00000005"),   # duplicado vs previo
        _linea_ple("01", "F201", "00000006"),
        _linea_ple("07", "B1", "00000013"),     # corte: faltan 11, 12
    ]))
    en_periodo = cruce.claves_duplicadas_en_periodo(actual)

    # Cruce desde ARCHIVOS (Opción B).
    origen_f = cruce.claves_a_periodos([prev])
    dup_files = cruce.duplicados_con_anterior(actual, set(origen_f), en_periodo)
    cortes_files = cruce.cortes_correlatividad(actual, prev)

    # Cruce desde STORE (Opción C): se indexa el previo y se consulta.
    idx = construir_indice(prev)
    repo.upsert_period_index(empresa.id, "ventas", "202609", idx["claves"], idx["serie_max"])
    claves_actual = construir_indice(actual)["claves"]
    origen_s = {
        (t, s, n): p
        for t, s, n, p in repo.cruce_duplicidad_store(empresa.id, "ventas", "202610", claves_actual)
    }
    ultimos_s = {
        (t, s): (p, n)
        for t, s, p, n in repo.cruce_correlatividad_store(empresa.id, "ventas", "202610")
    }
    dup_store = cruce.duplicados_con_anterior(actual, set(origen_s), en_periodo)
    cortes_store = cruce.cortes_correlatividad_desde_ultimos(actual, cruce.merge_ultimos(ultimos_s))

    # Equivalencia exacta entre ambos caminos.
    def claves_de(dups):
        return sorted((d.tipo, d.serie, d.numero) for d in dups)

    def cortes_de(cortes):
        return sorted((c.tipo, c.serie, c.faltantes, c.cantidad) for c in cortes)

    assert claves_de(dup_files) == claves_de(dup_store) == [("01", "F201", "00000005")]
    assert cortes_de(cortes_files) == cortes_de(cortes_store) == [("07", "B1", "11-12", 2)]
    # El origen del store trae el periodo canónico AAAAMM.
    assert origen_s[("01", "F201", "5")] == ["202609"]
