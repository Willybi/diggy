"""Tests for the OPS placeholder-artist cleanup (scripts/cleanup_placeholder_artists).

Exercises the broad-prefilter + exact-predicate selection and the run() delete pass
against a sync SQLite session: placeholders ("Various Artists", "Unknown Artist"…)
are matched and deleted; real artists that merely CONTAIN those words survive.
"""
import os
import sys

import pytest
from sqlalchemy import func, select

_SERVER_PATH = os.path.join(os.path.dirname(__file__), "../../server")
if _SERVER_PATH not in sys.path:
    sys.path.insert(0, _SERVER_PATH)

import scripts.cleanup_placeholder_artists as mod  # noqa: E402
from models import Artist, CatalogArtist, CatalogEntry  # noqa: E402
from scripts.cleanup_placeholder_artists import run, select_placeholders  # noqa: E402
from utils import normalize  # noqa: E402


def _artist(session, name, **kw):
    a = Artist(name=name, normalized_name=normalize(name), **kw)
    session.add(a)
    session.commit()
    return a


def _attach(session, artist):
    entry = CatalogEntry(title=f"T{artist.id}", artist=artist.name, normalized_key=f"nk-{artist.id}")
    session.add(entry)
    session.commit()
    session.add(CatalogArtist(catalog_id=entry.id, artist_id=artist.id, role="primary", position=0))
    session.commit()


@pytest.fixture
def seeded(sync_engine, sync_session):
    s = sync_session
    va = _artist(s, "Various Artists", deezer_id="NOT_FOUND")
    _attach(s, va)
    unk = _artist(s, "Unknown Artist")
    _attach(s, unk)
    # Real artists that CONTAIN the placeholder words → must survive.
    real1 = _artist(s, "Unknown Mortal Orchestra", deezer_id="1059486")
    _attach(s, real1)
    real2 = _artist(s, "Origin Unknown", deezer_id="12198")
    _attach(s, real2)

    mod._engine = sync_engine
    yield {
        "session": s,
        "placeholder_ids": {va.id, unk.id},
        "real_ids": {real1.id, real2.id},
    }
    mod._engine = None


def test_select_matches_only_placeholders(seeded):
    got = {r[0] for r in select_placeholders(seeded["session"])}
    assert got == seeded["placeholder_ids"]


def test_dry_run_deletes_nothing(seeded):
    stats = run(apply=False)
    assert stats["matched"] == 2
    assert stats["deleted"] == 0
    total = seeded["session"].execute(select(func.count(Artist.id))).scalar_one()
    assert total == 4


def test_apply_deletes_placeholders_keeps_real(seeded):
    stats = run(apply=True, keep_artwork=True)
    assert stats["deleted"] == 2
    assert stats["cat_links"] == 2  # one catalog link per placeholder
    s = seeded["session"]
    s.expire_all()
    remaining = {r[0] for r in s.execute(select(Artist.id)).all()}
    assert remaining == seeded["real_ids"]


def test_apply_is_idempotent(seeded):
    run(apply=True, keep_artwork=True)
    stats = run(apply=True, keep_artwork=True)
    assert stats["matched"] == 0
