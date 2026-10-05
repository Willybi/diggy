"""Tests for the C14.a Phase 2 backfill driver's PURE walk (bundle_driver.walk_and_bundle).

Exercises the artist→albums→album-tracks walk + NET-NEW classification against a keyset +
the per-net-new ``/track/{id}`` fetch, with a FAKE Deezer pool and an injected ``key_fn`` /
``http_error``. Asserts: a track whose key is in the catalog keyset is skipped (in base),
a net-new key triggers exactly one ``/track`` fetch, within-artist dedup by key, the
request count, and outage handling (album-list abort vs single-track skip).

``bundle_driver`` imports its sibling ``fetch_driver`` (both host-importable: their
``sys.path.insert(0, "/app")`` is harmless off the container and server imports are lazy).
"""
import asyncio
import os
import sys

_REPO_ROOT = os.path.join(os.path.dirname(__file__), "../../")
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from worker.discography_backfill import fetch_driver  # noqa: E402
from worker.discography_backfill.bundle_driver import walk_and_bundle  # noqa: E402


class FakeDeezerError(Exception):
    """Stand-in for workers.async_http.DeezerHTTPError (injected as http_error)."""


def _key(title, artist):
    return f"{title.strip().lower()} - {artist.strip().lower()}"


class FakePool:
    """Routes deezer_get by path: /albums pages, /album/{id} tracklists, /track/{id} hits."""

    def __init__(self, albums_pages, album_tracks, track_full=None, fail_paths=()):
        self.albums_pages = albums_pages
        self.album_tracks = album_tracks
        self.track_full = track_full or {}
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
        if "/tracks" in path:
            return {"data": [], "next": None}
        if path.startswith("/album/"):
            return self.album_tracks[int(path.split("/album/")[1])]
        if path.startswith("/track/"):
            return self.track_full[int(path.split("/track/")[1])]
        raise AssertionError(f"unexpected path {path}")

    def count(self, needle):
        return sum(1 for c in self.calls if needle in c)


def _walk(pool, keyset, deezer_id="10", fallback="Fallback"):
    return asyncio.run(
        walk_and_bundle(pool, deezer_id, _key, keyset, fallback, FakeDeezerError)
    )


def _album(album_id, tracks, artist_name="X"):
    return {"tracks": {"data": tracks, "next": None}, "artist": {"name": artist_name}}


def _track(tid, title, artist_name="X"):
    return {"id": tid, "title": title, "artist": {"name": artist_name}}


def _full(tid, title, isrc, artist_name="X"):
    return {"id": tid, "title": title, "isrc": isrc, "artist": {"name": artist_name},
            "album": {"id": 1, "title": "Alb"}}


def test_only_net_new_are_fetched():
    # album has 3 distinct tracks; one is already in base (keyset) → 2 net-new fetched
    pages = [{"data": [{"id": 1}], "next": None}]
    albums = {1: _album(1, [_track(11, "InBase"), _track(12, "NewA"), _track(13, "NewB")])}
    keyset = {"inbase - x"}
    full = {12: _full(12, "NewA", "ISRC12"), 13: _full(13, "NewB", "ISRC13")}
    pool = FakePool(pages, albums, track_full=full)
    res = _walk(pool, keyset)
    assert res["n_net_new"] == 2
    titles = {t["title"] for t in res["tracks"]}
    assert titles == {"NewA", "NewB"}
    assert pool.count("/track/") == 2                 # only the 2 net-new fetched
    assert pool.count("/album/") == 1
    # 1 albums-list + 1 album-detail + 2 /track = 4
    assert res["n_requests"] == 4
    assert res["error"] is None


def test_within_artist_dedup_before_fetch():
    # same recording on 2 albums → deduped to one net-new, fetched once
    pages = [{"data": [{"id": 1}, {"id": 2}], "next": None}]
    albums = {
        1: _album(1, [_track(11, "Dup")]),
        2: _album(2, [_track(11, "Dup")]),
    }
    pool = FakePool(pages, albums, track_full={11: _full(11, "Dup", "I")})
    res = _walk(pool, set())
    assert res["n_net_new"] == 1
    assert pool.count("/track/") == 1


def test_all_in_base_fetches_nothing():
    pages = [{"data": [{"id": 1}], "next": None}]
    albums = {1: _album(1, [_track(11, "A"), _track(12, "B")])}
    keyset = {"a - x", "b - x"}
    pool = FakePool(pages, albums)
    res = _walk(pool, keyset)
    assert res["n_net_new"] == 0
    assert res["tracks"] == []
    assert pool.count("/track/") == 0


def test_albums_list_outage_aborts_artist():
    pool = FakePool([], {}, fail_paths=("/albums",))
    res = _walk(pool, set())
    assert res["tracks"] == [] and res["n_net_new"] == 0
    assert res["error"] and "albums:" in res["error"]
    assert res["n_requests"] == 1


def test_single_track_outage_skipped():
    pages = [{"data": [{"id": 1}], "next": None}]
    albums = {1: _album(1, [_track(11, "Good"), _track(12, "Bad")])}
    full = {11: _full(11, "Good", "I11")}          # /track/12 will raise
    pool = FakePool(pages, albums, track_full=full, fail_paths=("/track/12",))
    res = _walk(pool, set())
    assert {t["title"] for t in res["tracks"]} == {"Good"}
    assert res["error"] and "track 12:" in res["error"]
