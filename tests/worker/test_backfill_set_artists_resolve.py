"""Tests for the C3 container resolver's PURE logic (resolve_driver.resolve_set_links).

Exercises the ordered/deduped base-vs-deezer resolution with a FAKE ``deezer_search``
and a REAL fold-key lookup (``workers.set_artist_link.build_artist_lookup``). Asserts:
a base hit emits a ``base`` link with the prod artist_id; a base miss confirmed by
Deezer emits a ``deezer`` link with the id; a base miss + Deezer miss emits no link;
per-space de-dup (base by artist_id, deezer by deezer_id); order preserved; the buried
KNOWN-artist scan is appended. It does NOT re-test the extractor/matcher internals
(those have their own tests) — only the driver's orchestration + emission shape.

Imports the local-tool module by putting the repo root on sys.path (the module's
server imports are lazy, so it imports cleanly; ``../../server`` gives the pure
workers.* deps the resolution reuses). redis/curl_cffi are mocked like the sibling
OPS test — the reused modules import them at load.
"""
import asyncio
import os
import sys
from unittest.mock import MagicMock

_REPO_ROOT = os.path.join(os.path.dirname(__file__), "../../")
_SERVER_PATH = os.path.join(os.path.dirname(__file__), "../../server")
for _p in (_REPO_ROOT, _SERVER_PATH):
    if _p not in sys.path:
        sys.path.insert(0, _p)

_saved_redis = sys.modules.get("redis")
sys.modules.setdefault("redis", MagicMock())
_saved_curl = sys.modules.get("curl_cffi")
sys.modules.setdefault("curl_cffi", MagicMock())

from workers.set_artist_link import build_artist_lookup  # noqa: E402

from worker.set_artist_backfill.resolve_driver import resolve_set_links  # noqa: E402

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


def _run(coro):
    return asyncio.run(coro)


def _fake_deezer(mapping):
    """An async ``deezer_search(name) -> deezer_id | None`` from a name->id dict."""

    async def search(name):
        return mapping.get(name)

    return search


def test_base_hit_emits_base_link():
    lookup = build_artist_lookup([("Bicep", 42)])
    links = _run(
        resolve_set_links("Bicep - Live at X", None, lookup, _fake_deezer({}))
    )
    assert {"source": "base", "name": "Bicep", "artist_id": 42} in links
    # No deezer_search hit was needed for a base match.
    assert all(link["source"] == "base" for link in links)


def test_base_miss_confirmed_by_deezer_emits_deezer_link():
    lookup = build_artist_lookup([])  # empty base → every candidate is a base miss
    search = _fake_deezer({"Peggy Gou": "555"})
    links = _run(resolve_set_links("Peggy Gou - Boiler Room", None, lookup, search))
    assert {"source": "deezer", "name": "Peggy Gou", "deezer_id": "555"} in links


def test_base_miss_and_deezer_miss_emits_no_link():
    lookup = build_artist_lookup([])
    links = _run(
        resolve_set_links("Totally Unknown DJ", None, lookup, _fake_deezer({}))
    )
    assert links == []


def test_base_takes_priority_over_deezer():
    # A candidate that resolves in the base must NOT trigger a Deezer search.
    lookup = build_artist_lookup([("Four Tet", 7)])
    called = []

    async def search(name):
        called.append(name)
        return "should-not-be-used"

    links = _run(resolve_set_links("Four Tet", None, lookup, search))
    assert links == [{"source": "base", "name": "Four Tet", "artist_id": 7}]
    assert called == []  # base hit → Deezer never consulted


def test_dedup_base_by_artist_id_and_deezer_by_id():
    # Channel duplicates the title artist; the second occurrence must not re-link.
    lookup = build_artist_lookup([("Bonobo", 3)])
    links = _run(resolve_set_links("Bonobo - Set", "Bonobo", lookup, _fake_deezer({})))
    base_ids = [link["artist_id"] for link in links if link["source"] == "base"]
    assert base_ids.count(3) == 1


def test_deezer_dedup_across_candidates():
    lookup = build_artist_lookup([])
    # Two different candidate names resolving to the SAME deezer id → one link.
    search = _fake_deezer({"A": "100", "B": "100"})
    links = _run(resolve_set_links("A & B", None, lookup, search))
    deezer_ids = [link["deezer_id"] for link in links if link["source"] == "deezer"]
    assert deezer_ids == ["100"]


def test_buried_known_artist_is_appended():
    # A multi-token known artist buried in a free-text title is recovered by the scan.
    lookup = build_artist_lookup([("Ricardo Villalobos", 88)])
    links = _run(
        resolve_set_links(
            "Ricardo Villalobos Recorded Live From Fabric",
            None,
            lookup,
            _fake_deezer({}),
        )
    )
    assert any(
        link["source"] == "base" and link["artist_id"] == 88 for link in links
    )
