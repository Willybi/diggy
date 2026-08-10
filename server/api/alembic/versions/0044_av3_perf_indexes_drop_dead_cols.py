"""AV3 — perf indexes (Explorer composite, radar_trends, BPM backlog partial) +
drop of 4 dead columns (catalog.needs_reconciliation/status/origin, sets.platform).

Destructif : le DROP des colonnes détruit leurs données. Le downgrade recrée la
STRUCTURE (mêmes types + server_default d'origine) mais PAS les valeurs — comme
0031 (drop fingerprint/preview_url), la restauration est structurelle seulement.
"""

import sqlalchemy as sa
from alembic import op

revision = "0044"
down_revision = "0043"


def upgrade():
    # A2-01 — Explorer trie par created_at DESC puis id DESC (tie-break stable de
    # la fenêtre virtuelle). Le b-tree simple ne couvre pas le tie-break.
    op.drop_index("ix_catalog_created_at", table_name="catalog")
    op.create_index(
        "ix_catalog_created_at_id",
        "catalog",
        [sa.text("created_at DESC NULLS LAST"), sa.text("id DESC")],
    )

    # A2-02 — radar_trends : rangs par famille (radar_service.list_bi_score) et rang global.
    op.create_index(
        "ix_radar_trends_family_rank", "radar_trends", ["family", "rank_in_family"]
    )
    op.create_index("ix_radar_trends_rank_global", "radar_trends", ["rank_global"])

    # A2-07 — index partiel backlog analyse BPM (E2.c) : miroir de
    # bpm_analysis_candidate_filter(), pour l'admin Aperçu et la tâche nocturne.
    op.create_index(
        "ix_catalog_bpm_analysis_backlog",
        "catalog",
        ["id"],
        postgresql_where=sa.text(
            "has_preview AND bpm IS NULL AND bpm_analyzed_at IS NULL "
            "AND deezer_id IS NOT NULL AND deezer_id <> 'NOT_FOUND'"
        ),
    )

    # Q5 — colonnes mortes (0 reader/writer applicatif, valeur unique en prod).
    op.drop_column("catalog", "needs_reconciliation")
    op.drop_column("catalog", "status")
    op.drop_column("catalog", "origin")
    op.drop_column("sets", "platform")


def downgrade():
    # Structure only — les valeurs des 4 colonnes ne sont pas restaurées (drop destructif).
    op.add_column(
        "sets", sa.Column("platform", sa.String(32), nullable=True)
    )
    op.add_column(
        "catalog",
        sa.Column(
            "origin", sa.String(50), nullable=False, server_default="deezer"
        ),
    )
    op.add_column(
        "catalog",
        sa.Column(
            "status", sa.String(20), nullable=False, server_default="official"
        ),
    )
    op.add_column(
        "catalog",
        sa.Column(
            "needs_reconciliation", sa.Boolean(), server_default="false", nullable=True
        ),
    )

    op.drop_index("ix_catalog_bpm_analysis_backlog", table_name="catalog")
    op.drop_index("ix_radar_trends_rank_global", table_name="radar_trends")
    op.drop_index("ix_radar_trends_family_rank", table_name="radar_trends")
    op.drop_index("ix_catalog_created_at_id", table_name="catalog")
    op.create_index("ix_catalog_created_at", "catalog", ["created_at"])
