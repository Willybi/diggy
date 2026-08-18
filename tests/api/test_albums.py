"""Tests for /api/albums endpoints (L5)."""
from datetime import date

from models import (
    Album,
    AlbumType,
    Artist,
    CatalogAlbum,
    CatalogArtist,
    CatalogEntry,
    User,
    UserTrack,
)


async def _add_album(db, *, title="Random Access Memories", artist_id=None, **kw):
    album = Album(
        title=title,
        record_type=kw.pop("record_type", AlbumType.album),
        release_date=kw.pop("release_date", date(2013, 5, 17)),
        label=kw.pop("label", "Columbia"),
        artist_id=artist_id,
        has_artwork=kw.pop("has_artwork", True),
        **kw,
    )
    db.add(album)
    await db.flush()
    return album


async def _link_track(db, album, *, title, artist, scope="shared", owner_id=None, **kw):
    cat = CatalogEntry(
        title=title,
        artist=artist,
        normalized_key=f"{artist}|{title}".lower(),
        scope=scope,
        owner_id=owner_id,
        **kw,
    )
    db.add(cat)
    await db.flush()
    db.add(CatalogAlbum(catalog_id=cat.id, album_id=album.id))
    return cat


class TestAlbumDetail:
    async def test_returns_album_with_metadata_and_tracklist(self, client, db):
        a = Artist(name="Daft Punk", normalized_name="daft punk")
        db.add(a)
        await db.flush()
        album = await _add_album(db, title="Random Access Memories", artist_id=a.id)
        await _link_track(
            db, album, title="Get Lucky", artist="Daft Punk",
            bpm=116.0, key="6A", duration_ms=369000,
        )
        await _link_track(db, album, title="Instant Crush", artist="Daft Punk")
        await db.commit()

        r = await client.get(f"/api/albums/{album.id}")
        assert r.status_code == 200
        data = r.json()
        assert data["title"] == "Random Access Memories"
        assert data["record_type"] == "album"
        assert data["release_date"] == "2013-05-17"
        assert data["label"] == "Columbia"
        assert data["has_artwork"] is True
        assert data["artist"] == {
            "id": a.id, "name": "Daft Punk", "role": None, "has_artwork": False
        }
        assert data["total_tracks"] == 2
        titles = {t["title"] for t in data["tracklist"]}
        assert titles == {"Get Lucky", "Instant Crush"}
        gl = next(t for t in data["tracklist"] if t["title"] == "Get Lucky")
        assert gl["bpm"] == 116.0
        assert gl["key"] == "6A"
        assert gl["duration_ms"] == 369000

    async def test_tracklist_carries_linked_artists(self, client, db):
        a = Artist(name="Pharrell", normalized_name="pharrell")
        db.add(a)
        await db.flush()
        album = await _add_album(db, title="RAM", artist_id=None)
        cat = await _link_track(db, album, title="Get Lucky", artist="Daft Punk")
        db.add(CatalogArtist(catalog_id=cat.id, artist_id=a.id, role="feat", position=1))
        await db.commit()

        r = await client.get(f"/api/albums/{album.id}")
        assert r.status_code == 200
        track = r.json()["tracklist"][0]
        assert track["artists"] == [
            {"id": a.id, "name": "Pharrell", "role": "feat", "has_artwork": False}
        ]

    async def test_album_without_artist_returns_null(self, client, db):
        album = await _add_album(db, title="Compilation", artist_id=None)
        await _link_track(db, album, title="Track", artist="VA")
        await db.commit()

        r = await client.get(f"/api/albums/{album.id}")
        assert r.status_code == 200
        assert r.json()["artist"] is None

    async def test_404_when_not_found(self, client):
        r = await client.get("/api/albums/999999")
        assert r.status_code == 404

    async def test_empty_tracklist(self, client, db):
        album = await _add_album(db, title="Ghost Album", artist_id=None)
        await db.commit()

        r = await client.get(f"/api/albums/{album.id}")
        assert r.status_code == 200
        data = r.json()
        assert data["tracklist"] == []
        assert data["total_tracks"] == 0


class TestAlbumDetailVisibility:
    """The tracklist must apply catalog_visible: a foreign private track never
    surfaces to a guest or a third-party viewer (C3)."""

    async def test_guest_never_sees_foreign_private_track(self, client, db):
        other = User(
            email="own@test.com", username="own", google_id="g-own", is_active=True
        )
        db.add(other)
        await db.flush()
        album = await _add_album(db, title="Mixed Visibility", artist_id=None)
        await _link_track(db, album, title="Public", artist="Alpha")
        await _link_track(
            db, album, title="Private", artist="Beta",
            scope="private", owner_id=other.id,
        )
        await db.commit()

        r = await client.get(f"/api/albums/{album.id}")
        assert r.status_code == 200
        data = r.json()
        assert {t["title"] for t in data["tracklist"]} == {"Public"}
        assert data["total_tracks"] == 1

    async def test_third_party_user_does_not_see_foreign_private_track(
        self, auth_client, db, auth_user
    ):
        other = User(
            email="own2@test.com", username="own2", google_id="g-own2", is_active=True
        )
        db.add(other)
        await db.flush()
        album = await _add_album(db, title="Mixed Visibility", artist_id=None)
        await _link_track(db, album, title="Public", artist="Alpha")
        await _link_track(
            db, album, title="Private", artist="Beta",
            scope="private", owner_id=other.id,
        )
        await db.commit()

        r = await auth_client.get(f"/api/albums/{album.id}")
        assert r.status_code == 200
        data = r.json()
        assert {t["title"] for t in data["tracklist"]} == {"Public"}
        assert data["total_tracks"] == 1

    async def test_owner_sees_their_private_track_and_in_lib(
        self, auth_client, db, auth_user
    ):
        album = await _add_album(db, title="My Album", artist_id=None)
        cat = await _link_track(
            db, album, title="Mine", artist="Me",
            scope="private", owner_id=auth_user.id,
        )
        db.add(UserTrack(user_id=auth_user.id, catalog_id=cat.id, source="test"))
        await db.commit()

        r = await auth_client.get(f"/api/albums/{album.id}")
        assert r.status_code == 200
        data = r.json()
        assert {t["title"] for t in data["tracklist"]} == {"Mine"}
        assert data["tracklist"][0]["in_lib"] is True
