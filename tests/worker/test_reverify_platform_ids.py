"""Tests for the X3.c OPS repair script (scripts/reverify_platform_ids).

Exercises the testable core ``reverify_by_column`` (extracted from ``main`` so it
runs without the CLI) against a real sync SQLite session (``sync_session``
fixture). Builds small groups sharing a platform id and asserts that ONLY groups
spanning DISTINCT recordings (an id shared by a remix + its original, an EP id
shared by distinct tracks) are flagged suspect and get their id + E1 search state
cleared — while TRUE-duplicate groups (a single recording under the id) are left
untouched (that is ``dedup_catalog.py``'s job, not this script's). Same
import/path pattern as test_catalog_merge_script.py.
"""
import itertools
import os
import sys
from datetime import datetime

from sqlalchemy import select

# Make the workers package importable (same pattern as test_catalog_merge_script.py).
_SERVER_PATH = os.path.join(os.path.dirname(__file__), "../../server")
if _SERVER_PATH not in sys.path:
    sys.path.insert(0, _SERVER_PATH)

from models import CatalogEntry  # noqa: E402

from scripts.reverify_platform_ids import reverify_by_column  # noqa: E402

_nk = itertools.count(1)
_SEARCHED = datetime(2026, 1, 1)


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


class TestSuspectGroups:
    def test_remix_and_original_sharing_id_are_suspect(self, sync_session):
        # A remix inherited the original's deezer_id (Deezer hits[0] bug): distinct
        # recordings under one id → both rows suspect.
        orig = _cat(
            sync_session,
            title="Meridian",
            deezer_id="DZ1",
            isrc="ISRC-ORIG",
            deezer_searched_at=_SEARCHED,
            deezer_search_attempts=2,
        )
        remix = _cat(
            sync_session,
            title="Meridian (Julian Muller Remix)",
            deezer_id="DZ1",
            deezer_searched_at=_SEARCHED,
            deezer_search_attempts=1,
        )

        stats = reverify_by_column(sync_session, "deezer_id", apply=False)

        assert stats["suspect_groups"] == 1
        assert stats["clean_groups"] == 0
        assert stats["suspect_rows"] == 2
        assert stats["reset"] == 0  # dry-run
        assert stats["examples"] == [
            ("DZ1", [(orig.id, "Meridian"), (remix.id, "Meridian (Julian Muller Remix)")])
        ]

    def test_apply_clears_id_and_resets_search_state(self, sync_session):
        orig = _cat(
            sync_session,
            title="Meridian",
            deezer_id="DZ2",
            isrc="ISRC-ORIG",
            deezer_searched_at=_SEARCHED,
            deezer_search_attempts=2,
            # beatport state must be left alone by the deezer pass.
            beatport_id="BP-keep",
            beatport_searched_at=_SEARCHED,
            beatport_search_attempts=3,
        )
        remix = _cat(
            sync_session,
            title="Meridian (Julian Muller Remix)",
            deezer_id="DZ2",
            deezer_searched_at=_SEARCHED,
            deezer_search_attempts=1,
        )

        stats = reverify_by_column(sync_session, "deezer_id", apply=True)

        assert stats["suspect_groups"] == 1
        assert stats["suspect_rows"] == 2
        assert stats["reset"] == 2

        for row_id in (orig.id, remix.id):
            row = sync_session.get(CatalogEntry, row_id)
            assert row.deezer_id is None
            assert row.deezer_searched_at is None
            assert row.deezer_search_attempts == 0
        # The deezer pass must not touch the beatport columns.
        keeper = sync_session.get(CatalogEntry, orig.id)
        assert keeper.beatport_id == "BP-keep"
        assert keeper.beatport_searched_at == _SEARCHED
        assert keeper.beatport_search_attempts == 3

    def test_apply_is_idempotent(self, sync_session):
        _cat(sync_session, title="Meridian", deezer_id="DZ3", isrc="ISRC-A")
        _cat(sync_session, title="Meridian (Shed Remix)", deezer_id="DZ3")

        first = reverify_by_column(sync_session, "deezer_id", apply=True)
        assert first["suspect_groups"] == 1 and first["reset"] == 2

        # The cleared ids are NULL, so nothing is shared any more → 0 suspect.
        second = reverify_by_column(sync_session, "deezer_id", apply=True)
        assert second == {
            "suspect_groups": 0,
            "clean_groups": 0,
            "suspect_rows": 0,
            "reset": 0,
            "meta_cleared": 0,
            "preview_cleared": 0,
            "examples": [],
        }

    def test_mixed_group_clears_even_the_true_duplicate_pair(self, sync_session):
        # An ambiguous group holding a TRUE-duplicate pair AND a distinct remix:
        # the whole group is suspect, so EVERY row (incl. the duplicate pair) is
        # cleared — the assumed X3.c design decision (no row keeps a maybe-wrong id).
        dup_a = _cat(sync_session, title="Meridian", deezer_id="DZ4", isrc="ISRC-A")
        dup_b = _cat(sync_session, title="Meridian", deezer_id="DZ4")  # same recording
        remix = _cat(sync_session, title="Meridian (Shed Remix)", deezer_id="DZ4")

        stats = reverify_by_column(sync_session, "deezer_id", apply=True)

        assert stats["suspect_groups"] == 1
        assert stats["suspect_rows"] == 3
        assert stats["reset"] == 3
        for row_id in (dup_a.id, dup_b.id, remix.id):
            assert sync_session.get(CatalogEntry, row_id).deezer_id is None

    def test_beatport_column_uses_its_own_search_state(self, sync_session):
        # Same mechanism on the beatport column: an EP beatport_id shared by two
        # distinct remixes → both suspect, beatport state reset.
        remix_a = _cat(
            sync_session,
            title="Funk Solo (Batu Remix)",
            beatport_id="EP1",
            beatport_searched_at=_SEARCHED,
            beatport_search_attempts=2,
        )
        remix_b = _cat(
            sync_session,
            title="Funk Solo (Shed Remix)",
            beatport_id="EP1",
            beatport_searched_at=_SEARCHED,
            beatport_search_attempts=1,
        )

        stats = reverify_by_column(sync_session, "beatport_id", apply=True)

        assert stats["suspect_groups"] == 1 and stats["reset"] == 2
        for row_id in (remix_a.id, remix_b.id):
            row = sync_session.get(CatalogEntry, row_id)
            assert row.beatport_id is None
            assert row.beatport_searched_at is None
            assert row.beatport_search_attempts == 0


class TestTrueDuplicatesLeftIntact:
    def test_true_duplicate_group_not_flagged(self, sync_session):
        # Two rows, same title, same deezer_id → a single same-recording cluster.
        # That is dedup_catalog's job, NOT this script's: counted clean, left as-is.
        a = _cat(
            sync_session,
            title="Same Track",
            deezer_id="DZ5",
            isrc="ISRC-A",
            deezer_searched_at=_SEARCHED,
            deezer_search_attempts=1,
        )
        b = _cat(sync_session, title="Same Track", deezer_id="DZ5")

        stats = reverify_by_column(sync_session, "deezer_id", apply=True)

        assert stats["suspect_groups"] == 0
        assert stats["clean_groups"] == 1
        assert stats["suspect_rows"] == 0
        assert stats["reset"] == 0
        # Both rows keep their id and (for a) their search state untouched.
        assert sync_session.get(CatalogEntry, a.id).deezer_id == "DZ5"
        assert sync_session.get(CatalogEntry, a.id).deezer_searched_at == _SEARCHED
        assert sync_session.get(CatalogEntry, a.id).deezer_search_attempts == 1
        assert sync_session.get(CatalogEntry, b.id).deezer_id == "DZ5"

    def test_unique_id_and_null_id_ignored(self, sync_session):
        # A row with a solo id and a row with no id at all are never candidates.
        solo = _cat(sync_session, title="Solo", deezer_id="DZ6")
        none = _cat(sync_session, title="NoId")

        stats = reverify_by_column(sync_session, "deezer_id", apply=True)

        assert stats == {
            "suspect_groups": 0,
            "clean_groups": 0,
            "suspect_rows": 0,
            "reset": 0,
            "meta_cleared": 0,
            "preview_cleared": 0,
            "examples": [],
        }
        assert sync_session.get(CatalogEntry, solo.id).deezer_id == "DZ6"
        assert sync_session.get(CatalogEntry, none.id).deezer_id is None


class TestDryRun:
    def test_dry_run_modifies_nothing(self, sync_session):
        orig = _cat(
            sync_session,
            title="Meridian",
            deezer_id="DZ7",
            isrc="ISRC-A",
            deezer_searched_at=_SEARCHED,
            deezer_search_attempts=2,
        )
        remix = _cat(
            sync_session,
            title="Meridian (Shed Remix)",
            deezer_id="DZ7",
            deezer_searched_at=_SEARCHED,
            deezer_search_attempts=1,
        )

        stats = reverify_by_column(sync_session, "deezer_id", apply=False)
        assert stats["suspect_groups"] == 1 and stats["reset"] == 0

        # Nothing changed: ids and search state intact on both rows.
        for row_id, attempts in ((orig.id, 2), (remix.id, 1)):
            row = sync_session.get(CatalogEntry, row_id)
            assert row.deezer_id == "DZ7"
            assert row.deezer_searched_at == _SEARCHED
            assert row.deezer_search_attempts == attempts


class TestBeatportMetadataReset:
    """X3.c-ext: the beatport pass ALSO nulls bpm/key WHEN beatport-sourced.

    enrich_from_beatport only writes bpm/key when bpm_source/key_source is not
    already "beatport"; a suspect row still carrying the WRONG match's
    bpm_source="beatport" would keep its wrong bpm/key on re-enrichment. So the
    beatport pass nulls value + source to re-open the guard. The ABSOLUTE guard
    (data-authority invariant #2): a bpm/key from any other source is authoritative
    and must NEVER be blanked. The deezer pass never touches bpm/key.
    """

    def test_beatport_pass_clears_beatport_sourced_bpm_key(self, sync_session):
        # Two distinct remixes under one EP beatport_id, both carrying a
        # beatport-sourced bpm/key derived from the (wrong) match → id + bpm/key +
        # their sources cleared, search state reset.
        remix_a = _cat(
            sync_session,
            title="Funk Solo (Batu Remix)",
            beatport_id="EP-M",
            bpm=128.0,
            key="8A",
            bpm_source="beatport",
            key_source="beatport",
            beatport_searched_at=_SEARCHED,
            beatport_search_attempts=2,
        )
        remix_b = _cat(
            sync_session,
            title="Funk Solo (Shed Remix)",
            beatport_id="EP-M",
            bpm=130.0,
            key="9A",
            bpm_source="beatport",
            key_source="beatport",
            beatport_searched_at=_SEARCHED,
            beatport_search_attempts=1,
        )

        stats = reverify_by_column(sync_session, "beatport_id", apply=True)

        assert stats["suspect_groups"] == 1
        assert stats["reset"] == 2
        assert stats["meta_cleared"] == 4  # 2 rows × (bpm + key)
        for row_id in (remix_a.id, remix_b.id):
            row = sync_session.get(CatalogEntry, row_id)
            assert row.beatport_id is None
            assert row.bpm is None and row.bpm_source is None
            assert row.key is None and row.key_source is None
            assert row.beatport_searched_at is None
            assert row.beatport_search_attempts == 0

    def test_beatport_pass_keeps_non_beatport_sourced_bpm_key(self, sync_session):
        # THE invariant #2 test: a bpm/key sourced from rekordbox or deezer did NOT
        # come from the suspect Beatport match and may be authoritative → the id +
        # search state are reset but the bpm/key (and their sources) are UNTOUCHED.
        row_rb = _cat(
            sync_session,
            title="Funk Solo (Batu Remix)",
            beatport_id="EP-N",
            bpm=126.0,
            key="7A",
            bpm_source="rekordbox",
            key_source="rekordbox",
            beatport_searched_at=_SEARCHED,
            beatport_search_attempts=2,
        )
        row_dz = _cat(
            sync_session,
            title="Funk Solo (Shed Remix)",
            beatport_id="EP-N",
            bpm=124.0,
            key="6A",
            bpm_source="deezer",
            key_source="deezer",
            beatport_searched_at=_SEARCHED,
            beatport_search_attempts=1,
        )

        stats = reverify_by_column(sync_session, "beatport_id", apply=True)

        assert stats["suspect_groups"] == 1
        assert stats["reset"] == 2
        assert stats["meta_cleared"] == 0  # nothing beatport-sourced → nothing cleared

        rb = sync_session.get(CatalogEntry, row_rb.id)
        assert rb.beatport_id is None  # id reset...
        assert rb.beatport_searched_at is None and rb.beatport_search_attempts == 0
        assert rb.bpm == 126.0 and rb.bpm_source == "rekordbox"  # ...but bpm/key KEPT
        assert rb.key == "7A" and rb.key_source == "rekordbox"

        dz = sync_session.get(CatalogEntry, row_dz.id)
        assert dz.beatport_id is None
        assert dz.bpm == 124.0 and dz.bpm_source == "deezer"
        assert dz.key == "6A" and dz.key_source == "deezer"

    def test_beatport_guard_is_per_field(self, sync_session):
        # A row can hold a beatport-sourced bpm AND a rekordbox-sourced key: only
        # the beatport-sourced field is cleared, proving the guard is per-field.
        mixed = _cat(
            sync_session,
            title="Funk Solo (Batu Remix)",
            beatport_id="EP-P",
            bpm=130.0,
            bpm_source="beatport",
            key="5A",
            key_source="rekordbox",
        )
        _cat(sync_session, title="Funk Solo (Shed Remix)", beatport_id="EP-P")

        stats = reverify_by_column(sync_session, "beatport_id", apply=True)

        assert stats["suspect_groups"] == 1
        assert stats["meta_cleared"] == 1  # only the beatport-sourced bpm
        row = sync_session.get(CatalogEntry, mixed.id)
        assert row.beatport_id is None
        assert row.bpm is None and row.bpm_source is None  # beatport-sourced → cleared
        assert row.key == "5A" and row.key_source == "rekordbox"  # rekordbox → KEPT

    def test_deezer_pass_leaves_bpm_key_untouched(self, sync_session):
        # The deezer pass is id-only: even a beatport-sourced bpm/key on a suspect
        # deezer group is NOT touched (deezer enrichment never stamps bpm/key).
        orig = _cat(
            sync_session,
            title="Meridian",
            deezer_id="DZM",
            isrc="ISRC-ORIG",
            bpm=128.0,
            key="8A",
            bpm_source="beatport",
            key_source="beatport",
        )
        remix = _cat(
            sync_session,
            title="Meridian (Julian Muller Remix)",
            deezer_id="DZM",
            bpm=132.0,
            key="10A",
            bpm_source="beatport",
            key_source="beatport",
        )

        stats = reverify_by_column(sync_session, "deezer_id", apply=True)

        assert stats["suspect_groups"] == 1
        assert stats["reset"] == 2
        assert stats["meta_cleared"] == 0  # deezer pass never clears bpm/key
        for row_id, bpm, key in ((orig.id, 128.0, "8A"), (remix.id, 132.0, "10A")):
            row = sync_session.get(CatalogEntry, row_id)
            assert row.deezer_id is None  # id reset
            assert row.bpm == bpm and row.bpm_source == "beatport"  # bpm/key intact
            assert row.key == key and row.key_source == "beatport"

    def test_dry_run_counts_meta_without_clearing(self, sync_session):
        # meta_cleared is reported in dry-run (how many WOULD be cleared) but the
        # rows are untouched — the count informs the run/no-run decision.
        remix_a = _cat(
            sync_session,
            title="Funk Solo (Batu Remix)",
            beatport_id="EP-D",
            bpm=128.0,
            key="8A",
            bpm_source="beatport",
            key_source="beatport",
        )
        remix_b = _cat(
            sync_session,
            title="Funk Solo (Shed Remix)",
            beatport_id="EP-D",
            bpm=130.0,
            key="9A",
            bpm_source="beatport",
            key_source="beatport",
        )

        stats = reverify_by_column(sync_session, "beatport_id", apply=False)

        assert stats["suspect_groups"] == 1
        assert stats["reset"] == 0
        assert stats["meta_cleared"] == 4  # counted, but nothing mutated
        for row_id in (remix_a.id, remix_b.id):
            row = sync_session.get(CatalogEntry, row_id)
            assert row.beatport_id == "EP-D"
            assert row.bpm is not None and row.bpm_source == "beatport"
            assert row.key is not None and row.key_source == "beatport"

    def test_beatport_meta_reset_is_idempotent(self, sync_session):
        # After the first apply cleared id + bpm/key, a second apply finds no shared
        # id → 0 suspect group, 0 meta cleared.
        _cat(
            sync_session,
            title="Funk Solo (Batu Remix)",
            beatport_id="EP-I",
            bpm=128.0,
            key="8A",
            bpm_source="beatport",
            key_source="beatport",
        )
        _cat(
            sync_session,
            title="Funk Solo (Shed Remix)",
            beatport_id="EP-I",
            bpm=130.0,
            key="9A",
            bpm_source="beatport",
            key_source="beatport",
        )

        first = reverify_by_column(sync_session, "beatport_id", apply=True)
        assert first["suspect_groups"] == 1 and first["meta_cleared"] == 4

        second = reverify_by_column(sync_session, "beatport_id", apply=True)
        assert second == {
            "suspect_groups": 0,
            "clean_groups": 0,
            "suspect_rows": 0,
            "reset": 0,
            "meta_cleared": 0,
            "preview_cleared": 0,
            "examples": [],
        }


class TestDeezerHasPreviewReset:
    """X3.c-ext: the deezer pass ALSO resets stale ``has_preview``.

    ``has_preview`` is a Deezer-only signal (only a Deezer hit sets it True). Once
    the suspect ``deezer_id`` is cleared, an orphaned ``has_preview=True`` with no
    ``deezer`` radar source can never be resolved by ``get_preview_url`` — the
    frontend offers a Play button that 404s. So the deezer pass nulls it, UNLESS a
    ``deezer`` radar source still backs the row (that source keeps the preview
    servable). The beatport pass never touches ``has_preview``.
    """

    def _radar(self, session, catalog_id, source):
        from models import RadarTrack

        session.add(
            RadarTrack(
                watched_entity_id=1,
                external_track_id="ext-1",
                source=source,
                title="src",
                catalog_id=catalog_id,
            )
        )
        session.commit()

    def test_deezer_pass_resets_stale_has_preview(self, sync_session):
        # Suspect deezer group (remix + original), both has_preview=True, NO deezer
        # radar source → both reset to False and counted.
        orig = _cat(
            sync_session, title="Meridian", deezer_id="DZP1", isrc="ISRC-O",
            has_preview=True,
        )
        remix = _cat(
            sync_session, title="Meridian (Shed Remix)", deezer_id="DZP1",
            has_preview=True,
        )

        stats = reverify_by_column(sync_session, "deezer_id", apply=True)

        assert stats["suspect_groups"] == 1
        assert stats["reset"] == 2
        assert stats["preview_cleared"] == 2
        for row_id in (orig.id, remix.id):
            row = sync_session.get(CatalogEntry, row_id)
            assert row.deezer_id is None
            assert row.has_preview is False

    def test_deezer_pass_keeps_has_preview_with_deezer_radar_source(self, sync_session):
        # A suspect row still backed by a deezer radar source stays has_preview=True
        # (get_preview_url resolves it via the radar external_track_id); a sibling
        # with no source is reset. Proves the guard is per-row.
        with_src = _cat(
            sync_session, title="Meridian", deezer_id="DZP2", isrc="ISRC-O",
            has_preview=True,
        )
        no_src = _cat(
            sync_session, title="Meridian (Shed Remix)", deezer_id="DZP2",
            has_preview=True,
        )
        self._radar(sync_session, with_src.id, "deezer")

        stats = reverify_by_column(sync_session, "deezer_id", apply=True)

        assert stats["suspect_groups"] == 1
        assert stats["preview_cleared"] == 1  # only the row without a deezer source
        assert sync_session.get(CatalogEntry, with_src.id).has_preview is True
        assert sync_session.get(CatalogEntry, no_src.id).has_preview is False

    def test_non_deezer_radar_source_does_not_protect_has_preview(self, sync_session):
        # A TIDAL radar source does NOT keep a preview servable (Deezer-only), so the
        # row's stale has_preview is still reset.
        tidal_backed = _cat(
            sync_session, title="Meridian", deezer_id="DZP3", isrc="ISRC-O",
            has_preview=True,
        )
        _cat(
            sync_session, title="Meridian (Shed Remix)", deezer_id="DZP3",
            has_preview=True,
        )
        self._radar(sync_session, tidal_backed.id, "tidal")

        stats = reverify_by_column(sync_session, "deezer_id", apply=True)

        assert stats["preview_cleared"] == 2
        assert sync_session.get(CatalogEntry, tidal_backed.id).has_preview is False

    def test_beatport_pass_never_touches_has_preview(self, sync_session):
        # The beatport pass leaves has_preview alone (Beatport never sets it).
        remix_a = _cat(
            sync_session, title="Funk (Batu Remix)", beatport_id="EPH",
            has_preview=True,
        )
        remix_b = _cat(
            sync_session, title="Funk (Shed Remix)", beatport_id="EPH",
            has_preview=True,
        )

        stats = reverify_by_column(sync_session, "beatport_id", apply=True)

        assert stats["suspect_groups"] == 1
        assert stats["preview_cleared"] == 0
        for row_id in (remix_a.id, remix_b.id):
            assert sync_session.get(CatalogEntry, row_id).has_preview is True

    def test_dry_run_counts_preview_without_clearing(self, sync_session):
        orig = _cat(
            sync_session, title="Meridian", deezer_id="DZP4", isrc="ISRC-O",
            has_preview=True,
        )
        remix = _cat(
            sync_session, title="Meridian (Shed Remix)", deezer_id="DZP4",
            has_preview=True,
        )

        stats = reverify_by_column(sync_session, "deezer_id", apply=False)

        assert stats["preview_cleared"] == 2  # counted...
        for row_id in (orig.id, remix.id):
            assert sync_session.get(CatalogEntry, row_id).has_preview is True  # ...not mutated
