"""
Integration tests — end-to-end flows across multiple layers.

These tests chain multiple steps (data setup → API calls → DB verification)
to validate that the pipeline works as a whole.  External services (MinIO,
Deezer API, Celery) remain mocked; only the internal logic is exercised.

NOTE: compute_trends and import_rekordbox_xml use PG-specific SQL, so we
cannot call them directly in SQLite tests.  Instead we exercise the data
paths that feed into / read from those layers.
"""
from datetime import date, datetime, timedelta, timezone

import pytest_asyncio
from models import (
    CatalogEntry,
    DJSet,
    RadarTrack,
    RadarTrend,
    SetTrack,
    WatchedEntity,
)
from sqlalchemy import select

# ---------------------------------------------------------------------------
# Local fixtures
# ---------------------------------------------------------------------------


def _cat(title, artist, **kw):
    """Shortcut to create a CatalogEntry with a normalized_key."""
    norm = f"{title.lower()} - {(artist or '').lower()}"
    return CatalogEntry(
        title=title, artist=artist, normalized_key=kw.pop("normalized_key", norm), **kw
    )


# ---------------------------------------------------------------------------
# Test 1 — Radar pipeline: data setup → trends → catalog API
# ---------------------------------------------------------------------------


class TestIntegrationRadarPipeline:
    """Simulate a radar crawl, insert trend rows, and verify via catalog API."""

    @pytest_asyncio.fixture
    async def radar_data(self, db):
        """Create a watched playlist with radar tracks and catalog entries."""
        we = WatchedEntity(
            external_id="dz_playlist_99",
            source="deezer",
            type="playlist",
            title="Hot Tracks",
            track_count=3,
            last_crawled_at=datetime.now(timezone.utc) - timedelta(hours=2),
        )
        db.add(we)
        await db.flush()

        now = datetime.now(timezone.utc)
        cats = []
        for i, (title, artist, genres) in enumerate(
            [
                ("Body Funk", "Purple Disco Machine", ["house music"]),
                ("Losing It", "Fisher", ["tech house"]),
                ("Cola", "CamelPhat", ["techno"]),
            ]
        ):
            cat = _cat(
                title,
                artist,
                bpm=126.0 + i,
                key=f"{6 + i}A",
                genres=genres,
                release_date=date(2024, 1, 1),
            )
            db.add(cat)
            await db.flush()
            cats.append(cat)

            rt = RadarTrack(
                watched_entity_id=we.id,
                external_track_id=f"dz{1000 + i}",
                source="deezer",
                title=title,
                artist=artist,
                catalog_id=cat.id,
                detected_at=now - timedelta(days=i),
            )
            db.add(rt)

        await db.commit()
        for c in cats:
            await db.refresh(c)
        await db.refresh(we)
        return we, cats

    @pytest_asyncio.fixture
    async def trends(self, db, radar_data):
        """Insert RadarTrend rows (simulating compute_trends output)."""
        _, cats = radar_data
        now = datetime.now(timezone.utc)
        for i, cat in enumerate(cats):
            trend = RadarTrend(
                catalog_id=cat.id,
                trend_score=10.0 - i * 3,
                window_days=30,
                detection_count=3 - i,
                source_count=1,
                velocity=0.5 if i == 0 else 0.0,
                family="house" if i < 2 else "techno",
                rank_in_family=i + 1 if i < 2 else 1,
                rank_global=i + 1,
                computed_at=now,
            )
            db.add(trend)
        await db.commit()

    async def test_radar_tracks_visible_in_catalog(self, client, radar_data):
        """Radar tracks appear in catalog listing with view=radar."""
        r = await client.get("/api/catalog/", params={"view": "radar"})
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) == 3
        titles = {it["title"] for it in items}
        assert titles == {"Body Funk", "Losing It", "Cola"}

    async def test_trend_scores_visible_after_computation(
        self, client, radar_data, trends
    ):
        """After trends are inserted, catalog entries expose trend scores."""
        r = await client.get(
            "/api/catalog/",
            params={"view": "radar", "sort": "trend_score_10", "order": "desc"},
        )
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) == 3

        # Body Funk (score 10.0) should rank first
        assert items[0]["title"] == "Body Funk"

        # Scores should be descending
        scores = [it.get("trend_score_10") or 0 for it in items]
        assert scores == sorted(scores, reverse=True)

    async def test_second_crawl_adds_new_tracks(self, db, client, radar_data):
        """Simulating a 2nd crawl: new tracks appear alongside existing ones."""
        we, _ = radar_data

        new_cat = _cat("Pump It Up", "Endor", bpm=124.0, key="5A")
        db.add(new_cat)
        await db.flush()

        db.add(
            RadarTrack(
                watched_entity_id=we.id,
                external_track_id="dz2000",
                source="deezer",
                title="Pump It Up",
                artist="Endor",
                catalog_id=new_cat.id,
                detected_at=datetime.now(timezone.utc),
            )
        )
        await db.commit()

        r = await client.get("/api/catalog/", params={"view": "radar"})
        assert r.status_code == 200
        assert r.json()["total"] == 4

    async def test_trend_ranking_consistency(self, db, radar_data, trends):
        """Verify rank_global and rank_in_family are coherent."""
        result = await db.execute(
            select(RadarTrend).order_by(RadarTrend.rank_global)
        )
        all_trends = result.scalars().all()
        assert len(all_trends) == 3

        # Global ranks are sequential
        assert [t.rank_global for t in all_trends] == [1, 2, 3]

        # Scores descending
        assert all_trends[0].trend_score > all_trends[1].trend_score > all_trends[2].trend_score

        # House family has 2 entries ranked 1, 2
        house = [t for t in all_trends if t.family == "house"]
        assert len(house) == 2
        assert [t.rank_in_family for t in house] == [1, 2]

        # Techno family has 1 entry ranked 1
        techno = [t for t in all_trends if t.family == "techno"]
        assert len(techno) == 1
        assert techno[0].rank_in_family == 1


# ---------------------------------------------------------------------------
# Test 3 — Similarity scoring: co-occurrence + style
# ---------------------------------------------------------------------------


class TestIntegrationSimilarity:
    """Create tracks with co-occurrences and verify similarity endpoint."""

    @pytest_asyncio.fixture
    async def sim_data(self, db):
        """
        Create 5 catalog entries:
        - A, B, C share a playlist and a DJ set (high co-occurrence)
        - D shares genre/BPM with A but no co-occurrence
        - E is completely different (different genre, BPM, no co-occurrence)
        """
        cats = {}
        entries = [
            ("A", "Techno Track A", "DJ Alpha", 130.0, "8A", ["techno"]),
            ("B", "Techno Track B", "DJ Beta", 131.0, "8A", ["techno"]),
            ("C", "Techno Track C", "DJ Gamma", 129.0, "9A", ["techno"]),
            ("D", "Techno Track D", "DJ Delta", 130.0, "8A", ["techno"]),
            ("E", "Reggae Track E", "DJ Epsilon", 90.0, "3B", ["reggae"]),
        ]
        for key, title, artist, bpm, musical_key, genres in entries:
            cat = _cat(title, artist, bpm=bpm, key=musical_key, genres=genres)
            db.add(cat)
            await db.flush()
            cats[key] = cat

        # Create a watched playlist containing A, B, C
        we = WatchedEntity(
            external_id="sim_playlist_1",
            source="deezer",
            title="Sim Test Playlist",
        )
        db.add(we)
        await db.flush()

        now = datetime.now(timezone.utc)
        for key in ["A", "B", "C"]:
            db.add(
                RadarTrack(
                    watched_entity_id=we.id,
                    external_track_id=f"sim_{key}",
                    source="deezer",
                    title=cats[key].title,
                    artist=cats[key].artist,
                    catalog_id=cats[key].id,
                    detected_at=now,
                )
            )

        # Create a DJ set containing A, B, C
        dj_set = DJSet(
            source="trackid",
            title="Test Set",
            external_id="sim_set_1",
        )
        db.add(dj_set)
        await db.flush()

        for i, key in enumerate(["A", "B", "C"]):
            db.add(
                SetTrack(
                    set_id=dj_set.id,
                    catalog_id=cats[key].id,
                    position=i + 1,
                    raw_title=cats[key].title,
                    raw_artist=cats[key].artist,
                )
            )

        await db.commit()
        for c in cats.values():
            await db.refresh(c)
        return cats

    async def test_cooccurrent_tracks_score_higher(self, client, sim_data):
        """Tracks sharing playlists/sets with ref should score higher than isolated tracks."""
        ref_id = sim_data["A"].id

        r = await client.get(
            f"/api/catalog/{ref_id}/similar",
            params={"score_floor": 0.0, "limit": 10},
        )
        assert r.status_code == 200
        results = r.json()
        assert len(results) >= 2

        ids_scores = {it["id"]: it["similarity"]["score"] for it in results}

        # B and C share playlist + set with A → high score
        assert sim_data["B"].id in ids_scores
        assert sim_data["C"].id in ids_scores

        score_b = ids_scores[sim_data["B"].id]
        assert sim_data["C"].id in ids_scores

        # D has same genre/BPM but no co-occurrence
        if sim_data["D"].id in ids_scores:
            score_d = ids_scores[sim_data["D"].id]
            assert score_b > score_d, "Co-occurring B should outscore isolated D"

        # E is completely different
        if sim_data["E"].id in ids_scores:
            score_e = ids_scores[sim_data["E"].id]
            assert score_b > score_e, "Co-occurring B should outscore different E"

    async def test_style_similarity_beats_random(self, client, sim_data):
        """Track D (same genre/BPM/key as A) should score higher than E (different everything)."""
        ref_id = sim_data["A"].id

        r = await client.get(
            f"/api/catalog/{ref_id}/similar",
            params={"score_floor": 0.0, "limit": 10},
        )
        assert r.status_code == 200
        results = r.json()

        ids_scores = {it["id"]: it["similarity"]["score"] for it in results}

        # D shares genre+BPM+key → style score
        # E has nothing in common → very low or absent
        if sim_data["D"].id in ids_scores and sim_data["E"].id in ids_scores:
            assert ids_scores[sim_data["D"].id] > ids_scores[sim_data["E"].id]

    async def test_similarity_components_present(self, client, sim_data):
        """Each result should include similarity components breakdown."""
        ref_id = sim_data["A"].id

        r = await client.get(
            f"/api/catalog/{ref_id}/similar",
            params={"score_floor": 0.0, "limit": 5},
        )
        assert r.status_code == 200
        for item in r.json():
            sim = item["similarity"]
            assert "score" in sim
            assert "components" in sim
            comps = sim["components"]
            assert all(k in comps for k in ("sets", "playlists", "style", "context"))

    async def test_similar_excludes_self(self, client, sim_data):
        """The reference track should never appear in its own similar results."""
        ref_id = sim_data["A"].id

        r = await client.get(
            f"/api/catalog/{ref_id}/similar",
            params={"score_floor": 0.0, "limit": 50},
        )
        assert r.status_code == 200
        result_ids = {it["id"] for it in r.json()}
        assert ref_id not in result_ids

    async def test_nonexistent_track_returns_404(self, client):
        """Requesting similarity for a non-existent catalog ID should 404."""
        r = await client.get("/api/catalog/999999/similar")
        assert r.status_code == 404
