import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Sync URL: strip +asyncpg (same pattern as Celery tasks)
db_url = os.environ["DATABASE_URL"].replace("+asyncpg", "")

import models  # noqa: E402 — registers all tables on Base.metadata

target_metadata = models.Base.metadata

# Indexes created via raw SQL in a migration (not declared on any model) — they
# must be excluded from autogenerate comparison or it would emit a spurious
# drop_index. The pgvector HNSW index (0049) lives here because SQLite, which
# backs the test schema via create_all, cannot build it.
_AUTOGEN_SKIP_INDEXES = {"ix_track_embeddings_hnsw"}


def include_object(obj, name, type_, reflected, compare_to):
    if type_ == "index" and name in _AUTOGEN_SKIP_INDEXES:
        return False
    return True


def run_migrations_offline():
    context.configure(
        url=db_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    connectable = create_engine(db_url, poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
