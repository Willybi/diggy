"""Explorer FIX (D6 p.1) — one-off cleanup of leading/trailing whitespace in
catalog title/artist (spaces, tabs, newlines) that polluted the A–Z sort."""

from alembic import op

revision = "0040"
down_revision = "0039"


def upgrade():
    # btrim strips the given character set from both ends (PG). We trim spaces AND
    # tabs/newlines/form-feeds/vertical-tabs, which func.trim() alone cannot remove.
    # Idempotent + cheap: the WHERE guard only touches rows that actually change.
    op.execute(
        r"UPDATE catalog SET title = btrim(title, E' \t\n\r\f\v') "
        r"WHERE title IS NOT NULL AND title <> btrim(title, E' \t\n\r\f\v')"
    )
    op.execute(
        r"UPDATE catalog SET artist = btrim(artist, E' \t\n\r\f\v') "
        r"WHERE artist IS NOT NULL AND artist <> btrim(artist, E' \t\n\r\f\v')"
    )


def downgrade():
    # No-op: a whitespace trim is not reversible (the original padding is lost).
    pass
