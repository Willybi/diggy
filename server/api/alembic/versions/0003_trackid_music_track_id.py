"""Add trackid_music_track_id to set_tracks

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-14
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    columns = [c["name"] for c in insp.get_columns("set_tracks")]
    if "trackid_music_track_id" not in columns:
        op.add_column("set_tracks", sa.Column("trackid_music_track_id", sa.Integer, nullable=True))


def downgrade() -> None:
    op.drop_column("set_tracks", "trackid_music_track_id")
