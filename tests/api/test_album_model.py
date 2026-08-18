"""
Tests du modèle Album (L1 — entité Album de première classe) :
création, lien CatalogAlbum, unicité partielle de deezer_album_id, cascade.
"""
import pytest

from sqlalchemy import select

from models import (
    Album,
    AlbumType,
    Artist,
    CatalogAlbum,
    CatalogEntry,
)


# ── Album ────────────────────────────────────────────────────────────────


class TestAlbum:
    async def test_create(self, db):
        db.add(Album(title="Settle", record_type=AlbumType.album))
        await db.commit()
        result = await db.execute(select(Album))
        album = result.scalar_one()
        assert album.title == "Settle"
        assert album.record_type == AlbumType.album
        assert album.has_artwork in (False, None)

    async def test_link_to_artist(self, db):
        artist = Artist(name="Disclosure", normalized_name="disclosure")
        db.add(artist)
        await db.flush()
        db.add(Album(title="Settle", artist_id=artist.id))
        await db.commit()
        result = await db.execute(select(Album))
        assert result.scalar_one().artist.name == "Disclosure"


# ── CatalogAlbum (M2M) ───────────────────────────────────────────────────


class TestCatalogAlbum:
    async def test_link_catalog_to_album(self, db):
        cat = CatalogEntry(
            title="Latch", artist="Disclosure", normalized_key="latch - disclosure"
        )
        album = Album(title="Settle")
        db.add_all([cat, album])
        await db.flush()
        db.add(CatalogAlbum(catalog_id=cat.id, album_id=album.id))
        await db.commit()

        result = await db.execute(select(CatalogAlbum))
        link = result.scalar_one()
        assert link.catalog_id == cat.id
        assert link.album_id == album.id

    async def test_same_album_multiple_catalog_ok(self, db):
        album = Album(title="Settle")
        c1 = CatalogEntry(title="Latch", normalized_key="latch")
        c2 = CatalogEntry(title="White Noise", normalized_key="white noise")
        db.add_all([album, c1, c2])
        await db.flush()
        db.add(CatalogAlbum(catalog_id=c1.id, album_id=album.id))
        db.add(CatalogAlbum(catalog_id=c2.id, album_id=album.id))
        await db.commit()
        result = await db.execute(select(CatalogAlbum))
        assert len(result.scalars().all()) == 2


# ── Unicité partielle deezer_album_id ────────────────────────────────────


class TestDeezerAlbumUnique:
    async def test_multiple_null_deezer_id_ok(self, db):
        db.add(Album(title="A", deezer_album_id=None))
        db.add(Album(title="B", deezer_album_id=None))
        await db.commit()
        result = await db.execute(select(Album))
        assert len(result.scalars().all()) == 2

    async def test_duplicate_deezer_id_raises(self, db):
        db.add(Album(title="A", deezer_album_id="12345"))
        await db.commit()
        db.add(Album(title="B", deezer_album_id="12345"))
        with pytest.raises(Exception):
            await db.commit()

    async def test_distinct_deezer_id_ok(self, db):
        db.add(Album(title="A", deezer_album_id="1"))
        db.add(Album(title="B", deezer_album_id="2"))
        await db.commit()
        result = await db.execute(select(Album))
        assert len(result.scalars().all()) == 2


# ── Cascade ──────────────────────────────────────────────────────────────


class TestCascade:
    async def test_delete_catalog_cascades_album_link(self, db):
        cat = CatalogEntry(title="Latch", normalized_key="latch - disclosure")
        album = Album(title="Settle")
        db.add_all([cat, album])
        await db.flush()
        db.add(CatalogAlbum(catalog_id=cat.id, album_id=album.id))
        await db.commit()

        await db.delete(cat)
        await db.commit()

        # The link is gone, the album row survives.
        links = await db.execute(select(CatalogAlbum))
        assert links.scalars().all() == []
        albums = await db.execute(select(Album))
        assert len(albums.scalars().all()) == 1
