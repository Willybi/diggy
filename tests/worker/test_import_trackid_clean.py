"""Tests for the L3 OPS clean-import script (scripts/import_trackid_clean).

The script ingests a pre-computed enrichment BUNDLE (NDJSON) into prod by
replaying the import/enrichment funnel verbatim, with ZERO network I/O — every
value comes from the bundle. Coverage is split by session type:

  * PURE helpers (``_valid_bundle`` / ``_set_priority`` / ``_merge_priority`` /
    ``_decode_b64``) — exercised directly.
  * The SYNC core ``_enrich_set_sync`` — driven against the worker ``sync_session``
    fixture (full schema on SQLite). Catalog rows are PRE-CREATED so the dedup
    path is taken and ``bulk_get_or_create_catalog``'s PG-only ON CONFLICT insert
    is never compiled on SQLite (the CREATION path is covered by the PG-gated
    test at the bottom). Asserts: linking + priority, Deezer/Beatport/BPM/embedding
    application, the freshness/idempotence guards, the hydration flip, cover BYTES
    upload (mocked), and dry-run writing nothing.
  * The ASYNC orchestrator ``import_bundles`` — driven end-to-end over an OWN
    in-memory aiosqlite engine (StaticPool) via ``asyncio.run``, proving the
    ``import_audiostream`` short-circuit (bare TrackIDClient, prefetched detail →
    no network) wires through to a fully enriched, hydrated set.

The script REUSES the funnel functions; these tests assert the WIRING + accounting,
not the funnel mappings (those have their own tests). Same redis/curl_cffi mock
dance as test_import_beatport_matches (workers/enrichment imports them at load).
"""
import asyncio
import itertools
import json
import os
import sys
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

_SERVER_PATH = os.path.join(os.path.dirname(__file__), "../../server")
if _SERVER_PATH not in sys.path:
    sys.path.insert(0, _SERVER_PATH)

_saved_redis = sys.modules.get("redis")
sys.modules.setdefault("redis", MagicMock())
_saved_curl = sys.modules.get("curl_cffi")
sys.modules.setdefault("curl_cffi", MagicMock())

from scripts.import_trackid_clean import (  # noqa: E402
    FLUX_PRIORITY,
    _decode_b64,
    _enrich_set_sync,
    _merge_priority,
    _set_priority,
    _suppress_url_uploads,
    _valid_bundle,
    import_bundles,
)

if _saved_redis is None:
    sys.modules.pop("redis", None)
else:
    sys.modules["redis"] = _saved_redis
del _saved_redis
if _saved_curl is None:
    sys.modules.pop("curl_cffi", None)
else:
    sys.modules["curl_cffi"] = _saved_curl
del _saved_curl

from models import (  # noqa: E402
    CatalogArtist,
    CatalogEntry,
    DJSet,
    SetTrack,
    TrackEmbedding,
    TrackIdIndex,
)
from models.embedding import EMBEDDING_DIM, MODEL_NAME, MODEL_VERSION  # noqa: E402
from utils import make_normalized_key  # noqa: E402

NOW = datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc)
_seq = itertools.count(1)


# ── seed helpers ────────────────────────────────────────────────────────────────


def _cat(session, title, artist, **fields):
    """Pre-create a CatalogEntry keyed on make_normalized_key(title, artist)."""
    entry = CatalogEntry(
        title=title,
        artist=artist,
        normalized_key=make_normalized_key(title, artist),
        created_at=NOW,
        **fields,
    )
    session.add(entry)
    session.commit()
    return entry


def _seed_set(session, tracks, *, trackid_id=None, indexed=True):
    """Create a DJSet + its SetTracks (catalog_id NULL, as import_audiostream
    leaves them) and, optionally, a matching trackid_index row.

    ``tracks``: list of (title, artist, mtid) or (title, artist, mtid, is_id).
    Returns (set_id, trackid_id).
    """
    tid = trackid_id if trackid_id is not None else next(_seq) + 100000
    dj_set = DJSet(
        external_id=str(tid),
        source="trackid",
        title="Seed Set",
        created_at=NOW,
    )
    session.add(dj_set)
    session.flush()
    for pos, t in enumerate(tracks, start=1):
        title, artist, mtid = t[0], t[1], t[2]
        is_id = t[3] if len(t) > 3 else False
        session.add(
            SetTrack(
                set_id=dj_set.id,
                position=pos,
                raw_title=title,
                raw_artist=artist,
                is_id=is_id,
                trackid_music_track_id=mtid,
            )
        )
    if indexed:
        session.add(
            TrackIdIndex(trackid_id=tid, title="Seed Set", hydration_state="not_hydrated")
        )
    session.commit()
    return dj_set.id, tid


def _bundle(trackid_id, tracks, *, score=None):
    """Assemble a minimal bundle dict (detail is only needed by the async path)."""
    return {
        "trackid_id": trackid_id,
        "slug": "seed",
        "score": score,
        "detail": {"id": trackid_id, "slug": "seed"},
        "tracks": tracks,
    }


def _dz_track(dz_id, artist, *, isrc=None, album_id=None, album_title="Alb"):
    """A Deezer /track hit dict WITHOUT album covers (so the funnel's
    upload_from_url branch is skipped — no network in the direct sync tests)."""
    track = {
        "id": dz_id,
        "duration": 200,
        "preview": "https://preview",
        "contributors": [{"id": 7, "name": artist, "role": "Main"}],
    }
    if isrc:
        track["isrc"] = isrc
    if album_id:
        track["album"] = {"id": album_id, "title": album_title}
    return track


# ── pure helpers ────────────────────────────────────────────────────────────────


class TestPureHelpers:
    def test_valid_bundle(self):
        assert _valid_bundle(_bundle(5, []))
        # detail id backs trackid_id when top-level is absent
        assert _valid_bundle({"detail": {"id": 9}, "tracks": []})
        assert not _valid_bundle("nope")
        assert not _valid_bundle({"detail": {}, "tracks": []})  # no id
        assert not _valid_bundle({"detail": {"id": 1}})  # no tracks list
        assert not _valid_bundle({"detail": {"id": "x"}, "tracks": []})  # non-int id

    def test_set_priority(self):
        assert _set_priority(_bundle(1, [], score=2.4)) == 2
        assert _set_priority(_bundle(1, [], score=None)) == FLUX_PRIORITY
        assert _set_priority(_bundle(1, [], score=True)) == FLUX_PRIORITY  # bool != score

    def test_merge_priority(self):
        assert _merge_priority(None, 3) == 3
        assert _merge_priority(5, 3) == 5
        assert _merge_priority(2, 3) == 3

    def test_decode_b64(self):
        import base64

        assert _decode_b64(base64.b64encode(b"hi").decode()) == b"hi"
        assert _decode_b64(None) is None
        assert _decode_b64("!!!not b64!!!") is None


# ── sync core: linking + priority ───────────────────────────────────────────────


class TestLinkingAndPriority:
    def test_links_existing_catalog_and_stamps_priority(self, sync_session):
        a = _cat(sync_session, "Song A", "Artist A")
        b = _cat(sync_session, "Song B", "Artist B")
        set_id, tid = _seed_set(
            sync_session, [("Song A", "Artist A", 11), ("Song B", "Artist B", 12)]
        )
        bundle = _bundle(tid, [], score=2.0)

        counts = _enrich_set_sync(sync_session, set_id, bundle, True, NOW)

        assert counts["tracks_linked"] == 2
        sync_session.refresh(a)
        sync_session.refresh(b)
        # linked to the PRE-EXISTING rows (dedup, no new catalog)
        sts = sync_session.query(SetTrack).filter_by(set_id=set_id).all()
        assert {st.catalog_id for st in sts} == {a.id, b.id}
        assert a.enrich_priority == 2 and b.enrich_priority == 2

    def test_priority_max_merges(self, sync_session):
        a = _cat(sync_session, "Song A", "Artist A", enrich_priority=90)
        set_id, tid = _seed_set(sync_session, [("Song A", "Artist A", 11)])
        # a lower score never lowers an existing higher priority
        _enrich_set_sync(sync_session, set_id, _bundle(tid, [], score=1.0), True, NOW)
        sync_session.refresh(a)
        assert a.enrich_priority == 90

    def test_id_tracks_are_not_resolved(self, sync_session):
        set_id, tid = _seed_set(
            sync_session, [("ID", "ID", None, True), ("Song A", "Artist A", 11)]
        )
        _cat(sync_session, "Song A", "Artist A")
        counts = _enrich_set_sync(sync_session, set_id, _bundle(tid, []), True, NOW)
        assert counts["tracks_linked"] == 1  # only the non-ID track


# ── sync core: enrichment application ────────────────────────────────────────────


class TestDeezer:
    def test_applies_deezer_hit_creates_artist_and_album(self, sync_session):
        entry = _cat(sync_session, "Song A", "Artist A")
        set_id, tid = _seed_set(sync_session, [("Song A", "Artist A", 11)])
        bundle = _bundle(
            tid,
            [
                {
                    "raw_title": "Song A",
                    "raw_artist": "Artist A",
                    "is_id": False,
                    "musicTrackId": 11,
                    "deezer": {
                        "track": _dz_track("900", "Artist A", isrc="AA1", album_id="50"),
                        "cover_catalog_b64": None,
                        "cover_album_b64": None,
                    },
                }
            ],
        )

        counts = _enrich_set_sync(sync_session, set_id, bundle, True, NOW)

        assert counts["deezer_applied"] == 1
        sync_session.flush()
        sync_session.refresh(entry)
        assert entry.deezer_id == "900"
        assert entry.isrc == "AA1"
        assert entry.deezer_searched_at is not None
        assert entry.deezer_search_attempts == 1
        # artist linked via catalog_artists, album row created
        assert (
            sync_session.query(CatalogArtist).filter_by(catalog_id=entry.id).count() == 1
        )
        from models import Album

        assert sync_session.query(Album).filter_by(deezer_album_id="50").count() == 1

    def test_already_linked_deezer_is_not_restamped(self, sync_session):
        entry = _cat(
            sync_session,
            "Song A",
            "Artist A",
            deezer_id="OLD",
            deezer_search_attempts=1,
        )
        set_id, tid = _seed_set(sync_session, [("Song A", "Artist A", 11)])
        bundle = _bundle(
            tid,
            [
                {
                    "raw_title": "Song A",
                    "raw_artist": "Artist A",
                    "musicTrackId": 11,
                    "deezer": {"track": _dz_track("NEW", "Artist A")},
                }
            ],
        )

        counts = _enrich_set_sync(sync_session, set_id, bundle, True, NOW)

        assert counts["already_deezer"] == 1
        assert counts["deezer_applied"] == 0
        sync_session.refresh(entry)
        assert entry.deezer_id == "OLD"  # untouched
        assert entry.deezer_search_attempts == 1

    def test_deezer_id_collision_same_recording_folds(self, sync_session):
        # A pre-existing SAME-recording row already carries the deezer_id → the
        # enriched row is folded into it (merged), not double-stamped. Same
        # recording is proven by the feat-stripped title match (distinct
        # normalized_keys, so both rows coexist until the merge).
        holder = _cat(sync_session, "Song A feat. B", "Artist A", deezer_id="777")
        loser = _cat(sync_session, "Song A", "Artist A")
        set_id, tid = _seed_set(sync_session, [("Song A", "Artist A", 11)])
        bundle = _bundle(
            tid,
            [
                {
                    "raw_title": "Song A",
                    "raw_artist": "Artist A",
                    "musicTrackId": 11,
                    "deezer": {"track": _dz_track("777", "Artist A")},
                }
            ],
        )

        counts = _enrich_set_sync(sync_session, set_id, bundle, True, NOW)

        assert counts["merged"] == 1
        assert counts["deezer_applied"] == 0
        assert sync_session.get(CatalogEntry, loser.id) is None
        assert sync_session.get(CatalogEntry, holder.id) is not None


class TestBeatport:
    def test_applies_beatport_and_marks(self, sync_session):
        entry = _cat(sync_session, "Song B", "Artist B")
        set_id, tid = _seed_set(sync_session, [("Song B", "Artist B", 12)])
        bundle = _bundle(
            tid,
            [
                {
                    "raw_title": "Song B",
                    "raw_artist": "Artist B",
                    "musicTrackId": 12,
                    "beatport": {"bp_track": {"id": "bp1", "bpm": 130, "key": "9A"}},
                }
            ],
        )

        counts = _enrich_set_sync(sync_session, set_id, bundle, True, NOW)

        assert counts["beatport_applied"] == 1
        sync_session.flush()
        sync_session.refresh(entry)
        assert entry.beatport_id == "bp1"
        assert entry.bpm == 130
        assert entry.bpm_source == "beatport"
        assert entry.key == "9A"
        assert entry.beatport_search_attempts == 1

    def test_already_linked_beatport_is_skipped(self, sync_session):
        entry = _cat(sync_session, "Song B", "Artist B", beatport_id="OLD")
        set_id, tid = _seed_set(sync_session, [("Song B", "Artist B", 12)])
        bundle = _bundle(
            tid,
            [
                {
                    "raw_title": "Song B",
                    "raw_artist": "Artist B",
                    "musicTrackId": 12,
                    "beatport": {"bp_track": {"id": "NEW", "bpm": 140}},
                }
            ],
        )
        counts = _enrich_set_sync(sync_session, set_id, bundle, True, NOW)
        assert counts["already_beatport"] == 1
        sync_session.refresh(entry)
        assert entry.beatport_id == "OLD"


class TestBpm:
    def _run(self, sync_session, entry, bpm_payload):
        set_id, tid = _seed_set(sync_session, [("Song A", "Artist A", 11)])
        bundle = _bundle(
            tid,
            [
                {
                    "raw_title": "Song A",
                    "raw_artist": "Artist A",
                    "musicTrackId": 11,
                    "bpm": bpm_payload,
                }
            ],
        )
        return _enrich_set_sync(sync_session, set_id, bundle, True, NOW)

    def test_sets_analysis_bpm_when_null(self, sync_session):
        entry = _cat(sync_session, "Song A", "Artist A")
        counts = self._run(sync_session, entry, {"value": 123.5, "conf": 2.5})
        assert counts["bpm_set"] == 1
        sync_session.flush()
        sync_session.refresh(entry)
        assert entry.bpm == 123.5
        assert entry.bpm_source == "analysis"

    def test_does_not_override_existing_bpm(self, sync_session):
        entry = _cat(
            sync_session, "Song A", "Artist A", bpm=128.0, bpm_source="beatport"
        )
        counts = self._run(sync_session, entry, {"value": 123.5, "conf": 2.5})
        assert counts["already_bpm"] == 1
        assert counts["bpm_set"] == 0
        sync_session.refresh(entry)
        assert entry.bpm == 128.0
        assert entry.bpm_source == "beatport"  # never downgraded


class TestEmbedding:
    def _bundle_with_emb(self, tid, emb):
        return _bundle(
            tid,
            [
                {
                    "raw_title": "Song A",
                    "raw_artist": "Artist A",
                    "musicTrackId": 11,
                    "embedding": emb,
                }
            ],
        )

    def test_inserts_embedding_and_is_idempotent(self, sync_session):
        entry = _cat(sync_session, "Song A", "Artist A")
        set_id, tid = _seed_set(sync_session, [("Song A", "Artist A", 11)])
        emb = [0.01] * EMBEDDING_DIM

        c1 = _enrich_set_sync(
            sync_session, set_id, self._bundle_with_emb(tid, emb), True, NOW
        )
        assert c1["embeddings_inserted"] == 1
        row = (
            sync_session.query(TrackEmbedding)
            .filter_by(catalog_id=entry.id, model_name=MODEL_NAME)
            .one()
        )
        assert row.model_version == MODEL_VERSION
        assert len(row.embedding) == EMBEDDING_DIM

        # Re-run: the (catalog, model, version) row exists → not re-inserted.
        c2 = _enrich_set_sync(
            sync_session, set_id, self._bundle_with_emb(tid, emb), True, NOW
        )
        assert c2["embeddings_inserted"] == 0
        assert c2["already_embedded"] == 1
        assert (
            sync_session.query(TrackEmbedding).filter_by(catalog_id=entry.id).count()
            == 1
        )

    def test_wrong_length_embedding_is_ignored(self, sync_session):
        _cat(sync_session, "Song A", "Artist A")
        set_id, tid = _seed_set(sync_session, [("Song A", "Artist A", 11)])
        counts = _enrich_set_sync(
            sync_session, set_id, self._bundle_with_emb(tid, [0.1, 0.2]), True, NOW
        )
        assert counts["embeddings_inserted"] == 0
        assert sync_session.query(TrackEmbedding).count() == 0


class TestHydration:
    def test_flips_hydration_and_links_set(self, sync_session):
        _cat(sync_session, "Song A", "Artist A")
        set_id, tid = _seed_set(sync_session, [("Song A", "Artist A", 11)])
        counts = _enrich_set_sync(sync_session, set_id, _bundle(tid, []), True, NOW)
        assert counts["hydrated"] == 1
        idx = sync_session.query(TrackIdIndex).filter_by(trackid_id=tid).one()
        assert idx.hydration_state == "hydrated"
        assert idx.set_id == set_id

    def test_already_hydrated_is_noop(self, sync_session):
        _cat(sync_session, "Song A", "Artist A")
        set_id, tid = _seed_set(sync_session, [("Song A", "Artist A", 11)])
        _enrich_set_sync(sync_session, set_id, _bundle(tid, []), True, NOW)
        counts = _enrich_set_sync(sync_session, set_id, _bundle(tid, []), True, NOW)
        assert counts["hydrated"] == 0
        assert counts["already_hydrated"] == 1

    def test_missing_index_row_counted(self, sync_session):
        _cat(sync_session, "Song A", "Artist A")
        set_id, tid = _seed_set(
            sync_session, [("Song A", "Artist A", 11)], indexed=False
        )
        counts = _enrich_set_sync(sync_session, set_id, _bundle(tid, []), True, NOW)
        assert counts["hydration_index_missing"] == 1
        assert counts["hydrated"] == 0


# ── cover bytes + dry-run (external write control) ───────────────────────────────


class TestCoverBytesAndDryRun:
    def _cover_bundle(self, tid):
        import base64

        blob = base64.b64encode(b"x" * 2048).decode()
        return _bundle(
            tid,
            [
                {
                    "raw_title": "Song A",
                    "raw_artist": "Artist A",
                    "musicTrackId": 11,
                    "deezer": {
                        "track": _dz_track("900", "Artist A", album_id="50"),
                        "cover_catalog_b64": blob,
                        "cover_album_b64": blob,
                    },
                }
            ],
        )

    def test_apply_uploads_cover_bytes(self, sync_session, monkeypatch):
        from services.image_service import ImageService

        # Simulate the run-level suppression (upload_from_url must never fire).
        url_spy = MagicMock(return_value=False)
        bytes_spy = MagicMock(return_value=True)
        monkeypatch.setattr(ImageService, "upload_from_url", url_spy)
        monkeypatch.setattr(ImageService, "upload_bytes", bytes_spy)

        entry = _cat(sync_session, "Song A", "Artist A")
        set_id, tid = _seed_set(sync_session, [("Song A", "Artist A", 11)])

        _enrich_set_sync(sync_session, set_id, self._cover_bundle(tid), True, NOW)

        assert url_spy.call_count == 0  # never fetch over the network
        # catalog cover + album cover uploaded from the bundle bytes
        buckets = {c.args[1] for c in bytes_spy.call_args_list}
        assert buckets == {"catalog-artworks", "album-artworks"}
        sync_session.flush()
        sync_session.refresh(entry)
        assert entry.has_artwork is True

    def test_dry_run_writes_nothing(self, sync_session, monkeypatch):
        from services.image_service import ImageService

        bytes_spy = MagicMock(return_value=True)
        monkeypatch.setattr(ImageService, "upload_from_url", MagicMock(return_value=False))
        monkeypatch.setattr(ImageService, "upload_bytes", bytes_spy)

        entry = _cat(sync_session, "Song A", "Artist A")
        set_id, tid = _seed_set(sync_session, [("Song A", "Artist A", 11)])

        counts = _enrich_set_sync(
            sync_session, set_id, self._cover_bundle(tid), False, NOW
        )

        # Counts are accurate (the funnel ran)...
        assert counts["deezer_applied"] == 1
        # ...no cover byte upload in dry-run (external write gated on apply)...
        assert bytes_spy.call_count == 0
        # ...and the caller rolls back, discarding the in-memory mutations.
        sync_session.rollback()
        reloaded = sync_session.get(CatalogEntry, entry.id)
        assert reloaded.deezer_id is None
        assert reloaded.deezer_searched_at is None


# ── async orchestrator: end-to-end over aiosqlite ────────────────────────────────


def _async_run_import(bundles, *, apply):
    """Build an OWN in-memory aiosqlite engine (StaticPool → one shared conn),
    seed the catalog + trackid_index for the fixture set, run import_bundles over
    the given bundles, and return (counts, reader) where reader(fn) opens a fresh
    sync-style read via the async engine's run_sync. Fully self-contained."""
    from database import Base
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    async def _go():
        engine = create_async_engine(
            "sqlite+aiosqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        # Seed: catalog for the two tracks + the not_hydrated index row.
        def _seed(session):
            session.add(
                CatalogEntry(
                    title="Song A",
                    artist="Artist A",
                    normalized_key=make_normalized_key("Song A", "Artist A"),
                    created_at=NOW,
                )
            )
            session.add(
                CatalogEntry(
                    title="Song B",
                    artist="Artist B",
                    normalized_key=make_normalized_key("Song B", "Artist B"),
                    created_at=NOW,
                )
            )
            session.add(
                TrackIdIndex(trackid_id=555, title="My Set", hydration_state="not_hydrated")
            )

        async with factory() as db:
            await db.run_sync(_seed)
            await db.commit()

        with _suppress_url_uploads():
            counts = await import_bundles(factory, bundles, apply=apply, now=NOW)

        snapshot = {}

        def _read(session):
            snapshot["sets"] = session.query(DJSet).count()
            dj = session.query(DJSet).first()
            snapshot["set_has_artwork"] = dj.has_artwork if dj else None
            snapshot["linked"] = (
                session.query(SetTrack).filter(SetTrack.catalog_id.isnot(None)).count()
            )
            a = (
                session.query(CatalogEntry)
                .filter_by(normalized_key=make_normalized_key("Song A", "Artist A"))
                .one()
            )
            b = (
                session.query(CatalogEntry)
                .filter_by(normalized_key=make_normalized_key("Song B", "Artist B"))
                .one()
            )
            snapshot["a_deezer"] = a.deezer_id
            snapshot["a_bpm"] = a.bpm
            snapshot["a_bpm_source"] = a.bpm_source
            snapshot["a_embeddings"] = (
                session.query(TrackEmbedding).filter_by(catalog_id=a.id).count()
            )
            snapshot["b_beatport"] = b.beatport_id
            idx = session.query(TrackIdIndex).filter_by(trackid_id=555).one()
            snapshot["hydration"] = idx.hydration_state
            snapshot["idx_set_id"] = idx.set_id

        async with factory() as db:
            await db.run_sync(_read)

        await engine.dispose()
        return counts, snapshot

    return asyncio.run(_go())


_ASYNC_DETAIL = {
    "id": 555,
    "slug": "my-set",
    "title": "My Set",
    "url": "https://trackid.net/audiostream/my-set",
    "duration": "01:00:00",
    "createdOn": "2026-01-01T00:00:00",
    "detectionProcesses": [
        {
            "detectionProcessMusicTracks": [
                {
                    "musicTrackId": 11,
                    "title": "Song A",
                    "artist": "Artist A",
                    "startTime": "00:01:00",
                },
                {
                    "musicTrackId": 12,
                    "title": "Song B",
                    "artist": "Artist B",
                    "startTime": "00:05:00",
                },
            ]
        }
    ],
}

_ASYNC_BUNDLE = {
    "trackid_id": 555,
    "slug": "my-set",
    "score": 3.0,
    "detail": _ASYNC_DETAIL,
    "tracks": [
        {
            "position": 1,
            "raw_title": "Song A",
            "raw_artist": "Artist A",
            "is_id": False,
            "musicTrackId": 11,
            "deezer": {
                "track": {
                    "id": "900",
                    "duration": 200,
                    "preview": "https://preview",
                    "contributors": [{"id": 7, "name": "Artist A", "role": "Main"}],
                    "album": {"id": "50", "title": "Alb"},
                },
                "cover_catalog_b64": None,
                "cover_album_b64": None,
            },
            "bpm": {"value": 128.0, "conf": 2.5},
            "key": "8A",
            "embedding": [0.02] * EMBEDDING_DIM,
        },
        {
            "position": 2,
            "raw_title": "Song B",
            "raw_artist": "Artist B",
            "is_id": False,
            "musicTrackId": 12,
            "beatport": {"bp_track": {"id": "bp1", "bpm": 130, "key": "9A"}},
        },
    ],
}


class TestAsyncOrchestrator:
    def test_end_to_end_apply(self):
        line = json.dumps(_ASYNC_BUNDLE)
        counts, snap = _async_run_import([line], apply=True)

        # import_audiostream ran with a bare client + prefetched detail (no network)
        assert counts["sets_imported"] == 1
        assert counts["tracks_linked"] == 2
        assert counts["deezer_applied"] == 1
        assert counts["beatport_applied"] == 1
        assert counts["bpm_set"] == 1
        assert counts["embeddings_inserted"] == 1
        assert counts["hydrated"] == 1

        assert snap["sets"] == 1
        assert snap["linked"] == 2
        assert snap["a_deezer"] == "900"
        assert snap["a_bpm"] == 128.0
        assert snap["a_bpm_source"] == "analysis"
        assert snap["a_embeddings"] == 1
        assert snap["b_beatport"] == "bp1"
        assert snap["hydration"] == "hydrated"
        assert snap["idx_set_id"] is not None

    def test_dry_run_writes_nothing(self):
        line = json.dumps(_ASYNC_BUNDLE)
        counts, snap = _async_run_import([line], apply=False)

        # Counts computed by running the funnel...
        assert counts["sets_imported"] == 1
        assert counts["deezer_applied"] == 1
        # ...but the per-set transaction was rolled back: no set, no link persisted.
        assert snap["sets"] == 0
        assert snap["linked"] == 0
        assert snap["a_deezer"] is None
        assert snap["hydration"] == "not_hydrated"

    def test_malformed_line_counted_and_skipped(self):
        counts, _ = _async_run_import(["not json at all", "{}"], apply=True)
        assert counts["total"] == 2
        assert counts["malformed"] == 2
        assert counts["sets_imported"] == 0


class TestSetArtwork:
    """The set cover rides the bundle (set_artwork_b64) and is uploaded from bytes
    — the funnel's network fetch is suppressed, and a hydrated set is never
    re-crawled to get one. Uploaded ONLY in --apply, keyed by set id."""

    def _blob(self):
        import base64

        return base64.b64encode(b"y" * 2048).decode()

    def test_uploaded_in_apply(self, monkeypatch):
        from services.image_service import ImageService

        spy = MagicMock(return_value=True)
        monkeypatch.setattr(ImageService, "upload_bytes", spy)

        bundle = dict(_ASYNC_BUNDLE, set_artwork_b64=self._blob())
        _counts, snap = _async_run_import([json.dumps(bundle)], apply=True)

        set_calls = [c for c in spy.call_args_list if c.args[1] == "set-artworks"]
        assert len(set_calls) == 1
        # keyed by the set id, .jpg
        assert set_calls[0].args[2].endswith(".jpg")
        assert snap["set_has_artwork"] is True

    def test_not_uploaded_in_dry_run(self, monkeypatch):
        from services.image_service import ImageService

        spy = MagicMock(return_value=True)
        monkeypatch.setattr(ImageService, "upload_bytes", spy)

        bundle = dict(_ASYNC_BUNDLE, set_artwork_b64=self._blob())
        _counts, snap = _async_run_import([json.dumps(bundle)], apply=False)

        assert not [c for c in spy.call_args_list if c.args[1] == "set-artworks"]
        # dry-run rolled the set back entirely
        assert snap["sets"] == 0

    def test_absent_field_no_regression(self, monkeypatch):
        from services.image_service import ImageService

        spy = MagicMock(return_value=True)
        monkeypatch.setattr(ImageService, "upload_bytes", spy)

        # _ASYNC_BUNDLE carries no set_artwork_b64 → no set cover upload.
        _counts, snap = _async_run_import([json.dumps(_ASYNC_BUNDLE)], apply=True)

        assert not [c for c in spy.call_args_list if c.args[1] == "set-artworks"]
        assert snap["set_has_artwork"] is False


# ── PG-only: the catalog CREATION path (bulk_get_or_create ON CONFLICT) ──────────

pytestmark_pg = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL", "").startswith("postgresql"),
    reason="catalog creation uses PG-only ON CONFLICT (bulk_get_or_create_catalog)",
)


@pytestmark_pg
class TestCatalogCreationPG:
    """When a set_track's normalized_key has NO catalog row yet,
    bulk_get_or_create_catalog INSERTs it via a PG ON CONFLICT clause SQLite can't
    compile. Drive _enrich_set_sync against a throwaway PG DB (own database, same
    maintenance-connection pattern as test_import_rb_upsert) so the creation path +
    real pgvector embedding are exercised."""

    _LOCK = 0x1C3E

    @staticmethod
    def _maintenance(dsn, statements):
        import psycopg2

        conn = psycopg2.connect(dsn)
        conn.autocommit = True
        try:
            cur = conn.cursor()
            cur.execute("SELECT pg_advisory_lock(%s)", (TestCatalogCreationPG._LOCK,))
            try:
                for stmt in statements:
                    cur.execute(stmt)
            finally:
                cur.execute(
                    "SELECT pg_advisory_unlock(%s)", (TestCatalogCreationPG._LOCK,)
                )
            cur.close()
        finally:
            conn.close()

    @pytest.fixture
    def pg_engine(self):
        from database import Base
        from sqlalchemy import create_engine
        from sqlalchemy.engine import make_url

        base_url = make_url(os.environ["DATABASE_URL"].replace("+asyncpg", ""))
        worker = os.environ.get("PYTEST_XDIST_WORKER", "solo")
        test_db = f"{base_url.database}_tidclean_{worker}"
        maint = base_url.render_as_string(hide_password=False)
        terminate = (
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            f"WHERE datname = '{test_db}' AND pid <> pg_backend_pid()"
        )
        self._maintenance(
            maint,
            [terminate, f'DROP DATABASE IF EXISTS "{test_db}"', f'CREATE DATABASE "{test_db}"'],
        )
        engine = create_engine(
            base_url.set(database=test_db).render_as_string(hide_password=False)
        )
        try:
            Base.metadata.create_all(engine)
            yield engine
        finally:
            engine.dispose()
            self._maintenance(
                maint, [terminate, f'DROP DATABASE IF EXISTS "{test_db}"']
            )

    def test_creates_missing_catalog_and_inserts_pgvector_embedding(self, pg_engine):
        from sqlalchemy.orm import Session

        with Session(pg_engine) as session:
            # No catalog row pre-created → bulk_get_or_create_catalog must INSERT it.
            set_id, tid = _seed_set(session, [("Fresh Song", "Fresh Artist", 11)])
            session.commit()

            bundle = _bundle(
                tid,
                [
                    {
                        "raw_title": "Fresh Song",
                        "raw_artist": "Fresh Artist",
                        "musicTrackId": 11,
                        "embedding": [0.03] * EMBEDDING_DIM,
                    }
                ],
            )
            counts = _enrich_set_sync(session, set_id, bundle, True, NOW)
            session.commit()

            assert counts["tracks_linked"] == 1
            assert counts["embeddings_inserted"] == 1
            entry = (
                session.query(CatalogEntry)
                .filter_by(normalized_key=make_normalized_key("Fresh Song", "Fresh Artist"))
                .one()
            )
            assert entry.enrich_priority == FLUX_PRIORITY  # score None → flux
            assert (
                session.query(TrackEmbedding).filter_by(catalog_id=entry.id).count() == 1
            )
