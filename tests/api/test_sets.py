"""Tests for /api/sets endpoints."""
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from main import app
from models import (
    Artist,
    CatalogEntry,
    DJSet,
    SetArtist,
    SetTrack,
    User,
    UserOpinion,
    UserSetFollow,
    UserTrack,
)
from sqlalchemy import select


async def _attach_identified_track(
    db, set_obj, *, position=1, title=None, artist=None, genres=None, is_id=False
):
    """Attach an identified catalog track to a set so it clears the list's
    ``having(identified > 0)`` gate. normalized_key is derived from the set id +
    position to stay globally unique across a test."""
    title = title or f"trk-{set_obj.id}-{position}"
    artist = artist or f"art-{set_obj.id}-{position}"
    cat = CatalogEntry(
        title=title,
        artist=artist,
        normalized_key=f"{artist}|{title}".lower(),
        genres=genres or [],
        scope="shared",
    )
    db.add(cat)
    await db.flush()
    db.add(
        SetTrack(
            set_id=set_obj.id, position=position, catalog_id=cat.id,
            raw_title=title, is_id=is_id,
        )
    )
    return cat


class TestListSets:
    async def test_empty_returns_zero(self, client):
        r = await client.get("/api/sets/")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 0
        assert data["items"] == []

    async def test_returns_sets(self, client, db):
        s = DJSet(source="trackid", title="Boiler Room London")
        db.add(s)
        await db.flush()
        await _attach_identified_track(db, s)
        await db.commit()
        r = await client.get("/api/sets/")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 1
        assert data["items"][0]["title"] == "Boiler Room London"

    async def test_filter_by_title(self, client, db):
        s1 = DJSet(source="trackid", title="Boiler Room London")
        s2 = DJSet(source="trackid", title="Cercle Paris")
        db.add_all([s1, s2])
        await db.flush()
        await _attach_identified_track(db, s1)
        await _attach_identified_track(db, s2)
        await db.commit()
        r = await client.get("/api/sets/?q=boiler")
        data = r.json()
        assert data["total"] == 1
        assert data["items"][0]["title"] == "Boiler Room London"

    async def test_includes_track_counts(self, client, db):
        s = DJSet(source="trackid", title="Test Set")
        db.add(s)
        await db.flush()
        # Track 1 is identified (catalog-linked) so the set clears the gate; the
        # count stays 2 because we don't add a 3rd track.
        cat = CatalogEntry(
            title="Track 1", artist="A1", normalized_key="a1|track 1", scope="shared"
        )
        db.add(cat)
        await db.flush()
        db.add(SetTrack(set_id=s.id, position=1, catalog_id=cat.id, raw_title="Track 1"))
        db.add(SetTrack(set_id=s.id, position=2, raw_title="ID", is_id=True))
        await db.commit()
        r = await client.get("/api/sets/")
        data = r.json()
        assert data["items"][0]["total_tracks"] == 2

    async def test_includes_artists(self, client, db):
        a = Artist(name="ANNA", normalized_name="anna")
        db.add(a)
        s = DJSet(source="trackid", title="ANNA at Boiler Room")
        db.add(s)
        await db.flush()
        db.add(SetArtist(set_id=s.id, artist_id=a.id, role="main", position=1))
        await _attach_identified_track(db, s)
        await db.commit()
        r = await client.get("/api/sets/")
        data = r.json()
        artist = data["items"][0]["artists"][0]
        assert artist["name"] == "ANNA"
        assert artist["id"] == a.id

    async def test_pagination(self, client, db):
        for i in range(5):
            s = DJSet(source="trackid", title=f"Set {i}")
            db.add(s)
            await db.flush()
            await _attach_identified_track(db, s)
        await db.commit()
        r = await client.get("/api/sets/?limit=2")
        data = r.json()
        assert len(data["items"]) == 2
        assert data["total"] == 5

    async def test_pagination_offset(self, client, db):
        for i in range(5):
            s = DJSet(source="trackid", title=f"Set {i}")
            db.add(s)
            await db.flush()
            await _attach_identified_track(db, s)
        await db.commit()
        r = await client.get("/api/sets/?offset=3&limit=10")
        data = r.json()
        assert len(data["items"]) == 2
        assert data["total"] == 5


class TestListSetsEnriched:
    """Lot 0 enriched list: 0-identified exclusion, sort keys/direction,
    ids/exclude_ids filters, batch top_genres (catalog_visible), artists shape."""

    async def test_zero_identified_set_absent_from_list_and_total(self, client, db):
        visible = DJSet(source="trackid", title="Has Identified")
        db.add(visible)
        await db.flush()
        await _attach_identified_track(db, visible)
        # A set whose only tracks are ID placeholders / uncatalogued -> excluded
        empty = DJSet(source="trackid", title="All Unknown")
        db.add(empty)
        await db.flush()
        db.add(SetTrack(set_id=empty.id, position=1, raw_title="ID", is_id=True))
        db.add(SetTrack(set_id=empty.id, position=2, raw_title="Mystery"))
        await db.commit()

        r = await client.get("/api/sets/")
        data = r.json()
        assert [it["title"] for it in data["items"]] == ["Has Identified"]
        assert data["total"] == 1

    async def test_sort_by_date(self, client, db):
        old = DJSet(source="trackid", title="Old", played_date=date(2020, 1, 1))
        new = DJSet(source="trackid", title="New", played_date=date(2024, 1, 1))
        db.add_all([old, new])
        await db.flush()
        await _attach_identified_track(db, old)
        await _attach_identified_track(db, new)
        await db.commit()

        # default -date -> most recent first
        r = await client.get("/api/sets/")
        assert [it["title"] for it in r.json()["items"]] == ["New", "Old"]
        # date asc -> oldest first
        r = await client.get("/api/sets/?sort=date")
        assert [it["title"] for it in r.json()["items"]] == ["Old", "New"]

    async def test_sort_by_title(self, client, db):
        alpha = DJSet(source="trackid", title="Alpha")
        zeta = DJSet(source="trackid", title="Zeta")
        db.add_all([alpha, zeta])
        await db.flush()
        await _attach_identified_track(db, alpha)
        await _attach_identified_track(db, zeta)
        await db.commit()

        r = await client.get("/api/sets/?sort=title")
        assert [it["title"] for it in r.json()["items"]] == ["Alpha", "Zeta"]
        r = await client.get("/api/sets/?sort=-title")
        assert [it["title"] for it in r.json()["items"]] == ["Zeta", "Alpha"]

    async def test_sort_by_duration(self, client, db):
        short = DJSet(source="trackid", title="Short", duration_ms=100)
        long_ = DJSet(source="trackid", title="Long", duration_ms=200)
        db.add_all([short, long_])
        await db.flush()
        await _attach_identified_track(db, short)
        await _attach_identified_track(db, long_)
        await db.commit()

        r = await client.get("/api/sets/?sort=duration")
        assert [it["title"] for it in r.json()["items"]] == ["Short", "Long"]
        r = await client.get("/api/sets/?sort=-duration")
        assert [it["title"] for it in r.json()["items"]] == ["Long", "Short"]

    async def test_sort_by_tracks_ratio(self, client, db):
        full = DJSet(source="trackid", title="Full")  # 1/1 identified
        half = DJSet(source="trackid", title="Half")  # 1/2 identified
        db.add_all([full, half])
        await db.flush()
        await _attach_identified_track(db, full, position=1)
        await _attach_identified_track(db, half, position=1)
        db.add(SetTrack(set_id=half.id, position=2, raw_title="ID", is_id=True))
        await db.commit()

        # -tracks -> highest identified ratio first
        r = await client.get("/api/sets/?sort=-tracks")
        assert [it["title"] for it in r.json()["items"]] == ["Full", "Half"]
        r = await client.get("/api/sets/?sort=tracks")
        assert [it["title"] for it in r.json()["items"]] == ["Half", "Full"]

    async def test_unknown_sort_falls_back_to_date(self, client, db):
        old = DJSet(source="trackid", title="Old", played_date=date(2020, 1, 1))
        new = DJSet(source="trackid", title="New", played_date=date(2024, 1, 1))
        db.add_all([old, new])
        await db.flush()
        await _attach_identified_track(db, old)
        await _attach_identified_track(db, new)
        await db.commit()

        r = await client.get("/api/sets/?sort=bogus")
        assert [it["title"] for it in r.json()["items"]] == ["New", "Old"]

    async def test_ids_restricts_and_exclude_ids_removes(self, client, db):
        s1 = DJSet(source="trackid", title="One")
        s2 = DJSet(source="trackid", title="Two")
        s3 = DJSet(source="trackid", title="Three")
        db.add_all([s1, s2, s3])
        await db.flush()
        for s in (s1, s2, s3):
            await _attach_identified_track(db, s)
        await db.commit()

        r = await client.get(f"/api/sets/?ids={s1.id},{s3.id}")
        data = r.json()
        assert {it["id"] for it in data["items"]} == {s1.id, s3.id}
        assert data["total"] == 2

        r = await client.get(f"/api/sets/?exclude_ids={s2.id}")
        data = r.json()
        assert s2.id not in {it["id"] for it in data["items"]}
        assert data["total"] == 2

        # junk tokens are ignored; an all-junk CSV drops the filter entirely
        r = await client.get("/api/sets/?ids=abc,")
        assert r.json()["total"] == 3

    async def test_items_carry_top_genres(self, client, db):
        s = DJSet(source="trackid", title="Genre Set")
        db.add(s)
        await db.flush()
        await _attach_identified_track(db, s, position=1, genres=["techno"])
        await _attach_identified_track(db, s, position=2, genres=["techno"])
        await _attach_identified_track(db, s, position=3, genres=["house"])
        await db.commit()

        r = await client.get("/api/sets/")
        item = r.json()["items"][0]
        assert [g["name"] for g in item["top_genres"]] == ["techno", "house"]
        by_name = {g["name"]: g for g in item["top_genres"]}
        assert by_name["techno"]["pct"] == 67  # round(100 * 2 / 3)

    async def test_top_genres_respect_catalog_visible(self, auth_client, db, auth_user):
        other = User(email="o2@test.com", username="o2", google_id="g-o2", is_active=True)
        db.add(other)
        await db.flush()
        s = DJSet(source="trackid", title="Visibility Set")
        db.add(s)
        await db.flush()
        # shared techno track (visible) + foreign private house track (hidden)
        cat_shared = CatalogEntry(
            title="Shared", artist="Alpha", normalized_key="alpha|shared",
            genres=["techno"], scope="shared",
        )
        cat_private = CatalogEntry(
            title="Secret", artist="Beta", normalized_key="beta|secret",
            genres=["house"], scope="private", owner_id=other.id,
        )
        db.add_all([cat_shared, cat_private])
        await db.flush()
        db.add(SetTrack(set_id=s.id, position=1, catalog_id=cat_shared.id, raw_title="Shared"))
        db.add(SetTrack(set_id=s.id, position=2, catalog_id=cat_private.id, raw_title="Secret"))
        await db.commit()

        r = await auth_client.get("/api/sets/")
        item = r.json()["items"][0]
        # foreign private "house" is excluded from the aggregate
        assert {g["name"] for g in item["top_genres"]} == {"techno"}

    async def test_artists_shape_is_id_name(self, client, db):
        a = Artist(name="ANNA", normalized_name="anna")
        db.add(a)
        s = DJSet(source="trackid", title="ANNA set")
        db.add(s)
        await db.flush()
        db.add(SetArtist(set_id=s.id, artist_id=a.id, role="main", position=1))
        await _attach_identified_track(db, s)
        await db.commit()

        r = await client.get("/api/sets/")
        artists = r.json()["items"][0]["artists"]
        assert artists == [
            {"id": a.id, "name": "ANNA", "role": None, "has_artwork": False}
        ]


class TestSetDetail:
    async def test_returns_set(self, client, db):
        s = DJSet(source="trackid", title="Test Set")
        db.add(s)
        await db.commit()
        await db.refresh(s)
        r = await client.get(f"/api/sets/{s.id}")
        assert r.status_code == 200
        assert r.json()["title"] == "Test Set"

    async def test_404_when_not_found(self, client):
        r = await client.get("/api/sets/9999")
        assert r.status_code == 404

    async def test_includes_tracklist(self, client, db):
        s = DJSet(source="trackid", title="Test Set")
        db.add(s)
        await db.flush()
        db.add(SetTrack(set_id=s.id, position=1, raw_title="Cola", raw_artist="CamelPhat"))
        await db.commit()
        await db.refresh(s)
        r = await client.get(f"/api/sets/{s.id}")
        data = r.json()
        assert len(data["tracklist"]) == 1
        assert data["tracklist"][0]["raw_title"] == "Cola"


class TestSetDetailInLib:
    """in_lib in the tracklist must be scoped to the requesting user (M1)."""

    async def _make_set_with_track(self, db):
        cat = CatalogEntry(title="Cola", artist="CamelPhat", normalized_key="cola - camelphat")
        db.add(cat)
        await db.flush()
        s = DJSet(source="trackid", title="In-Lib Set")
        db.add(s)
        await db.flush()
        db.add(SetTrack(set_id=s.id, position=1, catalog_id=cat.id, raw_title="Cola"))
        return s, cat

    async def test_guest_in_lib_is_false_even_if_others_own_it(self, client, db, auth_user):
        """Guests own nothing: in_lib must be False even when a user has the track."""
        s, cat = await self._make_set_with_track(db)
        db.add(UserTrack(user_id=auth_user.id, catalog_id=cat.id, source="test"))
        await db.commit()

        r = await client.get(f"/api/sets/{s.id}")
        assert r.status_code == 200
        assert r.json()["tracklist"][0]["in_lib"] is False

    async def test_in_lib_true_for_owner(self, auth_client, db, auth_user):
        s, cat = await self._make_set_with_track(db)
        db.add(UserTrack(user_id=auth_user.id, catalog_id=cat.id, source="test"))
        await db.commit()

        r = await auth_client.get(f"/api/sets/{s.id}")
        assert r.status_code == 200
        assert r.json()["tracklist"][0]["in_lib"] is True

    async def test_in_lib_false_when_only_another_user_owns_it(self, auth_client, db, auth_user):
        """A track owned by a different user must not leak into auth_user's in_lib."""
        s, cat = await self._make_set_with_track(db)
        other = User(
            email="other@test.com", username="other", google_id="g-other", is_active=True
        )
        db.add(other)
        await db.flush()
        db.add(UserTrack(user_id=other.id, catalog_id=cat.id, source="test"))
        await db.commit()

        r = await auth_client.get(f"/api/sets/{s.id}")
        assert r.status_code == 200
        assert r.json()["tracklist"][0]["in_lib"] is False


class TestSetDetailEnriched:
    """Lot 0 enriched detail: bpm/key/duration_ms on the tracklist + top_genres
    deduced from the identified, viewer-visible tracks."""

    async def _add_identified(
        self, db, s, position, *, title, artist,
        bpm=None, key=None, duration_ms=None, genres=None,
        scope="shared", owner_id=None, is_id=False,
    ):
        cat = CatalogEntry(
            title=title,
            artist=artist,
            normalized_key=f"{artist}|{title}".lower(),
            bpm=bpm,
            key=key,
            duration_ms=duration_ms,
            genres=genres or [],
            scope=scope,
            owner_id=owner_id,
        )
        db.add(cat)
        await db.flush()
        db.add(
            SetTrack(
                set_id=s.id, position=position, catalog_id=cat.id,
                raw_title=title, is_id=is_id,
            )
        )
        return cat

    async def test_tracklist_carries_bpm_key_duration(self, client, db):
        s = DJSet(source="trackid", title="Enriched Set")
        db.add(s)
        await db.flush()
        await self._add_identified(
            db, s, 1, title="Cola", artist="CamelPhat",
            bpm=124.0, key="8A", duration_ms=210000,
        )
        await db.commit()
        await db.refresh(s)

        r = await client.get(f"/api/sets/{s.id}")
        assert r.status_code == 200
        tr = r.json()["tracklist"][0]
        assert tr["bpm"] == 124.0
        assert tr["key"] == "8A"
        assert tr["duration_ms"] == 210000

    async def test_tracklist_fields_none_without_catalog(self, client, db):
        s = DJSet(source="trackid", title="Raw Set")
        db.add(s)
        await db.flush()
        db.add(SetTrack(set_id=s.id, position=1, raw_title="ID", is_id=True))
        await db.commit()
        await db.refresh(s)

        r = await client.get(f"/api/sets/{s.id}")
        tr = r.json()["tracklist"][0]
        assert tr["bpm"] is None
        assert tr["key"] is None
        assert tr["duration_ms"] is None

    async def test_top_genres_count_pct_and_order(self, client, db):
        s = DJSet(source="trackid", title="Genre Set")
        db.add(s)
        await db.flush()
        pos, n = 1, 0
        for genre, cnt in [("techno", 3), ("house", 2), ("trance", 1)]:
            for _ in range(cnt):
                await self._add_identified(
                    db, s, pos, title=f"t{n}", artist=f"a{n}", genres=[genre]
                )
                pos, n = pos + 1, n + 1
        # a genre-less identified track: excluded from the pct denominator (=6)
        await self._add_identified(db, s, pos, title=f"t{n}", artist=f"a{n}", genres=[])
        await db.commit()
        await db.refresh(s)

        r = await client.get(f"/api/sets/{s.id}")
        tg = r.json()["top_genres"]
        assert [g["name"] for g in tg] == ["techno", "house", "trance"]
        by_name = {g["name"]: g for g in tg}
        assert by_name["techno"]["pct"] == 50  # round(100 * 3 / 6)
        assert by_name["house"]["pct"] == 33  # round(100 * 2 / 6)
        assert by_name["trance"]["pct"] == 17  # round(100 * 1 / 6)

    async def test_top_genres_capped_at_five(self, client, db):
        s = DJSet(source="trackid", title="Many Genres")
        db.add(s)
        await db.flush()
        pos, n = 1, 0
        for genre, cnt in [("g6", 6), ("g5", 5), ("g4", 4), ("g3", 3), ("g2", 2), ("g1", 1)]:
            for _ in range(cnt):
                await self._add_identified(
                    db, s, pos, title=f"x{n}", artist=f"y{n}", genres=[genre]
                )
                pos, n = pos + 1, n + 1
        await db.commit()
        await db.refresh(s)

        r = await client.get(f"/api/sets/{s.id}")
        tg = r.json()["top_genres"]
        assert [g["name"] for g in tg] == ["g6", "g5", "g4", "g3", "g2"]
        assert len(tg) == 5

    async def test_top_genres_ignores_unidentified_tracks(self, client, db):
        s = DJSet(source="trackid", title="Mixed Set")
        db.add(s)
        await db.flush()
        await self._add_identified(db, s, 1, title="Real", artist="A", genres=["techno"])
        # catalog-linked but flagged is_id: must NOT contribute genres
        await self._add_identified(
            db, s, 2, title="Guess", artist="B", genres=["house"], is_id=True
        )
        await db.commit()
        await db.refresh(s)

        r = await client.get(f"/api/sets/{s.id}")
        assert {g["name"] for g in r.json()["top_genres"]} == {"techno"}

    async def test_top_genres_excludes_foreign_private_track(self, auth_client, db, auth_user):
        other = User(
            email="o@test.com", username="o", google_id="g-o", is_active=True
        )
        db.add(other)
        await db.flush()
        s = DJSet(source="trackid", title="Isolation Set")
        db.add(s)
        await db.flush()
        await self._add_identified(db, s, 1, title="Shared", artist="Alpha", genres=["techno"])
        await self._add_identified(
            db, s, 2, title="Secret", artist="Beta", genres=["house"],
            scope="private", owner_id=other.id,
        )
        await db.commit()
        await db.refresh(s)

        r = await auth_client.get(f"/api/sets/{s.id}")
        assert r.status_code == 200
        data = r.json()
        # foreign private "house" is excluded from the aggregate…
        assert {g["name"] for g in data["top_genres"]} == {"techno"}
        # …while the tracklist itself stays unfiltered (accepted C3 residual)
        assert {t["catalog_title"] for t in data["tracklist"]} == {"Shared", "Secret"}

    async def test_top_genres_guest_access(self, client, db):
        s = DJSet(source="trackid", title="Guest Genre Set")
        db.add(s)
        await db.flush()
        await self._add_identified(db, s, 1, title="Cola", artist="CamelPhat", genres=["techno"])
        await db.commit()
        await db.refresh(s)

        r = await client.get(f"/api/sets/{s.id}")
        assert r.status_code == 200
        assert {g["name"] for g in r.json()["top_genres"]} == {"techno"}


class TestImportSet:
    async def test_invalid_input_returns_422(self, auth_client):
        r = await auth_client.post("/api/sets/import", json={})
        assert r.status_code == 422

    async def test_import_with_slug(self, auth_client, db, mocker):
        fake_detail = {
            "id": 12345,
            "title": "Test Set from TrackID",
            "slug": "test-set",
            "duration": "01:30:00.0000000",
            "tracks": [],
        }
        mock_client_instance = AsyncMock()
        mock_client_instance.get_set_detail = AsyncMock(return_value=fake_detail)

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mocker.patch("trackid.client.TrackIDClient", return_value=mock_ctx)

        # Pre-create the set in the DB so refresh works
        dj_set = DJSet(source="trackid", title="Test Set from TrackID", external_id="12345")
        db.add(dj_set)
        await db.commit()
        await db.refresh(dj_set)

        mock_import = AsyncMock(return_value=(dj_set, []))
        mocker.patch("trackid.importer.import_audiostream", mock_import)

        r = await auth_client.post("/api/sets/import", json={"slug": "test-set"})
        assert r.status_code == 200
        assert r.json()["title"] == "Test Set from TrackID"

    async def test_import_with_existing_follow_but_no_opinion(
        self, auth_client, db, auth_user, mocker
    ):
        """Follow already present but opinion missing: the auto-like must not
        insert a duplicate follow (sync_set_opinion checks existence first)."""
        fake_detail = {
            "id": 54321,
            "title": "Already Followed Set",
            "slug": "already-followed",
            "duration": "01:00:00.0000000",
            "tracks": [],
        }
        mock_client_instance = AsyncMock()
        mock_client_instance.get_set_detail = AsyncMock(return_value=fake_detail)

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mocker.patch("trackid.client.TrackIDClient", return_value=mock_ctx)

        dj_set = DJSet(source="trackid", title="Already Followed Set", external_id="54321")
        db.add(dj_set)
        await db.flush()
        db.add(
            UserSetFollow(
                user_id=auth_user.id,
                set_id=dj_set.id,
                followed_at=datetime.now(timezone.utc),
            )
        )
        await db.commit()
        await db.refresh(dj_set)

        r = await auth_client.post("/api/sets/import", json={"slug": "already-followed"})
        assert r.status_code == 200

        follows = (
            await db.execute(
                select(UserSetFollow).where(
                    UserSetFollow.user_id == auth_user.id,
                    UserSetFollow.set_id == dj_set.id,
                )
            )
        ).scalars().all()
        assert len(follows) == 1

        opinion = (
            await db.execute(
                select(UserOpinion).where(
                    UserOpinion.user_id == auth_user.id,
                    UserOpinion.entity_type == "set",
                    UserOpinion.entity_key == str(dj_set.id),
                )
            )
        ).scalar_one_or_none()
        assert opinion is not None
        assert opinion.opinion == "liked"


class TestSetChildVisibility:
    """Un set enfant (parent_set_id non NULL) ne doit pas apparaître dans les listings."""

    async def test_list_sets_excludes_child(self, client, db):
        parent = DJSet(source="trackid", title="Parent Set")
        db.add(parent)
        await db.flush()
        await _attach_identified_track(db, parent)
        child = DJSet(source="trackid", title="Child Set", parent_set_id=parent.id)
        db.add(child)
        await db.commit()

        r = await client.get("/api/sets/")
        assert r.status_code == 200
        data = r.json()
        titles = [item["title"] for item in data["items"]]
        assert "Parent Set" in titles
        assert "Child Set" not in titles
        assert data["total"] == 1

    async def test_list_sets_with_q_excludes_child(self, client, db):
        parent = DJSet(source="trackid", title="Boiler Room Berlin")
        db.add(parent)
        await db.flush()
        await _attach_identified_track(db, parent)
        child = DJSet(source="trackid", title="Boiler Room Berlin Part 2", parent_set_id=parent.id)
        db.add(child)
        await db.commit()

        r = await client.get("/api/sets/?q=boiler")
        assert r.status_code == 200
        data = r.json()
        titles = [item["title"] for item in data["items"]]
        assert "Boiler Room Berlin" in titles
        assert "Boiler Room Berlin Part 2" not in titles
        assert data["total"] == 1


class TestSearchSets:
    async def test_search(self, client, mocker):
        mock_client_instance = AsyncMock()
        mock_client_instance.search_sets = AsyncMock(return_value=(
            [{"id": 1, "slug": "test", "title": "Test Set", "channel": None,
              "artworkUrl": None, "trackCount": 10, "duration": "01:00:00",
              "createdOn": "2024-01-01"}],
            1,
        ))

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mocker.patch("trackid.client.TrackIDClient", return_value=mock_ctx)

        r = await client.get("/api/sets/search?q=test")
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 1
        assert data[0]["title"] == "Test Set"
        assert data[0]["already_imported"] is False
