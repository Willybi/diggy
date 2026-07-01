"""Tests for services/artist_service.py."""
import pytest

from services import artist_service


class TestListArtists:
    async def test_returns_dict_with_expected_keys(self, db, auth_user):
        result = await artist_service.list_artists(
            db, auth_user.id, sort="name", family=None, q=None,
            no_deezer=False, ids=None, limit=20, offset=0
        )
        assert isinstance(result, dict)
        assert "items" in result
        assert "total" in result
        assert "pillarCounts" in result

    async def test_returns_empty_when_no_artists(self, db, auth_user):
        result = await artist_service.list_artists(
            db, auth_user.id, sort="name", family=None, q=None,
            no_deezer=False, ids=None, limit=20, offset=0
        )
        assert result["total"] == 0
        assert result["items"] == []

    async def test_filters_by_query(self, db, auth_user):
        from models import Artist
        a = Artist(name="Aphex Twin", normalized_name="aphex twin", deezer_id="99")
        db.add(a)
        await db.commit()

        result = await artist_service.list_artists(
            db, auth_user.id, sort="name", family=None, q="aphex",
            no_deezer=False, ids=None, limit=20, offset=0
        )
        assert result["total"] == 1
        assert result["items"][0]["name"] == "Aphex Twin"

    async def test_no_deezer_filter(self, db, auth_user):
        from models import Artist
        a1 = Artist(name="WithDeezer", normalized_name="withdeezer", deezer_id="1")
        a2 = Artist(name="NoDeezer", normalized_name="nodeezer")
        db.add_all([a1, a2])
        await db.commit()

        result = await artist_service.list_artists(
            db, auth_user.id, sort="name", family=None, q=None,
            no_deezer=True, ids=None, limit=20, offset=0
        )
        names = [a["name"] for a in result["items"]]
        assert "NoDeezer" in names
        assert "WithDeezer" not in names


class TestGetDetail:
    async def test_raises_lookup_error_for_missing_artist(self, db):
        with pytest.raises(LookupError, match="not found"):
            await artist_service.get_detail(db, 9999999)

    async def test_returns_dict_for_valid_artist(self, db):
        from models import Artist
        a = Artist(name="Test Artist", normalized_name="test artist")
        db.add(a)
        await db.commit()
        await db.refresh(a)

        result = await artist_service.get_detail(db, a.id)
        assert result.name == "Test Artist"


class TestResolveFlag:
    async def test_raises_lookup_error_for_missing_flag(self, db):
        with pytest.raises(LookupError):
            await artist_service.resolve_flag(db, 9999999, "approve")
