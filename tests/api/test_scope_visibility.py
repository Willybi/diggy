"""Isolation tests for private-scope catalog visibility (L1).

A ``private`` catalog row (imported from a user's Rekordbox library) must be
visible only to its owner: never to guests, never to other authenticated users.
``shared`` rows stay visible to everyone.
"""
import pytest
from models import CatalogEntry, User, UserTrack
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


async def _mk_user_track(db, user_id, catalog_id) -> UserTrack:
    ut = UserTrack(user_id=user_id, catalog_id=catalog_id, source="rekordbox_import")
    db.add(ut)
    await db.commit()
    return ut


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


class TestUserTrackVisibility:
    """A viewer sees a private row they hold a ``user_track`` for, even when they
    are neither its owner nor is it shared (Rekordbox import collision, C3.b L1).
    Guests and third parties without a user_track stay blind to it."""

    async def test_user_track_holder_sees_foreign_private(self, db):
        owner = await _mk_user(db, "owner@test.com")
        holder = await _mk_user(db, "holder@test.com")
        third = await _mk_user(db, "third@test.com")
        priv = await _mk_entry(db, "Held Private", "X", scope="private", owner_id=owner.id)
        await _mk_user_track(db, holder.id, priv.id)

        # Owner sees it (owner_id); the user_track holder sees it (user_track clause).
        assert "Held Private" in await _list_titles(db, owner.id)
        assert "Held Private" in await _list_titles(db, holder.id)
        # A guest and a third user (neither owner nor user_track holder) do not.
        assert "Held Private" not in await _list_titles(db, None)
        assert "Held Private" not in await _list_titles(db, third.id)

    async def test_owner_still_sees_own_private_without_user_track(self, db):
        # The user_track clause is additive: an owner with no user_track still sees
        # their private row via owner_id — no regression on the owner path.
        owner = await _mk_user(db, "owner@test.com")
        await _mk_entry(db, "Owned No UT", "Y", scope="private", owner_id=owner.id)
        assert "Owned No UT" in await _list_titles(db, owner.id)
        assert "Owned No UT" not in await _list_titles(db, None)


class TestCatalogVisibleSqlTwin:
    """Lock the raw-SQL twin ``catalog_visible_sql`` against the ORM twin: its 6
    call sites are Postgres-only (unnest/LATERAL/ARRAY_AGG) and never run on the
    SQLite harness, so a silent divergence (dropped EXISTS, mistyped ``utv``
    columns, broken OR grouping, or a guest-branch leak) would otherwise pass the
    whole suite green. These dialect-free string assertions catch that."""

    def test_auth_fragment_carries_user_track_exists(self):
        frag = catalog_service.catalog_visible_sql(7)
        assert "c.scope = 'shared'" in frag
        assert "c.owner_id = :viewer_id" in frag
        assert "EXISTS (SELECT 1 FROM user_tracks utv" in frag
        assert "utv.catalog_id = c.id" in frag
        assert "utv.user_id = :viewer_id" in frag

    def test_auth_fragment_honours_alias(self):
        frag = catalog_service.catalog_visible_sql(7, alias="catalog")
        assert "catalog.scope = 'shared'" in frag
        assert "catalog.owner_id = :viewer_id" in frag
        assert "utv.catalog_id = catalog.id" in frag

    def test_guest_fragment_is_shared_only(self):
        # A guest holds no user_track, so the guest branch must never gain the
        # clause nor reference :viewer_id.
        frag = catalog_service.catalog_visible_sql(None)
        assert frag == "c.scope = 'shared'"
        assert "user_tracks" not in frag
        assert ":viewer_id" not in frag
