"""Tests for services/catalog_service.py."""
import pytest

from services import catalog_service


class TestListCatalog:
    async def test_returns_catalog_list(self, db, auth_user):
        result = await catalog_service.list_catalog(
            db, auth_user.id, skip=0, limit=20, in_lib=None,
            search=None, genre=None, sort=None, order="desc", avis=None,
        )
        assert hasattr(result, "total")
        assert hasattr(result, "items")
        assert result.total == 0

    async def test_search_returns_matching_entry(self, db, auth_user):
        from models import CatalogEntry
        c = CatalogEntry(title="Windowlicker", artist="Aphex Twin", normalized_key="aphex twin|windowlicker")
        db.add(c)
        await db.commit()

        result = await catalog_service.list_catalog(
            db, auth_user.id, skip=0, limit=20, in_lib=None,
            search="Windowlicker", genre=None, sort=None, order="desc", avis=None,
        )
        assert result.total == 1
        assert result.items[0].title == "Windowlicker"

    async def test_limit_applied(self, db, auth_user):
        from models import CatalogEntry
        for i in range(5):
            db.add(CatalogEntry(title=f"Track {i}", artist="Artist", normalized_key=f"artist|track{i}"))
        await db.commit()

        result = await catalog_service.list_catalog(
            db, auth_user.id, skip=0, limit=2, in_lib=None,
            search=None, genre=None, sort=None, order="desc", avis=None,
        )
        assert result.total == 5
        assert len(result.items) == 2

    async def test_bpm_source_analysis_surfaces_without_rb(self, db, auth_user):
        """An estimated ('analysis') catalog BPM keeps its provenance when no
        Rekordbox override applies, so the front can flag it as estimated."""
        from models import CatalogEntry

        db.add(
            CatalogEntry(
                title="Estimated",
                artist="A",
                normalized_key="a|estimated",
                bpm=128.0,
                bpm_source="analysis",
            )
        )
        await db.commit()

        result = await catalog_service.list_catalog(db, auth_user.id, skip=0, limit=20)
        assert result.total == 1
        assert result.items[0].bpm == 128.0
        assert result.items[0].bpm_source == "analysis"

    async def test_bpm_source_rekordbox_when_rb_override(self, db, auth_user):
        """When the shown BPM is the viewer's Rekordbox value (coalesce hit), the
        provenance becomes 'rekordbox' — never the catalog's 'analysis'."""
        from models import CatalogEntry, UserTrack

        cat = CatalogEntry(
            title="Overridden",
            artist="A",
            normalized_key="a|rb-override",
            bpm=128.0,
            bpm_source="analysis",
        )
        db.add(cat)
        await db.commit()
        await db.refresh(cat)
        db.add(
            UserTrack(
                user_id=auth_user.id, catalog_id=cat.id, source="test", rb_bpm=130.0
            )
        )
        await db.commit()

        result = await catalog_service.list_catalog(db, auth_user.id, skip=0, limit=20)
        assert result.total == 1
        assert result.items[0].bpm == 130.0
        assert result.items[0].bpm_source == "rekordbox"

    async def test_catalog_ids_restricts_to_given_ids(self, db, auth_user):
        """The additive catalog_ids param filters to exactly those ids; None
        (default) leaves the Explorer behaviour unchanged."""
        from models import CatalogEntry
        rows = [
            CatalogEntry(title=f"T{i}", artist="Artist", normalized_key=f"artist|t{i}")
            for i in range(3)
        ]
        db.add_all(rows)
        await db.commit()
        for r in rows:
            await db.refresh(r)
        wanted = [rows[0].id, rows[2].id]

        restricted = await catalog_service.list_catalog(
            db, auth_user.id, skip=0, limit=50, catalog_ids=wanted,
        )
        assert restricted.total == 2
        assert {it.id for it in restricted.items} == set(wanted)

        # Default (catalog_ids=None) still returns everything.
        full = await catalog_service.list_catalog(db, auth_user.id, skip=0, limit=50)
        assert full.total == 3

        # Empty list yields no rows (valid, degenerate case).
        empty = await catalog_service.list_catalog(
            db, auth_user.id, skip=0, limit=50, catalog_ids=[],
        )
        assert empty.total == 0

    async def test_search_escapes_like_wildcards(self, db, auth_user):
        """A6-06: a literal % in Explorer search matches literally — 'A%B' must
        not also match 'AXB' (which a raw LIKE wildcard would)."""
        from models import CatalogEntry
        db.add_all([
            CatalogEntry(title="A%B", artist="X", normalized_key="x|apctb"),
            CatalogEntry(title="AXB", artist="X", normalized_key="x|axb"),
        ])
        await db.commit()

        res = await catalog_service.list_catalog(
            db, auth_user.id, skip=0, limit=20, search="A%B",
        )
        assert {it.title for it in res.items} == {"A%B"}


class TestGetDetail:
    async def test_raises_lookup_error_for_missing_entry(self, db, auth_user):
        with pytest.raises(LookupError):
            await catalog_service.get_detail(db, 9999999, auth_user.id)

    async def test_returns_detail_for_valid_entry(self, db, auth_user):
        from models import CatalogEntry
        c = CatalogEntry(title="Test Track", artist="Test Artist", normalized_key="test artist|test track")
        db.add(c)
        await db.commit()
        await db.refresh(c)

        result = await catalog_service.get_detail(db, c.id, auth_user.id)
        assert result.title == "Test Track"
        assert result.artist == "Test Artist"

    async def test_bpm_source_analysis_without_rb(self, db, auth_user):
        """Detail surfaces the catalog 'analysis' provenance when no rb override."""
        from models import CatalogEntry

        c = CatalogEntry(
            title="Estimated",
            artist="A",
            normalized_key="a|detail-analysis",
            bpm=124.0,
            bpm_source="analysis",
        )
        db.add(c)
        await db.commit()
        await db.refresh(c)

        result = await catalog_service.get_detail(db, c.id, auth_user.id)
        assert result.bpm == 124.0
        assert result.bpm_source == "analysis"

    async def test_bpm_source_rekordbox_when_rb_override(self, db, auth_user):
        """A coalesced Rekordbox BPM flips the detail provenance to 'rekordbox'."""
        from models import CatalogEntry, UserTrack

        c = CatalogEntry(
            title="Overridden",
            artist="A",
            normalized_key="a|detail-rb",
            bpm=124.0,
            bpm_source="analysis",
        )
        db.add(c)
        await db.commit()
        await db.refresh(c)
        db.add(
            UserTrack(
                user_id=auth_user.id, catalog_id=c.id, source="test", rb_bpm=126.0
            )
        )
        await db.commit()

        result = await catalog_service.get_detail(db, c.id, auth_user.id)
        assert result.bpm == 126.0
        assert result.bpm_source == "rekordbox"


class _RecordingRedis:
    """In-memory Redis stand-in that records the keys passed to delete()."""

    def __init__(self):
        self.store = {}
        self.deleted = []

    async def get(self, key):
        return self.store.get(key)

    async def setex(self, key, ttl, value):
        self.store[key] = value

    async def delete(self, key):
        self.deleted.append(key)
        return 1 if self.store.pop(key, None) is not None else 0


class TestUpdateAvis:
    async def test_raises_lookup_error_for_missing_catalog(self, db, auth_user):
        with pytest.raises(LookupError, match="not found"):
            await catalog_service.update_avis(db, 9999999, auth_user.id, "like")

    async def test_creates_user_track_for_existing_catalog(self, db, auth_user):
        from models import CatalogEntry
        c = CatalogEntry(title="Track", artist="Artist", normalized_key="artist|track")
        db.add(c)
        await db.commit()
        await db.refresh(c)

        result = await catalog_service.update_avis(db, c.id, auth_user.id, "like")
        assert result["catalog_id"] == c.id
        assert result["avis"] == "like"

    async def test_invalidates_reco_cache(self, db, auth_user):
        """A1-03: posting an avis via the main path drops the per-user reco cache
        so Radar 'Pour toi' recomputes (the invalidation lives AFTER the commit,
        mirroring routers/opinions.py)."""
        from models import CatalogEntry
        from services.recommendation_service import _cache_key

        c = CatalogEntry(title="T", artist="A", normalized_key="a|t-reco")
        db.add(c)
        await db.commit()
        await db.refresh(c)

        redis = _RecordingRedis()
        key = _cache_key(auth_user.id)
        redis.store[key] = b"stale-reco-list"

        result = await catalog_service.update_avis(
            db, c.id, auth_user.id, "liked", redis=redis
        )
        assert result["avis"] == "liked"
        # The seed's user reco cache was invalidated…
        assert key in redis.deleted
        # …and the entry is gone (a subsequent GET recomputes).
        assert key not in redis.store

    async def test_redis_none_is_fail_open(self, db, auth_user):
        """redis defaults to None (invalidate_user tolerates it) — the avis path
        still commits without raising."""
        from models import CatalogEntry

        c = CatalogEntry(title="T", artist="A", normalized_key="a|t-none")
        db.add(c)
        await db.commit()
        await db.refresh(c)

        result = await catalog_service.update_avis(db, c.id, auth_user.id, "disliked")
        assert result["avis"] == "disliked"


class TestGetOrCreateCatalog:
    async def test_trims_title_and_artist_on_create(self, db):
        """Leading/trailing whitespace (incl. tab) is stripped before storing."""
        entry = await catalog_service.get_or_create_catalog(
            db, "\t Padded Title ", "  Padded Artist\t"
        )
        assert entry.title == "Padded Title"
        assert entry.artist == "Padded Artist"

    async def test_none_artist_stays_none(self, db):
        entry = await catalog_service.get_or_create_catalog(db, "  Solo  ", None)
        assert entry.title == "Solo"
        assert entry.artist is None


class TestGetCrawlLogs:
    async def test_returns_dict_with_items(self, db):
        result = await catalog_service.get_crawl_logs(db, page=1, per_page=20, task_type=None, status=None)
        assert isinstance(result, dict)
        assert "items" in result
        assert "total" in result
        assert result["total"] == 0

    async def test_filter_by_task_type(self, db):
        result = await catalog_service.get_crawl_logs(db, page=1, per_page=20, task_type="crawl_radar", status=None)
        assert result["total"] == 0
