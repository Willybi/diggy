"""Tests for /api/search endpoint."""
from datetime import date

from models import (
    Album,
    AlbumType,
    Artist,
    CatalogEntry,
    DJSet,
    SetTrack,
    TrackIdIndex,
    WatchedEntity,
)
from services.search_service import _search_sets
from utils import search_fold


class TestSearch:
    async def test_empty_query_returns_empty(self, client):
        r = await client.get("/api/search?q=")
        assert r.status_code == 200
        data = r.json()
        assert data["items"] == []
        assert data["total"] == 0

    async def test_search_tracks_by_title(self, client, db):
        db.add(CatalogEntry(title="Cola", artist="CamelPhat", normalized_key="cola - camelphat"))
        db.add(CatalogEntry(title="Strobe", artist="Deadmau5", normalized_key="strobe - deadmau5"))
        await db.commit()

        r = await client.get("/api/search?q=cola&scope=track")
        data = r.json()
        assert data["totals"]["track"] == 1
        track_items = [i for i in data["items"] if i["type"] == "track"]
        assert len(track_items) == 1
        assert track_items[0]["title"] == "Cola"

    async def test_search_tracks_by_artist(self, client, db):
        db.add(CatalogEntry(title="Cola", artist="CamelPhat", normalized_key="cola - camelphat"))
        await db.commit()

        r = await client.get("/api/search?q=camelphat&scope=track")
        data = r.json()
        assert data["totals"]["track"] >= 1

    async def test_search_artists(self, client, db):
        db.add(Artist(name="CamelPhat", normalized_name="camelphat"))
        db.add(Artist(name="ANNA", normalized_name="anna"))
        await db.commit()

        r = await client.get("/api/search?q=camel&scope=artist")
        data = r.json()
        assert data["totals"]["artist"] == 1
        assert data["items"][0]["name"] == "CamelPhat"

    async def test_search_sets(self, client, db):
        # Set search now matches the pre-folded `search_text` column (L3), so
        # fixtures must populate it explicitly (the importer does this in prod).
        db.add(DJSet(title="Boiler Room Set", source="trackid", search_text="boiler room set"))
        db.add(DJSet(title="Radio Show", source="trackid", search_text="radio show"))
        await db.commit()

        r = await client.get("/api/search?q=boiler&scope=set")
        data = r.json()
        assert data["totals"]["set"] == 1
        assert data["items"][0]["title"] == "Boiler Room Set"

    async def test_search_sets_excludes_children(self, client, db):
        parent = DJSet(
            title="Boiler Room London",
            source="trackid",
            search_text="boiler room london",
        )
        db.add(parent)
        await db.flush()
        child = DJSet(
            title="Boiler Room London Part 2",
            source="trackid",
            search_text="boiler room london part 2",
            parent_set_id=parent.id,
        )
        db.add(child)
        await db.commit()

        r = await client.get("/api/search?q=boiler&scope=set")
        data = r.json()
        titles = [i["title"] for i in data["items"]]
        assert "Boiler Room London" in titles
        assert "Boiler Room London Part 2" not in titles
        assert data["totals"]["set"] == 1

    async def test_search_sets_excludes_unreliable(self, client, db):
        # C8 (L2): a flagged set must drop out of search results AND the count.
        db.add(DJSet(
            title="Boiler Room Trusted",
            source="trackid",
            search_text="boiler room trusted",
        ))
        db.add(DJSet(
            title="Boiler Room Flagged",
            source="trackid",
            search_text="boiler room flagged",
            unreliable=True,
        ))
        await db.commit()

        r = await client.get("/api/search?q=boiler&scope=set")
        data = r.json()
        titles = [i["title"] for i in data["items"]]
        assert "Boiler Room Trusted" in titles
        assert "Boiler Room Flagged" not in titles
        assert data["totals"]["set"] == 1

    async def test_search_playlists(self, client, db):
        db.add(WatchedEntity(external_id="123", source="deezer", title="Deep House Selection"))
        db.add(WatchedEntity(external_id="456", source="deezer", title="Techno Picks"))
        await db.commit()

        r = await client.get("/api/search?q=deep&scope=playlist")
        data = r.json()
        assert data["totals"]["playlist"] == 1
        assert data["items"][0]["title"] == "Deep House Selection"

    async def test_search_multiple_scopes(self, client, db):
        """Test searching across multiple entity types (not genre, which needs PG)."""
        db.add(CatalogEntry(title="Deep Track", artist="DJ Deep", normalized_key="deep track - dj deep"))
        db.add(Artist(name="DJ Deep", normalized_name="dj deep"))
        db.add(DJSet(title="Deep Session", source="trackid", search_text="deep session"))
        await db.commit()

        # Search tracks
        r1 = await client.get("/api/search?q=deep&scope=track")
        assert r1.json()["totals"]["track"] >= 1

        # Search artists
        r2 = await client.get("/api/search?q=deep&scope=artist")
        assert r2.json()["totals"]["artist"] >= 1

        # Search sets
        r3 = await client.get("/api/search?q=deep&scope=set")
        assert r3.json()["totals"]["set"] >= 1

    async def test_search_scope_single_type(self, client, db):
        db.add(CatalogEntry(title="Track", artist="Art", normalized_key="track - art"))
        db.add(Artist(name="Art", normalized_name="art"))
        await db.commit()

        r = await client.get("/api/search?q=art&scope=track")
        data = r.json()
        # Should only return tracks
        types = {i["type"] for i in data["items"]}
        assert types <= {"track"}

    async def test_guest_cap(self, client, db):
        """Guest users should have capped results."""
        for i in range(10):
            db.add(CatalogEntry(
                title=f"House Track {i}", artist="DJ",
                normalized_key=f"house track {i} - dj",
            ))
        await db.commit()

        r = await client.get("/api/search?q=house&scope=track")
        data = r.json()
        # client fixture has no user override, so it's guest
        # GUEST_CAP = 6
        assert len(data["items"]) <= 6

    async def test_search_with_auth_no_cap(self, auth_client, db):
        """Authenticated users should not be capped."""
        for i in range(10):
            db.add(CatalogEntry(
                title=f"House Track {i}", artist="DJ",
                normalized_key=f"house track {i} - dj",
            ))
        await db.commit()

        r = await auth_client.get("/api/search?q=house&scope=track")
        data = r.json()
        assert len(data["items"]) == 10

    async def test_relevance_sorting(self, client, db):
        """Exact matches should rank higher."""
        db.add(CatalogEntry(title="Cola", artist="CamelPhat", normalized_key="cola - camelphat"))
        db.add(CatalogEntry(title="Cola Remix", artist="CamelPhat", normalized_key="cola remix - camelphat"))
        await db.commit()

        r = await client.get("/api/search?q=cola&scope=track")
        data = r.json()
        assert len(data["items"]) == 2
        # Exact match "Cola" should come first
        assert data["items"][0]["title"] == "Cola"


class TestSearchAlbums:
    """L5: the `album` scope returns albums and feeds totals.album."""

    async def test_search_albums_by_title(self, client, db):
        a = Artist(name="Daft Punk", normalized_name="daft punk")
        db.add(a)
        await db.flush()
        db.add(Album(
            title="Random Access Memories", artist_id=a.id,
            record_type=AlbumType.album, release_date=date(2013, 5, 17),
        ))
        db.add(Album(title="Discovery", record_type=AlbumType.album))
        await db.commit()

        r = await client.get("/api/search?q=random&scope=album")
        assert r.status_code == 200
        data = r.json()
        assert data["totals"]["album"] == 1
        items = [i for i in data["items"] if i["type"] == "album"]
        assert len(items) == 1
        assert items[0]["title"] == "Random Access Memories"
        assert items[0]["artist"] == "Daft Punk"
        assert items[0]["record_type"] == "album"
        assert items[0]["year"] == 2013

    async def test_album_scope_returns_only_albums(self, client, db):
        db.add(Album(title="House Anthems", record_type=AlbumType.compile))
        db.add(CatalogEntry(
            title="House Track", artist="DJ", normalized_key="house track - dj"
        ))
        await db.commit()

        r = await client.get("/api/search?q=house&scope=album")
        data = r.json()
        types = {i["type"] for i in data["items"]}
        assert types <= {"album"}
        assert data["totals"]["album"] == 1

    async def test_album_feeds_overall_total(self, client, db):
        # scope=all triggers the PG-only genre query (SQLite can't run it), so we
        # assert the total-sum wiring on the single album scope: with only albums
        # matched, the overall `total` equals totals.album (proves it's summed in).
        db.add(Album(title="Deep Cuts", record_type=AlbumType.album))
        db.add(Album(title="Deep End", record_type=AlbumType.ep))
        await db.commit()

        r = await client.get("/api/search?q=deep&scope=album")
        data = r.json()
        assert data["totals"]["album"] == 2
        assert data["total"] == 2
        assert all(i["type"] == "album" for i in data["items"])

    async def test_no_album_match(self, client, db):
        db.add(Album(title="Only This", record_type=AlbumType.album))
        await db.commit()

        r = await client.get("/api/search?q=zzz&scope=album")
        data = r.json()
        assert data["totals"]["album"] == 0
        assert data["items"] == []


class TestSearchLikeEscape:
    """A6-06: % and _ in the query match literally instead of acting as wildcards."""

    async def test_percent_matches_literally(self, client, db):
        db.add(CatalogEntry(title="100% Pure", artist="DJ", normalized_key="100% pure - dj"))
        db.add(CatalogEntry(title="100 Degrees", artist="DJ", normalized_key="100 degrees - dj"))
        await db.commit()

        r = await client.get("/api/search", params={"q": "100%", "scope": "track"})
        data = r.json()
        assert data["totals"]["track"] == 1
        assert data["items"][0]["title"] == "100% Pure"

    async def test_underscore_is_not_a_wildcard(self, client, db):
        db.add(CatalogEntry(title="abc", artist="DJ", normalized_key="abc - dj"))
        await db.commit()

        r = await client.get("/api/search", params={"q": "ab_", "scope": "track"})
        data = r.json()
        assert data["totals"]["track"] == 0
        assert data["items"] == []

    async def test_underscore_matches_literally(self, client, db):
        db.add(CatalogEntry(title="ab_c", artist="DJ", normalized_key="ab_c - dj"))
        db.add(CatalogEntry(title="abXc", artist="DJ", normalized_key="abxc - dj"))
        await db.commit()

        r = await client.get("/api/search", params={"q": "ab_", "scope": "track"})
        data = r.json()
        assert data["totals"]["track"] == 1
        assert data["items"][0]["title"] == "ab_c"

    async def test_artist_scope_percent_literal(self, client, db):
        db.add(Artist(name="100% Techno", normalized_name="100% techno"))
        db.add(Artist(name="100 Grad", normalized_name="100 grad"))
        await db.commit()

        r = await client.get("/api/search", params={"q": "100%", "scope": "artist"})
        data = r.json()
        assert data["totals"]["artist"] == 1
        assert data["items"][0]["name"] == "100% Techno"


class TestSearchArtistSpaceInsensitive:
    """X4.f: a spaced-out Deezer artist name is findable by its collapsed spelling."""

    async def test_spaced_name_found_by_compact_query(self, client, db):
        # Real Deezer name spelled letter-by-letter; searching the collapsed
        # spelling must find it (the plain ILIKE alone would miss).
        db.add(Artist(name="t e s t p r e s s", normalized_name="t e s t p r e s s"))
        db.add(Artist(name="Carl Cox", normalized_name="carl cox"))
        await db.commit()

        r = await client.get("/api/search", params={"q": "testpress", "scope": "artist"})
        data = r.json()
        assert data["totals"]["artist"] == 1
        assert data["items"][0]["name"] == "t e s t p r e s s"

    async def test_normal_query_still_matches(self, client, db):
        db.add(Artist(name="Carl Cox", normalized_name="carl cox"))
        db.add(Artist(name="ANNA", normalized_name="anna"))
        await db.commit()

        r = await client.get("/api/search", params={"q": "carl", "scope": "artist"})
        data = r.json()
        assert data["totals"]["artist"] == 1
        assert data["items"][0]["name"] == "Carl Cox"

    async def test_compact_query_metachar_stays_literal(self, client, db):
        # The compact clause must escape LIKE metacharacters too: "_" is a literal,
        # not a wildcard, even against the space-collapsed name.
        db.add(Artist(name="a b_c", normalized_name="a b_c"))
        db.add(Artist(name="a b X c", normalized_name="a b x c"))
        await db.commit()

        # "ab_" collapses to "ab_"; only "ab_c" (compact of "a b_c") matches literally.
        r = await client.get("/api/search", params={"q": "ab_", "scope": "artist"})
        data = r.json()
        assert data["totals"]["artist"] == 1
        assert data["items"][0]["name"] == "a b_c"


class TestSearchSpaceInsensitive:
    """X4.h: space-insensitive matching extended to the Tracks / Sets / Playlists
    scopes via the shared helper. A letter-spaced Deezer name is found by its
    collapsed spelling, and the `total` count stays consistent with the items."""

    async def test_tracks_spaced_artist_found_by_compact(self, client, db):
        db.add(CatalogEntry(
            title="Some Track", artist="t e s t p r e s s",
            normalized_key="some track - t e s t p r e s s",
        ))
        db.add(CatalogEntry(title="Other", artist="Carl Cox", normalized_key="other - carl cox"))
        await db.commit()

        r = await client.get("/api/search", params={"q": "testpress", "scope": "track"})
        data = r.json()
        assert data["totals"]["track"] == 1
        assert data["items"][0]["artist"] == "t e s t p r e s s"

    async def test_tracks_normal_query_still_matches(self, client, db):
        db.add(CatalogEntry(title="Cola", artist="CamelPhat", normalized_key="cola - camelphat"))
        await db.commit()

        r = await client.get("/api/search", params={"q": "cola", "scope": "track"})
        assert r.json()["totals"]["track"] == 1

    async def test_sets_spaced_title_found_and_total_consistent(self, client, db):
        db.add(DJSet(
            title="t e s t p r e s s",
            source="trackid",
            search_text="t e s t p r e s s",
        ))
        db.add(DJSet(title="Radio Show", source="trackid", search_text="radio show"))
        await db.commit()

        r = await client.get("/api/search", params={"q": "testpress", "scope": "set"})
        data = r.json()
        set_items = [i for i in data["items"] if i["type"] == "set"]
        # total==1 proves the SEPARATE count query got the compact clause too.
        assert data["totals"]["set"] == 1
        assert data["totals"]["set"] == len(set_items)
        assert set_items[0]["title"] == "t e s t p r e s s"

    async def test_playlists_spaced_title_found_and_total_consistent(self, client, db):
        db.add(WatchedEntity(external_id="p1", source="deezer", title="t e s t p r e s s"))
        db.add(WatchedEntity(external_id="p2", source="deezer", title="Techno Picks"))
        await db.commit()

        r = await client.get("/api/search", params={"q": "testpress", "scope": "playlist"})
        data = r.json()
        pl_items = [i for i in data["items"] if i["type"] == "playlist"]
        assert data["totals"]["playlist"] == 1
        assert data["totals"]["playlist"] == len(pl_items)
        assert pl_items[0]["title"] == "t e s t p r e s s"


class TestSearchPagination:
    """A1-02: LIMIT must be deterministic (ORDER BY) and single-scope offset real."""

    async def test_order_stable_between_identical_calls(self, client, db):
        for i in range(5):
            db.add(CatalogEntry(
                title=f"Techno {i}", artist="DJ",
                normalized_key=f"techno {i} - dj",
            ))
        await db.commit()

        r1 = await client.get("/api/search?q=techno&scope=track")
        r2 = await client.get("/api/search?q=techno&scope=track")
        ids1 = [i["id"] for i in r1.json()["items"]]
        ids2 = [i["id"] for i in r2.json()["items"]]
        assert len(ids1) >= 1
        assert ids1 == ids2

    async def test_single_scope_offset_returns_distinct_pages(self, auth_client, db):
        for i in range(4):
            db.add(CatalogEntry(
                title=f"House {i}", artist="DJ",
                normalized_key=f"house {i} - dj",
            ))
        await db.commit()

        r0 = await auth_client.get("/api/search?q=house&scope=track&limit=2&offset=0")
        r2 = await auth_client.get("/api/search?q=house&scope=track&limit=2&offset=2")
        ids0 = {i["id"] for i in r0.json()["items"]}
        ids2 = {i["id"] for i in r2.json()["items"]}
        assert len(ids0) == 2
        assert len(ids2) == 2
        # Real DB pagination: the two windows never overlap.
        assert ids0.isdisjoint(ids2)


class TestSearchSetsWeighted:
    """L3: multi-field, fold-insensitive set search — title (via search_text,
    incl. children), artist, channel, date, weighted and roots-only."""

    async def test_curly_apostrophe_title_found_by_straight_quote(self, client, db):
        # search_text holds the folded form of a curly-apostrophe title; a query
        # typed with a straight apostrophe folds to the same string and matches.
        db.add(DJSet(
            title="DJ’s Warehouse Set",
            source="trackid",
            search_text=search_fold("DJ’s Warehouse Set"),
        ))
        db.add(DJSet(title="Radio Show", source="trackid", search_text="radio show"))
        await db.commit()

        r = await client.get("/api/search", params={"q": "dj's warehouse", "scope": "set"})
        data = r.json()
        assert data["totals"]["set"] == 1
        assert data["items"][0]["title"] == "DJ’s Warehouse Set"

    async def test_deaccented_query_matches_accented_title(self, client, db):
        db.add(DJSet(
            title="Beyoncé Live",
            source="trackid",
            search_text=search_fold("Beyoncé Live"),
        ))
        await db.commit()

        r = await client.get("/api/search", params={"q": "beyonce", "scope": "set"})
        data = r.json()
        assert data["totals"]["set"] == 1
        assert data["items"][0]["title"] == "Beyoncé Live"

    async def test_child_title_match_bubbles_to_root_once(self, client, db):
        # A dedup root carries an abbreviated title; the rich title is on the
        # CHILD. A query hitting the child's search_text must return the ROOT,
        # exactly once, and never the child as a standalone result.
        root = DJSet(title="Boiler Room", source="trackid", search_text="boiler room")
        db.add(root)
        await db.flush()
        child = DJSet(
            title="Boiler Room Amsterdam Warehouse",
            source="trackid",
            search_text="boiler room amsterdam warehouse",
            parent_set_id=root.id,
        )
        db.add(child)
        await db.commit()

        r = await client.get("/api/search", params={"q": "warehouse", "scope": "set"})
        data = r.json()
        set_items = [i for i in data["items"] if i["type"] == "set"]
        assert len(set_items) == 1
        assert set_items[0]["id"] == root.id
        assert data["totals"]["set"] == 1

    async def test_title_outranks_channel_at_endpoint(self, client, db):
        # Same weighting, but through the HTTP endpoint: proves the helper's
        # weighted order survives the orchestrator's global re-sort (skipped for
        # scope="set"). The channel-only set has a HIGHER track_count, so a naive
        # relevance+popularity re-sort would wrongly float it above the title
        # match (both have _relevance=1 on their title).
        titled = DJSet(title="Warehouse Night", source="trackid", search_text="warehouse night")
        channeled = DJSet(title="Random Show", source="trackid", search_text="random show")
        db.add_all([titled, channeled])
        await db.flush()
        # Give the channel-only set more tracks (higher popularity).
        for pos in range(5):
            db.add(SetTrack(set_id=channeled.id, position=pos, raw_title=f"t{pos}"))
        db.add(SetTrack(set_id=titled.id, position=0, raw_title="only"))
        db.add(TrackIdIndex(
            trackid_id=903, set_id=channeled.id, channel="Warehouse Radio",
            hydration_state="hydrated",
        ))
        await db.commit()

        r = await client.get("/api/search", params={"q": "warehouse", "scope": "set"})
        data = r.json()
        set_items = [i for i in data["items"] if i["type"] == "set"]
        assert data["totals"]["set"] == 2
        # Title match (weight 3) must come first despite fewer tracks.
        assert set_items[0]["title"] == "Warehouse Night"
        assert set_items[1]["title"] == "Random Show"

    async def test_title_match_outranks_channel_match(self, db):
        # Direct service call so the assertion targets the helper's own weighted
        # ordering (title weight 3 > channel weight 2), independent of the
        # cross-scope re-sort the orchestrator applies for scope="all".
        a = DJSet(title="Techno Night", source="trackid", search_text="techno night")
        b = DJSet(title="Random Show", source="trackid", search_text="random show")
        db.add_all([a, b])
        await db.flush()
        # b only matches "techno" through its trackid_index channel.
        db.add(TrackIdIndex(
            trackid_id=901, set_id=b.id, channel="Techno Radio",
            hydration_state="hydrated",
        ))
        await db.commit()

        items, total = await _search_sets(db, "techno", 10, 0)
        titles = [i.title for i in items]
        assert titles == ["Techno Night", "Random Show"]
        assert total == 2

    async def test_channel_match_via_child_trackid_index(self, db):
        # A virtual root has no trackid_index of its own; the listing (and its
        # channel) hangs off the CHILD. The channel signal must still lift the root.
        root = DJSet(title="Set A", source="virtual", search_text="set a", is_virtual=True)
        db.add(root)
        await db.flush()
        child = DJSet(
            title="Set A raw", source="trackid", search_text="set a raw",
            parent_set_id=root.id,
        )
        db.add(child)
        await db.flush()
        db.add(TrackIdIndex(
            trackid_id=902, set_id=child.id, channel="HATE Channel",
            hydration_state="hydrated",
        ))
        await db.commit()

        items, total = await _search_sets(db, "hate", 10, 0)
        assert [i.id for i in items] == [root.id]
        assert total == 1

    async def test_roots_only_and_reliable_enforced(self, db):
        # A matching CHILD is never a standalone result (roots-only), and a
        # matching UNRELIABLE root is excluded entirely — only the clean root
        # that a child lifts comes back.
        root = DJSet(title="Parent", source="trackid", search_text="parent")
        db.add(root)
        await db.flush()
        child = DJSet(
            title="Warehouse Rave", source="trackid",
            search_text="warehouse rave", parent_set_id=root.id,
        )
        unreliable = DJSet(
            title="Warehouse Trash", source="trackid",
            search_text="warehouse trash", unreliable=True,
        )
        db.add_all([child, unreliable])
        await db.commit()

        items, total = await _search_sets(db, "warehouse", 10, 0)
        assert [i.id for i in items] == [root.id]
        assert total == 1

    async def test_broad_term_exact_total_and_weight_after_rewrite(self, db):
        # A broad query hitting several roots via DIFFERENT signals: the set-based
        # rewrite must return an EXACT total over the full match union (roots-only
        # + reliable), even when `limit` is smaller than the match count, AND keep
        # the weighted order (title 3 > channel 2).
        titled = DJSet(title="Warehouse Night", source="trackid", search_text="warehouse night")
        child_root = DJSet(title="Root", source="trackid", search_text="root")
        channeled = DJSet(title="Basement Show", source="trackid", search_text="basement show")
        flagged = DJSet(
            title="Warehouse Trash",
            source="trackid",
            search_text="warehouse trash",
            unreliable=True,
        )
        db.add_all([titled, child_root, channeled, flagged])
        await db.flush()
        # child_root matches "warehouse" ONLY through a CHILD title (bubbles up).
        db.add(DJSet(
            title="Warehouse Bootleg",
            source="trackid",
            search_text="warehouse bootleg",
            parent_set_id=child_root.id,
        ))
        # channeled matches "warehouse" ONLY through its trackid_index channel.
        db.add(TrackIdIndex(
            trackid_id=950, set_id=channeled.id, channel="Warehouse FM",
            hydration_state="hydrated",
        ))
        await db.commit()

        # 3 reliable roots match (titled + child_root via title, channeled via
        # channel); the unreliable "Warehouse Trash" is excluded → total EXACT = 3
        # despite the limit=2 window.
        items, total = await _search_sets(db, "warehouse", 2, 0)
        assert total == 3
        # Weight order: the two title matches (weight 3) rank above the
        # channel-only match (weight 2), so the limit=2 window is exactly them.
        top_ids = {i.id for i in items}
        assert top_ids == {titled.id, child_root.id}
        assert channeled.id not in top_ids
        assert flagged.id not in top_ids
