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


class TestLinkToDeezer:
    @staticmethod
    def _stub_requests(monkeypatch, name="Canonical"):
        """Avoid the real Deezer call (returns a name, no picture)."""
        import requests

        class _Resp:
            def json(self):
                return {"name": name}

        monkeypatch.setattr(requests, "get", lambda *a, **k: _Resp())

    async def _catalog_entry(self, db, key):
        from datetime import datetime, timezone

        from models import CatalogEntry

        entry = CatalogEntry(
            title=f"Track {key}",
            artist="X",
            normalized_key=key,
            created_at=datetime.now(timezone.utc),
        )
        db.add(entry)
        await db.flush()
        return entry

    async def test_merge_reassigns_catalog_links(self, db, monkeypatch):
        """Regression: merging into a canonical artist must move catalog_artists
        instead of orphaning them — leaving the row behind made the ORM try to
        NULL the PK column artist_id → AssertionError → HTTP 500."""
        from models import Artist, CatalogArtist
        from sqlalchemy import select

        self._stub_requests(monkeypatch)

        dup = Artist(name="Dup Name", normalized_name="dup name")
        canonical = Artist(
            name="Canonical", normalized_name="canonical", deezer_id="777"
        )
        db.add_all([dup, canonical])
        await db.flush()

        entry = await self._catalog_entry(db, "dup|track")
        db.add(CatalogArtist(catalog_id=entry.id, artist_id=dup.id, role="main"))
        await db.commit()
        dup_id = dup.id

        result = await artist_service.link_to_deezer(db, dup_id, "777")

        assert result["merged"] is True
        assert result["id"] == canonical.id
        # The old artist is gone (no crash), the catalog link now points to canonical.
        assert (await db.get(Artist, dup_id)) is None
        links = (
            await db.execute(
                select(CatalogArtist).where(CatalogArtist.catalog_id == entry.id)
            )
        ).scalars().all()
        assert len(links) == 1
        assert links[0].artist_id == canonical.id

    async def test_merge_dedups_shared_catalog_link(self, db, monkeypatch):
        """When both artists already link the same track, the duplicate is
        dropped (composite PK) and a single link to canonical remains."""
        from models import Artist, CatalogArtist
        from sqlalchemy import select

        self._stub_requests(monkeypatch)

        dup = Artist(name="Dup2", normalized_name="dup2")
        canonical = Artist(name="Canon2", normalized_name="canon2", deezer_id="888")
        db.add_all([dup, canonical])
        await db.flush()

        entry = await self._catalog_entry(db, "shared|track")
        db.add_all([
            CatalogArtist(catalog_id=entry.id, artist_id=dup.id, role="main"),
            CatalogArtist(catalog_id=entry.id, artist_id=canonical.id, role="main"),
        ])
        await db.commit()
        dup_id = dup.id

        result = await artist_service.link_to_deezer(db, dup_id, "888")

        assert result["merged"] is True
        assert (await db.get(Artist, dup_id)) is None
        links = (
            await db.execute(
                select(CatalogArtist).where(CatalogArtist.catalog_id == entry.id)
            )
        ).scalars().all()
        assert len(links) == 1
        assert links[0].artist_id == canonical.id

    async def test_merge_survives_preloaded_catalog_links(self, db, monkeypatch):
        """Regression: even when the artist's catalog_links collection is already
        loaded in the session, deleting the merged artist must not try to NULL the
        composite-PK artist_id. passive_deletes=True on the relationship makes the
        ORM defer to the DB ON DELETE CASCADE instead of blanking the PK (500)."""
        from models import Artist, CatalogArtist
        from sqlalchemy import select

        self._stub_requests(monkeypatch)

        dup = Artist(name="DupPre", normalized_name="duppre")
        canonical = Artist(name="CanonPre", normalized_name="canonpre", deezer_id="999")
        db.add_all([dup, canonical])
        await db.flush()

        entry = await self._catalog_entry(db, "pre|track")
        db.add(CatalogArtist(catalog_id=entry.id, artist_id=dup.id, role="main"))
        await db.commit()
        dup_id = dup.id

        # Force the relationship into the session identity map BEFORE the merge —
        # this is what the bulk-reassign guard alone does not neutralize.
        preloaded = (
            await db.execute(select(Artist).where(Artist.id == dup_id))
        ).scalar_one()
        await db.refresh(preloaded, ["catalog_links"])
        assert len(preloaded.catalog_links) == 1

        result = await artist_service.link_to_deezer(db, dup_id, "999")

        assert result["merged"] is True
        assert (await db.get(Artist, dup_id)) is None
        links = (
            await db.execute(
                select(CatalogArtist).where(CatalogArtist.catalog_id == entry.id)
            )
        ).scalars().all()
        assert len(links) == 1
        assert links[0].artist_id == canonical.id


class TestResolveFlag:
    async def test_raises_lookup_error_for_missing_flag(self, db):
        with pytest.raises(LookupError):
            await artist_service.resolve_flag(db, 9999999, "approve")


class TestResolveFlagSplitDisposal:
    """N2.a — on a manual split the combined row must be disposed of and its
    catalog links fanned out to both tokens."""

    @staticmethod
    async def _catalog_entry(db, artist, key):
        from datetime import datetime, timezone

        from models import CatalogEntry

        entry = CatalogEntry(
            title=f"Track {key}",
            artist=artist,
            normalized_key=key,
            created_at=datetime.now(timezone.utc),
        )
        db.add(entry)
        await db.flush()
        return entry

    @staticmethod
    def _flag(raw, tokens):
        from datetime import datetime, timezone

        from models import ArtistFlag

        now = datetime.now(timezone.utc)
        return ArtistFlag(
            raw_artist_string=raw,
            reason="manual",
            tokens=tokens,
            deezer_ids={},
            status="pending",
            created_at=now,
            updated_at=now,
        )

    async def test_disposes_combined_and_links_both_tokens(self, db):
        from models import Artist, CatalogArtist
        from sqlalchemy import select
        from utils import normalize

        combined = Artist(name="A | B", normalized_name=normalize("A | B"))
        db.add(combined)
        await db.flush()
        entry = await self._catalog_entry(db, "A | B", "a | b|track")
        db.add(
            CatalogArtist(
                catalog_id=entry.id, artist_id=combined.id, role="primary", position=0
            )
        )
        flag = self._flag("A | B", ["A", "B"])
        db.add(flag)
        await db.commit()
        combined_id, entry_id = combined.id, entry.id

        result = await artist_service.resolve_flag(db, flag.id, "split")

        assert result.status == "validated"
        assert len(result.resolved_artist_ids) == 2
        # Combined row is gone — no 500, no PK blank-out.
        assert (await db.get(Artist, combined_id)) is None
        # Both tokens now link the catalog row.
        linked = set(
            (
                await db.execute(
                    select(CatalogArtist.artist_id).where(
                        CatalogArtist.catalog_id == entry_id
                    )
                )
            ).scalars().all()
        )
        assert set(result.resolved_artist_ids).issubset(linked)

    async def test_fanout_covers_nonexact_rows_preserving_role_position(self, db):
        """The fan-out is driven by the combined row's REAL links, so it reaches
        catalog rows whose `artist` string differs (casing) from the flag —
        which the exact-string relink cannot — and preserves role/position."""
        from models import Artist, CatalogArtist
        from sqlalchemy import select
        from utils import normalize

        combined = Artist(name="A | B", normalized_name=normalize("A | B"))
        db.add(combined)
        await db.flush()
        # entry.artist ("a | b") != flag.raw_artist_string ("A | B") on casing.
        entry = await self._catalog_entry(db, "a | b", "nonexact|track")
        db.add(
            CatalogArtist(
                catalog_id=entry.id,
                artist_id=combined.id,
                role="featured",
                position=3,
            )
        )
        flag = self._flag("A | B", ["A", "B"])
        db.add(flag)
        await db.commit()
        entry_id = entry.id

        result = await artist_service.resolve_flag(db, flag.id, "split")

        rows = (
            await db.execute(
                select(
                    CatalogArtist.artist_id,
                    CatalogArtist.role,
                    CatalogArtist.position,
                ).where(
                    CatalogArtist.catalog_id == entry_id,
                    CatalogArtist.artist_id.in_(result.resolved_artist_ids),
                )
            )
        ).all()
        assert len(rows) == 2
        for _aid, role, position in rows:
            assert role == "featured"
            assert position == 3

    async def test_guard_keeps_combined_when_it_is_a_created_token(self, db):
        """If a split token resolves back to the combined row itself, the guard
        must NOT delete it (id ∈ resolved_artist_ids)."""
        from models import Artist
        from utils import normalize

        combined = Artist(name="Solo Duo", normalized_name=normalize("Solo Duo"))
        db.add(combined)
        await db.flush()
        # Degenerate split: the only token normalizes back to the combined row.
        flag = self._flag("Solo Duo", ["Solo Duo"])
        db.add(flag)
        await db.commit()
        combined_id = combined.id

        result = await artist_service.resolve_flag(db, flag.id, "split")

        assert combined_id in result.resolved_artist_ids
        assert (await db.get(Artist, combined_id)) is not None

    async def test_split_without_combined_row_is_noop(self, db):
        """No combined Artist row exists → nothing to dispose of, no crash."""
        from models import Artist
        from sqlalchemy import select

        flag = self._flag("Ghost | Phantom", ["Ghost", "Phantom"])
        db.add(flag)
        await db.commit()

        result = await artist_service.resolve_flag(db, flag.id, "split")

        assert result.status == "validated"
        assert len(result.resolved_artist_ids) == 2
        names = set(
            (await db.execute(select(Artist.name))).scalars().all()
        )
        assert {"Ghost", "Phantom"}.issubset(names)
