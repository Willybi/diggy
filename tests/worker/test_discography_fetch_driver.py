"""Tests for the C14.a Phase 2 benchmark driver's PURE walk (fetch_driver.walk_discography).

Exercises the artist→albums→album-tracks walk with a FAKE Deezer pool and an injected
``key_fn`` / ``http_error`` class. Asserts: within-artist dedup by key (a recording on
a single AND its album counts once), the request count (~1 + nb albums, + 1/track under
with_isrc), the artist-name fallback chain (track → album → sampled), album-list outage
aborts only that artist, a single-album outage is skipped and the walk continues, and
the album-list pagination loop.

``fetch_driver`` is host-importable: its ``sys.path.insert(0, "/app")`` is harmless off
the container and its server imports are lazy (inside ``_run``), so ``walk_discography``
— which takes the pool + key_fn + http_error injected — needs no server modules.
"""
import asyncio
import os
import sys

_REPO_ROOT = os.path.join(os.path.dirname(__file__), "../../")
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from worker.discography_backfill import fetch_driver  # noqa: E402
from worker.discography_backfill.fetch_driver import walk_discography  # noqa: E402


class FakeDeezerError(Exception):
    """Stand-in for workers.async_http.DeezerHTTPError (injected as http_error)."""


def _key(title, artist):
    """A deterministic stand-in for make_normalized_key (title-first, ' - ' join)."""
    return f"{title.strip().lower()} - {artist.strip().lower()}"


class FakePool:
    """Routes deezer_get by path over canned responses; records every call.

    - albums_pages: list of ``{"data": [...], "next": <truthy|None>}`` pages, indexed by
      ``params["index"] // fetch_driver.PAGE``.
    - album_tracks: ``{album_id: {"tracks": {"data": [...], "next": None}, "artist": {...}}}``.
    - track_isrcs: ``{track_id: isrc}`` for the /track/{id} path.
    - fail_paths: substrings that should raise FakeDeezerError.
    """

    def __init__(self, albums_pages, album_tracks, track_isrcs=None, fail_paths=()):
        self.albums_pages = albums_pages
        self.album_tracks = album_tracks
        self.track_isrcs = track_isrcs or {}
        self.fail_paths = tuple(fail_paths)
        self.calls = []

    async def deezer_get(self, path, params=None):
        self.calls.append(path)
        for f in self.fail_paths:
            if f in path:
                raise FakeDeezerError(f"boom {path}")
        if path.endswith("/albums"):
            idx = (params or {}).get("index", 0) // fetch_driver.PAGE
            return self.albums_pages[idx] if idx < len(self.albums_pages) else {"data": [], "next": None}
        if "/tracks" in path:  # /album/{id}/tracks pagination
            return {"data": [], "next": None}
        if path.startswith("/album/"):
            return self.album_tracks[int(path.split("/album/")[1])]
        if path.startswith("/track/"):
            return {"isrc": self.track_isrcs.get(int(path.split("/track/")[1]))}
        raise AssertionError(f"unexpected path {path}")

    def count(self, needle):
        return sum(1 for c in self.calls if needle in c)


def _walk(pool, deezer_id="10", fallback="Fallback", with_isrc=False):
    return asyncio.run(
        walk_discography(pool, deezer_id, _key, fallback, with_isrc, FakeDeezerError)
    )


def _album(album_id, tracks, artist_name="AlbumArtist"):
    return {"tracks": {"data": tracks, "next": None}, "artist": {"name": artist_name}}


def _track(tid, title, artist_name):
    return {"id": tid, "title": title, "artist": {"name": artist_name}}


def test_walk_dedup_and_request_count():
    # 2 albums; the same recording (Cola/CamelPhat) appears on both → deduped to once.
    pages = [{"data": [{"id": 1}, {"id": 2}], "next": None}]
    albums = {
        1: _album(1, [_track(11, "Cola", "CamelPhat"), _track(12, "Breeze", "CamelPhat")]),
        2: _album(2, [_track(11, "Cola", "CamelPhat"), _track(13, "Rabbit", "CamelPhat")]),
    }
    pool = FakePool(pages, albums)
    res = _walk(pool)
    keys = {t["key"] for t in res["tracks"]}
    assert keys == {"cola - camelphat", "breeze - camelphat", "rabbit - camelphat"}
    assert res["n_tracks_distinct"] == 3
    assert res["n_tracks_raw"] == 4          # 4 raw rows across the 2 albums
    assert res["n_albums"] == 2
    assert res["n_requests"] == 3            # 1 albums-list + 2 album-details
    assert res["error"] is None
    assert all(t["isrc"] is None for t in res["tracks"])


def test_artist_name_fallback_chain():
    # track with no artist → album artist; album with no artist → sampled fallback.
    pages = [{"data": [{"id": 1}, {"id": 2}], "next": None}]
    albums = {
        1: _album(1, [{"id": 11, "title": "NoArtistTrack"}], artist_name="TheAlbumArtist"),
        2: {"tracks": {"data": [{"id": 21, "title": "OrphanTrack"}], "next": None}, "artist": {}},
    }
    pool = FakePool(pages, albums)
    res = _walk(pool, fallback="SampledArtist")
    keys = {t["key"] for t in res["tracks"]}
    assert "noartisttrack - thealbumartist" in keys   # album artist used
    assert "orphantrack - sampledartist" in keys      # sampled fallback used


def test_with_isrc_fetches_per_distinct_track():
    pages = [{"data": [{"id": 1}], "next": None}]
    albums = {1: _album(1, [_track(11, "A", "X"), _track(12, "B", "X")])}
    pool = FakePool(pages, albums, track_isrcs={11: "ISRC11", 12: "ISRC12"})
    res = _walk(pool, with_isrc=True)
    isrcs = {t["isrc"] for t in res["tracks"]}
    assert isrcs == {"ISRC11", "ISRC12"}
    # 1 albums + 1 album-detail + 2 /track = 4
    assert res["n_requests"] == 4
    assert pool.count("/track/") == 2


def test_albums_list_outage_aborts_only_this_artist():
    pool = FakePool([], {}, fail_paths=("/albums",))
    res = _walk(pool)
    assert res["tracks"] == []
    assert res["n_tracks_distinct"] == 0
    assert res["error"] and "albums:" in res["error"]
    assert res["n_requests"] == 1


def test_single_album_outage_is_skipped_and_walk_continues():
    pages = [{"data": [{"id": 1}, {"id": 2}], "next": None}]
    albums = {2: _album(2, [_track(21, "Good", "X")])}
    # album 1 detail raises; album 2 succeeds
    pool = FakePool(pages, albums, fail_paths=("/album/1",))
    res = _walk(pool)
    assert {t["key"] for t in res["tracks"]} == {"good - x"}
    assert res["error"] and "album 1:" in res["error"]
    # 1 albums-list + 1 failed album/1 + 1 album/2 = 3
    assert res["n_requests"] == 3


def test_albums_pagination(monkeypatch):
    # shrink the page size so 3 albums span two pages
    monkeypatch.setattr(fetch_driver, "PAGE", 2)
    pages = [
        {"data": [{"id": 1}, {"id": 2}], "next": "more"},   # full page + next → continue
        {"data": [{"id": 3}], "next": None},                # short page → stop
    ]
    albums = {
        1: _album(1, [_track(11, "T1", "X")]),
        2: _album(2, [_track(21, "T2", "X")]),
        3: _album(3, [_track(31, "T3", "X")]),
    }
    pool = FakePool(pages, albums)
    res = _walk(pool)
    assert res["n_albums"] == 3
    assert {t["key"] for t in res["tracks"]} == {"t1 - x", "t2 - x", "t3 - x"}
    # 2 albums-list pages + 3 album-details = 5
    assert res["n_requests"] == 5
    assert pool.count("/albums") == 2
