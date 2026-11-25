"""
Opción C (historial automático) — Fase 1: construcción del índice del periodo y
su persistencia idempotente. Los tests de unidad no tocan BD; los de integración
usan Postgres (en CI).
"""
from decimal import Decimal

from sqlalchemy import select

from src.modules.sire.infrastructure.models import PeriodClaveModel
from src.modules.sire.infrastructure.reconciliation.cruce_periodos import _clave
from src.modules.sire.infrastructure.reconciliation.period_index import construir_indice
from src.modules.sire.infrastructure.reconciliation.ple_ventas import FilaPLE
from src.modules.sire.infrastructure.repositories import SqlReconciliationRepository
from src.platform.tenancy.models import Company


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
