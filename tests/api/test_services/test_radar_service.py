"""Tests for services/radar_service.py."""
from datetime import datetime, timedelta, timezone

import pytest

from services import radar_service


# ── Bi-score feed helpers ─────────────────────────────────────────────────────

async def _mk_track(db, title, nk, *, bpm=None, key=None, genres=None,
                    created_at=None, scope="shared", artist="Artist"):
    from models import CatalogEntry
    c = CatalogEntry(
        title=title, artist=artist, normalized_key=nk, scope=scope,
        bpm=bpm, key=key, genres=genres or [], created_at=created_at,
    )
    db.add(c)
    await db.commit()
    await db.refresh(c)
    return c


async def _mk_trend(db, catalog_id, trend_score, *, family="house",
                    rank_in_family=1, rank_global=1, velocity=None):
    from models import RadarTrend
    db.add(RadarTrend(
        catalog_id=catalog_id, trend_score=trend_score, family=family,
        rank_in_family=rank_in_family, rank_global=rank_global, velocity=velocity,
    ))
    await db.commit()


async def _put_in_set(db, catalog_ids, title="Set"):
    from models import DJSet, SetTrack
    s = DJSet(source="trackid", title=title)
    db.add(s)
    await db.commit()
    await db.refresh(s)
    for pos, cid in enumerate(catalog_ids):
        db.add(SetTrack(set_id=s.id, catalog_id=cid, position=pos))
    await db.commit()
    return s


async def _like(db, user_id, catalog_id):
    from models import UserOpinion
    db.add(UserOpinion(
        user_id=user_id, entity_type="track", entity_key=str(catalog_id),
        opinion="liked", created_at=datetime.now(timezone.utc),
    ))
    await db.commit()


def _reco(cid, score, **over):
    """Build a RecommendationItem (all CatalogEntryOut Optionals are required)."""
    from schemas import RecommendationItem
    return RecommendationItem(
        id=cid, title=over.get("title", f"Reco{cid}"), artist=over.get("artist"),
        isrc=None, bpm=over.get("bpm"), key=over.get("key"),
        duration_ms=over.get("duration_ms"), release_date=over.get("release_date"),
        created_at=over.get("created_at"), reco_score=score,
    )


def _mock_reco(mocker, items):
    from schemas import RecommendationList
    return mocker.patch(
        "services.recommendation_service.get_recommendations",
        return_value=RecommendationList(items=items),
    )


def _by_id(result):
    return {it.id: it for it in result.items}


# ── list_bi_score ─────────────────────────────────────────────────────────────

class TestListBiScore:
    async def test_real_reco_integration(self, db, auth_user):
        """End-to-end wiring with the REAL reco engine: a liked seed surfaces its
        set co-occurrence partner as a reco-only feed row (no trend)."""
        seed = await _mk_track(db, "Seed", "a|seed")
        b = await _mk_track(db, "B", "a|b")
        await _put_in_set(db, [seed.id, b.id])
        await _like(db, auth_user.id, seed.id)

        res = await radar_service.list_bi_score(db, auth_user.id, redis=None)
        items = _by_id(res)
        assert b.id in items
        assert seed.id not in items  # liked seed excluded from reco
        assert res.reco_count >= 1
        assert res.trend_count == 0
        # single reco item → its score max-normalises to 10.0
        assert items[b.id].reco_score_10 == 10.0
        assert items[b.id].trend_score_10 is None

    async def test_union_trend_and_reco(self, db, auth_user, mocker):
        t = await _mk_track(db, "Trend", "a|trend")
        await _mk_trend(db, t.id, 5.0, velocity=0.4)
        _mock_reco(mocker, [_reco(900001, 0.5)])

        res = await radar_service.list_bi_score(db, auth_user.id, redis=None)
        items = _by_id(res)
        assert set(items) == {t.id, 900001}
        assert res.total == 2
        assert res.trend_count == 1
        assert res.reco_count == 1
        # trend-only row
        assert items[t.id].trend_score_10 is not None
        assert items[t.id].reco_score_10 is None
        assert items[t.id].velocity == 0.4
        # reco-only row
        assert items[900001].reco_score_10 == 10.0
        assert items[900001].trend_score_10 is None
        assert items[900001].velocity is None

    async def test_overlap_carries_both_scores(self, db, auth_user, mocker):
        b = await _mk_track(db, "Both", "a|both")
        await _mk_trend(db, b.id, 8.0, velocity=0.7)
        _mock_reco(mocker, [_reco(b.id, 0.4)])

        res = await radar_service.list_bi_score(db, auth_user.id, redis=None)
        items = _by_id(res)
        assert set(items) == {b.id}  # a single merged row, not two
        assert res.total == 1
        assert res.trend_count == 1
        assert res.reco_count == 1
        assert items[b.id].trend_score_10 is not None
        assert items[b.id].reco_score_10 == 10.0
        assert items[b.id].velocity == 0.7

    async def test_cold_start_reco_empty(self, db, auth_user):
        """No like/lib → real reco empty → every row is trend-only."""
        t1 = await _mk_track(db, "T1", "a|t1")
        t2 = await _mk_track(db, "T2", "a|t2")
        await _mk_trend(db, t1.id, 10.0, rank_in_family=1)
        await _mk_trend(db, t2.id, 4.0, rank_in_family=2)

        res = await radar_service.list_bi_score(db, auth_user.id, redis=None)
        assert res.reco_count == 0
        assert res.trend_count == 2
        assert res.total == 2
        assert all(it.reco_score_10 is None for it in res.items)

    async def test_sort_tendance_desc_nulls_last(self, db, auth_user, mocker):
        hi = await _mk_track(db, "Hi", "a|hi")
        mid = await _mk_track(db, "Mid", "a|mid")
        await _mk_trend(db, hi.id, 10.0, rank_in_family=1)
        await _mk_trend(db, mid.id, 5.0, rank_in_family=2)
        _mock_reco(mocker, [_reco(900001, 0.5)])  # reco-only → trend None → last

        res = await radar_service.list_bi_score(
            db, auth_user.id, sort="tendance", order="desc", redis=None
        )
        order = [it.id for it in res.items]
        assert order == [hi.id, mid.id, 900001]
        assert [it.trend_score_10 for it in res.items] == [10.0, 5.0, None]

    async def test_sort_pour_toi_desc_nulls_last(self, db, auth_user, mocker):
        t = await _mk_track(db, "Trend", "a|trend")
        await _mk_trend(db, t.id, 5.0)
        _mock_reco(mocker, [_reco(900001, 0.9), _reco(900002, 0.3)])

        res = await radar_service.list_bi_score(
            db, auth_user.id, sort="pour_toi", order="desc", redis=None
        )
        order = [it.id for it in res.items]
        assert order == [900001, 900002, t.id]  # highest reco first, None last
        assert res.items[0].reco_score_10 == 10.0
        assert res.items[1].reco_score_10 == 3.3  # 0.3/0.9*10
        assert res.items[2].reco_score_10 is None

    async def test_sort_bpm(self, db, auth_user):
        lo = await _mk_track(db, "Lo", "a|lo", bpm=120.0)
        mid = await _mk_track(db, "Mid", "a|mid", bpm=128.0)
        hi = await _mk_track(db, "Hi", "a|hi", bpm=130.0)
        for i, tr in enumerate([lo, mid, hi]):
            await _mk_trend(db, tr.id, 5.0, rank_in_family=i + 1)

        desc = await radar_service.list_bi_score(
            db, auth_user.id, sort="bpm", order="desc", redis=None
        )
        assert [it.bpm for it in desc.items] == [130.0, 128.0, 120.0]
        asc = await radar_service.list_bi_score(
            db, auth_user.id, sort="bpm", order="asc", redis=None
        )
        assert [it.bpm for it in asc.items] == [120.0, 128.0, 130.0]

    async def test_sort_recent(self, db, auth_user):
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        old = await _mk_track(db, "Old", "a|old", created_at=base)
        mid = await _mk_track(db, "Mid", "a|mid", created_at=base + timedelta(days=1))
        new = await _mk_track(db, "New", "a|new", created_at=base + timedelta(days=2))
        for i, tr in enumerate([old, mid, new]):
            await _mk_trend(db, tr.id, 5.0, rank_in_family=i + 1)

        res = await radar_service.list_bi_score(
            db, auth_user.id, sort="recent", order="desc", redis=None
        )
        assert [it.id for it in res.items] == [new.id, mid.id, old.id]

    async def test_filter_bpm_and_genre_keeps_counters_pre_filter(
        self, db, auth_user, mocker
    ):
        t1 = await _mk_track(db, "House", "a|house", bpm=128.0, genres=["House"])
        t2 = await _mk_track(db, "Techno", "a|techno", bpm=140.0, genres=["Techno"])
        await _mk_trend(db, t1.id, 5.0, rank_in_family=1)
        await _mk_trend(db, t2.id, 6.0, rank_in_family=2)
        _mock_reco(mocker, [_reco(900001, 0.5)])

        res = await radar_service.list_bi_score(
            db, auth_user.id,
            bpm_min=125, bpm_max=132, genre=["House"], redis=None,
        )
        # Only T1 passes the live filter …
        assert [it.id for it in res.items] == [t1.id]
        assert res.total == 1
        # … but the head counters are computed over the UNFILTERED union.
        assert res.trend_count == 2
        assert res.reco_count == 1

    async def test_pagination(self, db, auth_user):
        tracks = [await _mk_track(db, f"T{i}", f"a|t{i}") for i in range(5)]
        for i, tr in enumerate(tracks):
            await _mk_trend(db, tr.id, float(10 - i), rank_in_family=i + 1)

        page = await radar_service.list_bi_score(
            db, auth_user.id, skip=2, limit=2, redis=None
        )
        assert page.total == 5  # total is the full filtered union
        assert len(page.items) == 2


class TestNewCount:
    async def test_returns_zero_with_no_tracks(self, db, auth_user):
        result = await radar_service.new_count(db, auth_user.id)
        assert result == {"count": 0}

    async def test_returns_count_for_tracks_without_state(self, db, auth_user):
        from models import CatalogEntry, RadarTrack, WatchedEntity
        entity = WatchedEntity(
            source="deezer", external_id="pl_001", title="Test Playlist"
        )
        db.add(entity)
        await db.commit()
        await db.refresh(entity)

        cat = CatalogEntry(title="T1", artist="A1", normalized_key="a1|t1")
        db.add(cat)
        await db.commit()
        await db.refresh(cat)

        rt = RadarTrack(
            watched_entity_id=entity.id, external_track_id="t1",
            source="deezer", title="T1", artist="A1", catalog_id=cat.id
        )
        db.add(rt)
        await db.commit()

        result = await radar_service.new_count(db, auth_user.id)
        assert result["count"] == 1


class TestBatchUpdateState:
    async def test_returns_zero_for_empty_items(self, db, auth_user):
        result = await radar_service.batch_update_state(db, auth_user.id, [])
        assert result == {"updated": 0}

    async def test_creates_state_for_valid_catalog(self, db, auth_user):
        from models import CatalogEntry
        c = CatalogEntry(title="T", artist="A", normalized_key="a|t")
        db.add(c)
        await db.commit()
        await db.refresh(c)

        result = await radar_service.batch_update_state(
            db, auth_user.id, [{"catalog_id": c.id, "status": "new"}]
        )
        assert result == {"updated": 1}

    async def test_batch_status_alias(self, db, auth_user):
        from models import CatalogEntry, UserRadarState
        from sqlalchemy import select
        c = CatalogEntry(title="T2", artist="A2", normalized_key="a2|t2")
        db.add(c)
        await db.commit()
        await db.refresh(c)

        await radar_service.batch_update_state(
            db, auth_user.id, [{"catalog_id": c.id, "status": "liked"}]
        )
        # "liked" is aliased to "added"
        result = await db.execute(
            select(UserRadarState).where(
                UserRadarState.user_id == auth_user.id,
                UserRadarState.catalog_id == c.id,
            )
        )
        state = result.scalar_one_or_none()
        assert state is not None
        assert state.status == "added"


class TestAddTrack:
    async def test_raises_lookup_error_for_missing_watched_entity(self, db, auth_user):
        class FakeBody:
            watched_playlist_id = 9999999
            external_track_id = "ext1"
            source = "deezer"
            title = "T"
            artist = "A"
            isrc = None

        with pytest.raises(LookupError, match="watched_entity not found"):
            await radar_service.add_track(db, auth_user.id, FakeBody())

    async def test_creates_track_for_valid_entity(self, db, auth_user):
        from models import WatchedEntity

        entity = WatchedEntity(source="deezer", external_id="pl_002", title="Playlist")
        db.add(entity)
        await db.commit()
        await db.refresh(entity)

        class FakeBody:
            watched_playlist_id = entity.id
            external_track_id = "ext_new"
            source = "deezer"
            title = "New Track"
            artist = "Artist"
            isrc = None

        track, existed = await radar_service.add_track(db, auth_user.id, FakeBody())
        assert not existed
        assert track.title == "New Track"
        assert track.watched_entity_id == entity.id

    async def test_returns_existing_track_on_duplicate(self, db, auth_user):
        from models import WatchedEntity

        entity = WatchedEntity(source="deezer", external_id="pl_003", title="Playlist 2")
        db.add(entity)
        await db.commit()
        await db.refresh(entity)

        class FakeBody:
            watched_playlist_id = entity.id
            external_track_id = "ext_dup"
            source = "deezer"
            title = "Dup Track"
            artist = "Artist"
            isrc = None

        _, existed1 = await radar_service.add_track(db, auth_user.id, FakeBody())
        _, existed2 = await radar_service.add_track(db, auth_user.id, FakeBody())
        assert not existed1
        assert existed2
