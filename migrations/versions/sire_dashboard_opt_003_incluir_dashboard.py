"""sire: dashboard opcional en el reporte

Columna `incluir_dashboard` en reconciliation_jobs: el usuario decide al cargar si
el reporte incluye la hoja «Dashboard». NOT NULL con default true, así los jobs
existentes conservan el comportamiento actual (dashboard incluido).

Revision ID: sire_dashboard_opt_003
Revises: sire_prev_files_002
Create Date: 2026-11-23 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "sire_dashboard_opt_003"
down_revision: Union[str, None] = "sire_prev_files_002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "reconciliation_jobs",
        sa.Column("incluir_dashboard", sa.Boolean(), nullable=False, server_default=sa.true()),
        schema="sire",
    )


def downgrade() -> None:
    op.drop_column("reconciliation_jobs", "incluir_dashboard", schema="sire")
