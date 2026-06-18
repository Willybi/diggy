"""Tests for server/api/trackid/importer.py — get_or_create_artist logic."""
from models import Artist, ArtistAlias
from trackid.importer import get_or_create_artist


class TestGetOrCreateArtist:
    async def test_creates_new_artist(self, db):
        artist = await get_or_create_artist(db, "CamelPhat")
        await db.commit()
        assert artist.name == "CamelPhat"
        assert artist.normalized_name == "camelphat"
        assert artist.id is not None

    async def test_returns_existing_by_normalized_name(self, db):
        a1 = await get_or_create_artist(db, "CamelPhat")
        await db.flush()
        a2 = await get_or_create_artist(db, "CAMELPHAT")
        assert a1.id == a2.id

    async def test_matches_via_alias(self, db):
        artist = Artist(name="CamelPhat", normalized_name="camelphat")
        db.add(artist)
        await db.flush()
        db.add(ArtistAlias(
            artist_id=artist.id,
            alias="Camel Phat",
            normalized_alias="camel phat",
        ))
        await db.flush()

        found = await get_or_create_artist(db, "Camel Phat")
        assert found.id == artist.id

    async def test_sets_trackid_id(self, db):
        artist = await get_or_create_artist(db, "TestArtist", trackid_id="99")
        await db.commit()
        assert artist.trackid_id == "99"

    async def test_updates_trackid_id_on_existing(self, db):
        artist = await get_or_create_artist(db, "TestArtist")
        await db.flush()
        same = await get_or_create_artist(db, "TestArtist", trackid_id="42")
        assert same.trackid_id == "42"
        assert same.id == artist.id
