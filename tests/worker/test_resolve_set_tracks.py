"""
Tests de la logique de resolution set_tracks -> catalog.
Utilise un SQLite sync en memoire (meme pattern que la tache Celery).
"""
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import CatalogEntry, DJSet, SetTrack
from utils import make_normalized_key


def _resolve(session):
    """Replique la logique core de resolve_set_tracks (sans Celery)."""
    resolved = 0
    created = 0

    tracks = session.execute(
        select(SetTrack).where(
            SetTrack.catalog_id.is_(None),
            SetTrack.is_id == False,  # noqa: E712
            SetTrack.raw_title.isnot(None),
        )
    ).scalars().all()

    for st in tracks:
        norm_key = make_normalized_key(st.raw_title, st.raw_artist)

        entry = session.execute(
            select(CatalogEntry).where(CatalogEntry.normalized_key == norm_key)
        ).scalar_one_or_none()

        if not entry:
            entry = CatalogEntry(
                title=st.raw_title,
                artist=st.raw_artist,
                normalized_key=norm_key,
                created_at=datetime.now(timezone.utc),
            )
            session.add(entry)
            session.flush()
            created += 1

        st.catalog_id = entry.id
        resolved += 1

    session.commit()
    return {"resolved": resolved, "catalog_created": created}


class TestResolveSetTracks:
    def test_resolves_to_existing_catalog(self, sync_session):
        s = sync_session
        cat = CatalogEntry(title="Cola", artist="CamelPhat", normalized_key=make_normalized_key("Cola", "CamelPhat"))
        s.add(cat)
        dj = DJSet(source="trackid", title="Test Set")
        s.add(dj)
        s.flush()
        s.add(SetTrack(set_id=dj.id, position=1, raw_title="Cola", raw_artist="CamelPhat"))
        s.commit()

        result = _resolve(s)
        assert result["resolved"] == 1
        assert result["catalog_created"] == 0

        track = s.execute(select(SetTrack)).scalar_one()
        assert track.catalog_id == cat.id

    def test_creates_catalog_when_missing(self, sync_session):
        s = sync_session
        dj = DJSet(source="trackid", title="Test Set")
        s.add(dj)
        s.flush()
        s.add(SetTrack(set_id=dj.id, position=1, raw_title="New Track", raw_artist="Unknown"))
        s.commit()

        result = _resolve(s)
        assert result["resolved"] == 1
        assert result["catalog_created"] == 1

        cat = s.execute(select(CatalogEntry)).scalar_one()
        assert cat.title == "New Track"
        assert cat.artist == "Unknown"

    def test_skips_is_id_tracks(self, sync_session):
        s = sync_session
        dj = DJSet(source="trackid", title="Test Set")
        s.add(dj)
        s.flush()
        s.add(SetTrack(set_id=dj.id, position=1, raw_title="ID", raw_artist="ID", is_id=True))
        s.commit()

        result = _resolve(s)
        assert result["resolved"] == 0
        assert result["catalog_created"] == 0

    def test_skips_already_resolved(self, sync_session):
        s = sync_session
        cat = CatalogEntry(title="Cola", artist="CamelPhat", normalized_key=make_normalized_key("Cola", "CamelPhat"))
        s.add(cat)
        dj = DJSet(source="trackid", title="Test Set")
        s.add(dj)
        s.flush()
        s.add(SetTrack(set_id=dj.id, position=1, raw_title="Cola", raw_artist="CamelPhat", catalog_id=cat.id))
        s.commit()

        result = _resolve(s)
        assert result["resolved"] == 0

    def test_skips_null_raw_title(self, sync_session):
        s = sync_session
        dj = DJSet(source="trackid", title="Test Set")
        s.add(dj)
        s.flush()
        s.add(SetTrack(set_id=dj.id, position=1, raw_title=None, raw_artist=None))
        s.commit()

        result = _resolve(s)
        assert result["resolved"] == 0

    def test_idempotent(self, sync_session):
        s = sync_session
        dj = DJSet(source="trackid", title="Test Set")
        s.add(dj)
        s.flush()
        s.add(SetTrack(set_id=dj.id, position=1, raw_title="Cola", raw_artist="CamelPhat"))
        s.commit()

        r1 = _resolve(s)
        assert r1["resolved"] == 1
        assert r1["catalog_created"] == 1

        r2 = _resolve(s)
        assert r2["resolved"] == 0
        assert r2["catalog_created"] == 0

    def test_multiple_tracks_same_song_one_catalog(self, sync_session):
        s = sync_session
        dj1 = DJSet(source="trackid", title="Set 1")
        dj2 = DJSet(source="manual", title="Set 2")
        s.add_all([dj1, dj2])
        s.flush()
        s.add(SetTrack(set_id=dj1.id, position=1, raw_title="Cola", raw_artist="CamelPhat"))
        s.add(SetTrack(set_id=dj2.id, position=1, raw_title="Cola", raw_artist="CamelPhat"))
        s.commit()

        result = _resolve(s)
        assert result["resolved"] == 2
        assert result["catalog_created"] == 1

        cats = s.execute(select(CatalogEntry)).scalars().all()
        assert len(cats) == 1
