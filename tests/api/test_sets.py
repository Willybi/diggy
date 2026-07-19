"""Tests for /api/sets endpoints."""
from datetime import datetime, timezone
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


class TestListSets:
    async def test_empty_returns_zero(self, client):
        r = await client.get("/api/sets/")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 0
        assert data["items"] == []

    async def test_returns_sets(self, client, db):
        db.add(DJSet(source="trackid", title="Boiler Room London"))
        await db.commit()
        r = await client.get("/api/sets/")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 1
        assert data["items"][0]["title"] == "Boiler Room London"

    async def test_filter_by_title(self, client, db):
        db.add(DJSet(source="trackid", title="Boiler Room London"))
        db.add(DJSet(source="trackid", title="Cercle Paris"))
        await db.commit()
        r = await client.get("/api/sets/?q=boiler")
        data = r.json()
        assert data["total"] == 1
        assert data["items"][0]["title"] == "Boiler Room London"

    async def test_includes_track_counts(self, client, db):
        s = DJSet(source="trackid", title="Test Set")
        db.add(s)
        await db.flush()
        db.add(SetTrack(set_id=s.id, position=1, raw_title="Track 1"))
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
        await db.commit()
        r = await client.get("/api/sets/")
        data = r.json()
        assert data["items"][0]["artists"] == ["ANNA"]

    async def test_pagination(self, client, db):
        for i in range(5):
            db.add(DJSet(source="trackid", title=f"Set {i}"))
        await db.commit()
        r = await client.get("/api/sets/?limit=2")
        data = r.json()
        assert len(data["items"]) == 2
        assert data["total"] == 5

    async def test_pagination_offset(self, client, db):
        for i in range(5):
            db.add(DJSet(source="trackid", title=f"Set {i}"))
        await db.commit()
        r = await client.get("/api/sets/?offset=3&limit=10")
        data = r.json()
        assert len(data["items"]) == 2
        assert data["total"] == 5


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
