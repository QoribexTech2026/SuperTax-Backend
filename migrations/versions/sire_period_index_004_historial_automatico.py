"""sire: índice de periodo para el historial automático (Opción C)

Tablas `sire.period_clave` (claves tipo+serie+número por periodo, para la
duplicidad contra meses anteriores) y `sire.serie_max` (último número por serie
por periodo, para la correlatividad). Cada conciliación de ventas persiste su
índice; las siguientes cruzan contra él en SQL sin re-subir los PLE.

Revision ID: sire_period_index_004
Revises: sire_dashboard_opt_003
Create Date: 2026-11-25 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "sire_period_index_004"
down_revision: Union[str, None] = "sire_dashboard_opt_003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "period_clave",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "company_id", sa.Integer(),
            sa.ForeignKey("core.companies.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("tipo_libro", sa.String(length=10), nullable=False),
        sa.Column("periodo", sa.String(length=6), nullable=False),
        sa.Column("tipo", sa.String(length=2), nullable=False),
        sa.Column("serie", sa.String(length=20), nullable=False),
        sa.Column("numero", sa.String(length=20), nullable=False),
        schema="sire",
    )
    op.create_index(
        "ix_period_clave_lookup", "period_clave",
        ["company_id", "tipo_libro", "tipo", "serie", "numero", "periodo"],
        schema="sire",
    )
    op.create_index(
        "ix_period_clave_periodo", "period_clave",
        ["company_id", "tipo_libro", "periodo"],
        schema="sire",
    )

    op.create_table(
        "serie_max",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "company_id", sa.Integer(),
            sa.ForeignKey("core.companies.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("tipo_libro", sa.String(length=10), nullable=False),
        sa.Column("periodo", sa.String(length=6), nullable=False),
        sa.Column("tipo", sa.String(length=2), nullable=False),
        sa.Column("serie", sa.String(length=20), nullable=False),
        sa.Column("numero_max", sa.BigInteger(), nullable=False),
        schema="sire",
    )
    op.create_index(
        "ix_serie_max_lookup", "serie_max",
        ["company_id", "tipo_libro", "tipo", "serie", "periodo"],
        schema="sire",
    )


def downgrade() -> None:
    op.drop_index("ix_serie_max_lookup", table_name="serie_max", schema="sire")
    op.drop_table("serie_max", schema="sire")
    op.drop_index("ix_period_clave_periodo", table_name="period_clave", schema="sire")
    op.drop_index("ix_period_clave_lookup", table_name="period_clave", schema="sire")
    op.drop_table("period_clave", schema="sire")
