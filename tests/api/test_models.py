"""
Tests des nouveaux modèles : Genre, Artist, ArtistAlias, DJSet, SetArtist, SetTrack.
Vérifie CRUD, contraintes d'unicité, relations et cascades.
"""
import pytest
import pytest_asyncio

pytestmark = pytest.mark.asyncio

from sqlalchemy import select

from models import (
    Genre,
    Artist,
    ArtistAlias,
    CatalogEntry,
    DJSet,
    SetArtist,
    SetTrack,
    catalog_genres,
)


# ── Genre ────────────────────────────────────────────────────────────────


class TestGenre:
    async def test_create(self, db):
        db.add(Genre(name="Tech House"))
        await db.commit()
        result = await db.execute(select(Genre))
        assert result.scalar_one().name == "Tech House"

    async def test_unique_name(self, db):
        db.add(Genre(name="Techno"))
        await db.commit()
        db.add(Genre(name="Techno"))
        with pytest.raises(Exception):
            await db.commit()

    async def test_hierarchy(self, db):
        parent = Genre(name="Techno")
        db.add(parent)
        await db.flush()
        child = Genre(name="Melodic Techno", parent_id=parent.id)
        db.add(child)
        await db.commit()

        result = await db.execute(select(Genre).where(Genre.name == "Melodic Techno"))
        assert result.scalar_one().parent_id == parent.id


# ── Artist ───────────────────────────────────────────────────────────────


class TestArtist:
    async def test_create(self, db):
        db.add(Artist(name="CamelPhat", normalized_name="camelphat"))
        await db.commit()
        result = await db.execute(select(Artist))
        assert result.scalar_one().name == "CamelPhat"

    async def test_unique_normalized_name(self, db):
        db.add(Artist(name="CamelPhat", normalized_name="camelphat"))
        await db.commit()
        db.add(Artist(name="CAMELPHAT", normalized_name="camelphat"))
        with pytest.raises(Exception):
            await db.commit()


# ── ArtistAlias ──────────────────────────────────────────────────────────


class TestArtistAlias:
    async def test_create(self, db):
        artist = Artist(name="CamelPhat", normalized_name="camelphat")
        db.add(artist)
        await db.flush()
        db.add(ArtistAlias(artist_id=artist.id, alias="Camel Phat", normalized_alias="camel phat"))
        await db.commit()
        result = await db.execute(select(ArtistAlias))
        assert result.scalar_one().alias == "Camel Phat"

    async def test_unique_normalized_alias(self, db):
        artist = Artist(name="CamelPhat", normalized_name="camelphat")
        db.add(artist)
        await db.flush()
        db.add(ArtistAlias(artist_id=artist.id, alias="A", normalized_alias="same"))
        await db.commit()
        db.add(ArtistAlias(artist_id=artist.id, alias="B", normalized_alias="same"))
        with pytest.raises(Exception):
            await db.commit()


# ── DJSet ────────────────────────────────────────────────────────────────


class TestDJSet:
    async def test_create(self, db):
        db.add(DJSet(source="trackid", title="Boiler Room London"))
        await db.commit()
        result = await db.execute(select(DJSet))
        assert result.scalar_one().title == "Boiler Room London"

    async def test_unique_external_id_per_source(self, db):
        db.add(DJSet(external_id="123", source="trackid", title="Set A"))
        await db.commit()
        db.add(DJSet(external_id="123", source="trackid", title="Set B"))
        with pytest.raises(Exception):
            await db.commit()

    async def test_same_external_id_different_source_ok(self, db):
        db.add(DJSet(external_id="123", source="trackid", title="Set A"))
        db.add(DJSet(external_id="123", source="1001tracklists", title="Set B"))
        await db.commit()
        result = await db.execute(select(DJSet))
        assert len(result.scalars().all()) == 2

    async def test_null_external_id_multiple_ok(self, db):
        db.add(DJSet(external_id=None, source="manual", title="Set A"))
        db.add(DJSet(external_id=None, source="manual", title="Set B"))
        await db.commit()
        result = await db.execute(select(DJSet))
        assert len(result.scalars().all()) == 2


# ── SetArtist (B2B) ─────────────────────────────────────────────────────


class TestSetArtist:
    async def test_b2b_two_artists(self, db):
        a1 = Artist(name="CamelPhat", normalized_name="camelphat")
        a2 = Artist(name="Solardo", normalized_name="solardo")
        db.add_all([a1, a2])
        await db.flush()

        s = DJSet(source="trackid", title="CamelPhat b2b Solardo")
        db.add(s)
        await db.flush()

        db.add(SetArtist(set_id=s.id, artist_id=a1.id, role="b2b", position=1))
        db.add(SetArtist(set_id=s.id, artist_id=a2.id, role="b2b", position=2))
        await db.commit()

        result = await db.execute(select(SetArtist).where(SetArtist.set_id == s.id))
        assert len(result.scalars().all()) == 2


# ── SetTrack ─────────────────────────────────────────────────────────────


class TestSetTrack:
    async def test_create(self, db):
        s = DJSet(source="trackid", title="Test Set")
        db.add(s)
        await db.flush()
        db.add(SetTrack(set_id=s.id, position=1, raw_title="Cola", raw_artist="CamelPhat"))
        await db.commit()
        result = await db.execute(select(SetTrack))
        track = result.scalar_one()
        assert track.raw_title == "Cola"
        assert track.catalog_id is None

    async def test_unique_position_per_set(self, db):
        s = DJSet(source="trackid", title="Test Set")
        db.add(s)
        await db.flush()
        db.add(SetTrack(set_id=s.id, position=1, raw_title="Track A"))
        await db.commit()
        db.add(SetTrack(set_id=s.id, position=1, raw_title="Track B"))
        with pytest.raises(Exception):
            await db.commit()

    async def test_same_position_different_sets_ok(self, db):
        s1 = DJSet(source="trackid", title="Set 1")
        s2 = DJSet(source="manual", title="Set 2")
        db.add_all([s1, s2])
        await db.flush()
        db.add(SetTrack(set_id=s1.id, position=1, raw_title="A"))
        db.add(SetTrack(set_id=s2.id, position=1, raw_title="B"))
        await db.commit()
        result = await db.execute(select(SetTrack))
        assert len(result.scalars().all()) == 2

    async def test_link_to_catalog(self, db):
        cat = CatalogEntry(title="Cola", artist="CamelPhat", normalized_key="cola - camelphat")
        db.add(cat)
        await db.flush()
        s = DJSet(source="trackid", title="Test")
        db.add(s)
        await db.flush()
        db.add(SetTrack(set_id=s.id, position=1, raw_title="Cola", catalog_id=cat.id))
        await db.commit()
        result = await db.execute(select(SetTrack))
        assert result.scalar_one().catalog_id == cat.id

    async def test_is_id_flag(self, db):
        s = DJSet(source="trackid", title="Test")
        db.add(s)
        await db.flush()
        db.add(SetTrack(set_id=s.id, position=1, raw_title="ID", raw_artist="ID", is_id=True))
        await db.commit()
        result = await db.execute(select(SetTrack))
        assert result.scalar_one().is_id is True


# ── Cascades ─────────────────────────────────────────────────────────────


class TestCascade:
    async def test_delete_set_cascades_tracks(self, db):
        s = DJSet(source="trackid", title="Test")
        db.add(s)
        await db.flush()
        db.add(SetTrack(set_id=s.id, position=1, raw_title="A"))
        db.add(SetTrack(set_id=s.id, position=2, raw_title="B"))
        await db.commit()

        await db.delete(s)
        await db.commit()
        result = await db.execute(select(SetTrack))
        assert result.scalars().all() == []

    async def test_delete_set_cascades_artist_links(self, db):
        a = Artist(name="Test", normalized_name="test")
        db.add(a)
        s = DJSet(source="trackid", title="Test")
        db.add(s)
        await db.flush()
        db.add(SetArtist(set_id=s.id, artist_id=a.id, role="main"))
        await db.commit()

        await db.delete(s)
        await db.commit()
        result = await db.execute(select(SetArtist))
        assert result.scalars().all() == []

    async def test_delete_artist_cascades_aliases(self, db):
        a = Artist(name="CamelPhat", normalized_name="camelphat")
        db.add(a)
        await db.flush()
        db.add(ArtistAlias(artist_id=a.id, alias="Camel Phat", normalized_alias="camel phat"))
        await db.commit()

        await db.delete(a)
        await db.commit()
        result = await db.execute(select(ArtistAlias))
        assert result.scalars().all() == []


# ── CatalogGenres (association) ──────────────────────────────────────


class TestCatalogGenres:
    async def test_link_catalog_to_genre(self, db):
        cat = CatalogEntry(title="Cola", artist="CamelPhat", normalized_key="cola|camelphat")
        g = Genre(name="Tech House")
        db.add_all([cat, g])
        await db.flush()

        await db.execute(catalog_genres.insert().values(catalog_id=cat.id, genre_id=g.id))
        await db.commit()

        result = await db.execute(
            select(catalog_genres).where(catalog_genres.c.catalog_id == cat.id)
        )
        rows = result.all()
        assert len(rows) == 1
        assert rows[0].genre_id == g.id

    async def test_catalog_multiple_genres(self, db):
        cat = CatalogEntry(title="Track", artist="Artist", normalized_key="track|artist")
        g1 = Genre(name="Tech House")
        g2 = Genre(name="Deep House")
        db.add_all([cat, g1, g2])
        await db.flush()

        await db.execute(catalog_genres.insert().values(catalog_id=cat.id, genre_id=g1.id))
        await db.execute(catalog_genres.insert().values(catalog_id=cat.id, genre_id=g2.id))
        await db.commit()

        result = await db.execute(
            select(catalog_genres).where(catalog_genres.c.catalog_id == cat.id)
        )
        assert len(result.all()) == 2

    async def test_genre_linked_to_multiple_catalogs(self, db):
        g = Genre(name="Techno")
        c1 = CatalogEntry(title="A", artist="X", normalized_key="a|x")
        c2 = CatalogEntry(title="B", artist="Y", normalized_key="b|y")
        db.add_all([g, c1, c2])
        await db.flush()

        await db.execute(catalog_genres.insert().values(catalog_id=c1.id, genre_id=g.id))
        await db.execute(catalog_genres.insert().values(catalog_id=c2.id, genre_id=g.id))
        await db.commit()

        result = await db.execute(
            select(catalog_genres).where(catalog_genres.c.genre_id == g.id)
        )
        assert len(result.all()) == 2

    async def test_no_duplicate_link(self, db):
        cat = CatalogEntry(title="Track", artist="Art", normalized_key="track|art")
        g = Genre(name="House")
        db.add_all([cat, g])
        await db.flush()

        await db.execute(catalog_genres.insert().values(catalog_id=cat.id, genre_id=g.id))
        await db.commit()
        with pytest.raises(Exception):
            await db.execute(catalog_genres.insert().values(catalog_id=cat.id, genre_id=g.id))
            await db.commit()

    async def test_genre_relationship_on_catalog(self, db):
        """Test the ORM relationship CatalogEntry.genres."""
        cat = CatalogEntry(title="Track", artist="Art", normalized_key="track|art2")
        g = Genre(name="Melodic Techno")
        db.add_all([cat, g])
        await db.flush()

        await db.execute(catalog_genres.insert().values(catalog_id=cat.id, genre_id=g.id))
        await db.commit()

        await db.refresh(cat, ["genres"])
        assert len(cat.genres) == 1
        assert cat.genres[0].name == "Melodic Techno"
