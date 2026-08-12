"""Tests for GET /api/admin/monitoring — backlog time-series + throughput
history + current status. Seeds a metric_snapshots row + a crawl_logs row and
asserts the three sections. Also confirms the MetricSnapshot model is picked up
by the conftest create_all (writing a row through the ORM would fail otherwise).
"""
from datetime import datetime, timedelta, timezone

from models import Artist, CatalogArtist, CatalogEntry, CrawlLog, MetricSnapshot
from sqlalchemy import select


def _now():
    return datetime.now(timezone.utc)


async def _seed_catalog(
    db,
    *,
    title,
    artist,
    key,
    deezer_id=None,
    beatport_id=None,
    deezer_searched_at=None,
    beatport_searched_at=None,
    m2m_names=None,
):
    """Seed a catalog row + optional catalog_artists links (get-or-create the
    artists by a lower() normalized_name so repeated names reuse one row)."""
    entry = CatalogEntry(
        title=title,
        artist=artist,
        normalized_key=key,
        deezer_id=deezer_id,
        beatport_id=beatport_id,
        deezer_searched_at=deezer_searched_at,
        beatport_searched_at=beatport_searched_at,
        created_at=_now(),
    )
    db.add(entry)
    await db.flush()
    for pos, name in enumerate(m2m_names or []):
        norm = name.lower()
        art = (
            await db.execute(select(Artist).where(Artist.normalized_name == norm))
        ).scalar_one_or_none()
        if art is None:
            art = Artist(name=name, normalized_name=norm)
            db.add(art)
            await db.flush()
        db.add(CatalogArtist(catalog_id=entry.id, artist_id=art.id, position=pos))
    await db.commit()
    return entry


async def _seed_snapshot(db, *, captured_at=None, payload=None):
    snap = MetricSnapshot(
        captured_at=captured_at or _now(),
        payload=payload
        or {
            "enrich": {
                "deezer": {"total_missing": 5, "total_linked": 100},
                "beatport": {"total_missing": 50, "total_linked": 60},
            },
            "artists": {"backlog_link": 3, "backlog_artwork": 7},
            "sets": {"recrawl_backlog": 2},
            "catalog": {"total": 105},
        },
    )
    db.add(snap)
    await db.commit()
    return snap


async def _seed_crawl_log(db, **overrides):
    started = overrides.pop("started_at", _now())
    log = CrawlLog(
        task_type=overrides.pop("task_type", "enrich_catalog"),
        source=overrides.pop("source", "deezer"),
        status=overrides.pop("status", "success"),
        started_at=started,
        finished_at=overrides.pop("finished_at", started + timedelta(seconds=5)),
        duration_ms=overrides.pop("duration_ms", 5000),
        stats=overrides.pop("stats", {"enriched": 8, "not_found": 2, "merged": 1}),
        **overrides,
    )
    db.add(log)
    await db.commit()
    return log


class TestMonitoringAuth:
    async def test_requires_auth(self, client):
        r = await client.get("/api/admin/monitoring")
        assert r.status_code == 401

    async def test_rejected_for_non_admin(self, auth_client):
        r = await auth_client.get("/api/admin/monitoring")
        assert r.status_code == 403


class TestMonitoringResponse:
    async def test_returns_sections(self, admin_client, db):
        await _seed_snapshot(db)
        await _seed_crawl_log(db)

        r = await admin_client.get("/api/admin/monitoring")
        assert r.status_code == 200
        data = r.json()
        # X4.d (L6) added the additive "integrity" block alongside the original 3.
        assert set(data) == {
            "backlog_series",
            "throughput_series",
            "status",
            "integrity",
        }
        assert "last_runs" in data["status"]
        assert "latest_snapshot" in data["status"]
        assert set(data["integrity"]) == {
            "artist_divergence",
            "platform_ids_pre_x3",
            "missing_m2m_link",
        }

    async def test_empty_db_ok(self, admin_client):
        r = await admin_client.get("/api/admin/monitoring")
        assert r.status_code == 200
        data = r.json()
        assert data["backlog_series"] == []
        assert data["throughput_series"] == []
        assert data["status"]["last_runs"] == []
        assert data["status"]["latest_snapshot"] is None

    async def test_backlog_snapshot_returned(self, admin_client, db):
        await _seed_snapshot(db)

        r = await admin_client.get("/api/admin/monitoring")
        series = r.json()["backlog_series"]
        assert len(series) == 1
        item = series[0]
        assert item["payload"]["catalog"]["total"] == 105
        assert item["payload"]["artists"]["backlog_link"] == 3

    async def test_throughput_aggregates_and_hit_rate(self, admin_client, db):
        # Two runs of the same task/source on the same day → aggregated into one
        # row (runs=2), hit_rate = enriched/(enriched+not_found).
        now = _now()
        await _seed_crawl_log(db, started_at=now, stats={"enriched": 8, "not_found": 2})
        await _seed_crawl_log(
            db,
            started_at=now,
            stats={"enriched": 2, "not_found": 8},
            duration_ms=3000,
        )

        r = await admin_client.get("/api/admin/monitoring")
        series = r.json()["throughput_series"]
        assert len(series) == 1
        row = series[0]
        assert row["task_type"] == "enrich_catalog"
        assert row["source"] == "deezer"
        assert row["runs"] == 2
        assert row["enriched"] == 10
        assert row["not_found"] == 10
        assert row["hit_rate"] == 0.5
        assert row["duration_ms_max"] == 5000
        assert row["duration_ms_avg"] == 4000

    async def test_error_run_counted(self, admin_client, db):
        await _seed_crawl_log(
            db, status="error", stats=None, error_message="boom"
        )

        r = await admin_client.get("/api/admin/monitoring")
        row = r.json()["throughput_series"][0]
        assert row["runs"] == 1
        assert row["errors"] == 1
        # No enriched/not_found → hit_rate undefined
        assert row["hit_rate"] is None

    async def test_status_reports_latest_run_and_snapshot(self, admin_client, db):
        old = _now() - timedelta(hours=2)
        recent = _now()
        await _seed_crawl_log(db, started_at=old, status="error")
        await _seed_crawl_log(db, started_at=recent, status="success")
        await _seed_snapshot(db)

        r = await admin_client.get("/api/admin/monitoring")
        status = r.json()["status"]
        runs = {row["task_type"]: row for row in status["last_runs"]}
        assert "enrich_catalog" in runs
        # Latest run wins (the recent success, not the older error)
        assert runs["enrich_catalog"]["status"] == "success"
        assert status["latest_snapshot"]["payload"]["catalog"]["total"] == 105

    async def test_days_window_excludes_old_snapshots(self, admin_client, db):
        await _seed_snapshot(db, captured_at=_now() - timedelta(days=40))

        r = await admin_client.get("/api/admin/monitoring?days=14")
        assert r.json()["backlog_series"] == []

        r2 = await admin_client.get("/api/admin/monitoring?days=60")
        assert len(r2.json()["backlog_series"]) == 1


class TestIntegrityCounters:
    """X4.d (L6) — instant artist-integrity counters exposed under `integrity`."""

    async def test_empty_db_all_zero(self, admin_client):
        r = await admin_client.get("/api/admin/monitoring")
        assert r.json()["integrity"] == {
            "artist_divergence": 0,
            "platform_ids_pre_x3": 0,
            "missing_m2m_link": 0,
        }

    async def test_artist_divergence(self, admin_client, db):
        # (1) Divergent: enriched, flat "Ejeca" vs first M2M "Carl Cox" → counted.
        await _seed_catalog(
            db,
            title="Rhythm Of The House",
            artist="Ejeca",
            key="rhythm - ejeca",
            deezer_id="111",
            m2m_names=["Carl Cox"],
        )
        # (2) Coherent: flat == first M2M → not counted (dropped by SQL pre-filter).
        await _seed_catalog(
            db,
            title="Coherent",
            artist="Carl Cox",
            key="coherent - carl cox",
            deezer_id="222",
            m2m_names=["Carl Cox"],
        )
        # (3) Accent-only difference: folds equal → contained → not counted.
        await _seed_catalog(
            db,
            title="Accented",
            artist="Zoë",
            key="accented - zoe",
            deezer_id="333",
            m2m_names=["Zoe"],
        )
        # (4) Divergent BUT not enriched (no platform id) → excluded by the gate.
        await _seed_catalog(
            db,
            title="Not Enriched",
            artist="Someone",
            key="not enriched - someone",
            m2m_names=["Different Person"],
        )
        # (5) Containment (multi-artist flat contains the M2M name) → not counted.
        await _seed_catalog(
            db,
            title="Multi",
            artist="Carl Cox, Green Velvet",
            key="multi - carl cox",
            beatport_id="444",
            m2m_names=["Carl Cox"],
        )

        r = await admin_client.get("/api/admin/monitoring")
        assert r.json()["integrity"]["artist_divergence"] == 1

    async def test_platform_ids_pre_x3(self, admin_client, db):
        # Beatport id searched BEFORE the X3 fix → counted.
        await _seed_catalog(
            db,
            title="Pre",
            artist="A",
            key="pre - a",
            beatport_id="900",
            beatport_searched_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
        )
        # Deezer id searched AFTER the fix → not counted.
        await _seed_catalog(
            db,
            title="Post",
            artist="B",
            key="post - b",
            deezer_id="901",
            deezer_searched_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        )
        # Id present but searched_at NULL → not counted (NULL comparison).
        await _seed_catalog(
            db,
            title="NullDate",
            artist="C",
            key="nulldate - c",
            deezer_id="902",
        )

        r = await admin_client.get("/api/admin/monitoring")
        assert r.json()["integrity"]["platform_ids_pre_x3"] == 1

    async def test_missing_m2m_link(self, admin_client, db):
        # Flat artist, no M2M link → counted (un-clickable artist).
        await _seed_catalog(
            db, title="Solo", artist="Solo Artist", key="solo - solo artist"
        )
        # Flat artist WITH a link → not counted.
        await _seed_catalog(
            db,
            title="Linked",
            artist="Linked Artist",
            key="linked - linked artist",
            m2m_names=["Linked Artist"],
        )
        # Blank flat artist, no link → not counted (trimmed empty).
        await _seed_catalog(db, title="Blank", artist="   ", key="blank - x")
        # NULL flat artist → not counted.
        await _seed_catalog(db, title="NullArtist", artist=None, key="nullartist - x")

        r = await admin_client.get("/api/admin/monitoring")
        assert r.json()["integrity"]["missing_m2m_link"] == 1
