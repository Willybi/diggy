"""Add genre_nodes, genre_edges, genre_mappings tables for taxonomy."""
import sqlalchemy as sa
from alembic import op

revision = "0019"
down_revision = "0018"


def upgrade():
    op.create_table(
        "genre_nodes",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("wikidata_id", sa.String(64), unique=True, nullable=False),
        sa.Column("label", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_genre_nodes_label", "genre_nodes", ["label"])

    op.create_table(
        "genre_edges",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("from_node_id", sa.Integer, sa.ForeignKey("genre_nodes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("to_node_id", sa.Integer, sa.ForeignKey("genre_nodes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", sa.String(20), nullable=False),
        sa.Column("source", sa.String(50), nullable=False),
        sa.UniqueConstraint("from_node_id", "to_node_id", "type", name="uq_genre_edge"),
    )
    op.create_index("ix_genre_edges_from", "genre_edges", ["from_node_id"])
    op.create_index("ix_genre_edges_to", "genre_edges", ["to_node_id"])

    op.create_table(
        "genre_mappings",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("raw_name", sa.String(255), unique=True, nullable=False),
        sa.Column("node_id", sa.Integer, sa.ForeignKey("genre_nodes.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_genre_mappings_node_id", "genre_mappings", ["node_id"])


def downgrade():
    op.drop_table("genre_mappings")
    op.drop_table("genre_edges")
    op.drop_table("genre_nodes")
