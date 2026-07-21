"""Tests for the catalog merge primitive (workers/catalog_merge).

Exercises the two public helpers against a real sync SQLite session
(``sync_session`` fixture, which ``create_all``s every table incl. the FK
children). SQLite does not enforce FKs or ON DELETE RESTRICT — that is the
point: the primitive must repoint every referencing row EXPLICITLY rather than
lean on a DB cascade.
"""
import itertools
import os
import sys
from datetime import datetime
from types import SimpleNamespace

from sqlalchemy import select

# Make the workers package importable (same pattern as test_enrichment_isrc.py).
_SERVER_PATH = os.path.join(os.path.dirname(__file__), "../../server")
if _SERVER_PATH not in sys.path:
    sys.path.insert(0, _SERVER_PATH)

from models import (  # noqa: E402
    ArtistActivity,
    CatalogArtist,
    CatalogEntry,
    CollectionItem,
    RadarTrack,
    RadarTrend,
    SetTrack,
    UserOpinion,
    UserRadarState,
    UserTrack,
)
from workers.catalog_merge import (  # noqa: E402
    merge_catalog_entries,
    normalize_track_title,
    pick_canonical,
    same_track,
)

_nk = itertools.count(1)


def _row(title="X", isrc=None):
    """Lightweight stand-in for a catalog row (same_track only reads title/isrc).

    Uses SimpleNamespace rather than a real row so two entries can carry equal
    ISRCs — the DB's UNIQUE(isrc) constraint would forbid inserting those.
    """
    return SimpleNamespace(title=title, isrc=isrc)


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


# ── normalize_track_title ──────────────────────────────────────────────────


class TestNormalizeTrackTitle:
    def test_plain_title_unchanged(self):
        assert normalize_track_title("ten") == "ten"

    def test_lowercase_trim_and_compact_spaces(self):
        assert normalize_track_title("  Ten  ") == "ten"
        assert normalize_track_title("Head &   Heart") == "head & heart"

    def test_feat_credit_stripped(self):
        assert normalize_track_title("Head & Heart (feat. MNEK)") == "head & heart"
        assert normalize_track_title("Head & Heart feat. MNEK") == "head & heart"
        assert normalize_track_title("Head & Heart ft. MNEK") == "head & heart"
        assert normalize_track_title("Head & Heart (featuring MNEK)") == "head & heart"

    def test_original_marker_stripped(self):
        assert normalize_track_title("303 State (Original Mix)") == "303 state"
        assert normalize_track_title("303 State (Original)") == "303 state"

    def test_remix_marker_preserved(self):
        # The safety-critical direction: version markers MUST survive.
        assert (
            normalize_track_title("Meridian (Julian Muller Remix)")
            == "meridian (julian muller remix)"
        )
        assert (
            normalize_track_title("Happiness (Dr. Atmo Remix)")
            == "happiness (dr. atmo remix)"
        )
        assert (
            normalize_track_title("Funk Solo (Shed Remix)") == "funk solo (shed remix)"
        )

    def test_non_remix_version_markers_preserved(self):
        assert (
            normalize_track_title("Feel The Need (Extended Dance Version)")
            == "feel the need (extended dance version)"
        )
        assert (
            normalize_track_title("Fantasy (Sweet Dub Mix)") == "fantasy (sweet dub mix)"
        )

    def test_feature_word_not_mistaken_for_feat_credit(self):
        # "feature" starts with "feat" but is not a credit — must be preserved.
        assert (
            normalize_track_title("Main Feature (Club Mix)") == "main feature (club mix)"
        )

    def test_bare_feat_stripped_when_no_version_follows(self):
        # A bare feat credit with no trailing version marker is fully removed.
        assert normalize_track_title("Song feat. X") == "song"
        assert normalize_track_title("Song feat. A, B, C") == "song"
        assert normalize_track_title("Song ft. X") == "song"

    def test_bare_feat_does_not_swallow_version_marker(self):
        # The X1-FIX-2 bug: a bare feat credit must NOT eat a version marker that
        # follows it, or two distinct versions collapse to the same string.
        club = normalize_track_title("Song feat. X (Club Mix)")
        radio = normalize_track_title("Song feat. X (Radio Edit)")
        assert "club mix" in club
        assert "radio edit" in radio
        assert club != radio
        assert "extended mix" in normalize_track_title("Track ft. A B (Extended Mix)")

    def test_none_title_is_empty(self):
        assert normalize_track_title(None) == ""


# ── same_track ─────────────────────────────────────────────────────────────


class TestSameTrack:
    def test_equal_isrcs_are_same(self):
        assert same_track(_row(isrc="AAA"), _row(isrc="AAA")) is True

    def test_null_isrcs_fall_back_to_title(self):
        # Two rows titled "ten" (ISRCs null) are the same recording.
        assert same_track(_row(title="Ten"), _row(title="ten")) is True
        assert same_track(_row(title="Ten"), _row(title="Eleven")) is False

    def test_one_isrc_present_uses_title(self):
        assert (
            same_track(
                _row(title="Head & Heart (feat. MNEK)", isrc="AAA"),
                _row(title="Head & Heart", isrc=None),
            )
            is True
        )
        assert (
            same_track(
                _row(title="303 State (Original Mix)", isrc=None),
                _row(title="303 State", isrc="AAA"),
            )
            is True
        )

    def test_different_isrcs_never_same(self):
        # ISRC contradiction wins even when the titles are identical: the remixes
        # of "Funk Solo" share a beatport_id but have distinct ISRCs.
        assert (
            same_track(
                _row(title="Funk Solo", isrc="ISRC-1"),
                _row(title="Funk Solo", isrc="ISRC-2"),
            )
            is False
        )
        assert (
            same_track(
                _row(title="Funk Solo (Batu Remix)", isrc="ISRC-1"),
                _row(title="Funk Solo (Shed Remix)", isrc="ISRC-2"),
            )
            is False
        )

    def test_remix_vs_original_not_same(self):
        # The Deezer hits[0] bug: a remix inherits the original's deezer_id. The
        # original carries the ISRC, the remix does not → title fallback separates.
        assert (
            same_track(
                _row(title="Meridian", isrc="ISRC-ORIG"),
                _row(title="Meridian (Julian Muller Remix)", isrc=None),
            )
            is False
        )
        assert (
            same_track(
                _row(title="Happiness"),
                _row(title="Happiness (Dr. Atmo Remix)"),
            )
            is False
        )

    def test_distinct_remixes_not_same(self):
        assert (
            same_track(
                _row(title="Funk Solo (Batu Remix)"),
                _row(title="Funk Solo (Shed Remix)"),
            )
            is False
        )

    def test_bare_feat_with_distinct_versions_not_same(self):
        # Same base + same feat artist, but different versions (Club vs Radio).
        # The bare-feat fix keeps the versions in the normalized title, so these
        # two ISRC-less rows are NOT merged.
        assert (
            same_track(
                _row(title="Song feat. X (Club Mix)"),
                _row(title="Song feat. X (Radio Edit)"),
            )
            is False
        )


# ── pick_canonical ────────────────────────────────────────────────────────


class TestPickCanonical:
    def test_isrc_present_wins_over_older_and_more_complete(self, sync_session):
        # The no-ISRC row is older AND more complete, yet the ISRC row wins.
        rich_old = _cat(
            sync_session,
            created_at=datetime(2019, 1, 1),
            bpm=128,
            key="8A",
            has_artwork=True,
        )
        with_isrc = _cat(
            sync_session, created_at=datetime(2023, 1, 1), isrc="ISRC1"
        )
        assert pick_canonical([rich_old, with_isrc]) is with_isrc
        assert pick_canonical([with_isrc, rich_old]) is with_isrc

    def test_oldest_wins_over_more_complete(self, sync_session):
        # Both lack an ISRC: age beats completeness (older is less complete).
        old_bare = _cat(sync_session, created_at=datetime(2019, 1, 1))
        new_rich = _cat(
            sync_session, created_at=datetime(2022, 1, 1), bpm=120, label="Lbl"
        )
        assert pick_canonical([new_rich, old_bare]) is old_bare

    def test_completeness_breaks_created_at_tie_over_id(self, sync_session):
        # Same ISRC status + same created_at: the more complete wins even though
        # it has the HIGHER id (proving completeness is ranked before id).
        bare = _cat(sync_session, created_at=datetime(2020, 1, 1))
        rich = _cat(
            sync_session, created_at=datetime(2020, 1, 1), bpm=130, key="9A"
        )
        assert rich.id > bare.id
        assert pick_canonical([bare, rich]) is rich

    def test_id_is_final_tiebreak(self, sync_session):
        # Fully tied rows fall back to the lowest id.
        a = _cat(sync_session, created_at=datetime(2020, 1, 1))
        b = _cat(sync_session, created_at=datetime(2020, 1, 1))
        assert a.id < b.id
        assert pick_canonical([b, a]) is a

    def test_null_created_at_is_deprioritised(self, sync_session):
        with_date = _cat(sync_session, created_at=datetime(2020, 1, 1))
        without_date = _cat(sync_session, created_at=None)
        assert pick_canonical([without_date, with_date]) is with_date

    def test_empty_raises(self):
        try:
            pick_canonical([])
        except ValueError:
            pass
        else:
            raise AssertionError("expected ValueError on empty input")


# ── merge_catalog_entries: FK / pseudo-FK repointing ───────────────────────


class TestMergeRepoint:
    def test_catalog_artists_simple_move(self, sync_session):
        canon = _cat(sync_session)
        loser = _cat(sync_session)
        sync_session.add(
            CatalogArtist(catalog_id=loser.id, artist_id=7, role="main", position=0)
        )
        sync_session.commit()

        merge_catalog_entries(sync_session, canon.id, loser.id)
        sync_session.commit()

        links = sync_session.execute(select(CatalogArtist)).scalars().all()
        assert len(links) == 1
        assert links[0].catalog_id == canon.id
        assert links[0].artist_id == 7

    def test_catalog_artists_conflict_drops_duplicate(self, sync_session):
        canon = _cat(sync_session)
        loser = _cat(sync_session)
        sync_session.add(CatalogArtist(catalog_id=canon.id, artist_id=7, position=0))
        sync_session.add(CatalogArtist(catalog_id=loser.id, artist_id=7, position=0))
        sync_session.commit()

        merge_catalog_entries(sync_session, canon.id, loser.id)
        sync_session.commit()

        links = sync_session.execute(select(CatalogArtist)).scalars().all()
        assert len(links) == 1
        assert links[0].catalog_id == canon.id

    def test_user_tracks_simple_move(self, sync_session):
        canon = _cat(sync_session)
        loser = _cat(sync_session)
        sync_session.add(UserTrack(user_id=3, catalog_id=loser.id, avis="yes"))
        sync_session.commit()

        merge_catalog_entries(sync_session, canon.id, loser.id)
        sync_session.commit()

        rows = sync_session.execute(select(UserTrack)).scalars().all()
        assert len(rows) == 1
        assert rows[0].user_id == 3
        assert rows[0].catalog_id == canon.id
        assert rows[0].avis == "yes"

    def test_user_tracks_conflict_merges_null_fields(self, sync_session):
        canon = _cat(sync_session)
        loser = _cat(sync_session)
        # Same user owns both: canonical is missing avis/rating, loser has them.
        sync_session.add(
            UserTrack(user_id=3, catalog_id=canon.id, avis=None, rating=None)
        )
        sync_session.add(
            UserTrack(user_id=3, catalog_id=loser.id, avis="love", rating=5)
        )
        sync_session.commit()

        merge_catalog_entries(sync_session, canon.id, loser.id)
        sync_session.commit()

        rows = sync_session.execute(select(UserTrack)).scalars().all()
        assert len(rows) == 1
        row = rows[0]
        assert row.user_id == 3 and row.catalog_id == canon.id
        assert row.avis == "love"  # filled from loser
        assert row.rating == 5

    def test_user_tracks_conflict_keeps_canonical_non_null(self, sync_session):
        canon = _cat(sync_session)
        loser = _cat(sync_session)
        sync_session.add(
            UserTrack(user_id=3, catalog_id=canon.id, avis="keepme", rating=1)
        )
        sync_session.add(
            UserTrack(user_id=3, catalog_id=loser.id, avis="drop", rating=9)
        )
        sync_session.commit()

        merge_catalog_entries(sync_session, canon.id, loser.id)
        sync_session.commit()

        row = sync_session.execute(select(UserTrack)).scalar_one()
        assert row.avis == "keepme"  # canonical's own value is not overwritten
        assert row.rating == 1

    def test_set_tracks_move(self, sync_session):
        canon = _cat(sync_session)
        loser = _cat(sync_session)
        sync_session.add(SetTrack(set_id=1, catalog_id=loser.id, position=0))
        sync_session.commit()

        merge_catalog_entries(sync_session, canon.id, loser.id)
        sync_session.commit()

        st = sync_session.execute(select(SetTrack)).scalar_one()
        assert st.catalog_id == canon.id

    def test_radar_tracks_move(self, sync_session):
        canon = _cat(sync_session)
        loser = _cat(sync_session)
        sync_session.add(
            RadarTrack(
                watched_entity_id=1,
                external_track_id="ext1",
                source="deezer",
                title="X",
                catalog_id=loser.id,
            )
        )
        sync_session.commit()

        merge_catalog_entries(sync_session, canon.id, loser.id)
        sync_session.commit()

        rt = sync_session.execute(select(RadarTrack)).scalar_one()
        assert rt.catalog_id == canon.id

    def test_collection_items_simple_and_conflict(self, sync_session):
        canon = _cat(sync_session)
        loser = _cat(sync_session)
        # collection 1: only loser -> move. collection 2: both -> drop loser.
        sync_session.add(CollectionItem(collection_id=1, catalog_id=loser.id))
        sync_session.add(CollectionItem(collection_id=2, catalog_id=canon.id))
        sync_session.add(CollectionItem(collection_id=2, catalog_id=loser.id))
        sync_session.commit()

        merge_catalog_entries(sync_session, canon.id, loser.id)
        sync_session.commit()

        items = sync_session.execute(select(CollectionItem)).scalars().all()
        assert all(it.catalog_id == canon.id for it in items)
        assert {it.collection_id for it in items} == {1, 2}
        assert len(items) == 2

    def test_user_radar_state_simple_and_conflict(self, sync_session):
        # user_radar_state is not in the L1 brief's list but is a genuine
        # catalog_id FK — the primitive must repoint it too.
        canon = _cat(sync_session)
        loser = _cat(sync_session)
        sync_session.add(
            UserRadarState(user_id=1, catalog_id=loser.id, status="new")
        )
        sync_session.add(
            UserRadarState(user_id=2, catalog_id=canon.id, status="seen")
        )
        sync_session.add(
            UserRadarState(user_id=2, catalog_id=loser.id, status="new")
        )
        sync_session.commit()

        merge_catalog_entries(sync_session, canon.id, loser.id)
        sync_session.commit()

        rows = sync_session.execute(select(UserRadarState)).scalars().all()
        assert all(r.catalog_id == canon.id for r in rows)
        assert {r.user_id for r in rows} == {1, 2}
        # user 2's canonical row (status 'seen') is kept, loser dup dropped.
        seen = {r.user_id: r.status for r in rows}
        assert seen[2] == "seen"

    def test_artist_activity_move(self, sync_session):
        canon = _cat(sync_session)
        loser = _cat(sync_session)
        sync_session.add(
            ArtistActivity(
                artist_id=1,
                activity_type="release",
                source="deezer",
                external_id="e1",
                catalog_id=loser.id,
                detected_at=datetime(2020, 1, 1),
            )
        )
        sync_session.commit()

        merge_catalog_entries(sync_session, canon.id, loser.id)
        sync_session.commit()

        act = sync_session.execute(select(ArtistActivity)).scalar_one()
        assert act.catalog_id == canon.id

    def test_radar_trends_loser_rows_deleted(self, sync_session):
        canon = _cat(sync_session)
        loser = _cat(sync_session)
        sync_session.add(RadarTrend(catalog_id=canon.id, trend_score=2.0))
        sync_session.add(RadarTrend(catalog_id=loser.id, trend_score=1.0))
        sync_session.commit()

        merge_catalog_entries(sync_session, canon.id, loser.id)
        sync_session.commit()

        trends = sync_session.execute(select(RadarTrend)).scalars().all()
        assert len(trends) == 1
        assert trends[0].catalog_id == canon.id  # loser trend dropped, not moved

    def test_user_opinions_repoint_and_conflict(self, sync_session):
        canon = _cat(sync_session)
        loser = _cat(sync_session)
        # user 1: opinion only on loser -> repoint entity_key.
        sync_session.add(
            UserOpinion(
                user_id=1,
                entity_type="track",
                entity_key=str(loser.id),
                opinion="liked",
            )
        )
        # user 2: opinions on BOTH -> loser opinion dropped, canonical kept.
        sync_session.add(
            UserOpinion(
                user_id=2,
                entity_type="track",
                entity_key=str(canon.id),
                opinion="liked",
            )
        )
        sync_session.add(
            UserOpinion(
                user_id=2,
                entity_type="track",
                entity_key=str(loser.id),
                opinion="disliked",
            )
        )
        # an unrelated (non-track) opinion keyed by the loser id must be left alone.
        sync_session.add(
            UserOpinion(
                user_id=1,
                entity_type="artist",
                entity_key=str(loser.id),
                opinion="liked",
            )
        )
        sync_session.commit()

        merge_catalog_entries(sync_session, canon.id, loser.id)
        sync_session.commit()

        track_ops = (
            sync_session.execute(
                select(UserOpinion).where(UserOpinion.entity_type == "track")
            )
            .scalars()
            .all()
        )
        assert all(op.entity_key == str(canon.id) for op in track_ops)
        assert len(track_ops) == 2  # user1 repointed, user2 dedup to canonical
        by_user = {op.user_id: op.opinion for op in track_ops}
        assert by_user[1] == "liked"
        assert by_user[2] == "liked"  # canonical kept, loser 'disliked' dropped

        # the artist-type opinion is untouched.
        artist_op = sync_session.execute(
            select(UserOpinion).where(UserOpinion.entity_type == "artist")
        ).scalar_one()
        assert artist_op.entity_key == str(loser.id)


# ── merge_catalog_entries: metadata union ──────────────────────────────────


class TestMergeMetadata:
    def test_genres_union_ordered_no_duplicates(self, sync_session):
        canon = _cat(sync_session, genres=["house", "techno"])
        loser = _cat(sync_session, genres=["techno", "trance"])

        merge_catalog_entries(sync_session, canon.id, loser.id)
        sync_session.commit()

        assert canon.genres == ["house", "techno", "trance"]

    def test_null_only_fill(self, sync_session):
        canon = _cat(sync_session, duration_ms=None, label=None, release_date=None)
        loser = _cat(
            sync_session,
            duration_ms=210000,
            label="Loser Records",
            release_date=datetime(2021, 5, 1).date(),
        )

        merge_catalog_entries(sync_session, canon.id, loser.id)
        sync_session.commit()

        assert canon.duration_ms == 210000
        assert canon.label == "Loser Records"
        assert canon.release_date == datetime(2021, 5, 1).date()

    def test_canonical_non_null_metadata_is_kept(self, sync_session):
        canon = _cat(sync_session, duration_ms=100, label="Keep")
        loser = _cat(sync_session, duration_ms=999, label="Drop")

        merge_catalog_entries(sync_session, canon.id, loser.id)
        sync_session.commit()

        assert canon.duration_ms == 100
        assert canon.label == "Keep"

    def test_artwork_and_preview_logical_or(self, sync_session):
        canon = _cat(sync_session, has_artwork=False, has_preview=True)
        loser = _cat(sync_session, has_artwork=True, has_preview=False)

        merge_catalog_entries(sync_session, canon.id, loser.id)
        sync_session.commit()

        assert canon.has_artwork is True  # from loser
        assert canon.has_preview is True  # kept from canonical

    def test_bpm_key_filled_with_provenance_when_null(self, sync_session):
        canon = _cat(sync_session, bpm=None, key=None)
        loser = _cat(
            sync_session,
            bpm=126.0,
            bpm_source="beatport",
            key="7A",
            key_source="beatport",
        )

        merge_catalog_entries(sync_session, canon.id, loser.id)
        sync_session.commit()

        assert canon.bpm == 126.0
        assert canon.bpm_source == "beatport"
        assert canon.key == "7A"
        assert canon.key_source == "beatport"

    def test_bpm_key_not_overwritten_when_present(self, sync_session):
        canon = _cat(
            sync_session, bpm=124.0, bpm_source="rekordbox", key="5A", key_source="rb"
        )
        loser = _cat(
            sync_session,
            bpm=126.0,
            bpm_source="beatport",
            key="7A",
            key_source="beatport",
        )

        merge_catalog_entries(sync_session, canon.id, loser.id)
        sync_session.commit()

        assert canon.bpm == 124.0  # authority invariant: existing value stands
        assert canon.bpm_source == "rekordbox"
        assert canon.key == "5A"
        assert canon.key_source == "rb"

    def test_unique_ids_transferred_when_canonical_null(self, sync_session):
        # isrc carries a real UNIQUE constraint on SQLite: this proves the
        # delete-loser-then-assign ordering avoids a transient violation.
        canon = _cat(sync_session, isrc=None, deezer_id=None, beatport_id=None)
        loser = _cat(
            sync_session, isrc="ISRCX", deezer_id="D9", beatport_id="B9"
        )

        merge_catalog_entries(sync_session, canon.id, loser.id)
        sync_session.commit()

        assert canon.isrc == "ISRCX"
        assert canon.deezer_id == "D9"
        assert canon.beatport_id == "B9"

    def test_shared_deezer_id_kept_no_conflict(self, sync_session):
        # The realistic X1 case: both duplicates carry the same deezer_id.
        canon = _cat(sync_session, deezer_id="SAME")
        loser = _cat(sync_session, deezer_id="SAME")

        merge_catalog_entries(sync_session, canon.id, loser.id)
        sync_session.commit()

        assert canon.deezer_id == "SAME"
        assert sync_session.get(CatalogEntry, loser.id) is None

    def test_search_history_kept(self, sync_session):
        canon = _cat(
            sync_session,
            deezer_search_attempts=1,
            deezer_searched_at=datetime(2021, 1, 1),
            beatport_search_attempts=0,
            beatport_searched_at=None,
        )
        loser = _cat(
            sync_session,
            deezer_search_attempts=3,
            deezer_searched_at=datetime(2022, 6, 1),
            beatport_search_attempts=2,
            beatport_searched_at=datetime(2022, 1, 1),
        )

        merge_catalog_entries(sync_session, canon.id, loser.id)
        sync_session.commit()

        assert canon.deezer_search_attempts == 3  # max
        assert canon.deezer_searched_at == datetime(2022, 6, 1)  # latest
        assert canon.beatport_search_attempts == 2  # from loser (canon had 0)
        assert canon.beatport_searched_at == datetime(2022, 1, 1)

    def test_shared_scope_wins_over_private(self, sync_session):
        canon = _cat(sync_session, scope="private", owner_id=42)
        loser = _cat(sync_session, scope="shared", owner_id=None)

        merge_catalog_entries(sync_session, canon.id, loser.id)
        sync_session.commit()

        assert canon.scope == "shared"  # never downgrade a shared row
        assert canon.owner_id is None

    def test_both_private_scope_preserved(self, sync_session):
        canon = _cat(sync_session, scope="private", owner_id=42)
        loser = _cat(sync_session, scope="private", owner_id=42)

        merge_catalog_entries(sync_session, canon.id, loser.id)
        sync_session.commit()

        assert canon.scope == "private"
        assert canon.owner_id == 42


# ── merge_catalog_entries: deletion & idempotence ──────────────────────────


class TestMergeLifecycle:
    def test_loser_row_is_deleted(self, sync_session):
        canon = _cat(sync_session)
        loser = _cat(sync_session)
        loser_id = loser.id

        merge_catalog_entries(sync_session, canon.id, loser_id)
        sync_session.commit()

        assert sync_session.get(CatalogEntry, loser_id) is None
        assert sync_session.get(CatalogEntry, canon.id) is not None

    def test_canonical_equals_loser_is_noop(self, sync_session):
        canon = _cat(sync_session, genres=["house"])

        merge_catalog_entries(sync_session, canon.id, canon.id)
        sync_session.commit()

        assert sync_session.get(CatalogEntry, canon.id) is not None
        assert canon.genres == ["house"]

    def test_second_merge_is_noop(self, sync_session):
        canon = _cat(sync_session)
        loser = _cat(sync_session)
        loser_id = loser.id

        merge_catalog_entries(sync_session, canon.id, loser_id)
        sync_session.commit()
        # Running again with the already-removed loser must not raise.
        merge_catalog_entries(sync_session, canon.id, loser_id)
        sync_session.commit()

        assert sync_session.get(CatalogEntry, loser_id) is None

    def test_missing_canonical_raises(self, sync_session):
        loser = _cat(sync_session)
        try:
            merge_catalog_entries(sync_session, 999999, loser.id)
        except ValueError:
            pass
        else:
            raise AssertionError("expected ValueError for missing canonical")
