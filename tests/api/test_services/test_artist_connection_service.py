"""Tests for services/artist_connection_service.py."""

import pytest

from services.artist_connection_service import CFG, score_segment


# ---------------------------------------------------------------------------
# score_segment (pure)
# ---------------------------------------------------------------------------


class TestScoreSegment:
    def test_zero(self):
        assert score_segment(0, 2.0, 3.0) == 0.0

    def test_one_collab(self):
        # k=1.5, n=1, cap=3 -> 3*(1-e^-1.5) ~ 2.330
        s = score_segment(1, CFG.K_COLLABS, CFG.CAP_COLLABS)
        assert abs(s - 2.330) < 0.01

    def test_one_set(self):
        # k=2.0, n=1, cap=2 -> 2*(1-e^-2) ~ 1.729
        s = score_segment(1, CFG.K_SETS, CFG.CAP_SETS)
        assert abs(s - 1.729) < 0.01

    def test_one_playlist(self):
        # k=0.5, n=1, cap=2 -> 2*(1-e^-0.5) ~ 0.787
        s = score_segment(1, CFG.K_PLAYLISTS, CFG.CAP_PLAYLISTS)
        assert abs(s - 0.787) < 0.01

    def test_approaches_cap(self):
        assert score_segment(10, 2.0, 3.0) > 2.99

    def test_monotone(self):
        assert score_segment(2, 1.5, 3.0) > score_segment(1, 1.5, 3.0)

    def test_negative_n(self):
        assert score_segment(-1, 2.0, 3.0) == 0.0


# ---------------------------------------------------------------------------
# Integration: get_connections
# ---------------------------------------------------------------------------


class TestGetConnections:
    async def test_raises_for_missing_artist(self, db):
        from services import artist_connection_service

        with pytest.raises(LookupError):
            await artist_connection_service.get_connections(db, 999999)

    async def test_empty_for_isolated_artist(self, db):
        from models import Artist
        from services import artist_connection_service

        a = Artist(name="Lonely", normalized_name="lonely")
        db.add(a)
        await db.commit()
        await db.refresh(a)
        a_id = a.id

        result = await artist_connection_service.get_connections(db, a_id)
        assert result == []

    async def test_collab_detected(self, db):
        from models import Artist, CatalogArtist, CatalogEntry
        from services import artist_connection_service

        a1 = Artist(name="Artist A", normalized_name="artist-a")
        a2 = Artist(name="Artist B", normalized_name="artist-b")
        track = CatalogEntry(
            title="Collab Track", artist="A & B", normalized_key="a|collab",
        )
        db.add_all([a1, a2, track])
        await db.commit()
        await db.refresh(a1)
        await db.refresh(a2)
        await db.refresh(track)

        a1_id, a2_id = a1.id, a2.id
        db.add(CatalogArtist(catalog_id=track.id, artist_id=a1_id, position=1))
        db.add(CatalogArtist(catalog_id=track.id, artist_id=a2_id, position=2))
        await db.commit()

        result = await artist_connection_service.get_connections(db, a1_id)
        assert len(result) == 1
        assert result[0]["artist_id"] == a2_id
        assert result[0]["shared_tracks"] == 1
        assert result[0]["components"]["collabs"] > 0

    async def test_set_detected(self, db):
        from models import Artist, DJSet, SetArtist
        from services import artist_connection_service

        a1 = Artist(name="DJ A", normalized_name="dj-a")
        a2 = Artist(name="DJ B", normalized_name="dj-b")
        dj_set = DJSet(source="trackid", title="B2B Set", external_id="set-conn-test")
        db.add_all([a1, a2, dj_set])
        await db.commit()
        await db.refresh(a1)
        await db.refresh(a2)
        await db.refresh(dj_set)

        a1_id, a2_id = a1.id, a2.id
        db.add(SetArtist(set_id=dj_set.id, artist_id=a1_id, position=1))
        db.add(SetArtist(set_id=dj_set.id, artist_id=a2_id, position=2))
        await db.commit()

        result = await artist_connection_service.get_connections(db, a1_id)
        assert len(result) == 1
        assert result[0]["artist_id"] == a2_id
        assert result[0]["shared_sets"] == 1
        assert result[0]["components"]["sets"] > 0

    async def test_limit_respected(self, db):
        from models import Artist, CatalogArtist, CatalogEntry
        from services import artist_connection_service

        ref = Artist(name="Ref", normalized_name="ref-conn-lim")
        db.add(ref)
        await db.commit()
        await db.refresh(ref)
        ref_id = ref.id

        for i in range(5):
            other = Artist(name=f"Other{i}", normalized_name=f"other-conn-{i}")
            track = CatalogEntry(
                title=f"Track{i}", artist=f"Ref & Other{i}",
                normalized_key=f"ref|track-conn-{i}",
            )
            db.add_all([other, track])
            await db.commit()
            await db.refresh(other)
            await db.refresh(track)
            db.add(CatalogArtist(catalog_id=track.id, artist_id=ref_id, position=1))
            db.add(CatalogArtist(catalog_id=track.id, artist_id=other.id, position=2))
            await db.commit()

        result = await artist_connection_service.get_connections(db, ref_id, limit=2)
        assert len(result) == 2

    async def test_response_shape(self, db):
        from models import Artist, CatalogArtist, CatalogEntry
        from services import artist_connection_service

        a1 = Artist(name="Shape A", normalized_name="shape-a")
        a2 = Artist(name="Shape B", normalized_name="shape-b", has_artwork=True)
        track = CatalogEntry(
            title="Shape Track", artist="A & B", normalized_key="a|shape",
        )
        db.add_all([a1, a2, track])
        await db.commit()
        await db.refresh(a1)
        await db.refresh(a2)
        await db.refresh(track)

        a1_id = a1.id
        db.add(CatalogArtist(catalog_id=track.id, artist_id=a1.id, position=1))
        db.add(CatalogArtist(catalog_id=track.id, artist_id=a2.id, position=2))
        await db.commit()

        result = await artist_connection_service.get_connections(db, a1_id)
        assert len(result) == 1
        conn = result[0]
        assert "artist_id" in conn
        assert "name" in conn
        assert "has_artwork" in conn
        assert "score" in conn
        assert "components" in conn
        assert "shared_tracks" in conn
        assert "shared_sets" in conn
        assert "shared_playlists" in conn
        assert conn["has_artwork"] is True
        assert 0 < conn["score"] <= 1
