"""Reversible masking (``hidden_reason``) — read-side exclusion (lot L1).

A masked catalog row disappears for every reader EXCEPT a viewer holding it in
their library (``user_track``) and the owner of a private row. A masked artist
is excluded from the artist listing and the artist search (items + totals).
"""
from datetime import datetime, timezone

from models import Artist, CatalogEntry, User, UserTrack
from services import artist_service, search_service
from services.catalog_service import catalog_visible, catalog_visible_sql
from sqlalchemy import select, text


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


async def _mk_entry(db, title, hidden=None, scope="shared", owner_id=None):
    c = CatalogEntry(
        title=title,
        artist="A",
        normalized_key=f"a|{title}".lower(),
        scope=scope,
        owner_id=owner_id,
        hidden_reason=hidden,
        hidden_at=datetime.now(timezone.utc) if hidden else None,
    )
    db.add(c)
    await db.commit()
    await db.refresh(c)
    return c


async def _seed(db):
    """Shared visible + shared hidden (in `holder`'s library) + private hidden."""
    holder = await _mk_user(db, "holder@test.com")
    other = await _mk_user(db, "other@test.com")
    owner = await _mk_user(db, "owner@test.com")
    await _mk_entry(db, "Visible")
    hidden = await _mk_entry(db, "Hidden", hidden="farm_fort")
    await _mk_entry(
        db, "Private Hidden", hidden="farm_fort", scope="private", owner_id=owner.id
    )
    db.add(UserTrack(user_id=holder.id, catalog_id=hidden.id, source="rekordbox_import"))
    await db.commit()
    return holder, other, owner


async def _orm_titles(db, user_id):
    rows = await db.execute(select(CatalogEntry.title).where(catalog_visible(user_id)))
    return {r[0] for r in rows.all()}


async def _sql_titles(db, user_id):
    rows = await db.execute(
        text(f"SELECT c.title FROM catalog c WHERE {catalog_visible_sql(user_id)}"),
        {"viewer_id": user_id} if user_id is not None else {},
    )
    return {r[0] for r in rows.all()}


class TestCatalogVisibleOrm:
    async def test_guest_does_not_see_hidden(self, db):
        await _seed(db)
        assert await _orm_titles(db, None) == {"Visible"}

    async def test_authenticated_user_does_not_see_hidden(self, db):
        _, other, _ = await _seed(db)
        assert await _orm_titles(db, other.id) == {"Visible"}

    async def test_library_holder_sees_hidden(self, db):
        holder, _, _ = await _seed(db)
        assert await _orm_titles(db, holder.id) == {"Visible", "Hidden"}

    async def test_owner_sees_own_private_even_hidden(self, db):
        _, _, owner = await _seed(db)
        assert await _orm_titles(db, owner.id) == {"Visible", "Private Hidden"}


class TestCatalogVisibleSql:
    async def test_guest_does_not_see_hidden(self, db):
        await _seed(db)
        assert await _sql_titles(db, None) == {"Visible"}

    async def test_authenticated_user_does_not_see_hidden(self, db):
        _, other, _ = await _seed(db)
        assert await _sql_titles(db, other.id) == {"Visible"}

    async def test_library_holder_sees_hidden(self, db):
        holder, _, _ = await _seed(db)
        assert await _sql_titles(db, holder.id) == {"Visible", "Hidden"}

    async def test_owner_sees_own_private_even_hidden(self, db):
        _, _, owner = await _seed(db)
        assert await _sql_titles(db, owner.id) == {"Visible", "Private Hidden"}

    async def test_custom_alias(self, db):
        await _seed(db)
        rows = await db.execute(
            text(
                "SELECT title FROM catalog WHERE "
                f"{catalog_visible_sql(None, alias='catalog')}"
            )
        )
        assert {r[0] for r in rows.all()} == {"Visible"}


class TestExplorerEndpoint:
    async def test_catalog_list_hides_masked_track(self, client, db):
        await _mk_entry(db, "Visible")
        await _mk_entry(db, "Hidden", hidden="isrc_block")
        r = await client.get("/api/catalog/")
        assert r.status_code == 200
        body = r.json()
        assert {i["title"] for i in body["items"]} == {"Visible"}
        assert body["total"] == 1


async def _seed_artists(db):
    db.add(Artist(name="Real Artist", normalized_name="real artist"))
    db.add(
        Artist(
            name="Fake Artist",
            normalized_name="fake artist",
            hidden_reason="farm_fort",
            hidden_at=datetime.now(timezone.utc),
        )
    )
    await db.commit()


class TestArtistMasking:
    async def test_list_artists_excludes_hidden(self, db):
        await _seed_artists(db)
        result = await artist_service.list_artists(
            db, None, sort="name", family=None, q=None, no_deezer=False,
            ids=None, limit=50, offset=0,
        )
        assert {i["name"] for i in result["items"]} == {"Real Artist"}
        assert result["total"] == 1
        assert sum(result["pillarCounts"].values()) == 1

    async def test_list_artists_query_excludes_hidden(self, db):
        await _seed_artists(db)
        result = await artist_service.list_artists(
            db, None, sort="name", family=None, q="artist", no_deezer=False,
            ids=None, limit=50, offset=0,
        )
        assert {i["name"] for i in result["items"]} == {"Real Artist"}
        assert result["total"] == 1

    async def test_search_artists_excludes_hidden(self, db):
        await _seed_artists(db)
        items, total = await search_service._search_artists(
            db, "artist", user_id=None, is_guest=True, limit=20
        )
        assert {i.name for i in items} == {"Real Artist"}
        assert total == 1

    async def test_get_detail_still_reachable_by_id(self, db):
        await _seed_artists(db)
        fake = (
            await db.execute(select(Artist).where(Artist.name == "Fake Artist"))
        ).scalar_one()
        detail = await artist_service.get_detail(db, fake.id, None)
        assert detail is not None

    async def test_no_deezer_counters_exclude_hidden(self, db):
        from models import CatalogArtist

        await _seed_artists(db)
        track = await _mk_entry(db, "Linked")
        for a in (await db.execute(select(Artist))).scalars().all():
            db.add(CatalogArtist(catalog_id=track.id, artist_id=a.id))
        await db.commit()
        result = await artist_service.list_artists(
            db, None, sort="name", family=None, q=None, no_deezer=True,
            ids=None, limit=50, offset=0,
        )
        assert {i["name"] for i in result["items"]} == {"Real Artist"}
        assert result["active_count"] == 1


async def _list(db, user_id, sort="name"):
    return await artist_service.list_artists(
        db, user_id, sort=sort, family=None, q=None, no_deezer=False,
        ids=None, limit=50, offset=0,
    )


async def _mk_artist_with_tracks(db, name, visible, hidden, start=0):
    """Artist linked to ``visible`` shared tracks + ``hidden`` masked ones.

    Returns plain ids (artist id, entry ids) — the ORM objects are expired by
    the commits and lazy-loading them outside the greenlet would fail.
    """
    from models import CatalogArtist

    a = Artist(name=name, normalized_name=name.lower())
    db.add(a)
    await db.commit()
    await db.refresh(a)
    entries = []
    for i in range(visible + hidden):
        e = CatalogEntry(
            title=f"{name} T{i}",
            artist=name,
            normalized_key=f"{name}|t{i}".lower(),
            scope="shared",
            hidden_reason="farm_fort" if i >= visible else None,
            hidden_at=datetime.now(timezone.utc) if i >= visible else None,
        )
        db.add(e)
        entries.append(e)
    await db.commit()
    artist_id = a.id
    entry_ids = [e.id for e in entries]
    for eid in entry_ids:
        db.add(CatalogArtist(catalog_id=eid, artist_id=artist_id))
    await db.commit()
    return artist_id, entry_ids


class TestArtistListCountsVisibleOnly:
    async def test_nb_catalog_excludes_masked_guest_and_auth(self, db):
        user = await _mk_user(db, "viewer@test.com")
        await _mk_artist_with_tracks(db, "Farm", visible=2, hidden=5)
        for uid in (None, user.id):
            items = (await _list(db, uid))["items"]
            assert items[0]["nb_catalog"] == 2

    async def test_masked_library_track_counted_for_holder_only(self, db):
        holder = await _mk_user(db, "holder2@test.com")
        _, entries = await _mk_artist_with_tracks(db, "Farm", visible=1, hidden=2)
        db.add(
            UserTrack(
                user_id=holder.id, catalog_id=entries[-1], source="rekordbox_import"
            )
        )
        await db.commit()
        holder_item = (await _list(db, holder.id))["items"][0]
        assert holder_item["nb_catalog"] == 2
        assert holder_item["nb_lib"] == 1
        guest_item = (await _list(db, None))["items"][0]
        assert guest_item["nb_catalog"] == 1
        assert guest_item["nb_lib"] == 0

    async def test_fully_masked_artist_shows_zero_and_stays_listed(self, db):
        await _mk_artist_with_tracks(db, "Ghost", visible=0, hidden=3)
        items = (await _list(db, None))["items"]
        assert [(i["name"], i["nb_catalog"]) for i in items] == [("Ghost", 0)]

    async def test_sort_catalog_uses_visible_count(self, db):
        await _mk_artist_with_tracks(db, "Farm", visible=2, hidden=100)
        await _mk_artist_with_tracks(db, "Real", visible=5, hidden=0)
        items = (await _list(db, None, sort="catalog"))["items"]
        assert [i["name"] for i in items] == ["Real", "Farm"]

    async def test_list_and_detail_counts_match(self, db):
        holder = await _mk_user(db, "holder3@test.com")
        artist_id, entries = await _mk_artist_with_tracks(
            db, "Farm", visible=3, hidden=4
        )
        db.add(
            UserTrack(
                user_id=holder.id, catalog_id=entries[-1], source="rekordbox_import"
            )
        )
        await db.commit()
        for uid in (None, holder.id):
            listed = (await _list(db, uid))["items"][0]["nb_catalog"]
            detail = await artist_service.get_detail(db, artist_id, uid)
            assert listed == detail.stats["nb_catalog"]
