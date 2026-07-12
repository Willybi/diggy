"""Isolation tests for private-scope catalog visibility (L1).

A ``private`` catalog row (imported from a user's Rekordbox library) must be
visible only to its owner: never to guests, never to other authenticated users.
``shared`` rows stay visible to everyone.
"""
import pytest
from models import CatalogEntry, User
from services import catalog_service, search_service


async def _mk_user(db, email: str) -> User:
    u = User(
        email=email,
        username=email.split("@")[0],
        google_id=f"g-{email}",
        is_active=True,
        is_admin=False,
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


async def _mk_entry(db, title, artist, scope="shared", owner_id=None) -> CatalogEntry:
    c = CatalogEntry(
        title=title,
        artist=artist,
        normalized_key=f"{artist}|{title}".lower(),
        scope=scope,
        owner_id=owner_id,
    )
    db.add(c)
    await db.commit()
    await db.refresh(c)
    return c


async def _list_titles(db, user_id):
    result = await catalog_service.list_catalog(
        db, user_id, skip=0, limit=50, in_lib=None,
        min_radar_playlists=None, search=None, genre=None,
        sort=None, order="desc", view=None, detected_after=None, avis=None,
    )
    return {item.title for item in result.items}


class TestListCatalogScope:
    async def test_guest_sees_only_shared(self, db):
        owner = await _mk_user(db, "owner@test.com")
        await _mk_entry(db, "Shared One", "A")
        await _mk_entry(db, "Private One", "B", scope="private", owner_id=owner.id)

        titles = await _list_titles(db, None)
        assert titles == {"Shared One"}

    async def test_other_user_does_not_see_foreign_private(self, db):
        owner = await _mk_user(db, "owner@test.com")
        other = await _mk_user(db, "other@test.com")
        await _mk_entry(db, "Shared One", "A")
        await _mk_entry(db, "Private One", "B", scope="private", owner_id=owner.id)

        titles = await _list_titles(db, other.id)
        assert titles == {"Shared One"}

    async def test_owner_sees_own_private_and_shared(self, db):
        owner = await _mk_user(db, "owner@test.com")
        await _mk_entry(db, "Shared One", "A")
        await _mk_entry(db, "Private One", "B", scope="private", owner_id=owner.id)

        titles = await _list_titles(db, owner.id)
        assert titles == {"Shared One", "Private One"}


class TestGetDetailScope:
    async def test_guest_gets_lookup_error_on_private(self, db):
        owner = await _mk_user(db, "owner@test.com")
        priv = await _mk_entry(db, "Private", "B", scope="private", owner_id=owner.id)
        with pytest.raises(LookupError):
            await catalog_service.get_detail(db, priv.id, None)

    async def test_other_user_gets_lookup_error_on_private(self, db):
        owner = await _mk_user(db, "owner@test.com")
        other = await _mk_user(db, "other@test.com")
        priv = await _mk_entry(db, "Private", "B", scope="private", owner_id=owner.id)
        with pytest.raises(LookupError):
            await catalog_service.get_detail(db, priv.id, other.id)

    async def test_owner_can_read_own_private(self, db):
        owner = await _mk_user(db, "owner@test.com")
        priv = await _mk_entry(db, "Private", "B", scope="private", owner_id=owner.id)
        detail = await catalog_service.get_detail(db, priv.id, owner.id)
        assert detail.title == "Private"

    async def test_shared_readable_by_guest(self, db):
        shared = await _mk_entry(db, "Shared", "A")
        detail = await catalog_service.get_detail(db, shared.id, None)
        assert detail.title == "Shared"


class TestPreviewUrlScope:
    async def test_guest_gets_lookup_error_on_private(self, db):
        owner = await _mk_user(db, "owner@test.com")
        priv = await _mk_entry(db, "Private", "B", scope="private", owner_id=owner.id)
        # The visibility guard runs before any Deezer call.
        with pytest.raises(LookupError):
            await catalog_service.get_preview_url(db, priv.id, None)

    async def test_other_user_gets_lookup_error_on_private(self, db):
        owner = await _mk_user(db, "owner@test.com")
        other = await _mk_user(db, "other@test.com")
        priv = await _mk_entry(db, "Private", "B", scope="private", owner_id=owner.id)
        with pytest.raises(LookupError):
            await catalog_service.get_preview_url(db, priv.id, other.id)


class TestSearchScope:
    async def _search_titles(self, db, user_id, is_guest):
        resp = await search_service.search(
            db, "Track", scope="track", limit=20, offset=0,
            user_id=user_id, is_guest=is_guest,
        )
        return {item.title for item in resp.items}

    async def test_guest_search_excludes_private(self, db):
        owner = await _mk_user(db, "owner@test.com")
        await _mk_entry(db, "Track Shared", "A")
        await _mk_entry(db, "Track Private", "B", scope="private", owner_id=owner.id)

        titles = await self._search_titles(db, None, is_guest=True)
        assert "Track Shared" in titles
        assert "Track Private" not in titles

    async def test_other_user_search_excludes_foreign_private(self, db):
        owner = await _mk_user(db, "owner@test.com")
        other = await _mk_user(db, "other@test.com")
        await _mk_entry(db, "Track Shared", "A")
        await _mk_entry(db, "Track Private", "B", scope="private", owner_id=owner.id)

        titles = await self._search_titles(db, other.id, is_guest=False)
        assert "Track Shared" in titles
        assert "Track Private" not in titles

    async def test_owner_search_includes_own_private(self, db):
        owner = await _mk_user(db, "owner@test.com")
        await _mk_entry(db, "Track Shared", "A")
        await _mk_entry(db, "Track Private", "B", scope="private", owner_id=owner.id)

        titles = await self._search_titles(db, owner.id, is_guest=False)
        assert "Track Shared" in titles
        assert "Track Private" in titles
