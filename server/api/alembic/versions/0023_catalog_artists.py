"""Add catalog_artists many-to-many table + backfill from catalog.artist strings."""
import re

import sqlalchemy as sa
from alembic import op

revision = "0023"
down_revision = "0022"

FEAT_RE = re.compile(r"\s+(?:feat\.?|featuring|ft\.?|vs\.?)\s+", flags=re.IGNORECASE)


def _normalize(s: str) -> str:
    s = (s or "").lower().strip()
    s = s.replace("\u2019", "'").replace("\u2018", "'")
    s = re.sub(r"\bft\.", "ft", s)
    s = re.sub(r"\bfeat\.", "feat", s)
    return s


def upgrade():
    op.create_table(
        "catalog_artists",
        sa.Column("catalog_id", sa.Integer, sa.ForeignKey("catalog.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("artist_id", sa.Integer, sa.ForeignKey("artists.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("role", sa.String(32), nullable=True),
        sa.Column("position", sa.Integer, nullable=True),
    )
    op.create_index("ix_catalog_artists_artist_id", "catalog_artists", ["artist_id"])

    # --- Backfill from existing data ---
    conn = op.get_bind()

    # Load all artists (normalized_name -> id)
    artist_rows = conn.execute(sa.text("SELECT id, normalized_name FROM artists")).fetchall()
    artists_by_norm = {row[1]: row[0] for row in artist_rows}

    # Load all aliases (normalized_alias -> artist_id)
    alias_rows = conn.execute(sa.text("SELECT normalized_alias, artist_id FROM artist_aliases")).fetchall()
    for row in alias_rows:
        if row[0] not in artists_by_norm:
            artists_by_norm[row[0]] = row[1]

    # Load all catalog entries
    catalog_rows = conn.execute(sa.text("SELECT id, artist FROM catalog WHERE artist IS NOT NULL")).fetchall()

    def _lookup(name):
        norm = _normalize(name)
        return artists_by_norm.get(norm)

    links = []
    seen = set()

    for cat_id, raw_artist in catalog_rows:
        if not raw_artist or not raw_artist.strip():
            continue

        raw = raw_artist.strip()
        parts = []

        if FEAT_RE.search(raw):
            tokens = [p.strip() for p in FEAT_RE.split(raw) if p.strip()]
            for i, token in enumerate(tokens):
                parts.append((token, "primary" if i == 0 else "featured", i))
        elif "," in raw:
            tokens = [p.strip() for p in raw.split(",") if p.strip()]
            for i, token in enumerate(tokens):
                parts.append((token, "primary", i))
        elif " & " in raw:
            tokens = [p.strip() for p in raw.split(" & ") if p.strip()]
            for i, token in enumerate(tokens):
                parts.append((token, "primary", i))
        else:
            parts.append((raw, "primary", 0))

        for name, role, position in parts:
            artist_id = _lookup(name)
            if artist_id and (cat_id, artist_id) not in seen:
                links.append({"catalog_id": cat_id, "artist_id": artist_id, "role": role, "position": position})
                seen.add((cat_id, artist_id))

    if links:
        # Batch insert
        batch_size = 500
        for i in range(0, len(links), batch_size):
            batch = links[i:i + batch_size]
            conn.execute(
                sa.text(
                    "INSERT INTO catalog_artists (catalog_id, artist_id, role, position) "
                    "VALUES (:catalog_id, :artist_id, :role, :position) "
                    "ON CONFLICT DO NOTHING"
                ),
                batch,
            )


def downgrade():
    op.drop_table("catalog_artists")
