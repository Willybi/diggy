"""Tests for GET /api/admin/backlog — aggregated admin backlog counters.

Half the response is read from the latest metric_snapshots payload (seeded via
the ORM), the other half are live COUNTs (SetFlag / ArtistFlag / GenreMapping /
CatalogEntry / WatchedEntity). Modelled on test_monitoring.py.
"""
from datetime import datetime, timedelta, timezone

from models import (
    ArtistFlag,
    CatalogEntry,
    DJSet,
    GenreMapping,
    MetricSnapshot,
    SetFlag,
    SetFlagStatus,
    SetFlagType,
    WatchedEntity,
)


def _now():
    return datetime.now(timezone.utc)


# Realistic payload, shaped exactly like snapshot_backlogs writes it (each enrich
# source dict mirrors workers.enrichment.count_enrich_backlog).
_PAYLOAD = {
    "enrich": {
        "deezer": {
            "never_tried": 4,
            "due_retry": 1,
            "cooldown": 2,
            "abandoned": 3,
            "total_missing": 10,
            "total_linked": 100,
        },
        "beatport": {
            "never_tried": 20,
            "due_retry": 5,
            "cooldown": 10,
            "abandoned": 15,
            "total_missing": 50,
            "total_linked": 60,
        },
    },
    "artists": {"backlog_link": 3, "backlog_artwork": 7},
    "sets": {"recrawl_backlog": 2},
    "catalog": {"total": 105},
}


async def _seed_snapshot(db, *, captured_at=None, payload=None):
    snap = MetricSnapshot(
        captured_at=captured_at or _now(),
        payload=payload if payload is not None else _PAYLOAD,
    )
    db.add(snap)
    await db.commit()
    return snap


async def _seed_live_counts(db):
    """One pending SetFlag, one pending ArtistFlag, one unmapped GenreMapping,
    one un-genred CatalogEntry, one never-crawled playlist → each live count = 1."""
    s = DJSet(source="trackid", title="Set A")
    db.add(s)
    await db.flush()
    db.add(
        SetFlag(
            set_id_a=s.id,
            set_id_b=None,
            flag_type=SetFlagType.duplicate_candidate,
            confidence=0.9,
            status=SetFlagStatus.pending,
            created_at=_now(),
        )
    )
    db.add(
        ArtistFlag(
            raw_artist_string="X / Y",
            reason="feat",
            tokens=["X", "Y"],
            deezer_ids={},
            status="pending",
        )
    )
    db.add(GenreMapping(raw_name="unmapped genre", node_id=None))
    db.add(
        CatalogEntry(
            title="No Genre", artist="A", normalized_key="no-genre-a", genres=[]
        )
    )
    db.add(WatchedEntity(external_id="pl-due", source="deezer", title="PL"))
    await db.commit()


class TestBacklogAuth:
    async def test_requires_auth(self, client):
        r = await client.get("/api/admin/backlog")
        assert r.status_code == 401

    async def test_rejected_for_non_admin(self, auth_client):
        r = await auth_client.get("/api/admin/backlog")
        assert r.status_code == 403

    async def test_ok_for_admin(self, admin_client):
        r = await admin_client.get("/api/admin/backlog")
        assert r.status_code == 200


class TestBacklogResponse:
    async def test_merged_body(self, admin_client, db):
        await _seed_snapshot(db)
        await _seed_live_counts(db)

        r = await admin_client.get("/api/admin/backlog")
        assert r.status_code == 200
        data = r.json()

        assert data["captured_at"] is not None
        # From the snapshot payload
        assert data["beatport"] == {"pending": 25, "total_missing": 50, "abandoned": 15}
        assert data["deezer"] == {"pending": 5, "total_missing": 10, "abandoned": 3}
        assert data["artists"] == {"to_link": 3, "no_artwork": 7}
        assert data["sets"]["recrawl"] == 2
        # Live COUNTs
        assert data["sets"]["flags_pending"] == 1
        assert data["artist_flags"]["pending"] == 1
        assert data["genres"]["unclassified"] == 1
        assert data["genres"]["mappings_unmapped"] == 1
        assert data["crawl"]["playlists_due"] == 1
        # DLQ: FakeRedis.llen on an empty store → 0 (fail-open not triggered).
        assert data["crawl"]["dlq"] == 0

    async def test_playlists_due_excludes_recently_crawled(self, admin_client, db):
        # Crawled 2h ago → NOT due; never crawled → due. Only the latter counts.
        db.add(
            WatchedEntity(
                external_id="fresh",
                source="deezer",
                title="Fresh",
                last_crawled_at=_now() - timedelta(hours=2),
            )
        )
        db.add(WatchedEntity(external_id="stale", source="deezer", title="Stale"))
        await db.commit()

        r = await admin_client.get("/api/admin/backlog")
        assert r.json()["crawl"]["playlists_due"] == 1

    async def test_empty_db_ok(self, admin_client):
        # No snapshot at all: captured_at None, snapshot-backed counters 0, and
        # the endpoint still answers 200 with zeroed live counts.
        r = await admin_client.get("/api/admin/backlog")
        assert r.status_code == 200
        data = r.json()
        assert data["captured_at"] is None
        assert data["beatport"] == {"pending": 0, "total_missing": 0, "abandoned": 0}
        assert data["deezer"] == {"pending": 0, "total_missing": 0, "abandoned": 0}
        assert data["artists"] == {"to_link": 0, "no_artwork": 0}
        assert data["sets"] == {"recrawl": 0, "flags_pending": 0}
        assert data["artist_flags"]["pending"] == 0
        assert data["genres"] == {"unclassified": 0, "mappings_unmapped": 0}
        assert data["crawl"]["playlists_due"] == 0

    async def test_partial_payload_does_not_raise(self, admin_client, db):
        # A payload missing whole sections must collapse to 0, never KeyError.
        await _seed_snapshot(db, payload={"enrich": {"deezer": {}}})

        r = await admin_client.get("/api/admin/backlog")
        assert r.status_code == 200
        data = r.json()
        assert data["deezer"] == {"pending": 0, "total_missing": 0, "abandoned": 0}
        assert data["beatport"] == {"pending": 0, "total_missing": 0, "abandoned": 0}
        assert data["artists"] == {"to_link": 0, "no_artwork": 0}
        assert data["sets"]["recrawl"] == 0
