"""Tests for the X4.b OPS resync (scripts/resync_catalog_artist).

Two layers:
  - the pure comparison helpers (``build_artist_string`` / ``is_franche_divergence``
    / ``classify_row``) — network- and DB-free;
  - the engine ``resync_catalog_artist`` against a real sync SQLite session
    (``sync_session`` fixture), building catalog rows + catalog_artists links and
    asserting only the frank-divergence "resync" rows get their flat rewritten while
    coherent and ambiguous rows are left intact.

Same import/path pattern as test_backfill_catalog_artists.py. Importing the script
pulls ``workers.deezer_enrich`` (for the shared ``_fold`` / ``_ARTIST_SPLIT``); that
module imports httpx/requests/services.image_service — all present in the test env,
boto3 is stubbed by conftest.
"""
import itertools
import os
import sys

from sqlalchemy import select

# Make the workers package importable (same pattern as test_backfill_catalog_artists.py).
_SERVER_PATH = os.path.join(os.path.dirname(__file__), "../../server")
if _SERVER_PATH not in sys.path:
    sys.path.insert(0, _SERVER_PATH)

from models import Artist, CatalogArtist, CatalogEntry  # noqa: E402
from utils import normalize  # noqa: E402

from scripts.resync_catalog_artist import (  # noqa: E402
    build_artist_string,
    classify_row,
    is_franche_divergence,
    resync_catalog_artist,
)

_nk = itertools.count(1)


# ── pure helpers ─────────────────────────────────────────────────────────────


class TestBuildArtistString:
    def test_orders_by_position(self):
        assert (
            build_artist_string([("Bart Skils", 1), ("Adam Beyer", 0)])
            == "Adam Beyer, Bart Skils"
        )

    def test_single_artist(self):
        assert build_artist_string([("Carl Cox", 0)]) == "Carl Cox"

    def test_null_positions_sort_last_then_by_name(self):
        # A legacy link with no position sorts AFTER the ordered ones; the two NULLs
        # tie-break deterministically by folded name.
        assert (
            build_artist_string([("Zoe", None), ("Amelie", None), ("Boris", 0)])
            == "Boris, Amelie, Zoe"
        )

    def test_strips_and_drops_blanks(self):
        assert build_artist_string([("  A  ", 0), ("", 1), ("  ", 2), ("B", 3)]) == "A, B"

    def test_empty_pairs_gives_empty_string(self):
        assert build_artist_string([]) == ""
        assert build_artist_string([("", 0), ("   ", 1)]) == ""


class TestIsFrancheDivergence:
    def test_identical_is_not_divergence(self):
        assert is_franche_divergence("Carl Cox", "Carl Cox") is False

    def test_case_and_accent_insensitive(self):
        # "Nick León" vs "Nick Leon" fold equal → contained → not a frank divergence.
        assert is_franche_divergence("Nick León", "nick leon") is False

    def test_whitespace_only_difference_is_not_divergence(self):
        assert is_franche_divergence("Adam  Beyer", "Adam Beyer") is False

    def test_containment_is_not_divergence(self):
        # The M2M merely adds a collaborator: the flat is a substring → coherent.
        assert is_franche_divergence("Adam Beyer", "Adam Beyer, Bart Skils") is False
        assert is_franche_divergence("Adam Beyer, Bart Skils", "Adam Beyer") is False

    def test_disjoint_is_divergence(self):
        assert is_franche_divergence("Various Artists", "Carl Cox") is True

    def test_reorder_is_divergence(self):
        # Same set, different order → neither is a substring of the other.
        assert is_franche_divergence("Bart Skils, Adam Beyer", "Adam Beyer, Bart Skils") is True

    def test_empty_side_is_never_divergence(self):
        assert is_franche_divergence("Carl Cox", "") is False
        assert is_franche_divergence("", "Carl Cox") is False


class TestClassifyRow:
    def test_identical_is_coherent(self):
        assert classify_row("Carl Cox", "Carl Cox") == "coherent"

    def test_containment_is_coherent(self):
        assert classify_row("Adam Beyer", "Adam Beyer, Bart Skils") == "coherent"

    def test_disjoint_is_resync(self):
        # Fully unrelated flat (stale junk) → trust the re-resolved M2M.
        assert classify_row("Unknown Artist", "Carl Cox") == "resync"

    def test_reorder_same_set_is_resync(self):
        # Same artists, reordered → resync to the M2M's position order.
        assert classify_row("Bart Skils, Adam Beyer", "Adam Beyer, Bart Skils") == "resync"

    def test_superset_m2m_is_resync(self):
        # M2M has all the flat's artists plus more, but a reorder breaks containment
        # → resync (nothing the flat carries is lost).
        assert classify_row("Bart Skils, Adam Beyer", "Adam Beyer, Carl Cox, Bart Skils") == "resync"

    def test_partial_overlap_is_ambiguous(self):
        # Share "Adam Beyer" but the flat carries "Someone Else" the M2M drops →
        # overwriting would lose it → ambiguous (invariant #4).
        assert classify_row("Adam Beyer, Someone Else", "Adam Beyer, Bart Skils") == "ambiguous"

    def test_m2m_partiel_is_ambiguous(self):
        # "M2M partiel": the M2M is a strict subset (dropped an artist) and reordered
        # so it is not a substring → ambiguous, do not blank the flat's extra artist.
        assert classify_row("Adam Beyer, Bart Skils, Carl Cox", "Carl Cox, Adam Beyer") == "ambiguous"


# ── engine ─────────────────────────────────────────────────────────────────


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
    """Insert (or reuse) an Artist with a unique normalized_name; return it."""
    norm = normalize(name)
    existing = session.execute(
        select(Artist).where(Artist.normalized_name == norm)
    ).scalar_one_or_none()
    if existing:
        return existing
    a = Artist(name=name, normalized_name=norm)
    session.add(a)
    session.commit()
    return a


def _link(session, catalog_id, name, position):
    """Create a catalog_artists link to a (resolved-or-created) artist by name."""
    artist = _artist(session, name)
    session.add(
        CatalogArtist(
            catalog_id=catalog_id, artist_id=artist.id, role="primary", position=position
        )
    )
    session.commit()


class TestEngineResync:
    def test_divergent_row_is_resynced(self, sync_session):
        row = _cat(sync_session, artist="Various Artists")
        _link(sync_session, row.id, "Adam Beyer", 0)
        _link(sync_session, row.id, "Bart Skils", 1)

        stats = resync_catalog_artist(sync_session, apply=True)

        assert stats["resync"] == 1
        assert stats["updated"] == 1
        assert sync_session.get(CatalogEntry, row.id).artist == "Adam Beyer, Bart Skils"

    def test_coherent_row_left_intact(self, sync_session):
        # Flat is a substring of the M2M (M2M more complete) → coherent, not touched.
        row = _cat(sync_session, artist="Adam Beyer")
        _link(sync_session, row.id, "Adam Beyer", 0)
        _link(sync_session, row.id, "Bart Skils", 1)

        stats = resync_catalog_artist(sync_session, apply=True)

        assert stats["resync"] == 0
        assert stats["coherent"] == 1
        assert sync_session.get(CatalogEntry, row.id).artist == "Adam Beyer"

    def test_ambiguous_row_left_intact(self, sync_session):
        # Partial overlap: flat carries "Someone Else" the M2M drops → ambiguous.
        row = _cat(sync_session, artist="Adam Beyer, Someone Else")
        _link(sync_session, row.id, "Adam Beyer", 0)
        _link(sync_session, row.id, "Bart Skils", 1)

        stats = resync_catalog_artist(sync_session, apply=True)

        assert stats["ambiguous"] == 1
        assert stats["resync"] == 0
        assert stats["updated"] == 0
        assert sync_session.get(CatalogEntry, row.id).artist == "Adam Beyer, Someone Else"

    def test_m2m_empty_row_ignored(self, sync_session):
        # No catalog_artists link → excluded by the INNER JOIN (lot X4.e's job).
        row = _cat(sync_session, artist="Solo Flat")

        stats = resync_catalog_artist(sync_session, apply=True)

        assert stats["considered"] == 0
        assert sync_session.get(CatalogEntry, row.id).artist == "Solo Flat"

    def test_dry_run_modifies_nothing(self, sync_session):
        row = _cat(sync_session, artist="Various Artists")
        _link(sync_session, row.id, "Adam Beyer", 0)
        _link(sync_session, row.id, "Bart Skils", 1)

        stats = resync_catalog_artist(sync_session, apply=False)

        assert stats["resync"] == 1
        assert stats["updated"] == 0
        assert sync_session.get(CatalogEntry, row.id).artist == "Various Artists"

    def test_apply_is_idempotent(self, sync_session):
        row = _cat(sync_session, artist="Various Artists")
        _link(sync_session, row.id, "Adam Beyer", 0)
        _link(sync_session, row.id, "Bart Skils", 1)

        first = resync_catalog_artist(sync_session, apply=True)
        assert first["resync"] == 1 and first["updated"] == 1

        second = resync_catalog_artist(sync_session, apply=True)
        assert second["resync"] == 0 and second["updated"] == 0
        assert sync_session.get(CatalogEntry, row.id).artist == "Adam Beyer, Bart Skils"
