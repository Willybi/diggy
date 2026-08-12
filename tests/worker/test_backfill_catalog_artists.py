"""Tests for the X4.e OPS backfill (scripts/backfill_catalog_artists).

Two layers:
  - the pure decision helpers (``plan_artist_links`` / ``split_artist_names`` /
    ``looks_spaced_multi_artist`` / ``has_recognized_separator``) — network- and
    DB-free;
  - the engine ``backfill_catalog_artists`` against a real sync SQLite session
    (``sync_session`` fixture), reusing the enrichment helpers to resolve/create
    artists and write ``catalog_artists`` links.

Same import/path pattern as test_reverify_platform_ids.py. Importing the script
pulls ``workers.deezer_enrich`` (for the shared resolve/link helpers); that module
imports httpx/requests/services.image_service — all present in the test env
(requirements-test.txt), boto3 is stubbed by conftest.
"""
import itertools
import os
import sys

from sqlalchemy import func, select

# Make the workers package importable (same pattern as test_reverify_platform_ids.py).
_SERVER_PATH = os.path.join(os.path.dirname(__file__), "../../server")
if _SERVER_PATH not in sys.path:
    sys.path.insert(0, _SERVER_PATH)

from models import Artist, CatalogArtist, CatalogEntry  # noqa: E402
from utils import normalize  # noqa: E402

from scripts.backfill_catalog_artists import (  # noqa: E402
    backfill_catalog_artists,
    has_recognized_separator,
    looks_spaced_multi_artist,
    plan_artist_links,
    split_artist_names,
)

_nk = itertools.count(1)


def _cat(session, *, commit=True, **fields):
    """Insert a CatalogEntry with a unique normalized_key; return it."""
    n = next(_nk)
    entry = CatalogEntry(
        title=fields.pop("title", f"Track {n}"),
        artist=fields.pop("artist", f"Artist {n}"),
        normalized_key=fields.pop("normalized_key", f"nk-{n}"),
        **fields,
    )
    session.add(entry)
    session.commit() if commit else session.flush()
    return entry


def _artist(session, name):
    """Insert a pre-existing Artist (unique normalized_name); return it."""
    a = Artist(name=name, normalized_name=normalize(name))
    session.add(a)
    session.commit()
    return a


def _links(session, catalog_id):
    """catalog_artists rows for a catalog id, ordered by position."""
    return (
        session.execute(
            select(CatalogArtist)
            .where(CatalogArtist.catalog_id == catalog_id)
            .order_by(CatalogArtist.position)
        )
        .scalars()
        .all()
    )


# ── pure helpers ─────────────────────────────────────────────────────────────


class TestSplitNames:
    def test_ampersand(self):
        assert split_artist_names("Adam Beyer & Bart Skils") == ["Adam Beyer", "Bart Skils"]

    def test_comma_three(self):
        assert split_artist_names("A, B, C") == ["A", "B", "C"]

    def test_feat_and_ft(self):
        assert split_artist_names("Artist feat. Guest") == ["Artist", "Guest"]
        assert split_artist_names("DJ ft Other") == ["DJ", "Other"]

    def test_x_and_vs(self):
        assert split_artist_names("Adam Beyer x Bart Skils") == ["Adam Beyer", "Bart Skils"]
        assert split_artist_names("Solomun vs. Kevin") == ["Solomun", "Kevin"]

    def test_pipe_spaced_and_bare(self):
        # The '|' branch is the only addition over deezer_enrich._ARTIST_SPLIT.
        assert split_artist_names("A | B | C") == ["A", "B", "C"]
        assert split_artist_names("Oliver Ho|James Ruskin") == ["Oliver Ho", "James Ruskin"]

    def test_drops_empty_fragments(self):
        assert split_artist_names("A |  | B") == ["A", "B"]


class TestHasSeparator:
    def test_pipe_is_recognized(self):
        assert has_recognized_separator("A|B") is True

    def test_plain_name_has_none(self):
        assert has_recognized_separator("Carl Cox") is False
        # "Charli XCX": the X is inside a word, not a space-bounded " x " separator.
        assert has_recognized_separator("Charli XCX") is False


class TestSpacedLetters:
    def test_run_of_three_singletons_flagged(self):
        assert looks_spaced_multi_artist("t e s t p r e s s Kichta") is True
        assert looks_spaced_multi_artist("M A X") is True

    def test_normal_name_not_flagged(self):
        assert looks_spaced_multi_artist("Carl Cox") is False
        # A run of only two single-char tokens is below the threshold.
        assert looks_spaced_multi_artist("A B Someone") is False


class TestPlan:
    def test_separator_splits(self):
        assert plan_artist_links("Adam Beyer & Bart Skils") == (
            "split",
            ["Adam Beyer", "Bart Skils"],
        )

    def test_single_name(self):
        assert plan_artist_links("Carl Cox") == ("single", ["Carl Cox"])

    def test_spaced_letters_delegated(self):
        assert plan_artist_links("t e s t p r e s s Kichta") == (
            "delegate",
            "t e s t p r e s s Kichta",
        )

    def test_separator_wins_over_spaced_guard(self):
        # A separator gives an explicit boundary → split even if a side is stylized.
        kind, names = plan_artist_links("t e s t p r e s s & Kichta")
        assert kind == "split"
        assert names == ["t e s t p r e s s", "Kichta"]

    def test_separator_yielding_one_token_is_single(self):
        assert plan_artist_links("Foo,") == ("single", ["Foo"])

    def test_blank_is_delegated(self):
        assert plan_artist_links("   ") == ("delegate", "")


# ── engine: the four mandated scenarios ──────────────────────────────────────


class TestBackfillEngine:
    def test_a_separator_creates_ordered_links(self, sync_session):
        entry = _cat(sync_session, artist="Adam Beyer & Bart Skils")

        stats = backfill_catalog_artists(sync_session, apply=True)

        links = _links(sync_session, entry.id)
        assert [link.position for link in links] == [0, 1]
        assert all(link.role == "primary" for link in links)
        names = [sync_session.get(Artist, link.artist_id).name for link in links]
        assert names == ["Adam Beyer", "Bart Skils"]
        assert stats["linked_rows"] == 1
        assert stats["links_created"] == 2
        assert stats["artists_created"] == 2
        assert stats["artists_reused"] == 0
        assert stats["delegated_n3"] == 0

    def test_b_no_separator_single_link(self, sync_session):
        entry = _cat(sync_session, artist="Carl Cox")

        stats = backfill_catalog_artists(sync_session, apply=True)

        links = _links(sync_session, entry.id)
        assert len(links) == 1
        assert links[0].position == 0 and links[0].role == "primary"
        assert sync_session.get(Artist, links[0].artist_id).name == "Carl Cox"
        assert stats["linked_rows"] == 1 and stats["links_created"] == 1
        assert stats["delegated_n3"] == 0

    def test_c_spaced_letters_delegated_no_link(self, sync_session):
        entry = _cat(sync_session, artist="t e s t p r e s s Kichta")

        stats = backfill_catalog_artists(sync_session, apply=True)

        assert sync_session.execute(select(CatalogArtist)).scalars().all() == []
        assert stats["candidates"] == 1
        assert stats["linked_rows"] == 0
        assert stats["links_created"] == 0
        assert stats["delegated_n3"] == 1
        assert stats["delegated_examples"] == [(entry.id, "t e s t p r e s s Kichta")]

    def test_d_apply_is_idempotent(self, sync_session):
        _cat(sync_session, artist="Adam Beyer & Bart Skils")

        first = backfill_catalog_artists(sync_session, apply=True)
        assert first["linked_rows"] == 1 and first["links_created"] == 2
        count_after_first = sync_session.execute(
            select(func.count()).select_from(CatalogArtist)
        ).scalar_one()

        # Second run: the row now has links → it leaves the selection entirely.
        second = backfill_catalog_artists(sync_session, apply=True)
        assert second["candidates"] == 0
        assert second["links_created"] == 0
        count_after_second = sync_session.execute(
            select(func.count()).select_from(CatalogArtist)
        ).scalar_one()
        assert count_after_first == count_after_second == 2


# ── engine: resolution, selection, dedup, dry-run ────────────────────────────


class TestResolutionAndSelection:
    def test_reuses_existing_artist(self, sync_session):
        existing = _artist(sync_session, "Carl Cox")
        entry = _cat(sync_session, artist="Carl Cox")

        stats = backfill_catalog_artists(sync_session, apply=True)

        links = _links(sync_session, entry.id)
        assert len(links) == 1
        assert links[0].artist_id == existing.id  # linked to the pre-existing row
        assert stats["artists_created"] == 0
        assert stats["artists_reused"] == 1
        # No duplicate artist row was created.
        assert (
            sync_session.execute(select(func.count()).select_from(Artist)).scalar_one()
            == 1
        )

    def test_new_artist_shared_across_rows_created_once(self, sync_session):
        # Two rows reference the SAME not-yet-existing artist: created once, the
        # second reference is neither a fresh creation nor an existing-artist reuse.
        e1 = _cat(sync_session, artist="Nina Kraviz")
        e2 = _cat(sync_session, artist="Nina Kraviz")

        stats = backfill_catalog_artists(sync_session, apply=True)

        assert stats["links_created"] == 2
        assert stats["linked_rows"] == 2
        assert stats["artists_created"] == 1
        assert stats["artists_reused"] == 0
        a1 = _links(sync_session, e1.id)[0].artist_id
        a2 = _links(sync_session, e2.id)[0].artist_id
        assert a1 == a2  # both rows point at the one created artist

    def test_row_with_existing_link_is_skipped(self, sync_session):
        entry = _cat(sync_session, artist="Adam Beyer & Bart Skils")
        keeper = _artist(sync_session, "Someone Else")
        sync_session.add(
            CatalogArtist(
                catalog_id=entry.id, artist_id=keeper.id, role="primary", position=0
            )
        )
        sync_session.commit()

        stats = backfill_catalog_artists(sync_session, apply=True)

        # Already-linked → never a candidate; its single link is left untouched.
        assert stats["candidates"] == 0
        links = _links(sync_session, entry.id)
        assert len(links) == 1 and links[0].artist_id == keeper.id

    def test_empty_and_whitespace_artist_ignored(self, sync_session):
        _cat(sync_session, artist=None)
        _cat(sync_session, artist="")
        _cat(sync_session, artist="   ")

        stats = backfill_catalog_artists(sync_session, apply=True)

        assert stats["candidates"] == 0
        assert sync_session.execute(select(CatalogArtist)).scalars().all() == []

    def test_duplicate_name_within_string_links_once(self, sync_session):
        entry = _cat(sync_session, artist="Foo, Foo")

        stats = backfill_catalog_artists(sync_session, apply=True)

        links = _links(sync_session, entry.id)
        assert len(links) == 1  # the repeated name collapses to one link
        assert stats["links_created"] == 1


class TestDryRun:
    def test_dry_run_writes_nothing_but_counts(self, sync_session):
        _cat(sync_session, artist="Adam Beyer & Bart Skils")
        _cat(sync_session, artist="Carl Cox")
        _cat(sync_session, artist="t e s t p r e s s Kichta")
        artists_before = sync_session.execute(
            select(func.count()).select_from(Artist)
        ).scalar_one()

        stats = backfill_catalog_artists(sync_session, apply=False)

        # Counts describe what --apply WOULD do...
        assert stats["candidates"] == 3
        assert stats["linked_rows"] == 2
        assert stats["links_created"] == 3  # 2 (split) + 1 (single)
        assert stats["artists_created"] == 3
        assert stats["delegated_n3"] == 1
        # ...but nothing was written: no links, no new artists.
        assert sync_session.execute(select(CatalogArtist)).scalars().all() == []
        assert (
            sync_session.execute(select(func.count()).select_from(Artist)).scalar_one()
            == artists_before
        )

    def test_dry_run_counts_reuse_like_apply(self, sync_session):
        # An existing artist is counted as reused (not created) even in dry-run.
        _artist(sync_session, "Carl Cox")
        _cat(sync_session, artist="Carl Cox")

        stats = backfill_catalog_artists(sync_session, apply=False)

        assert stats["artists_created"] == 0
        assert stats["artists_reused"] == 1
        assert sync_session.execute(select(CatalogArtist)).scalars().all() == []
