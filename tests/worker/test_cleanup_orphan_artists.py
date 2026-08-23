"""Tests for the OPS orphan-artist cleanup (scripts/cleanup_orphan_artists).

Exercises the selection predicate + the run() engine pass against a real sync
SQLite session (``sync_session`` fixture): an orphan is deletable ONLY when NO
catalog / set / follow / activity / album row references it, and --apply deletes
exactly those (dry-run deletes nothing). MinIO is out of scope here (--keep-artwork);
boto3 is stubbed by the worker conftest anyway.

Same import/path pattern as test_cleanup_artists.py.
"""
import os
import sys

import pytest
from sqlalchemy import func, select

_SERVER_PATH = os.path.join(os.path.dirname(__file__), "../../server")
if _SERVER_PATH not in sys.path:
    sys.path.insert(0, _SERVER_PATH)

import scripts.cleanup_orphan_artists as mod  # noqa: E402
from models import (  # noqa: E402
    Album,
    Artist,
    ArtistActivity,
    CatalogArtist,
    CatalogEntry,
    FollowedArtist,
    SetArtist,
)
from scripts.cleanup_orphan_artists import run, select_orphan_batch  # noqa: E402
from utils import normalize  # noqa: E402


def _artist(session, name, **kw):
    a = Artist(name=name, normalized_name=normalize(name), **kw)
    session.add(a)
    session.commit()
    return a


@pytest.fixture
def seeded(sync_engine, sync_session):
    """Build the eight-artist scenario; point the script's global engine at the
    fixture engine so run() operates on this in-memory DB."""
    s = sync_session
    orphan_null = _artist(s, "Orphan Null")
    orphan_linked = _artist(s, "Orphan Linked", deezer_id="123", has_artwork=True)
    orphan_notfound = _artist(s, "Orphan NF", deezer_id="NOT_FOUND")

    a_cat = _artist(s, "Has Catalog")
    entry = CatalogEntry(title="T", artist="x", normalized_key="nk-1")
    s.add(entry)
    s.commit()
    s.add(CatalogArtist(catalog_id=entry.id, artist_id=a_cat.id, role="primary", position=0))

    a_set = _artist(s, "Has Set")
    s.add(SetArtist(set_id=1, artist_id=a_set.id, role="primary", position=0))

    a_follow = _artist(s, "Followed")
    s.add(FollowedArtist(user_id=1, artist_id=a_follow.id))

    a_act = _artist(s, "Has Activity")
    s.add(
        ArtistActivity(
            artist_id=a_act.id, activity_type="release", source="deezer", external_id="e1"
        )
    )

    a_album = _artist(s, "Backs Album")
    s.add(Album(title="An Album", artist_id=a_album.id))
    s.commit()

    mod._engine = sync_engine  # run() reads this global instead of DATABASE_URL
    yield {
        "orphans": {orphan_null.id, orphan_linked.id, orphan_notfound.id},
        "kept": {a_cat.id, a_set.id, a_follow.id, a_act.id, a_album.id},
        "session": s,
    }
    mod._engine = None


def test_select_returns_only_unreferenced(seeded):
    got = {r[0] for r in select_orphan_batch(seeded["session"], after_id=0, limit=100)}
    assert got == seeded["orphans"]


def test_dry_run_counts_but_deletes_nothing(seeded):
    stats = run(apply=False)
    assert stats["scanned"] == 3
    assert stats["deleted"] == 0
    # Nothing removed.
    total = seeded["session"].execute(select(func.count(Artist.id))).scalar_one()
    assert total == 8


def test_apply_deletes_only_orphans(seeded):
    stats = run(apply=True, keep_artwork=True)
    assert stats["deleted"] == 3
    s = seeded["session"]
    s.expire_all()
    remaining = {r[0] for r in s.execute(select(Artist.id)).all()}
    assert remaining == seeded["kept"]


def test_apply_is_idempotent(seeded):
    run(apply=True, keep_artwork=True)
    stats = run(apply=True, keep_artwork=True)  # second pass finds nothing
    assert stats["scanned"] == 0
    assert stats["deleted"] == 0


def test_limit_caps_scan(seeded):
    stats = run(apply=False, limit=2)
    assert stats["scanned"] == 2
