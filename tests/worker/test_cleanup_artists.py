"""Tests for the L4 OPS cleanup (scripts/cleanup_artists).

Two layers:
  - the pure decision helper ``decide_cluster`` — network- and DB-free (the dupe
    cluster verdict, including the fan-dominance STRETCH branch, exercised with a
    plain fans dict, no network);
  - the two engine passes (``run_noise_pass`` / ``run_dupes_pass``) against a real
    sync SQLite session (``sync_session`` fixture), building attached artists +
    catalog_artists / set_artists links and asserting renames / merges / flat
    rewrites happen only where they should (and NOT at all in dry-run, idempotent on
    a second --apply).

Same import/path pattern as test_backfill_catalog_artists.py. The script only pulls
``models`` / ``utils`` / ``workers.artist_merge`` / ``workers.artist_names`` — none
need celery/redis — so no sys.modules stubbing is required (boto3 is stubbed by the
conftest anyway).
"""
import itertools
import os
import sys

from sqlalchemy import func, select

# Make the workers package importable (same pattern as test_backfill_catalog_artists.py).
_SERVER_PATH = os.path.join(os.path.dirname(__file__), "../../server")
if _SERVER_PATH not in sys.path:
    sys.path.insert(0, _SERVER_PATH)

from models import Artist, CatalogArtist, CatalogEntry, DJSet, SetArtist  # noqa: E402
from utils import normalize  # noqa: E402

from scripts.cleanup_artists import (  # noqa: E402
    Member,
    decide_cluster,
    run_dupes_pass,
    run_noise_pass,
)

_nk = itertools.count(1)


# ── fixtures / builders ──────────────────────────────────────────────────────


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


def _artist(session, name, deezer_id=None):
    """Insert an Artist with a unique normalized_name; return it."""
    a = Artist(name=name, normalized_name=normalize(name), deezer_id=deezer_id)
    session.add(a)
    session.commit()
    return a


def _attach_cat(session, artist, *, flat="unrelated flat"):
    """Attach ``artist`` to a fresh catalog row via catalog_artists; return the row.

    The catalog row's own flat ``artist`` is deliberately unrelated so it is not
    swept by the noise pass's flat rewrite (which matches the noisy name verbatim).
    """
    entry = _cat(session, artist=flat)
    session.add(
        CatalogArtist(
            catalog_id=entry.id, artist_id=artist.id, role="primary", position=0
        )
    )
    session.commit()
    return entry


def _attach_set(session, artist):
    """Attach ``artist`` to a fresh DJ set via set_artists; return the set."""
    n = next(_nk)
    dj_set = DJSet(source="trackid", title=f"Set {n}")
    session.add(dj_set)
    session.flush()
    session.add(SetArtist(set_id=dj_set.id, artist_id=artist.id, role="primary", position=0))
    session.commit()
    return dj_set


def _cat_links(session, catalog_id):
    return (
        session.execute(
            select(CatalogArtist).where(CatalogArtist.catalog_id == catalog_id)
        )
        .scalars()
        .all()
    )


def _m(id, name, deezer_id=None):
    return Member(id=id, name=name, deezer_id=deezer_id)


# ── pure decision: decide_cluster ────────────────────────────────────────────


class TestDecideCluster:
    def test_one_linked_plus_null_merges(self):
        # Exactly one Deezer-linked row + a NULL twin, no acronym → safe auto-merge.
        linked = _m(1, "St. Germain", deezer_id="42")
        orphan = _m(2, "St Germain")
        d = decide_cluster([linked, orphan], "st germain")
        assert d.action == "merge"
        assert d.reason == "one_linked_nulls"
        assert d.canonical_id == 1
        assert d.source_ids == [2]

    def test_multiple_nulls_all_merge_into_the_linked(self):
        linked = _m(1, "Mr. Oizo", deezer_id="7")
        a = _m(2, "Mr Oizo")
        b = _m(3, "Mr.Oizo")
        d = decide_cluster([linked, a, b], "mr oizo")
        assert d.action == "merge"
        assert d.canonical_id == 1
        assert sorted(d.source_ids) == [2, 3]

    def test_two_linked_distinct_is_flagged(self):
        a = _m(1, "St. Germain", deezer_id="42")
        b = _m(2, "St Germain", deezer_id="99")  # a DIFFERENT real artist, same fold
        d = decide_cluster([a, b], "st germain")
        assert d.action == "flag"
        assert d.reason == "multi_linked"
        assert d.source_ids == []

    def test_acronym_member_is_flagged(self):
        # "N.E.R.D." folds to a short letter run → the acronym guard flags the cluster
        # even though it is otherwise a clean 1-linked + 1-NULL shape.
        linked = _m(1, "N.E.R.D.", deezer_id="5")
        orphan = _m(2, "N.E.R.D")
        d = decide_cluster([linked, orphan], "nerd")
        assert d.action == "flag"
        assert d.reason == "acronym"

    def test_no_linked_row_is_flagged(self):
        a = _m(1, "St. Germain")
        b = _m(2, "St Germain")
        d = decide_cluster([a, b], "st germain")
        assert d.action == "flag"
        assert d.reason == "no_linked"

    def test_one_linked_with_not_found_sentinel_is_flagged(self):
        # A NOT_FOUND sibling makes the cluster mixed → not a clean twin merge.
        linked = _m(1, "St. Germain", deezer_id="42")
        sentinel = _m(2, "St Germain", deezer_id="NOT_FOUND")
        d = decide_cluster([linked, sentinel], "st germain")
        assert d.action == "flag"
        assert d.reason == "one_linked_mixed"

    def test_fans_stretch_dominant_merges(self):
        # STRETCH: with a fans map, a confidently dominant linked row absorbs the rest.
        a = _m(1, "St. Germain", deezer_id="1")
        b = _m(2, "St Germain", deezer_id="2")
        d = decide_cluster([a, b], "st germain", fans={"1": 50_000, "2": 100})
        assert d.action == "merge"
        assert d.reason == "fan_dominant"
        assert d.canonical_id == 1
        assert d.source_ids == [2]

    def test_fans_stretch_no_dominance_flags(self):
        a = _m(1, "St. Germain", deezer_id="1")
        b = _m(2, "St Germain", deezer_id="2")
        # 5000 vs 4000: below the 10x ratio → no confident dominance → flag.
        d = decide_cluster([a, b], "st germain", fans={"1": 5000, "2": 4000})
        assert d.action == "flag"
        assert d.reason == "multi_linked"


# ── engine: noise pass ───────────────────────────────────────────────────────


class TestNoisePass:
    def test_pro_suffix_renamed_in_place(self, sync_session):
        noisy = _artist(sync_session, "Ioannis Siopis (GEMA)")
        _attach_cat(sync_session, noisy)
        # A catalog row whose flat artist is the noisy string → rewritten to clean.
        flat_row = _cat(sync_session, artist="Ioannis Siopis (GEMA)")

        stats = run_noise_pass(sync_session, apply=True)

        assert stats["renamed"] == 1
        assert stats["merged"] == 0
        assert stats["flat_updated"] == 1
        refreshed = sync_session.get(Artist, noisy.id)
        assert refreshed.name == "Ioannis Siopis"
        assert refreshed.normalized_name == normalize("Ioannis Siopis")
        assert sync_session.get(CatalogEntry, flat_row.id).artist == "Ioannis Siopis"

    def test_bullet_prefix_via_set_attachment(self, sync_session):
        # Attachment through set_artists (not catalog_artists) still selects the row.
        noisy = _artist(sync_session, "Vinyl • Harvey Mason")
        _attach_set(sync_session, noisy)

        stats = run_noise_pass(sync_session, apply=True)

        assert stats["renamed"] == 1
        assert sync_session.get(Artist, noisy.id).name == "Harvey Mason"

    def test_merges_into_existing_clean_twin(self, sync_session):
        twin = _artist(sync_session, "Ioannis Siopis")  # holds the clean norm already
        noisy = _artist(sync_session, "Ioannis Siopis (GEMA)")
        entry = _attach_cat(sync_session, noisy)

        stats = run_noise_pass(sync_session, apply=True)

        assert stats["merged"] == 1
        assert stats["renamed"] == 0
        # The noisy row is gone; its catalog link now points at the clean twin.
        assert sync_session.get(Artist, noisy.id) is None
        links = _cat_links(sync_session, entry.id)
        assert len(links) == 1 and links[0].artist_id == twin.id

    def test_unattached_noisy_artist_is_ignored(self, sync_session):
        noisy = _artist(sync_session, "Vinyl • Harvey Mason")  # NOT attached

        stats = run_noise_pass(sync_session, apply=True)

        assert stats["renamed"] == 0 and stats["merged"] == 0
        assert sync_session.get(Artist, noisy.id).name == "Vinyl • Harvey Mason"

    def test_clean_name_is_untouched(self, sync_session):
        clean = _artist(sync_session, "Carl Cox")
        _attach_cat(sync_session, clean)

        stats = run_noise_pass(sync_session, apply=True)

        assert stats["renamed"] == 0 and stats["merged"] == 0

    def test_dry_run_writes_nothing_but_counts(self, sync_session):
        noisy = _artist(sync_session, "Ioannis Siopis (GEMA)")
        _attach_cat(sync_session, noisy)
        flat_row = _cat(sync_session, artist="Ioannis Siopis (GEMA)")

        stats = run_noise_pass(sync_session, apply=False)

        assert stats["renamed"] == 1
        assert stats["flat_updated"] == 1
        # ...but nothing was actually written.
        assert sync_session.get(Artist, noisy.id).name == "Ioannis Siopis (GEMA)"
        assert sync_session.get(CatalogEntry, flat_row.id).artist == "Ioannis Siopis (GEMA)"

    def test_apply_is_idempotent(self, sync_session):
        noisy = _artist(sync_session, "Ioannis Siopis (GEMA)")
        _attach_cat(sync_session, noisy)

        first = run_noise_pass(sync_session, apply=True)
        assert first["renamed"] == 1

        second = run_noise_pass(sync_session, apply=True)
        assert second["renamed"] == 0 and second["merged"] == 0
        assert second["flat_updated"] == 0

    def test_two_noisy_rows_cleaning_to_same_name_rename_then_merge(self, sync_session):
        # Two distinct noisy spellings collapse to one clean name: the first renames,
        # the second collides on the unique norm and MERGES into it instead.
        a = _artist(sync_session, "Ioannis Siopis (GEMA)")
        b = _artist(sync_session, "Ioannis Siopis (ASCAP)")
        _attach_cat(sync_session, a)
        _attach_cat(sync_session, b)

        stats = run_noise_pass(sync_session, apply=True)

        assert stats["renamed"] == 1
        assert stats["merged"] == 1
        # Exactly one "Ioannis Siopis" artist survives.
        survivors = (
            sync_session.execute(
                select(Artist).where(Artist.normalized_name == normalize("Ioannis Siopis"))
            )
            .scalars()
            .all()
        )
        assert len(survivors) == 1


# ── engine: dupes pass ───────────────────────────────────────────────────────


class TestDupesPass:
    def test_null_twin_folds_into_linked_canonical(self, sync_session):
        linked = _artist(sync_session, "St. Germain", deezer_id="42")
        orphan = _artist(sync_session, "St Germain")  # deezer_id NULL
        _attach_cat(sync_session, linked)
        orphan_entry = _attach_cat(sync_session, orphan)

        stats = run_dupes_pass(sync_session, apply=True)

        assert stats["merged"] == 1
        assert stats["link_recovered"] == 1
        assert stats["flagged"] == 0
        # The orphan is gone; its catalog link moved to the linked canonical.
        assert sync_session.get(Artist, orphan.id) is None
        links = _cat_links(sync_session, orphan_entry.id)
        assert len(links) == 1 and links[0].artist_id == linked.id

    def test_two_linked_cluster_is_flagged_not_merged(self, sync_session):
        a = _artist(sync_session, "St. Germain", deezer_id="42")
        b = _artist(sync_session, "St Germain", deezer_id="99")
        _attach_cat(sync_session, a)
        _attach_cat(sync_session, b)

        stats = run_dupes_pass(sync_session, apply=True)

        assert stats["merged"] == 0
        assert stats["flagged"] == 1
        assert stats["flags"][0].reason == "multi_linked"
        # Both rows survive untouched.
        assert sync_session.get(Artist, a.id) is not None
        assert sync_session.get(Artist, b.id) is not None

    def test_acronym_cluster_is_flagged(self, sync_session):
        linked = _artist(sync_session, "N.E.R.D.", deezer_id="5")
        orphan = _artist(sync_session, "N.E.R.D")
        _attach_cat(sync_session, linked)
        _attach_cat(sync_session, orphan)

        stats = run_dupes_pass(sync_session, apply=True)

        assert stats["merged"] == 0
        assert stats["flagged"] == 1
        assert stats["flags"][0].reason == "acronym"
        assert sync_session.get(Artist, orphan.id) is not None

    def test_unattached_rows_do_not_cluster(self, sync_session):
        # Neither row is attached → both excluded from the selection → no cluster.
        _artist(sync_session, "St. Germain", deezer_id="42")
        _artist(sync_session, "St Germain")

        stats = run_dupes_pass(sync_session, apply=True)

        assert stats["merged"] == 0 and stats["flagged"] == 0

    def test_dry_run_modifies_nothing(self, sync_session):
        linked = _artist(sync_session, "St. Germain", deezer_id="42")
        orphan = _artist(sync_session, "St Germain")
        _attach_cat(sync_session, linked)
        _attach_cat(sync_session, orphan)

        stats = run_dupes_pass(sync_session, apply=False)

        assert stats["merged"] == 1  # counts what --apply WOULD do...
        assert stats["link_recovered"] == 1
        # ...but the orphan is still present.
        assert sync_session.get(Artist, orphan.id) is not None

    def test_apply_is_idempotent(self, sync_session):
        linked = _artist(sync_session, "St. Germain", deezer_id="42")
        orphan = _artist(sync_session, "St Germain")
        _attach_cat(sync_session, linked)
        _attach_cat(sync_session, orphan)

        first = run_dupes_pass(sync_session, apply=True)
        assert first["merged"] == 1

        second = run_dupes_pass(sync_session, apply=True)
        assert second["merged"] == 0 and second["link_recovered"] == 0
        assert second["flagged"] == 0
