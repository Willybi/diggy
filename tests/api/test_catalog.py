"""Tests for /api/catalog endpoints."""
from datetime import date, datetime, timezone

from models import CatalogEntry, CatalogArtist, UserTrack, Artist, RadarTrack, WatchedEntity, SetTrack, DJSet, User, UserOpinion


class TestListCatalog:
    async def test_empty_returns_zero(self, client):
        r = await client.get("/api/catalog/")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 0
        assert data["items"] == []

    async def test_returns_entries(self, client, db):
        db.add(CatalogEntry(title="Cola", artist="CamelPhat", normalized_key="cola - camelphat"))
        await db.commit()
        r = await client.get("/api/catalog/")
        data = r.json()
        assert data["total"] == 1
        assert data["items"][0]["title"] == "Cola"

    async def test_search_filter(self, client, db):
        db.add(CatalogEntry(title="Cola", artist="CamelPhat", normalized_key="cola - camelphat"))
        db.add(CatalogEntry(title="Strobe", artist="Deadmau5", normalized_key="strobe - deadmau5"))
        await db.commit()
        r = await client.get("/api/catalog/?search=cola")
        data = r.json()
        assert data["total"] == 1
        assert data["items"][0]["title"] == "Cola"

    async def test_pagination(self, client, db):
        for i in range(5):
            db.add(CatalogEntry(title=f"Track {i}", artist="Art", normalized_key=f"track {i} - art"))
        await db.commit()
        r = await client.get("/api/catalog/?limit=2")
        data = r.json()
        assert len(data["items"]) == 2
        assert data["total"] == 5

    async def test_pagination_skip(self, client, db):
        for i in range(5):
            db.add(CatalogEntry(title=f"Track {i}", artist="Art", normalized_key=f"track {i} - art"))
        await db.commit()
        r = await client.get("/api/catalog/?skip=3&limit=10")
        data = r.json()
        assert len(data["items"]) == 2


class TestCatalogDetail:
    async def test_returns_entry(self, client, db):
        cat = CatalogEntry(title="Cola", artist="CamelPhat", normalized_key="cola - camelphat")
        db.add(cat)
        await db.commit()
        await db.refresh(cat)
        r = await client.get(f"/api/catalog/{cat.id}")
        assert r.status_code == 200
        data = r.json()
        assert data["title"] == "Cola"
        assert data["artist"] == "CamelPhat"
        assert "radar_appearances" in data
        assert "set_appearances" in data

    async def test_404_when_not_found(self, client):
        r = await client.get("/api/catalog/9999")
        assert r.status_code == 404


class TestCatalogInLib:
    async def test_in_lib_true_filter(self, auth_client, db, auth_user):
        cat1 = CatalogEntry(title="InLib", artist="A", normalized_key="inlib - a")
        cat2 = CatalogEntry(title="NotInLib", artist="B", normalized_key="notinlib - b")
        db.add_all([cat1, cat2])
        await db.commit()
        await db.refresh(cat1)
        db.add(UserTrack(user_id=auth_user.id, catalog_id=cat1.id, source="test"))
        await db.commit()

        r = await auth_client.get("/api/catalog/?in_lib=true")
        data = r.json()
        assert data["total"] == 1
        assert data["items"][0]["title"] == "InLib"
        assert data["items"][0]["in_lib"] is True

    async def test_in_lib_false_filter(self, auth_client, db, auth_user):
        cat1 = CatalogEntry(title="InLib", artist="A", normalized_key="inlib - a")
        cat2 = CatalogEntry(title="NotInLib", artist="B", normalized_key="notinlib - b")
        db.add_all([cat1, cat2])
        await db.commit()
        await db.refresh(cat1)
        db.add(UserTrack(user_id=auth_user.id, catalog_id=cat1.id, source="test"))
        await db.commit()

        r = await auth_client.get("/api/catalog/?in_lib=false")
        data = r.json()
        assert data["total"] == 1
        assert data["items"][0]["title"] == "NotInLib"


class TestCatalogSort:
    async def test_sort_by_title_asc(self, client, db):
        db.add(CatalogEntry(title="Zebra", artist="A", normalized_key="zebra - a"))
        db.add(CatalogEntry(title="Alpha", artist="B", normalized_key="alpha - b"))
        await db.commit()

        r = await client.get("/api/catalog/?sort=title&order=asc")
        data = r.json()
        assert data["items"][0]["title"] == "Alpha"
        assert data["items"][1]["title"] == "Zebra"

    async def test_sort_by_title_desc(self, client, db):
        db.add(CatalogEntry(title="Zebra", artist="A", normalized_key="zebra - a"))
        db.add(CatalogEntry(title="Alpha", artist="B", normalized_key="alpha - b"))
        await db.commit()

        r = await client.get("/api/catalog/?sort=title&order=desc")
        data = r.json()
        assert data["items"][0]["title"] == "Zebra"

    async def test_sort_by_bpm(self, client, db):
        db.add(CatalogEntry(title="Slow", artist="A", normalized_key="slow - a", bpm=100))
        db.add(CatalogEntry(title="Fast", artist="B", normalized_key="fast - b", bpm=140))
        await db.commit()

        r = await client.get("/api/catalog/?sort=bpm&order=asc")
        data = r.json()
        assert data["items"][0]["bpm"] == 100


class TestCatalogSearchByArtist:
    async def test_search_artist(self, client, db):
        db.add(CatalogEntry(title="Track A", artist="CamelPhat", normalized_key="a - camelphat"))
        db.add(CatalogEntry(title="Track B", artist="Deadmau5", normalized_key="b - deadmau5"))
        await db.commit()

        r = await client.get("/api/catalog/?search=camelphat")
        data = r.json()
        assert data["total"] == 1
        assert data["items"][0]["artist"] == "CamelPhat"


class TestCatalogDetailEnriched:
    async def test_detail_includes_same_artist_tracks(self, client, db):
        a = Artist(name="CamelPhat", normalized_name="camelphat")
        cat1 = CatalogEntry(title="Cola", artist="CamelPhat", normalized_key="cola - camelphat")
        cat2 = CatalogEntry(title="Breathe", artist="CamelPhat", normalized_key="breathe - camelphat")
        db.add_all([a, cat1, cat2])
        await db.commit()
        await db.refresh(a)
        await db.refresh(cat1)
        await db.refresh(cat2)
        db.add_all([
            CatalogArtist(catalog_id=cat1.id, artist_id=a.id, role="primary", position=0),
            CatalogArtist(catalog_id=cat2.id, artist_id=a.id, role="primary", position=0),
        ])
        await db.commit()

        r = await client.get(f"/api/catalog/{cat1.id}")
        data = r.json()
        same = data["same_artist_tracks"]
        assert len(same) == 1
        assert same[0]["title"] == "Breathe"

    async def test_detail_with_radar_appearances(self, client, db):
        cat = CatalogEntry(title="Cola", artist="CamelPhat", normalized_key="cola - camelphat")
        we = WatchedEntity(external_id="123", source="deezer", title="Playlist 1")
        db.add_all([cat, we])
        await db.commit()
        await db.refresh(cat)
        await db.refresh(we)
        db.add(RadarTrack(
            watched_entity_id=we.id, external_track_id="ext1", source="deezer",
            title="Cola", artist="CamelPhat", catalog_id=cat.id,
            detected_at=datetime.now(timezone.utc),
        ))
        await db.commit()

        r = await client.get(f"/api/catalog/{cat.id}")
        data = r.json()
        assert len(data["radar_appearances"]) == 1
        assert data["radar_appearances"][0]["playlist_title"] == "Playlist 1"

    async def test_detail_with_set_appearances(self, client, db):
        cat = CatalogEntry(title="Cola", artist="CamelPhat", normalized_key="cola - camelphat")
        s = DJSet(title="My Set", source="trackid")
        db.add_all([cat, s])
        await db.commit()
        await db.refresh(cat)
        await db.refresh(s)
        db.add(SetTrack(set_id=s.id, catalog_id=cat.id, position=1))
        await db.commit()

        r = await client.get(f"/api/catalog/{cat.id}")
        data = r.json()
        assert len(data["set_appearances"]) == 1
        assert data["set_appearances"][0]["set_title"] == "My Set"

    async def test_list_includes_artist_id(self, client, db):
        """The list endpoint should resolve artist_id via catalog_artists."""
        a = Artist(name="CamelPhat", normalized_name="camelphat")
        cat = CatalogEntry(title="Cola", artist="CamelPhat", normalized_key="cola - camelphat")
        db.add_all([a, cat])
        await db.commit()
        await db.refresh(a)
        await db.refresh(cat)
        db.add(CatalogArtist(catalog_id=cat.id, artist_id=a.id, role="primary", position=0))
        await db.commit()

        r = await client.get("/api/catalog/")
        data = r.json()
        assert data["items"][0].get("artist_id") == a.id
        assert len(data["items"][0].get("artists", [])) == 1
        assert data["items"][0]["artists"][0]["name"] == "CamelPhat"


class TestCatalogAvis:
    async def test_set_avis_liked(self, auth_client, db, auth_user):
        cat = CatalogEntry(title="T", artist="A", normalized_key="t - a")
        db.add(cat)
        await db.commit()
        await db.refresh(cat)

        r = await auth_client.patch(f"/api/catalog/{cat.id}/avis", json={"avis": "liked"})
        assert r.status_code == 200
        assert r.json()["avis"] == "liked"

    async def test_set_avis_disliked(self, auth_client, db, auth_user):
        cat = CatalogEntry(title="T", artist="A", normalized_key="t - a")
        db.add(cat)
        await db.commit()
        await db.refresh(cat)

        r = await auth_client.patch(f"/api/catalog/{cat.id}/avis", json={"avis": "disliked"})
        assert r.status_code == 200
        assert r.json()["avis"] == "disliked"

    async def test_set_avis_creates_user_track_if_missing(self, auth_client, db, auth_user):
        cat = CatalogEntry(title="T", artist="A", normalized_key="t - a")
        db.add(cat)
        await db.commit()
        await db.refresh(cat)

        r = await auth_client.patch(f"/api/catalog/{cat.id}/avis", json={"avis": "liked"})
        assert r.status_code == 200

    async def test_set_avis_nonexistent_catalog_returns_404(self, auth_client):
        r = await auth_client.patch("/api/catalog/9999/avis", json={"avis": "liked"})
        assert r.status_code == 404

    async def test_set_avis_remove(self, auth_client, db, auth_user):
        cat = CatalogEntry(title="T", artist="A", normalized_key="t - a")
        db.add(cat)
        await db.commit()
        await db.refresh(cat)

        await auth_client.patch(f"/api/catalog/{cat.id}/avis", json={"avis": "liked"})
        r = await auth_client.patch(f"/api/catalog/{cat.id}/avis", json={"avis": None})
        assert r.status_code == 200
        assert r.json()["avis"] is None


class TestCatalogAvisReadPaths:
    """Read paths for avis: user_opinions is canonical, covers tracks outside the library."""

    async def test_avis_outside_library_in_detail_and_listing(self, auth_client, db, auth_user):
        cat = CatalogEntry(title="OutLib", artist="A", normalized_key="a|outlib")
        db.add(cat)
        await db.commit()
        await db.refresh(cat)

        r = await auth_client.patch(f"/api/catalog/{cat.id}/avis", json={"avis": "liked"})
        assert r.status_code == 200

        r = await auth_client.get(f"/api/catalog/{cat.id}")
        assert r.status_code == 200
        data = r.json()
        assert data["in_lib"] is False
        assert data["avis"] == "liked"

        r = await auth_client.get("/api/catalog/?avis=liked")
        data = r.json()
        assert data["total"] == 1
        assert data["items"][0]["id"] == cat.id
        assert data["items"][0]["avis"] == "liked"
        assert data["items"][0]["in_lib"] is False

    async def test_guest_detail_avis_is_none(self, client, db, auth_user):
        cat = CatalogEntry(title="GuestTrack", artist="A", normalized_key="a|guesttrack")
        db.add(cat)
        await db.commit()
        await db.refresh(cat)
        db.add(UserOpinion(
            user_id=auth_user.id, entity_type="track",
            entity_key=str(cat.id), opinion="liked",
        ))
        await db.commit()

        r = await client.get(f"/api/catalog/{cat.id}")
        assert r.status_code == 200
        assert r.json()["avis"] is None

    async def test_other_user_does_not_see_avis(self, client, db, auth_user):
        from dependencies import get_current_user, get_current_user_optional
        from main import app

        user2 = User(
            email="other@test.com", username="other",
            google_id="google-other-user", is_active=True, is_admin=False,
        )
        cat = CatalogEntry(title="Private", artist="A", normalized_key="a|private")
        db.add_all([user2, cat])
        await db.commit()
        await db.refresh(cat)
        db.add(UserOpinion(
            user_id=auth_user.id, entity_type="track",
            entity_key=str(cat.id), opinion="liked",
        ))
        await db.commit()

        app.dependency_overrides[get_current_user] = lambda: user2
        app.dependency_overrides[get_current_user_optional] = lambda: user2
        try:
            r = await client.get(f"/api/catalog/{cat.id}")
            assert r.status_code == 200
            assert r.json()["avis"] is None

            r = await client.get("/api/catalog/?avis=liked")
            assert r.json()["total"] == 0
        finally:
            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_current_user_optional, None)

    async def test_avis_in_library_still_served(self, auth_client, db, auth_user):
        cat = CatalogEntry(title="InLibAvis", artist="A", normalized_key="a|inlibavis")
        db.add(cat)
        await db.commit()
        await db.refresh(cat)
        db.add(UserTrack(user_id=auth_user.id, catalog_id=cat.id, source="test"))
        await db.commit()

        r = await auth_client.patch(f"/api/catalog/{cat.id}/avis", json={"avis": "disliked"})
        assert r.status_code == 200

        r = await auth_client.get(f"/api/catalog/{cat.id}")
        data = r.json()
        assert data["in_lib"] is True
        assert data["avis"] == "disliked"

        r = await auth_client.get("/api/catalog/?avis=disliked")
        data = r.json()
        assert data["total"] == 1
        assert data["items"][0]["avis"] == "disliked"
        assert data["items"][0]["in_lib"] is True

    async def test_legacy_ut_avis_without_opinion_row(self, auth_client, db, auth_user):
        """Legacy denormalized data: user_tracks.avis set without a user_opinions row."""
        cat = CatalogEntry(title="Legacy", artist="A", normalized_key="a|legacy")
        db.add(cat)
        await db.commit()
        await db.refresh(cat)
        db.add(UserTrack(user_id=auth_user.id, catalog_id=cat.id, source="test", avis="liked"))
        await db.commit()

        r = await auth_client.get(f"/api/catalog/{cat.id}")
        assert r.json()["avis"] == "liked"

        r = await auth_client.get("/api/catalog/?avis=liked")
        data = r.json()
        assert data["total"] == 1
        assert data["items"][0]["avis"] == "liked"


class TestCatalogSimilar:
    async def test_404_for_missing_id(self, client):
        r = await client.get("/api/catalog/999999/similar")
        assert r.status_code == 404

    async def test_returns_list(self, client, db):
        ref = CatalogEntry(title="Ref", artist="A", normalized_key="a|ref-sim", bpm=128.0, key="8A")
        close = CatalogEntry(title="Close", artist="A", normalized_key="a|close-sim", bpm=129.0, key="8A")
        db.add_all([ref, close])
        await db.commit()
        await db.refresh(ref)

        r = await client.get(f"/api/catalog/{ref.id}/similar?score_floor=0")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        assert data[0]["title"] == "Close"

    async def test_similarity_block_in_response(self, client, db):
        ref = CatalogEntry(title="Ref", artist="A", normalized_key="a|ref-blk", bpm=128.0, key="8A")
        other = CatalogEntry(title="Other", artist="A", normalized_key="a|other-blk", bpm=128.0, key="8A")
        db.add_all([ref, other])
        await db.commit()
        await db.refresh(ref)

        r = await client.get(f"/api/catalog/{ref.id}/similar?score_floor=0")
        data = r.json()
        assert len(data) == 1
        sim = data[0]["similarity"]
        assert "score" in sim
        assert "components" in sim
        assert "available_features" in sim
        assert "sets" in sim["components"]
        assert "playlists" in sim["components"]
        assert "style" in sim["components"]
        assert "context" in sim["components"]

    async def test_limit_param(self, client, db):
        ref = CatalogEntry(title="Ref", artist="A", normalized_key="a|ref-lp", bpm=128.0, key="8A")
        db.add(ref)
        for i in range(5):
            db.add(CatalogEntry(title=f"T{i}", artist="A", normalized_key=f"a|t{i}-lp", bpm=128.0 + i, key="8A"))
        await db.commit()
        await db.refresh(ref)

        r = await client.get(f"/api/catalog/{ref.id}/similar?limit=2&score_floor=0")
        assert r.status_code == 200
        assert len(r.json()) == 2

    async def test_cooc_playlist_signal(self, client, db):
        """Tracks partageant une playlist radar reçoivent playlists dans available_features."""
        ref = CatalogEntry(title="CoocRef", artist="A", normalized_key="a|cooc-ref", bpm=128.0, key="8A")
        other = CatalogEntry(title="CoocOther", artist="B", normalized_key="b|cooc-other", bpm=128.0, key="8A")
        db.add_all([ref, other])
        await db.commit()
        await db.refresh(ref)
        await db.refresh(other)

        entity = WatchedEntity(external_id="test-playlist-cooc", source="deezer", type="playlist", title="Test")
        db.add(entity)
        await db.commit()
        await db.refresh(entity)

        db.add(RadarTrack(
            watched_entity_id=entity.id, external_track_id="ext-ref",
            source="deezer", title="CoocRef", catalog_id=ref.id,
        ))
        db.add(RadarTrack(
            watched_entity_id=entity.id, external_track_id="ext-other",
            source="deezer", title="CoocOther", catalog_id=other.id,
        ))
        await db.commit()

        r = await client.get(f"/api/catalog/{ref.id}/similar?score_floor=0")
        assert r.status_code == 200
        data = r.json()
        assert len(data) >= 1
        result = next((t for t in data if t["id"] == other.id), None)
        assert result is not None
        sim = result["similarity"]
        assert "playlists" in sim["available_features"]
        assert sim["components"]["playlists"] > 0

    async def test_cooc_set_signal(self, client, db):
        """Tracks dans le même set reçoivent sets dans available_features."""
        ref = CatalogEntry(title="SetRef", artist="A", normalized_key="a|set-ref", bpm=128.0, key="8A")
        other = CatalogEntry(title="SetOther", artist="B", normalized_key="b|set-other", bpm=128.0, key="8A")
        db.add_all([ref, other])
        await db.commit()
        await db.refresh(ref)
        await db.refresh(other)

        dj_set = DJSet(source="trackid", title="Test Set", external_id="set-cooc-test")
        db.add(dj_set)
        await db.commit()
        await db.refresh(dj_set)

        db.add(SetTrack(set_id=dj_set.id, catalog_id=ref.id, position=1))
        db.add(SetTrack(set_id=dj_set.id, catalog_id=other.id, position=2))
        await db.commit()

        r = await client.get(f"/api/catalog/{ref.id}/similar?score_floor=0")
        assert r.status_code == 200
        data = r.json()
        result = next((t for t in data if t["id"] == other.id), None)
        assert result is not None
        sim = result["similarity"]
        assert "sets" in sim["available_features"]
        assert sim["components"]["sets"] > 0

    async def test_cooc_playlist_boosts_score(self, client, db):
        """Tracks co-occurrentes en playlist remontent avec un score > 0."""
        ref = CatalogEntry(title="OnlyCoocRef", artist="A", normalized_key="a|only-cooc-ref", bpm=128.0)
        in_playlist = CatalogEntry(title="InPlaylist", artist="B", normalized_key="b|in-playlist", bpm=200.0)
        not_in = CatalogEntry(title="NotIn", artist="C", normalized_key="c|not-in", bpm=128.0)
        db.add_all([ref, in_playlist, not_in])
        await db.commit()
        await db.refresh(ref)
        await db.refresh(in_playlist)

        entity = WatchedEntity(external_id="only-cooc-entity", source="deezer", type="playlist", title="X")
        db.add(entity)
        await db.commit()
        await db.refresh(entity)

        db.add(RadarTrack(
            watched_entity_id=entity.id, external_track_id="ref-only",
            source="deezer", title="OnlyCoocRef", catalog_id=ref.id,
        ))
        db.add(RadarTrack(
            watched_entity_id=entity.id, external_track_id="in-only",
            source="deezer", title="InPlaylist", catalog_id=in_playlist.id,
        ))
        await db.commit()

        r = await client.get(f"/api/catalog/{ref.id}/similar?score_floor=0.01")
        assert r.status_code == 200
        ids = [t["id"] for t in r.json()]
        assert in_playlist.id in ids


class TestExplorerFilters:
    """Query-builder filters of GET /api/catalog/ (Explorer refonte, D6 p.1)."""

    async def test_bpm_range(self, client, db):
        db.add(CatalogEntry(title="Slow", artist="A", normalized_key="a|slow-bpm", bpm=100.0))
        db.add(CatalogEntry(title="Mid", artist="A", normalized_key="a|mid-bpm", bpm=128.0))
        db.add(CatalogEntry(title="Fast", artist="A", normalized_key="a|fast-bpm", bpm=150.0))
        db.add(CatalogEntry(title="NoBpm", artist="A", normalized_key="a|nobpm"))
        await db.commit()

        r = await client.get("/api/catalog/?bpm_min=120&bpm_max=140")
        data = r.json()
        assert data["total"] == 1
        assert data["items"][0]["title"] == "Mid"

    async def test_bpm_range_uses_rb_override(self, auth_client, db, auth_user):
        """The Rekordbox BPM is authoritative: the filter goes through the coalesce."""
        cat = CatalogEntry(title="Overridden", artist="A", normalized_key="a|rb-bpm", bpm=100.0)
        other = CatalogEntry(title="Plain", artist="A", normalized_key="a|plain-bpm", bpm=100.0)
        db.add_all([cat, other])
        await db.commit()
        await db.refresh(cat)
        db.add(UserTrack(user_id=auth_user.id, catalog_id=cat.id, source="test", rb_bpm=128.0))
        await db.commit()

        r = await auth_client.get("/api/catalog/?bpm_min=120&bpm_max=140")
        data = r.json()
        assert data["total"] == 1
        assert data["items"][0]["title"] == "Overridden"

    async def test_key_multi(self, client, db):
        for k in ["5A", "6A", "9B"]:
            db.add(CatalogEntry(title=f"K{k}", artist="A", normalized_key=f"a|k{k}", key=k))
        await db.commit()

        r = await client.get("/api/catalog/", params=[("key", "5A"), ("key", "6A")])
        data = r.json()
        assert data["total"] == 2
        assert {i["title"] for i in data["items"]} == {"K5A", "K6A"}

    async def test_key_invalid_rejected(self, client):
        for bad in ["13A", "0A", "5C", "A5"]:
            r = await client.get("/api/catalog/", params=[("key", bad)])
            assert r.status_code == 422, bad

    async def test_genre_single_compat(self, client, db):
        db.add(CatalogEntry(title="T1", artist="A", normalized_key="a|t1-g1", genres=["techno"]))
        db.add(CatalogEntry(title="T2", artist="A", normalized_key="a|t2-g1", genres=["trance"]))
        await db.commit()

        r = await client.get("/api/catalog/?genre=techno")
        data = r.json()
        assert data["total"] == 1
        assert data["items"][0]["title"] == "T1"

    async def test_genre_multi_or(self, client, db):
        db.add(CatalogEntry(title="T1", artist="A", normalized_key="a|t1-g2", genres=["techno"]))
        db.add(CatalogEntry(title="T2", artist="A", normalized_key="a|t2-g2", genres=["house music", "deep house"]))
        db.add(CatalogEntry(title="T3", artist="A", normalized_key="a|t3-g2", genres=["trance"]))
        await db.commit()

        r = await client.get(
            "/api/catalog/", params=[("genre", "techno"), ("genre", "house music")]
        )
        data = r.json()
        assert data["total"] == 2
        assert {i["title"] for i in data["items"]} == {"T1", "T2"}

    async def test_artist_id_multi(self, client, db):
        a1 = Artist(name="A1", normalized_name="a1")
        a2 = Artist(name="A2", normalized_name="a2")
        a3 = Artist(name="A3", normalized_name="a3")
        c1 = CatalogEntry(title="C1", artist="A1", normalized_key="a1|c1")
        c2 = CatalogEntry(title="C2", artist="A2", normalized_key="a2|c2")
        c3 = CatalogEntry(title="C3", artist="A3", normalized_key="a3|c3")
        db.add_all([a1, a2, a3, c1, c2, c3])
        await db.commit()
        for a, c in [(a1, c1), (a2, c2), (a3, c3)]:
            await db.refresh(a)
            await db.refresh(c)
            db.add(CatalogArtist(catalog_id=c.id, artist_id=a.id, role="primary", position=0))
        await db.commit()

        r = await client.get(
            "/api/catalog/", params=[("artist_id", a1.id), ("artist_id", a2.id)]
        )
        data = r.json()
        assert data["total"] == 2
        assert {i["title"] for i in data["items"]} == {"C1", "C2"}

    async def test_duration_range(self, client, db):
        db.add(CatalogEntry(title="Edit", artist="A", normalized_key="a|edit", duration_ms=150000))
        db.add(CatalogEntry(title="Club", artist="A", normalized_key="a|club", duration_ms=250000))
        db.add(CatalogEntry(title="Long", artist="A", normalized_key="a|long", duration_ms=400000))
        await db.commit()

        r = await client.get("/api/catalog/?duration_min=200000&duration_max=300000")
        data = r.json()
        assert data["total"] == 1
        assert data["items"][0]["title"] == "Club"

    async def test_has_preview_true(self, client, db):
        db.add(CatalogEntry(title="Audible", artist="A", normalized_key="a|audible", has_preview=True))
        db.add(CatalogEntry(title="Silent", artist="A", normalized_key="a|silent", has_preview=False))
        await db.commit()

        r = await client.get("/api/catalog/?has_preview=true")
        data = r.json()
        assert data["total"] == 1
        assert data["items"][0]["title"] == "Audible"

        # Param absent -> no filter
        r = await client.get("/api/catalog/")
        assert r.json()["total"] == 2

    async def test_avis_none(self, auth_client, db, auth_user):
        """avis=none returns only tracks with NO opinion (canonical or legacy)."""
        liked = CatalogEntry(title="Liked", artist="A", normalized_key="a|avis-liked")
        legacy = CatalogEntry(title="Legacy", artist="A", normalized_key="a|avis-legacy")
        neutral = CatalogEntry(title="Neutral", artist="A", normalized_key="a|avis-neutral")
        db.add_all([liked, legacy, neutral])
        await db.commit()
        await db.refresh(liked)
        await db.refresh(legacy)
        db.add(UserOpinion(
            user_id=auth_user.id, entity_type="track",
            entity_key=str(liked.id), opinion="liked",
        ))
        db.add(UserTrack(
            user_id=auth_user.id, catalog_id=legacy.id, source="test", avis="disliked",
        ))
        await db.commit()

        r = await auth_client.get("/api/catalog/?avis=none")
        data = r.json()
        assert data["total"] == 1
        assert data["items"][0]["title"] == "Neutral"

    async def test_year_range(self, client, db):
        db.add(CatalogEntry(title="Old", artist="A", normalized_key="a|old", release_date=date(2018, 5, 1)))
        db.add(CatalogEntry(title="Mid", artist="A", normalized_key="a|mid-y", release_date=date(2020, 6, 15)))
        db.add(CatalogEntry(title="New", artist="A", normalized_key="a|new", release_date=date(2023, 1, 1)))
        db.add(CatalogEntry(title="NoDate", artist="A", normalized_key="a|nodate"))
        await db.commit()

        r = await client.get("/api/catalog/?year_min=2019&year_max=2022")
        data = r.json()
        assert data["total"] == 1
        assert data["items"][0]["title"] == "Mid"

        # Bounds are inclusive over the whole year
        r = await client.get("/api/catalog/?year_min=2020&year_max=2020")
        assert r.json()["total"] == 1

    async def test_label_filter(self, client, db):
        db.add(CatalogEntry(title="T1", artist="A", normalized_key="a|t1-l", label="Drumcode"))
        db.add(CatalogEntry(title="T2", artist="A", normalized_key="a|t2-l", label="Afterlife"))
        await db.commit()

        r = await client.get("/api/catalog/?label=drum")
        data = r.json()
        assert data["total"] == 1
        assert data["items"][0]["title"] == "T1"

    async def test_search_matches_label(self, client, db):
        db.add(CatalogEntry(title="T1", artist="A", normalized_key="a|t1-sl", label="Kompakt"))
        db.add(CatalogEntry(title="T2", artist="A", normalized_key="a|t2-sl", label="Drumcode"))
        await db.commit()

        r = await client.get("/api/catalog/?search=kompakt")
        data = r.json()
        assert data["total"] == 1
        assert data["items"][0]["title"] == "T1"


class TestExplorerSort:
    async def test_default_sort_created_at_desc(self, client, db):
        db.add(CatalogEntry(title="Older", artist="A", normalized_key="a|older",
                            created_at=datetime(2024, 1, 1, tzinfo=timezone.utc)))
        db.add(CatalogEntry(title="Newest", artist="A", normalized_key="a|newest",
                            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc)))
        db.add(CatalogEntry(title="Oldest", artist="A", normalized_key="a|oldest",
                            created_at=datetime(2023, 1, 1, tzinfo=timezone.utc)))
        await db.commit()

        r = await client.get("/api/catalog/")
        titles = [i["title"] for i in r.json()["items"]]
        assert titles == ["Newest", "Older", "Oldest"]

    async def test_sort_key_harmonic(self, client, db):
        """length(key), key => 1B, 2A, 10A (not the lexicographic 10A, 1B, 2A); NULL last."""
        for t, k in [("T10A", "10A"), ("T2A", "2A"), ("T1B", "1B"), ("TNull", None)]:
            db.add(CatalogEntry(title=t, artist="A", normalized_key=f"a|{t.lower()}", key=k))
        await db.commit()

        r = await client.get("/api/catalog/?sort=key&order=asc")
        titles = [i["title"] for i in r.json()["items"]]
        assert titles == ["T1B", "T2A", "T10A", "TNull"]

    async def test_sort_release_date_nulls_last(self, client, db):
        db.add(CatalogEntry(title="Dated", artist="A", normalized_key="a|dated",
                            release_date=date(2020, 1, 1)))
        db.add(CatalogEntry(title="Undated", artist="A", normalized_key="a|undated"))
        await db.commit()

        r = await client.get("/api/catalog/?sort=release_date&order=desc")
        titles = [i["title"] for i in r.json()["items"]]
        assert titles == ["Dated", "Undated"]

    async def test_sort_by_artist_asc(self, client, db):
        db.add(CatalogEntry(title="T1", artist="Zeta", normalized_key="a|sortartz"))
        db.add(CatalogEntry(title="T2", artist="Alpha", normalized_key="a|sortarta"))
        await db.commit()

        r = await client.get("/api/catalog/?sort=artist&order=asc")
        assert r.status_code == 200
        artists = [i["artist"] for i in r.json()["items"]]
        assert artists == ["Alpha", "Zeta"]

    async def test_sort_duration_ms_nulls_last(self, client, db):
        """duration_ms ascending: value-less tracks land LAST, not first (fix #1:
        the bare column + .nulls_last(), no coalesce(..., 0) sinking NULLs to 0)."""
        db.add(CatalogEntry(title="Short", artist="A", normalized_key="a|durshort", duration_ms=150000))
        db.add(CatalogEntry(title="Long", artist="A", normalized_key="a|durlong", duration_ms=400000))
        db.add(CatalogEntry(title="NoDur", artist="A", normalized_key="a|durnone"))
        await db.commit()

        r = await client.get("/api/catalog/?sort=duration_ms&order=asc")
        assert r.status_code == 200
        titles = [i["title"] for i in r.json()["items"]]
        assert titles == ["Short", "Long", "NoDur"]

    async def test_tiebreak_stable_on_id(self, client, db):
        """Equal sort keys fall back to the id tiebreak (stable pagination, A1-02)."""
        same = datetime(2025, 1, 1, tzinfo=timezone.utc)
        for i in range(5):
            db.add(CatalogEntry(title=f"Tie{i}", artist="A", normalized_key=f"a|tie{i}",
                                created_at=same))
        await db.commit()

        r = await client.get("/api/catalog/")
        ids = [i["id"] for i in r.json()["items"]]
        assert ids == sorted(ids, reverse=True)

        # Pagination never yields duplicates across pages
        r1 = await client.get("/api/catalog/?skip=0&limit=3")
        r2 = await client.get("/api/catalog/?skip=3&limit=3")
        page_ids = [i["id"] for i in r1.json()["items"]] + [i["id"] for i in r2.json()["items"]]
        assert len(page_ids) == len(set(page_ids)) == 5

    async def test_removed_sorts_rejected(self, client):
        gone_sorts = [
            "rating", "nb_radar_playlists", "trend_score_10",
            "detected_at", "style", "in_lib", "avis",
        ]
        for gone in gone_sorts:
            r = await client.get(f"/api/catalog/?sort={gone}")
            assert r.status_code == 422, gone


class TestExplorerRatingRemoved:
    async def test_rating_absent_from_list_and_detail(self, auth_client, db, auth_user):
        cat = CatalogEntry(title="NoRating", artist="A", normalized_key="a|norating")
        db.add(cat)
        await db.commit()
        await db.refresh(cat)
        db.add(UserTrack(user_id=auth_user.id, catalog_id=cat.id, source="test", rating=5))
        await db.commit()

        r = await auth_client.get("/api/catalog/")
        assert "rating" not in r.json()["items"][0]

        r = await auth_client.get(f"/api/catalog/{cat.id}")
        assert "rating" not in r.json()


class TestExplorerVisibility:
    """catalog_visible(user_id) stays effective through the new filter branches."""

    async def _seed(self, db):
        owner = User(
            email="owner-x@test.com", username="ownerx",
            google_id="google-owner-x", is_active=True, is_admin=False,
        )
        db.add(owner)
        await db.commit()
        await db.refresh(owner)
        db.add(CatalogEntry(
            title="Foreign Private", artist="A", normalized_key="a|foreignpriv",
            scope="private", owner_id=owner.id,
            bpm=128.0, key="5A", genres=["techno"], label="Drumcode",
            duration_ms=250000, release_date=date(2024, 3, 1), has_preview=True,
        ))
        db.add(CatalogEntry(
            title="Shared Match", artist="A", normalized_key="a|sharedmatch",
            bpm=128.0, key="5A", genres=["techno"], label="Drumcode",
            duration_ms=250000, release_date=date(2024, 3, 1), has_preview=True,
        ))
        await db.commit()

    FILTERS = (
        "?bpm_min=120&bpm_max=140&key=5A&genre=techno&label=drum"
        "&duration_min=200000&duration_max=300000&has_preview=true"
        "&year_min=2024&year_max=2024"
    )

    async def test_foreign_private_hidden_with_filters(self, auth_client, db):
        await self._seed(db)
        r = await auth_client.get(f"/api/catalog/{self.FILTERS}&avis=none")
        data = r.json()
        assert data["total"] == 1
        assert data["items"][0]["title"] == "Shared Match"

    async def test_foreign_private_hidden_from_guest_with_filters(self, client, db):
        await self._seed(db)
        r = await client.get(f"/api/catalog/{self.FILTERS}")
        data = r.json()
        assert data["total"] == 1
        assert data["items"][0]["title"] == "Shared Match"
