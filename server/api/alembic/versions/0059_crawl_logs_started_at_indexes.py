"""crawl_logs_started_at_indexes — index started_at + (task_type, started_at).

The admin monitoring endpoint filters crawl_logs by ``started_at >= since``
(a seq scan — the table keeps ~13 months of logs) and looks up the latest run
per ``task_type`` (a sort the lone task_type index cannot serve). Two indexes:
plain ``started_at`` for the window filter, composite ``(task_type,
started_at)`` for the per-task latest-run lookup. Names match what the model
declarations generate (``index=True`` → ix_crawl_logs_started_at; the
composite is named explicitly in ``__table_args__``). The pre-existing
mono-column task_type index is left in place.
"""

from alembic import op

revision = "0059"
down_revision = "0058"


def upgrade():
    op.create_index("ix_crawl_logs_started_at", "crawl_logs", ["started_at"])
    op.create_index(
        "ix_crawl_logs_task_type_started_at",
        "crawl_logs",
        ["task_type", "started_at"],
    )


def downgrade():
    op.drop_index("ix_crawl_logs_task_type_started_at", table_name="crawl_logs")
    op.drop_index("ix_crawl_logs_started_at", table_name="crawl_logs")
