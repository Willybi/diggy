"""Tests for services/genre_service.py — pure logic + DB."""
import os

import pytest

from services.genre_service import (
    ALL_PILLARS,
    _pillar_genre_names,
    aggregate_top_genres,
    genre_pillar,
    lookup_deezer_genres,
    pillar_map,
)


class TestPillars:
    def test_all_pillars_set(self):
        assert set(ALL_PILLARS) == {
            "house", "techno", "trance", "dnb", "hardcore", "harddance", "autres"
        }

    def test_genre_pillar_fallback_for_unknown(self):
        # With an empty or unpopulated cache, unknown genres return "autres"
        result = genre_pillar("completely_unknown_genre_xyz")
        assert result == ("autres", 0)

    def test_genre_pillar_returns_tuple(self):
        result = genre_pillar("anything")
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_pillar_genre_names_empty_for_unknown_pillar(self):
        # If no genres are cached under a non-existent pillar name, return []
        result = _pillar_genre_names("nonexistent_pillar")
        assert result == []

    def test_pillar_genre_names_with_populated_cache(self):
        # Temporarily inject a value into the cache
        pillar_map()["Test House Genre"] = ("house", 1)
        try:
            result = _pillar_genre_names("house")
            assert "Test House Genre" in result
        finally:
            pillar_map().pop("Test House Genre", None)

    def test_pillar_genre_names_returns_list(self):
        assert isinstance(_pillar_genre_names("techno"), list)

    def test_all_pillars_is_tuple(self):
        assert isinstance(ALL_PILLARS, tuple)


class TestAggregateTopGenres:
    """Shared helper backing the playlist AND set detail top_genres aggregate."""

    def test_empty_input_returns_empty(self):
        assert aggregate_top_genres([]) == []

    def test_all_genreless_tracks_return_empty(self):
        assert aggregate_top_genres([[], [], []]) == []

    def test_counts_pct_and_alpha_tie_break(self):
        # techno appears on tracks 0,1 -> 2 ; house on tracks 1,2 -> 2 ; track 3
        # is genre-less (excluded from the denominator = 3 genre-bearing tracks).
        out = aggregate_top_genres([["techno"], ["techno", "house"], ["house"], []])
        # tie on count 2 -> alphabetical (house before techno)
        assert [g.name for g in out] == ["house", "techno"]
        assert {g.name: g.pct for g in out} == {"house": 67, "techno": 67}  # round(200/3)

    def test_dedupes_repeated_genre_within_a_track(self):
        out = aggregate_top_genres([["techno", "techno"]])
        assert len(out) == 1
        assert out[0].name == "techno"
        assert out[0].pct == 100  # 1 genre-bearing track

    def test_caps_at_five_by_default(self):
        lists = []
        for genre, cnt in [("g6", 6), ("g5", 5), ("g4", 4), ("g3", 3), ("g2", 2), ("g1", 1)]:
            lists += [[genre]] * cnt
        out = aggregate_top_genres(lists)
        assert [g.name for g in out] == ["g6", "g5", "g4", "g3", "g2"]
        assert len(out) == 5  # "g1" (count 1) dropped by the cap

    def test_cap_is_configurable(self):
        out = aggregate_top_genres([["a"], ["b"], ["c"]], cap=2)
        assert len(out) == 2

    def test_pillar_resolved_from_cache(self):
        pillar_map()["Test Deep House"] = ("house", 2)
        try:
            out = aggregate_top_genres([["Test Deep House"]])
        finally:
            pillar_map().pop("Test Deep House", None)
        assert (out[0].pillar, out[0].depth) == ("house", 2)


class TestLookupDeezerGenres:
    async def test_raises_lookup_error_for_missing_catalog(self, db):
        with pytest.raises(LookupError, match="not found"):
            await lookup_deezer_genres(db, catalog_id=9999999, apply=False)

    async def test_raises_value_error_when_no_deezer_id(self, db):
        from models import CatalogEntry
        c = CatalogEntry(title="T", artist="A", normalized_key="a|t")
        db.add(c)
        await db.commit()
        await db.refresh(c)

        with pytest.raises(ValueError, match="deezer_id"):
            await lookup_deezer_genres(db, catalog_id=c.id, apply=False)


@pytest.mark.skipif(
    not os.environ.get("DATABASE_URL", "").startswith("postgresql"),
    reason="list_genres uses PostgreSQL-only SQL (PERCENTILE_CONT, unnest, CROSS JOIN LATERAL)",
)
class TestListGenresLibSort:
    """`sort=lib` ranks genres by in-library track count (D6 p.7).

    Tie-break mirrors the artists list `lib` sort: in_lib_count desc, then total
    track_count desc, then name. Runs on PostgreSQL only (the stats SQL does not
    execute on the SQLite harness).
    """

    async def _seed(self, db, user):
        from models import CatalogEntry, UserTrack

        # (genre, total catalog tracks, tracks in the user's library)
        plan = [
            ("ztestlibsort_a", 3, 1),
            ("ztestlibsort_b", 2, 2),
            ("ztestlibsort_c", 1, 1),
            ("ztestlibsort_d", 1, 1),
        ]
        for genre, total, in_lib in plan:
            for i in range(total):
                entry = CatalogEntry(
                    title=f"{genre}-{i}",
                    artist="A",
                    normalized_key=f"{genre}|{i}",
                    genres=[genre],
                    scope="shared",
                )
                db.add(entry)
                await db.flush()
                if i < in_lib:
                    db.add(UserTrack(user_id=user.id, catalog_id=entry.id))
        await db.commit()

    async def test_lib_sort_orders_by_in_lib_then_tracks_then_name(self, db, auth_user):
        from services import genre_service

        await self._seed(db, auth_user)
        res = await genre_service.list_genres(
            db, auth_user.id, family=None, sort="lib", q=None, limit=24, offset=0
        )
        names = [it["name"] for it in res["items"]]
        # b (in_lib 2) leads; a/c/d tie on in_lib 1 -> track_count desc (a=3),
        # then c/d tie on track_count 1 -> alphabetical (c before d).
        assert names == [
            "ztestlibsort_b", "ztestlibsort_a", "ztestlibsort_c", "ztestlibsort_d"
        ]
        assert {it["name"]: it["inLibCount"] for it in res["items"]} == {
            "ztestlibsort_b": 2, "ztestlibsort_a": 1,
            "ztestlibsort_c": 1, "ztestlibsort_d": 1,
        }

    async def test_tracks_sort_differs_from_lib(self, db, auth_user):
        # Control: the default `tracks` sort ranks by total track_count, so
        # genre "a" (3 tracks) leads — proving `lib` genuinely reorders the set.
        from services import genre_service

        await self._seed(db, auth_user)
        res = await genre_service.list_genres(
            db, auth_user.id, family=None, sort="tracks", q=None, limit=24, offset=0
        )
        assert [it["name"] for it in res["items"]][0] == "ztestlibsort_a"


@pytest.mark.skipif(
    not os.environ.get("DATABASE_URL", "").startswith("postgresql"),
    reason="list_genre_tracks uses PostgreSQL-only SQL (= ANY(genres), unnest)",
)
class TestListGenreTracksArtistsAvis:
    """Additive `artists` + `avis` fields on GET /api/genres/tracks (genre-detail
    rebuild, Lot 0).

    `artists` = structured refs from catalog_artists in `position` order (empty
    list when the entry has none — the flat `artist` string stays as fallback).
    `avis` = canonical COALESCE(user_opinions.opinion, user_tracks.avis), None
    for guests and for other users' opinions. Runs on PostgreSQL only (the
    tracks SQL does not execute on the SQLite harness).
    """

    GENRE = "ztesttracksavis"

    async def _seed(self, db, user):
        from models import Artist, CatalogArtist, CatalogEntry, UserOpinion, UserTrack

        entries = {}
        for slug in ("t0_two_artists", "t1_opinion_only", "t2_ut_avis_only", "t3_both"):
            entry = CatalogEntry(
                title=slug,
                artist=f"flat {slug}",
                normalized_key=f"{self.GENRE}|{slug}",
                genres=[self.GENRE],
                scope="shared",
            )
            db.add(entry)
            entries[slug] = entry
        a1 = Artist(name="ZTest Artist One", normalized_name="ztest artist one")
        a2 = Artist(name="ZTest Artist Two", normalized_name="ztest artist two")
        db.add_all([a1, a2])
        await db.flush()

        # Inserted with position 2 BEFORE position 1: proves ORDER BY position.
        db.add(CatalogArtist(
            catalog_id=entries["t0_two_artists"].id, artist_id=a2.id, position=2
        ))
        db.add(CatalogArtist(
            catalog_id=entries["t0_two_artists"].id, artist_id=a1.id, position=1
        ))
        db.add(UserOpinion(
            user_id=user.id, entity_type="track",
            entity_key=str(entries["t1_opinion_only"].id), opinion="liked",
        ))
        db.add(UserTrack(
            user_id=user.id, catalog_id=entries["t2_ut_avis_only"].id, avis="disliked"
        ))
        db.add(UserTrack(
            user_id=user.id, catalog_id=entries["t3_both"].id, avis="disliked"
        ))
        db.add(UserOpinion(
            user_id=user.id, entity_type="track",
            entity_key=str(entries["t3_both"].id), opinion="liked",
        ))
        await db.commit()
        return {slug: e.id for slug, e in entries.items()}

    async def _list(self, db, user_id):
        from services import genre_service

        res = await genre_service.list_genre_tracks(
            db, self.GENRE, user_id, sort="alpha", q=None, in_lib=None,
            limit=50, offset=0,
        )
        return {it["title"]: it for it in res["items"]}

    async def test_artists_returned_in_position_order(self, db, auth_user):
        ids = await self._seed(db, auth_user)
        by_title = await self._list(db, auth_user.id)
        artists = by_title["t0_two_artists"]["artists"]
        assert [a["name"] for a in artists] == ["ZTest Artist One", "ZTest Artist Two"]
        assert all(isinstance(a["id"], int) for a in artists)
        assert ids["t0_two_artists"] == by_title["t0_two_artists"]["id"]

    async def test_no_structured_artists_gives_empty_list_and_flat_fallback(
        self, db, auth_user
    ):
        await self._seed(db, auth_user)
        by_title = await self._list(db, auth_user.id)
        item = by_title["t1_opinion_only"]
        assert item["artists"] == []
        assert item["artist"] == "flat t1_opinion_only"

    async def test_avis_coalesces_opinion_over_user_track(self, db, auth_user):
        await self._seed(db, auth_user)
        by_title = await self._list(db, auth_user.id)
        assert by_title["t1_opinion_only"]["avis"] == "liked"  # opinion alone
        assert by_title["t2_ut_avis_only"]["avis"] == "disliked"  # ut.avis alone
        assert by_title["t3_both"]["avis"] == "liked"  # opinion wins the COALESCE
        assert by_title["t0_two_artists"]["avis"] is None  # no opinion at all

    async def test_avis_is_scoped_to_the_viewer(self, db, auth_user):
        from models import User

        await self._seed(db, auth_user)
        other = User(
            email="other@test.com", username="otheruser",
            google_id="google-other-user", is_active=True, is_admin=False,
        )
        db.add(other)
        await db.commit()
        await db.refresh(other)
        by_title = await self._list(db, other.id)
        assert all(it["avis"] is None for it in by_title.values())

    async def test_guest_gets_null_avis_and_still_sees_artists(self, db, auth_user):
        await self._seed(db, auth_user)
        by_title = await self._list(db, None)
        assert all(it["avis"] is None for it in by_title.values())
        assert len(by_title["t0_two_artists"]["artists"]) == 2

    async def test_guest_endpoint_returns_200(self, db, auth_user, client):
        await self._seed(db, auth_user)
        r = await client.get(f"/api/genres/tracks/{self.GENRE}")
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) == 4
        assert all(it["avis"] is None for it in items)


_PG_ONLY = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL", "").startswith("postgresql"),
    reason="Genre Detail builders use PostgreSQL-only SQL (= ANY, unnest, LATERAL)",
)


@_PG_ONLY
class TestGenreDetailPaginationTieBreak:
    """A1-06: every Genre Detail builder ends its ORDER BY on the table PK so
    ex-aequo rows keep a total order across offset pages. Without the id
    tiebreak, ties reshuffle between two LIMIT/OFFSET pages and rows are
    duplicated or skipped in the infinite scroll. Runs on PostgreSQL only."""

    GENRE = "ztestpagetiebreak"

    @staticmethod
    def _assert_two_pages_cover(ids1, ids2, expected):
        assert len(ids1) == 3 and len(ids2) == 3
        assert set(ids1).isdisjoint(ids2)  # no row on both pages
        assert len(set(ids1 + ids2)) == expected  # no hole

    async def test_tracks_bpm_ties_stable(self, db, auth_user):
        from models import CatalogEntry
        from services import genre_service

        for i in range(6):
            db.add(CatalogEntry(
                title=f"pgtrack-{i}", artist="A",
                normalized_key=f"{self.GENRE}|trk{i}",
                genres=[self.GENRE], bpm=128.0, scope="shared",
            ))
        await db.commit()

        async def page(offset):
            res = await genre_service.list_genre_tracks(
                db, self.GENRE, auth_user.id, sort="bpm", q=None, in_lib=None,
                limit=3, offset=offset,
            )
            return [it["id"] for it in res["items"]]

        p1, p2 = await page(0), await page(3)
        self._assert_two_pages_cover(p1, p2, 6)
        # All bpm equal → order is purely c.id DESC across the two pages.
        assert (p1 + p2) == sorted(p1 + p2, reverse=True)

    async def test_sets_count_ties_stable(self, db, auth_user):
        from models import CatalogEntry, DJSet, SetTrack
        from services import genre_service

        for i in range(6):
            s = DJSet(source="trackid", title=f"pgset-{i}")
            db.add(s)
            await db.flush()
            cat = CatalogEntry(
                title=f"pgset-trk-{i}", artist="A",
                normalized_key=f"{self.GENRE}|set{i}",
                genres=[self.GENRE], scope="shared",
            )
            db.add(cat)
            await db.flush()
            db.add(SetTrack(
                set_id=s.id, position=1, catalog_id=cat.id,
                raw_title=cat.title, is_id=False,
            ))
        await db.commit()

        async def page(offset):
            res = await genre_service.list_genre_sets(
                db, self.GENRE, limit=3, offset=offset,
            )
            return [it["id"] for it in res["items"]]

        p1, p2 = await page(0), await page(3)
        # Equal genre_track_count + NULL played_date → order is s.id DESC.
        self._assert_two_pages_cover(p1, p2, 6)
        assert (p1 + p2) == sorted(p1 + p2, reverse=True)

    async def test_playlists_count_ties_stable(self, db, auth_user):
        from models import CatalogEntry, RadarTrack, WatchedEntity
        from services import genre_service

        for i in range(6):
            we = WatchedEntity(
                external_id=f"pgwe-{i}", source="deezer", title=f"pgpl-{i}",
            )
            db.add(we)
            await db.flush()
            cat = CatalogEntry(
                title=f"pgpl-trk-{i}", artist="A",
                normalized_key=f"{self.GENRE}|pl{i}",
                genres=[self.GENRE], scope="shared",
            )
            db.add(cat)
            await db.flush()
            db.add(RadarTrack(
                watched_entity_id=we.id, external_track_id=f"pgrt-{i}",
                source="deezer", title=cat.title, catalog_id=cat.id,
            ))
        await db.commit()

        async def page(offset):
            res = await genre_service.list_genre_playlists(
                db, self.GENRE, limit=3, offset=offset,
            )
            return [it["id"] for it in res["items"]]

        p1, p2 = await page(0), await page(3)
        # Equal genre_track_count → order is we.id DESC.
        self._assert_two_pages_cover(p1, p2, 6)
        assert (p1 + p2) == sorted(p1 + p2, reverse=True)

    async def test_artists_count_ties_stable(self, db, auth_user):
        from models import Artist, CatalogEntry
        from services import genre_service

        for i in range(6):
            name = f"PgArtist{i}"
            db.add(Artist(name=name, normalized_name=name.lower()))
            db.add(CatalogEntry(
                title=f"pgart-trk-{i}", artist=name,
                normalized_key=f"{self.GENRE}|art{i}",
                genres=[self.GENRE], scope="shared",
            ))
        await db.commit()

        async def page(offset):
            res = await genre_service.list_genre_artists(
                db, self.GENRE, auth_user.id, limit=3, offset=offset,
            )
            return [it["id"] for it in res["items"]]

        p1, p2 = await page(0), await page(3)
        # Equal track_count; a.name (then a.id DESC) gives the total order — the
        # point is that no artist is duplicated or skipped across pages.
        self._assert_two_pages_cover(p1, p2, 6)


@_PG_ONLY
class TestGenreDetailLikeEscape:
    """A6-06: literal % / _ in a Genre Detail query must match literally, not as
    a LIKE wildcard. Runs on PostgreSQL only (raw SQL builders)."""

    GENRE = "ztestgenreescape"

    async def test_tracklist_query_escapes_wildcards(self, db, auth_user):
        from models import CatalogEntry
        from services import genre_service

        db.add_all([
            CatalogEntry(
                title="A%B", artist="X", normalized_key=f"{self.GENRE}|apctb",
                genres=[self.GENRE], scope="shared",
            ),
            CatalogEntry(
                title="AXB", artist="X", normalized_key=f"{self.GENRE}|axb",
                genres=[self.GENRE], scope="shared",
            ),
        ])
        await db.commit()

        res = await genre_service.list_genre_tracks(
            db, self.GENRE, auth_user.id, sort="alpha", q="A%B", in_lib=None,
            limit=50, offset=0,
        )
        assert {it["title"] for it in res["items"]} == {"A%B"}

    async def test_genre_name_query_escapes_wildcards(self, db, auth_user):
        from models import CatalogEntry
        from services import genre_service

        db.add_all([
            CatalogEntry(
                title="g1", artist="X", normalized_key="x|g1",
                genres=["a%b"], scope="shared",
            ),
            CatalogEntry(
                title="g2", artist="X", normalized_key="x|g2",
                genres=["axb"], scope="shared",
            ),
        ])
        await db.commit()

        res = await genre_service.list_genres(
            db, auth_user.id, family=None, sort="tracks", q="a%b",
            limit=24, offset=0,
        )
        assert {it["name"] for it in res["items"]} == {"a%b"}


@_PG_ONLY
class TestGenreDetailReliability:
    """C8 (L2): a set flagged `unreliable` drops out of the genre-detail set list
    (list_genre_sets) AND the genre-detail set_count stat (get_detail). Runs on
    PostgreSQL only (raw-SQL builders)."""

    GENRE = "ztestgenrereliab"

    async def _seed(self, db):
        from models import CatalogEntry, DJSet, SetTrack

        good = DJSet(source="trackid", title="Trusted Genre Set")
        bad = DJSet(source="trackid", title="Flagged Genre Set", unreliable=True)
        db.add_all([good, bad])
        await db.flush()
        # each set carries its own genre-tagged identified track, so only the flag
        # separates the two (both would count if unfiltered).
        for i, s in enumerate((good, bad)):
            cat = CatalogEntry(
                title=f"{self.GENRE}-trk-{i}", artist="A",
                normalized_key=f"{self.GENRE}|{i}", genres=[self.GENRE],
                scope="shared",
            )
            db.add(cat)
            await db.flush()
            db.add(SetTrack(
                set_id=s.id, position=1, catalog_id=cat.id,
                raw_title=cat.title, is_id=False,
            ))
        await db.commit()

    async def test_list_genre_sets_excludes_unreliable(self, db):
        from services import genre_service

        await self._seed(db)
        res = await genre_service.list_genre_sets(db, self.GENRE, limit=50, offset=0)
        assert [it["title"] for it in res["items"]] == ["Trusted Genre Set"]
        assert res["total"] == 1

    async def test_get_detail_set_count_excludes_unreliable(self, db, auth_user):
        from services import genre_service

        await self._seed(db)
        detail = await genre_service.get_detail(db, self.GENRE, auth_user.id)
        assert detail["setCount"] == 1
