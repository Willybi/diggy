"""Tests for /api/artists endpoints."""
from models import Artist, ArtistAlias, CatalogEntry, CatalogArtist, DJSet, SetArtist


class TestListArtists:
    async def test_empty_returns_empty_list(self, client):
        r = await client.get("/api/artists/")
        assert r.status_code == 200
        data = r.json()
        assert data["items"] == []
        assert data["total"] == 0
        assert "pillarCounts" in data

    async def test_returns_artists(self, client, db):
        db.add(Artist(name="CamelPhat", normalized_name="camelphat"))
        await db.commit()
        r = await client.get("/api/artists/")
        data = r.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["name"] == "CamelPhat"
        assert data["total"] == 1

    async def test_search_filter(self, client, db):
        db.add(Artist(name="CamelPhat", normalized_name="camelphat"))
        db.add(Artist(name="ANNA", normalized_name="anna"))
        await db.commit()
        r = await client.get("/api/artists/?q=camel")
        data = r.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["name"] == "CamelPhat"

    async def test_no_deezer_filter(self, client, db):
        db.add(Artist(name="Known", normalized_name="known", deezer_id="123"))
        db.add(Artist(name="Unknown", normalized_name="unknown"))
        await db.commit()
        r = await client.get("/api/artists/?no_deezer=true")
        data = r.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["name"] == "Unknown"


class TestArtistDetail:
    async def test_returns_artist(self, client, db):
        a = Artist(name="CamelPhat", normalized_name="camelphat")
        db.add(a)
        await db.commit()
        await db.refresh(a)
        r = await client.get(f"/api/artists/{a.id}")
        assert r.status_code == 200
        data = r.json()
        assert data["name"] == "CamelPhat"
        assert "aliases" in data
        assert "genres" in data
        assert "catalog_tracks" in data
        assert "sets" in data
        assert "stats" in data

    async def test_404_when_not_found(self, client):
        r = await client.get("/api/artists/9999")
        assert r.status_code == 404

    async def test_includes_catalog_tracks(self, client, db):
        a = Artist(name="CamelPhat", normalized_name="camelphat")
        cat = CatalogEntry(title="Cola", artist="CamelPhat", normalized_key="cola - camelphat")
        db.add_all([a, cat])
        await db.commit()
        await db.refresh(a)
        await db.refresh(cat)
        db.add(CatalogArtist(catalog_id=cat.id, artist_id=a.id, role="primary", position=0))
        await db.commit()
        r = await client.get(f"/api/artists/{a.id}")
        data = r.json()
        assert len(data["catalog_tracks"]) == 1
        assert data["catalog_tracks"][0]["title"] == "Cola"

    async def test_detail_includes_aliases(self, client, db):
        a = Artist(name="CamelPhat", normalized_name="camelphat")
        db.add(a)
        await db.commit()
        await db.refresh(a)
        db.add(ArtistAlias(artist_id=a.id, alias="Camel Phat", normalized_alias="camel phat"))
        await db.commit()

        r = await client.get(f"/api/artists/{a.id}")
        data = r.json()
        assert len(data["aliases"]) == 1
        assert data["aliases"][0]["alias"] == "Camel Phat"

    async def test_detail_includes_sets(self, client, db):
        a = Artist(name="CamelPhat", normalized_name="camelphat")
        s = DJSet(title="Live at Fabric", source="trackid")
        db.add_all([a, s])
        await db.commit()
        await db.refresh(a)
        await db.refresh(s)
        db.add(SetArtist(set_id=s.id, artist_id=a.id, role="headliner"))
        await db.commit()

        r = await client.get(f"/api/artists/{a.id}")
        data = r.json()
        assert len(data["sets"]) == 1
        assert data["sets"][0]["title"] == "Live at Fabric"
        assert data["sets"][0]["role"] == "headliner"

    async def test_detail_stats(self, client, db):
        a = Artist(name="CamelPhat", normalized_name="camelphat")
        cat = CatalogEntry(title="Cola", artist="CamelPhat", normalized_key="cola - camelphat")
        db.add_all([a, cat])
        await db.commit()
        await db.refresh(a)
        await db.refresh(cat)
        db.add(CatalogArtist(catalog_id=cat.id, artist_id=a.id, role="primary", position=0))
        await db.commit()

        r = await client.get(f"/api/artists/{a.id}")
        data = r.json()
        assert "stats" in data
        assert data["stats"]["nb_catalog"] == 1
        assert data["stats"]["nb_lib"] == 0

    async def test_detail_alias_resolves_catalog_tracks(self, client, db):
        """Tracks linked via catalog_artists show up regardless of alias naming."""
        a = Artist(name="CamelPhat", normalized_name="camelphat")
        db.add(a)
        await db.commit()
        await db.refresh(a)
        db.add(ArtistAlias(artist_id=a.id, alias="Camel Phat", normalized_alias="camel phat"))
        cat = CatalogEntry(title="Track", artist="Camel Phat", normalized_key="track - camel phat")
        db.add(cat)
        await db.commit()
        await db.refresh(cat)
        db.add(CatalogArtist(catalog_id=cat.id, artist_id=a.id, role="primary", position=0))
        await db.commit()

        r = await client.get(f"/api/artists/{a.id}")
        data = r.json()
        assert data["stats"]["nb_catalog"] >= 1


class TestListArtistsPagination:
    async def test_pagination(self, client, db):
        for i in range(5):
            db.add(Artist(name=f"Artist {i}", normalized_name=f"artist{i}"))
        await db.commit()

        r = await client.get("/api/artists/?limit=2")
        data = r.json()
        assert len(data["items"]) == 2
        assert data["total"] == 5

    async def test_pagination_offset(self, client, db):
        for i in range(5):
            db.add(Artist(name=f"Artist {i}", normalized_name=f"artist{i}"))
        await db.commit()

        r = await client.get("/api/artists/?offset=3&limit=10")
        data = r.json()
        assert len(data["items"]) == 2

    async def test_ids_filter(self, client, db):
        a1 = Artist(name="A", normalized_name="a")
        a2 = Artist(name="B", normalized_name="b")
        a3 = Artist(name="C", normalized_name="c")
        db.add_all([a1, a2, a3])
        await db.commit()
        await db.refresh(a1)
        await db.refresh(a2)

        r = await client.get(f"/api/artists/?ids={a1.id},{a2.id}")
        data = r.json()
        assert data["total"] == 2

    async def test_sort_alpha(self, client, db):
        db.add(Artist(name="Zebra", normalized_name="zebra"))
        db.add(Artist(name="Alpha", normalized_name="alpha"))
        await db.commit()

        r = await client.get("/api/artists/?sort=alpha")
        data = r.json()
        assert data["items"][0]["name"] == "Alpha"
        assert data["items"][1]["name"] == "Zebra"
