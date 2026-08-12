"""Tests for X4.a — enrichment validates against the catalog_artists M2M.

The batch enrichers must match a platform hit against the artists the UI shows
(the ``catalog_artists`` many-to-many, via ``track.artists``), NOT the flat
``catalog.artist`` column. When the two diverge, matching on the flat column
confirms a hit against an artist the user never sees and stamps a WRONG platform
id (measured: 1664 rows post-X3). A fresh inline-crawled row with an empty M2M
still falls back to ``entry.artist``. Uses a real sync SQLite session
(sync_session fixture) so the M2M join query actually executes.
"""
import os
import sys
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

# Path so the workers package is importable (same pattern as test_enrichment_isrc.py)
_SERVER_PATH = os.path.join(os.path.dirname(__file__), "../../server")
if _SERVER_PATH not in sys.path:
    sys.path.insert(0, _SERVER_PATH)

# redis and curl_cffi are not installed in the test env; enrichment.py and
# async_http.py import them at module load.
_saved_redis = sys.modules.get("redis")
sys.modules.setdefault("redis", MagicMock())
_saved_curl = sys.modules.get("curl_cffi")
sys.modules.setdefault("curl_cffi", MagicMock())

import workers.enrichment as enrichment_mod  # noqa: E402
from workers.enrichment import (  # noqa: E402
    _load_m2m_artist_names,
    enrich_beatport_batch,
    enrich_deezer_batch,
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

from models import Artist, CatalogArtist, CatalogEntry  # noqa: E402


def _make_row(session, title, artist, **overrides):
    entry = CatalogEntry(
        title=title,
        artist=artist,
        normalized_key=f"{title.lower()}|{artist.lower()}",
        has_artwork=overrides.pop("has_artwork", True),  # skips cover upload path
        **overrides,
    )
    session.add(entry)
    session.commit()
    return entry


def _link_artist(session, catalog_id, name, position):
    """Create an Artist and link it to a catalog row via catalog_artists."""
    artist = Artist(name=name, normalized_name=name.lower())
    session.add(artist)
    session.flush()
    session.add(
        CatalogArtist(
            catalog_id=catalog_id,
            artist_id=artist.id,
            role="primary",
            position=position,
        )
    )
    session.commit()
    return artist


# ── _load_m2m_artist_names ────────────────────────────────────────────────────


class TestLoadM2mArtistNames:
    def test_empty_entries_returns_empty(self, sync_session):
        assert _load_m2m_artist_names(sync_session, []) == {}

    def test_single_link(self, sync_session):
        entry = _make_row(sync_session, "Track", "Flat Name")
        _link_artist(sync_session, entry.id, "Real Name", 0)

        assert _load_m2m_artist_names(sync_session, [entry]) == {entry.id: "Real Name"}

    def test_orders_by_position(self, sync_session):
        entry = _make_row(sync_session, "Track", "Flat")
        # Inserted out of position order to prove the ORDER BY sorts them.
        _link_artist(sync_session, entry.id, "Second", 1)
        _link_artist(sync_session, entry.id, "First", 0)

        assert _load_m2m_artist_names(sync_session, [entry]) == {
            entry.id: "First, Second"
        }

    def test_null_position_sorts_last(self, sync_session):
        entry = _make_row(sync_session, "Track", "Flat")
        _link_artist(sync_session, entry.id, "Unpositioned", None)
        _link_artist(sync_session, entry.id, "Positioned", 0)

        assert _load_m2m_artist_names(sync_session, [entry]) == {
            entry.id: "Positioned, Unpositioned"
        }

    def test_entry_without_link_absent_from_map(self, sync_session):
        linked = _make_row(sync_session, "Linked", "Flat A")
        unlinked = _make_row(sync_session, "Unlinked", "Flat B")
        _link_artist(sync_session, linked.id, "Real A", 0)

        result = _load_m2m_artist_names(sync_session, [linked, unlinked])

        assert result == {linked.id: "Real A"}
        assert unlinked.id not in result


# ── enrich_deezer_batch: validate against the M2M ─────────────────────────────


def _make_deezer_pool(hit):
    """Pool whose deezer_get returns ``hit`` for every /search, recording queries."""
    pool = MagicMock()
    pool.queries = []

    async def _deezer_get(path, params=None):
        pool.queries.append(params["q"])
        return {"data": [hit] if hit else []}

    pool.deezer_get = AsyncMock(side_effect=_deezer_get)
    return pool


class TestDeezerBatchM2m:
    async def test_wrong_artist_hit_rejected_when_m2m_diverges(self, sync_session):
        """catalog.artist != M2M: the searcher gets the M2M name, so a Deezer hit
        naming the FLAT-column artist is rejected — no deezer_id, still marked."""
        entry = _make_row(
            sync_session, "Track", "Wrong Artist", deezer_searched_at=None
        )
        _link_artist(sync_session, entry.id, "Right Artist", 0)

        # The only hit available names the flat-column artist (the X4.a bug: it
        # would have matched if we validated against catalog.artist).
        hit = {"id": 123, "title": "Track", "artist": {"name": "Wrong Artist"}}
        pool = _make_deezer_pool(hit)

        stats = await enrich_deezer_batch(sync_session, [entry], pool, None, set())

        assert entry.deezer_id is None  # rejected: wrong-artist hit not stamped
        assert stats == {"enriched": 0, "errors": 0, "merged": 0}
        assert isinstance(entry.deezer_searched_at, datetime)  # marked (not found)
        # The searcher received the M2M name, never the flat column.
        assert pool.queries and all("Right Artist" in q for q in pool.queries)
        assert not any("Wrong" in q for q in pool.queries)

    async def test_falls_back_to_flat_artist_without_m2m(self, sync_session):
        """No M2M link → validate against entry.artist (behavior preserved): a
        matching hit is accepted and its deezer_id stamped."""
        entry = _make_row(
            sync_session, "Track", "Solo Artist", deezer_searched_at=None
        )

        hit = {"id": 456, "title": "Track", "artist": {"name": "Solo Artist"}}
        pool = _make_deezer_pool(hit)

        stats = await enrich_deezer_batch(sync_session, [entry], pool, None, set())

        assert entry.deezer_id == "456"
        assert stats == {"enriched": 1, "errors": 0, "merged": 0}
        assert all("Solo Artist" in q for q in pool.queries)


# ── enrich_beatport_batch: validate against the M2M ───────────────────────────


class TestBeatportBatchM2m:
    async def test_uses_m2m_name_when_present(self, sync_session, monkeypatch):
        """The Beatport searcher is called with the M2M artist string, not the
        divergent flat catalog.artist."""
        search = AsyncMock(return_value=None)
        monkeypatch.setattr(enrichment_mod, "_search_beatport_async", search)
        monkeypatch.setattr(enrichment_mod, "_get_redis", lambda: None)

        entry = _make_row(sync_session, "Track", "Wrong Artist")
        _link_artist(sync_session, entry.id, "Right Artist", 0)

        await enrich_beatport_batch(sync_session, [entry], MagicMock(), None)

        # _search_beatport_async(pool, title, artist, isrc, rcache=...)
        assert search.call_args.args[2] == "Right Artist"

    async def test_falls_back_to_flat_artist_without_m2m(
        self, sync_session, monkeypatch
    ):
        """No M2M link → the searcher gets the flat catalog.artist (preserved)."""
        search = AsyncMock(return_value=None)
        monkeypatch.setattr(enrichment_mod, "_search_beatport_async", search)
        monkeypatch.setattr(enrichment_mod, "_get_redis", lambda: None)

        entry = _make_row(sync_session, "Track", "Solo Artist")

        await enrich_beatport_batch(sync_session, [entry], MagicMock(), None)

        assert search.call_args.args[2] == "Solo Artist"
