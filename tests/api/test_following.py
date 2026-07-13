"""Tests for artist following: /api/artists/{id}/follow + /api/following."""
from datetime import datetime, timezone

from models import Artist, ArtistActivity, FollowedArtist, User
from sqlalchemy import func, select


async def _make_artist(db, name="CamelPhat", normalized=None):
    artist = Artist(name=name, normalized_name=normalized or name.lower())
    db.add(artist)
    await db.commit()
    await db.refresh(artist)
    return artist


async def _make_catalog(db, *, title, artist, normalized_key, **kw):
    from datetime import date

    from models import CatalogEntry

    entry = CatalogEntry(
        title=title,
        artist=artist,
        normalized_key=normalized_key,
        scope="shared",
        has_artwork=kw.get("has_artwork", True),
        has_preview=kw.get("has_preview", True),
        bpm=kw.get("bpm", 128.0),
        key=kw.get("key", "8A"),
        duration_ms=kw.get("duration_ms", 210000),
        release_date=kw.get("release_date", date(2026, 7, 10)),
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return entry


async def _follow_count(db, user_id, artist_id):
    result = await db.execute(
        select(func.count())
        .select_from(FollowedArtist)
        .where(
            FollowedArtist.user_id == user_id,
            FollowedArtist.artist_id == artist_id,
        )
    )
    return result.scalar()


class TestFollowUnfollow:
    async def test_follow_then_refollow_idempotent(self, auth_client, auth_user, db):
        artist = await _make_artist(db)

        r = await auth_client.post(f"/api/artists/{artist.id}/follow")
        assert r.status_code == 200
        assert r.json() == {"following": True}

        r = await auth_client.post(f"/api/artists/{artist.id}/follow")
        assert r.status_code == 200
        assert r.json() == {"following": True}

        assert await _follow_count(db, auth_user.id, artist.id) == 1

    async def test_unfollow_idempotent(self, auth_client, auth_user, db):
        artist = await _make_artist(db)
        await auth_client.post(f"/api/artists/{artist.id}/follow")

        r = await auth_client.delete(f"/api/artists/{artist.id}/follow")
        assert r.status_code == 200
        assert r.json() == {"following": False}

        r = await auth_client.delete(f"/api/artists/{artist.id}/follow")
        assert r.status_code == 200
        assert r.json() == {"following": False}

        assert await _follow_count(db, auth_user.id, artist.id) == 0

    async def test_follow_unknown_artist_404(self, auth_client):
        r = await auth_client.post("/api/artists/999999/follow")
        assert r.status_code == 404

    async def test_follow_without_auth_401(self, client, db):
        artist = await _make_artist(db)
        r = await client.post(f"/api/artists/{artist.id}/follow")
        assert r.status_code == 401


class TestArtistDetailFollowing:
    async def test_guest_gets_following_false(self, client, db):
        artist = await _make_artist(db)
        r = await client.get(f"/api/artists/{artist.id}")
        assert r.status_code == 200
        assert r.json()["following"] is False

    async def test_following_true_after_follow(self, auth_client, db):
        artist = await _make_artist(db)

        r = await auth_client.get(f"/api/artists/{artist.id}")
        assert r.json()["following"] is False

        await auth_client.post(f"/api/artists/{artist.id}/follow")

        r = await auth_client.get(f"/api/artists/{artist.id}")
        assert r.status_code == 200
        assert r.json()["following"] is True


class TestFollowingList:
    async def test_without_auth_401(self, client):
        r = await client.get("/api/following/")
        assert r.status_code == 401

    async def test_empty_list(self, auth_client):
        r = await auth_client.get("/api/following/")
        assert r.status_code == 200
        assert r.json() == {"items": []}

    async def test_list_sorted_followed_at_desc(self, auth_client, auth_user, db):
        old = await _make_artist(db, name="Old Follow", normalized="old follow")
        new = await _make_artist(db, name="New Follow", normalized="new follow")
        db.add(
            FollowedArtist(
                user_id=auth_user.id,
                artist_id=old.id,
                followed_at=datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc),
            )
        )
        db.add(
            FollowedArtist(
                user_id=auth_user.id,
                artist_id=new.id,
                followed_at=datetime(2026, 7, 10, 10, 0, tzinfo=timezone.utc),
            )
        )
        await db.commit()

        r = await auth_client.get("/api/following/")
        assert r.status_code == 200
        items = r.json()["items"]
        assert [i["artist_id"] for i in items] == [new.id, old.id]
        assert items[0]["name"] == "New Follow"
        assert items[0]["has_artwork"] is False
        assert items[0]["followed_at"] is not None


async def _seed_activity(db, auth_user):
    """Followed artist with 2 activities + non-followed artist with 1."""
    followed = await _make_artist(db, name="Followed", normalized="followed")
    other = await _make_artist(db, name="Other", normalized="other")
    db.add(
        FollowedArtist(
            user_id=auth_user.id,
            artist_id=followed.id,
            followed_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
        )
    )
    db.add(
        ArtistActivity(
            artist_id=followed.id,
            activity_type="release",
            source="deezer",
            external_id="album-1",
            title="New EP",
            external_url="https://www.deezer.com/album/1",
            detected_at=datetime(2026, 7, 2, 12, 0, tzinfo=timezone.utc),
        )
    )
    db.add(
        ArtistActivity(
            artist_id=followed.id,
            activity_type="set",
            source="trackid",
            external_id="42",
            title="Live at Fabric",
            set_id=None,
            detected_at=datetime(2026, 7, 9, 12, 0, tzinfo=timezone.utc),
        )
    )
    db.add(
        ArtistActivity(
            artist_id=other.id,
            activity_type="release",
            source="deezer",
            external_id="album-2",
            title="Unfollowed release",
            detected_at=datetime(2026, 7, 8, 12, 0, tzinfo=timezone.utc),
        )
    )
    await db.commit()
    return followed, other


class TestActivityFeed:
    async def test_feed_envelope_type_and_sort(self, auth_client, auth_user, db):
        followed, _ = await _seed_activity(db, auth_user)

        r = await auth_client.get("/api/following/activity")
        assert r.status_code == 200
        data = r.json()
        assert "items" in data
        items = data["items"]
        # Only the followed artist's activities, newest first
        assert len(items) == 2
        assert items[0]["type"] == "set"
        assert items[1]["type"] == "release"
        assert all(i["artist_id"] == followed.id for i in items)
        assert items[0]["artist_name"] == "Followed"
        assert items[0]["source"] == "trackid"
        assert items[1]["title"] == "New EP"
        assert items[1]["external_url"] == "https://www.deezer.com/album/1"
        # A link-only release (no crawled catalog track) leaves the track fields
        # at their defaults.
        assert items[1]["catalog_id"] is None
        assert items[1]["has_artwork"] is False
        assert items[1]["bpm"] is None
        assert items[1]["release_date"] is None
        # No DB column name leaking into the contract
        assert "activity_type" not in items[0]

    async def test_feed_release_with_catalog_returns_track_fields(
        self, auth_client, auth_user, db
    ):
        from datetime import date

        followed = await _make_artist(db, name="Crawler", normalized="crawler")
        entry = await _make_catalog(
            db,
            title="Fresh Cut",
            artist="Crawler",
            normalized_key="crawler|fresh cut",
            release_date=date(2026, 7, 10),
        )
        db.add(
            FollowedArtist(
                user_id=auth_user.id,
                artist_id=followed.id,
                followed_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
            )
        )
        db.add(
            ArtistActivity(
                artist_id=followed.id,
                activity_type="release",
                source="deezer",
                external_id="track-9",
                title="Fresh Cut",
                external_url="https://www.deezer.com/track/9",
                catalog_id=entry.id,
                detected_at=datetime(2026, 7, 11, 12, 0, tzinfo=timezone.utc),
            )
        )
        await db.commit()

        r = await auth_client.get("/api/following/activity")
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) == 1
        it = items[0]
        assert it["type"] == "release"
        assert it["catalog_id"] == entry.id
        assert it["has_artwork"] is True
        assert it["has_preview"] is True
        assert it["bpm"] == 128.0
        assert it["key"] == "8A"
        assert it["duration_ms"] == 210000
        assert it["artist"] == "Crawler"
        assert it["release_date"] == "2026-07-10"

    async def test_feed_pagination(self, auth_client, auth_user, db):
        await _seed_activity(db, auth_user)

        r = await auth_client.get("/api/following/activity?limit=1")
        items = r.json()["items"]
        assert len(items) == 1
        assert items[0]["type"] == "set"

        r = await auth_client.get("/api/following/activity?limit=1&offset=1")
        items = r.json()["items"]
        assert len(items) == 1
        assert items[0]["type"] == "release"

    async def test_feed_limit_bounds(self, auth_client):
        r = await auth_client.get("/api/following/activity?limit=101")
        assert r.status_code == 422
        r = await auth_client.get("/api/following/activity?offset=-1")
        assert r.status_code == 422


class TestNewCountAndSeen:
    async def test_new_count_without_seen_marker(self, auth_client, auth_user, db):
        await _seed_activity(db, auth_user)

        r = await auth_client.get("/api/following/activity/new-count")
        assert r.status_code == 200
        assert r.json() == {"count": 2}

    async def test_new_count_with_seen_marker(self, auth_client, auth_user, db):
        await _seed_activity(db, auth_user)
        # Marker between the two activities (2026-07-02 and 2026-07-09)
        auth_user.settings = {
            **(auth_user.settings or {}),
            "artist_activity_seen_at": "2026-07-05T00:00:00+00:00",
        }
        await db.commit()

        r = await auth_client.get("/api/following/activity/new-count")
        assert r.json() == {"count": 1}

    async def test_seen_resets_new_count(self, auth_client, auth_user, db):
        await _seed_activity(db, auth_user)

        r = await auth_client.post("/api/following/activity/seen")
        assert r.status_code == 200
        assert r.json() == {"ok": True}

        r = await auth_client.get("/api/following/activity/new-count")
        assert r.json() == {"count": 0}

        user = await db.get(User, auth_user.id)
        await db.refresh(user)
        assert "artist_activity_seen_at" in (user.settings or {})
