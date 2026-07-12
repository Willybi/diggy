"""Multi-user scope safety of the Rekordbox import (C3.b, Lot L1).

The import worker (``workers/tasks/import_rb.py``) runs on SYNC SQLAlchemy against
Postgres; this suite is ASYNC SQLite. Both share one dialect-agnostic decision,
``catalog_service.resolve_import_catalog_entry``, so the scope resolution is
exercised here without standing up a sync harness. ``_import_track`` mirrors the
worker's per-track binding (resolve → create-if-needed → bind user_track) using
the async ``db`` fixture.

Bug fixed: import deduped on ``normalized_key`` alone, so user B importing a track
that collided with user A's ``private`` row was bound to A's catalog row — which
``catalog_visible`` hid from B, leaving a hole in B's library. ``normalized_key``
is globally UNIQUE, so a second private row is impossible AND A's row is never
mutated/promoted (that would leak it to guests and every other user). The fix is
at the read layer: ``catalog_visible`` also grants sight of any row the viewer
holds a ``user_track`` for, so B sees the track through their own ``user_track``
while it stays ``private``/owned by A — still invisible to guests and third parties.
"""
from types import SimpleNamespace

from models import CatalogEntry, User, UserTrack
from services import catalog_service
from sqlalchemy import func, select
from utils import make_normalized_key


# ── helpers ───────────────────────────────────────────────────────────────────

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


async def _catalog_count(db) -> int:
    return (await db.execute(select(func.count(CatalogEntry.id)))).scalar()


async def _import_track(db, user_id: int, title: str, artist: str) -> CatalogEntry:
    """Async mirror of import_rb.py phase 1+2 for a single track."""
    norm_key = make_normalized_key(title, artist)
    existing = (
        await db.execute(
            select(CatalogEntry).where(CatalogEntry.normalized_key == norm_key)
        )
    ).scalar_one_or_none()

    entry = catalog_service.resolve_import_catalog_entry(existing, user_id, title, artist)
    if entry is None:
        entry = CatalogEntry(
            title=title or "",
            artist=artist,
            normalized_key=norm_key,
            scope="private",
            owner_id=user_id,
            origin="rekordbox",
        )
        db.add(entry)
        await db.flush()

    await db.merge(UserTrack(user_id=user_id, catalog_id=entry.id, source="rekordbox_import"))
    await db.commit()
    await db.refresh(entry)
    return entry


async def _visible_titles(db, user_id) -> set[str]:
    """Titles a viewer may see, via the exact predicate every catalog read-path
    applies (``catalog_visible``). Queried directly rather than through
    ``list_catalog`` to keep the test off the genre/pillar machinery."""
    rows = await db.execute(
        select(CatalogEntry.title).where(catalog_service.catalog_visible(user_id))
    )
    return set(rows.scalars().all())


async def _user_track_count(db, catalog_id: int) -> int:
    return (
        await db.execute(
            select(func.count())
            .select_from(UserTrack)
            .where(UserTrack.catalog_id == catalog_id)
        )
    ).scalar()


# ── pure decision table (no DB) ───────────────────────────────────────────────

class TestResolveImportCatalogEntry:
    def test_no_match_returns_none(self):
        assert catalog_service.resolve_import_catalog_entry(None, 1, "t", "a") is None

    def test_shared_reused_unmutated(self):
        e = SimpleNamespace(scope="shared", owner_id=None, title="T", artist="A")
        out = catalog_service.resolve_import_catalog_entry(e, 1, "new", "new")
        assert out is e
        assert e.scope == "shared"
        assert e.title == "T"  # a shared canonical row is never mutated by an import

    def test_own_private_refreshed(self):
        e = SimpleNamespace(scope="private", owner_id=1, title="old", artist="a")
        out = catalog_service.resolve_import_catalog_entry(e, 1, "new", "b")
        assert out is e
        assert e.scope == "private"
        assert e.owner_id == 1
        assert (e.title, e.artist) == ("new", "b")

    def test_own_private_keeps_fields_when_incoming_blank(self):
        e = SimpleNamespace(scope="private", owner_id=1, title="keep", artist="a")
        catalog_service.resolve_import_catalog_entry(e, 1, "", None)
        assert (e.title, e.artist) == ("keep", "a")

    def test_foreign_private_returned_unmutated(self):
        e = SimpleNamespace(scope="private", owner_id=99, title="T", artist="A")
        out = catalog_service.resolve_import_catalog_entry(e, 1, "new", "new")
        assert out is e
        # Another user's private row is never mutated: not scope, owner, or fields.
        assert e.scope == "private"
        assert e.owner_id == 99
        assert (e.title, e.artist) == ("T", "A")


# ── integration through the async session ─────────────────────────────────────

class TestImportScopeIntegration:
    async def test_foreign_private_collision_stays_private_visible_via_user_track(self, db):
        a = await _mk_user(db, "a@test.com")
        b = await _mk_user(db, "b@test.com")
        c = await _mk_user(db, "c@test.com")  # third party: no user_track, not owner

        # A imports first → a private row owned by A, invisible to B.
        row_a = await _import_track(db, a.id, "strobe", "deadmau5")
        assert row_a.scope == "private"
        assert row_a.owner_id == a.id
        assert "strobe" not in await _visible_titles(db, b.id)
        before = await _catalog_count(db)

        # B imports the same track (same normalized_key).
        row_b = await _import_track(db, b.id, "strobe", "deadmau5")

        # No duplicate row (uniqueness forbids it): B is bound to A's row, which is
        # left completely untouched — still private, still owned by A (no promotion).
        assert row_b.id == row_a.id
        assert await _catalog_count(db) == before
        assert row_b.scope == "private"
        assert row_b.owner_id == a.id

        # The exact bug is fixed at the read layer: B now SEES the track through
        # their own user_track, and A sees it as owner. A guest and a third-party
        # user C — neither owner nor user_track holder — still do NOT.
        assert "strobe" in await _visible_titles(db, b.id)
        assert "strobe" in await _visible_titles(db, a.id)
        assert "strobe" not in await _visible_titles(db, None)
        assert "strobe" not in await _visible_titles(db, c.id)

        # Both A and B hold a user_track on the single private row.
        assert await _user_track_count(db, row_a.id) == 2

    async def test_shared_collision_reuses_without_duplicate(self, db):
        b = await _mk_user(db, "b@test.com")
        shared = CatalogEntry(
            title="Nightcall",
            artist="Kavinsky",
            normalized_key=make_normalized_key("Nightcall", "Kavinsky"),
            scope="shared",
            owner_id=None,
        )
        db.add(shared)
        await db.commit()
        await db.refresh(shared)
        before = await _catalog_count(db)

        row = await _import_track(db, b.id, "Nightcall", "Kavinsky")

        assert row.id == shared.id           # attached to the shared row
        assert await _catalog_count(db) == before  # no duplicate
        assert row.scope == "shared"
        assert row.owner_id is None
        assert "Nightcall" in await _visible_titles(db, b.id)

    async def test_own_private_collision_reuses_and_refreshes(self, db):
        a = await _mk_user(db, "a@test.com")
        # First import (lowercase) → private row owned by A.
        first = await _import_track(db, a.id, "strobe", "deadmau5")
        assert first.scope == "private"
        assert first.owner_id == a.id
        before = await _catalog_count(db)

        # Re-import with a cased title that normalizes to the same key.
        again = await _import_track(db, a.id, "Strobe", "deadmau5")

        assert again.id == first.id          # reused, no duplicate
        assert await _catalog_count(db) == before
        assert again.scope == "private"      # stays private
        assert again.owner_id == a.id        # owner unchanged (no promotion)
        assert again.title == "Strobe"       # title refreshed from the re-import

    async def test_mono_user_import_creates_private_owned(self, db):
        a = await _mk_user(db, "a@test.com")
        before = await _catalog_count(db)

        row = await _import_track(db, a.id, "Lone Track", "Solo")

        assert await _catalog_count(db) == before + 1
        assert row.scope == "private"
        assert row.owner_id == a.id

        # Owner sees it; guest and another user do not.
        assert "Lone Track" in await _visible_titles(db, a.id)
        assert "Lone Track" not in await _visible_titles(db, None)
        b = await _mk_user(db, "b@test.com")
        assert "Lone Track" not in await _visible_titles(db, b.id)
