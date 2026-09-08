"""Tests for the async decision core (workers/set_artist_resolve).

Pure orchestration — the ONLY I/O is the injected ``deezer_verify`` coroutine, faked
here as a ``name → id`` dict wrapped in an async callable that ALSO records its calls
(so "base hit ⇒ Deezer not called" is directly observable). The lookup corpus is
SYNTHETIC ``(name, artist_id)`` pairs. ``asyncio_mode = "auto"`` (pyproject) lets the
``async def`` tests run without a decorator.

Coverage mirrors the C2c-2a contract: base-first resolution, Deezer only on a base
miss, an unresolved candidate links nothing (invariant #4), de-dup by artist_id, a
buried KNOWN artist recovered by the scan, and stable order.
"""

import os
import sys

# Make the workers package importable (same pattern as test_set_artist_link.py).
_SERVER_PATH = os.path.join(os.path.dirname(__file__), "../../server")
if _SERVER_PATH not in sys.path:
    sys.path.insert(0, _SERVER_PATH)

from workers.set_artist_link import build_artist_lookup  # noqa: E402
from workers.set_artist_resolve import (  # noqa: E402
    ResolvedArtist,
    resolve_link_artist_ids,
)


class _FakeDeezer:
    """An async ``name → id`` stand-in for the injected Deezer path, recording calls."""

    def __init__(self, mapping=None):
        self.mapping = mapping or {}
        self.calls = []

    async def __call__(self, name):
        self.calls.append(name)
        return self.mapping.get(name)


class TestBaseFirst:
    async def test_base_hit_never_calls_deezer(self):
        lookup = build_artist_lookup([("Ricardo Villalobos", 1)])
        deezer = _FakeDeezer({"Ricardo Villalobos": 999})  # must NOT be consulted
        out = await resolve_link_artist_ids(
            "Ricardo Villalobos - Live", "", lookup, deezer
        )
        assert out == [ResolvedArtist(1, "title", "Ricardo Villalobos")]
        assert deezer.calls == []  # base resolved it → no network path

    async def test_base_miss_falls_back_to_deezer(self):
        deezer = _FakeDeezer({"Unknownguy": 42})
        out = await resolve_link_artist_ids("Unknownguy", "", {}, deezer)
        assert out == [ResolvedArtist(42, "title", "Unknownguy")]
        assert deezer.calls == ["Unknownguy"]  # base miss → verified via Deezer


class TestUnresolvedLinksNothing:
    async def test_deezer_none_yields_no_link(self):
        deezer = _FakeDeezer({})  # confirms nothing
        out = await resolve_link_artist_ids("Nobody Knows Me", "", {}, deezer)
        assert out == []
        assert deezer.calls  # it WAS asked, and declined → invariant #4, no link


class TestDedup:
    async def test_same_artist_via_title_and_channel_once(self):
        # Two DISTINCT spellings (different fold keys, so the extractor keeps both)
        # pointing at the SAME id via aliases → collapsed to one link, first wins.
        lookup = build_artist_lookup([("Aphex Twin", 3), ("AFX", 3)])
        deezer = _FakeDeezer({})  # "Warehouse Rave" (track half) resolves to nothing
        out = await resolve_link_artist_ids(
            "Aphex Twin - Warehouse Rave", "AFX", lookup, deezer
        )
        assert out == [ResolvedArtist(3, "title", "Aphex Twin")]
        assert deezer.calls == ["Warehouse Rave"]  # only the unresolved fragment


class TestScanKnownArtists:
    async def test_buried_known_artist_included(self):
        # The extractor produces one long junk candidate that resolves to nothing;
        # the scan recovers the known 2-token artist buried inside the title.
        lookup = build_artist_lookup([("Nina Kraviz", 7)])
        deezer = _FakeDeezer({})
        out = await resolve_link_artist_ids(
            "Amazing Nina Kraviz At Fabric London", "", lookup, deezer
        )
        assert out == [ResolvedArtist(7, "title", "Nina Kraviz")]


class TestOrder:
    async def test_stable_order_title_then_channel(self):
        lookup = build_artist_lookup(
            [("Artist A", 1), ("Artist B", 2), ("Artist C", 3)]
        )
        deezer = _FakeDeezer({})
        out = await resolve_link_artist_ids(
            "Artist A b2b Artist B - Live Set", "Artist C", lookup, deezer
        )
        assert [r.artist_id for r in out] == [1, 2, 3]
        assert [r.source for r in out] == ["title", "title", "channel"]
        assert deezer.calls == []  # every candidate resolved in the base
