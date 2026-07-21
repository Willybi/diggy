"""Tests for the X1/L2 collision prevention wired into the enrichment writes.

Before an enrichment function stamps a platform id (deezer_id/beatport_id), it
inspects the pre-existing rows already carrying that id. It folds the current row
ONLY into a holder that ``same_track`` confirms is the same recording (raising
``CatalogEntryMerged`` so the batch loop counts it and skips the dead row's
post-processing). When the holder is a distinct recording merely sharing the id
(a remix / EP track), it does NOT merge and does NOT raise — the two rows coexist
under one platform id (id-uniqueness on catalog is abandoned, X1-FIX). Uses a
real sync SQLite session (sync_session fixture) so the merge SQL actually
executes.
"""
import os
import sys
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy import select

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

import pytest  # noqa: E402

import workers.enrichment as enrichment_mod  # noqa: E402
from workers.enrichment import (  # noqa: E402
    _enrich_entry_async,
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

from beatport.enrich import enrich_from_beatport  # noqa: E402
from models import CatalogEntry  # noqa: E402
from workers.catalog_merge import CatalogEntryMerged  # noqa: E402
from workers.deezer_enrich import enrich_entry  # noqa: E402


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


# ── Deezer collision ──────────────────────────────────────────────────────────


class TestDeezerCollision:
    async def test_enrich_entry_async_folds_and_raises(self, sync_session):
        """A deezer_id already held by another row → merge + CatalogEntryMerged.

        The loser's metadata is unioned onto the canonical and the loser row is
        deleted; the canonical (pre-existing) always wins.
        """
        # Same title on both rows → same_track confirms the recording identity.
        canonical = _make_row(sync_session, "Canon", "A", deezer_id="123")
        loser = _make_row(sync_session, "Canon", "B", duration_ms=200_000)
        loser_id = loser.id
        hit = {"id": 123, "isrc": None, "preview": ""}

        with pytest.raises(CatalogEntryMerged) as exc:
            await _enrich_entry_async(
                loser, hit, MagicMock(), None, set(), session=sync_session
            )

        assert exc.value.surviving_id == canonical.id
        # Loser removed, canonical kept and NULL-filled from the loser.
        assert (
            sync_session.execute(
                select(CatalogEntry).where(CatalogEntry.id == loser_id)
            ).scalar_one_or_none()
            is None
        )
        survivor = sync_session.get(CatalogEntry, canonical.id)
        assert survivor.deezer_id == "123"
        assert survivor.duration_ms == 200_000  # unified from the loser

    async def test_no_collision_assigns_deezer_id(self, sync_session):
        """No other row holds the id → plain assignment, no exception."""
        entry = _make_row(sync_session, "Solo", "A")

        changed = await _enrich_entry_async(
            entry,
            {"id": 999, "isrc": None, "preview": ""},
            MagicMock(),
            None,
            set(),
            session=sync_session,
        )

        assert changed is True
        assert entry.deezer_id == "999"
        assert sync_session.get(CatalogEntry, entry.id) is not None

    async def test_batch_counts_merged_and_skips_post_processing(self, sync_session):
        """enrich_deezer_batch: a folded row is counted under `merged`, not
        `enriched`, and its dead row is neither marked nor kept."""
        canonical = _make_row(sync_session, "Canon", "A", deezer_id="555")
        loser = _make_row(sync_session, "Canon", "B", deezer_searched_at=None)
        loser_id = loser.id

        pool = MagicMock()
        pool.deezer_get = AsyncMock(
            return_value={"id": 555, "isrc": None, "preview": ""}
        )

        stats = await enrich_deezer_batch(
            sync_session,
            [loser],
            pool,
            None,
            set(),
            source="deezer",
            ext_id_map={loser_id: "555"},
        )

        assert stats == {"enriched": 0, "errors": 0, "merged": 1}
        # Dead row gone; canonical intact and never re-searched (post-processing
        # skipped: _mark_searched was not called on it).
        assert (
            sync_session.execute(
                select(CatalogEntry).where(CatalogEntry.id == loser_id)
            ).scalar_one_or_none()
            is None
        )
        survivor = sync_session.get(CatalogEntry, canonical.id)
        assert survivor.deezer_id == "555"
        assert survivor.deezer_searched_at is None

    def test_sync_enrich_entry_folds_and_raises(self, sync_session):
        """The sync twin (workers.deezer_enrich.enrich_entry) behaves identically
        when a session is passed and merge_on_collision is left on (default)."""
        canonical = _make_row(sync_session, "Canon", "A", deezer_id="321")
        loser = _make_row(sync_session, "Canon", "B")
        loser_id = loser.id

        with pytest.raises(CatalogEntryMerged) as exc:
            enrich_entry(loser, {"id": 321}, session=sync_session)

        assert exc.value.surviving_id == canonical.id
        assert (
            sync_session.execute(
                select(CatalogEntry).where(CatalogEntry.id == loser_id)
            ).scalar_one_or_none()
            is None
        )

    def test_merge_off_keeps_both_rows(self, sync_session):
        """merge_on_collision=False (the _crawl_track deferral) preserves the old
        dup-blind behavior: the id is stamped and no merge/exception occurs."""
        _make_row(sync_session, "Canon", "A", deezer_id="321")
        loser = _make_row(sync_session, "Dup", "B")

        changed = enrich_entry(
            loser, {"id": 321}, session=sync_session, merge_on_collision=False
        )

        assert changed is True
        assert loser.deezer_id == "321"
        # Both rows survive — no fold happened.
        rows = (
            sync_session.execute(
                select(CatalogEntry).where(CatalogEntry.deezer_id == "321")
            )
            .scalars()
            .all()
        )
        assert len(rows) == 2

    def test_remix_collision_does_not_merge(self, sync_session):
        """Same deezer_id but a DISTINCT recording — the remix inherited the
        original's id via the Deezer hits[0] bug. No merge, no exception; both
        rows keep the id (uniqueness is abandoned by design)."""
        original = _make_row(
            sync_session, "Meridian", "A", deezer_id="123", isrc="ISRC-ORIG"
        )
        remix = _make_row(sync_session, "Meridian (Julian Muller Remix)", "A")
        remix_id = remix.id

        changed = enrich_entry(remix, {"id": 123}, session=sync_session)

        assert changed is True
        assert remix.deezer_id == "123"
        assert sync_session.get(CatalogEntry, remix_id) is not None
        rows = (
            sync_session.execute(
                select(CatalogEntry).where(CatalogEntry.deezer_id == "123")
            )
            .scalars()
            .all()
        )
        assert {r.id for r in rows} == {original.id, remix_id}


# ── Beatport collision ──────────────────────────────────────────────────────────


class TestBeatportCollision:
    def test_enrich_from_beatport_folds_and_raises(self, sync_session):
        canonical = _make_row(sync_session, "Canon", "A", beatport_id="777")
        loser = _make_row(sync_session, "Canon", "B")
        loser_id = loser.id

        with pytest.raises(CatalogEntryMerged) as exc:
            enrich_from_beatport(loser, {"id": 777}, session=sync_session)

        assert exc.value.surviving_id == canonical.id
        assert (
            sync_session.execute(
                select(CatalogEntry).where(CatalogEntry.id == loser_id)
            ).scalar_one_or_none()
            is None
        )
        assert sync_session.get(CatalogEntry, canonical.id).beatport_id == "777"

    def test_no_collision_assigns_beatport_id(self, sync_session):
        entry = _make_row(sync_session, "Solo", "A")

        changed = enrich_from_beatport(entry, {"id": 888}, session=sync_session)

        assert changed is True
        assert entry.beatport_id == "888"
        assert sync_session.get(CatalogEntry, entry.id) is not None

    async def test_batch_counts_merged_and_skips_mark(self, sync_session, monkeypatch):
        canonical = _make_row(sync_session, "Canon", "A", beatport_id="999")
        loser = _make_row(sync_session, "Canon", "B", beatport_searched_at=None)
        loser_id = loser.id

        monkeypatch.setattr(enrichment_mod, "_get_redis", lambda: None)
        monkeypatch.setattr(
            enrichment_mod,
            "_search_beatport_async",
            AsyncMock(return_value={"id": 999}),
        )

        stats = await enrich_beatport_batch(sync_session, [loser], MagicMock(), None)

        assert stats == {"enriched": 0, "not_found": 0, "errors": 0, "merged": 1}
        assert (
            sync_session.execute(
                select(CatalogEntry).where(CatalogEntry.id == loser_id)
            ).scalar_one_or_none()
            is None
        )
        assert sync_session.get(CatalogEntry, canonical.id).beatport_searched_at is None

    def test_ep_track_collision_does_not_merge(self, sync_session):
        """Same beatport_id but a DISTINCT recording — the Beatport release
        fallback stamps one id on every EP track. No merge, no exception; both
        remix rows coexist under the shared id."""
        remix_a = _make_row(
            sync_session, "Funk Solo (Batu Remix)", "A", beatport_id="EP1"
        )
        remix_b = _make_row(sync_session, "Funk Solo (Shed Remix)", "A")
        remix_b_id = remix_b.id

        changed = enrich_from_beatport(remix_b, {"id": "EP1"}, session=sync_session)

        assert changed is True
        assert remix_b.beatport_id == "EP1"
        assert sync_session.get(CatalogEntry, remix_b_id) is not None
        rows = (
            sync_session.execute(
                select(CatalogEntry).where(CatalogEntry.beatport_id == "EP1")
            )
            .scalars()
            .all()
        )
        assert {r.id for r in rows} == {remix_a.id, remix_b_id}
