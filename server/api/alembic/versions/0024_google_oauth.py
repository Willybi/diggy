"""Replace email/password auth with Google OAuth.

Drop hashed_password, add google_id + picture_url.
Purge existing users (cascade deletes dependents).
"""
import sqlalchemy as sa
from alembic import op

revision = "0024"
down_revision = "0023"


def upgrade():
    # Purge existing users — FK CASCADE handles dependents
    op.execute("DELETE FROM users")

    op.drop_column("users", "hashed_password")
    op.add_column("users", sa.Column("google_id", sa.String(255), nullable=False))
    op.create_unique_constraint("uq_users_google_id", "users", ["google_id"])
    op.add_column("users", sa.Column("picture_url", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("users", "picture_url")
    op.drop_constraint("uq_users_google_id", "users", type_="unique")
    op.drop_column("users", "google_id")
    op.add_column(
        "users",
        sa.Column("hashed_password", sa.Text(), nullable=False, server_default=""),
    )
