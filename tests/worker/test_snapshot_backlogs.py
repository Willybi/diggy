"""Test for the snapshot_backlogs Celery task (workers/tasks/monitoring).

Runs the real task function (celery ecosystem mocked, same pattern as
test_tasks_observability.py) against an in-memory SQLite engine and asserts it
writes ONE metric_snapshots row whose payload is structured by domain.
"""
import os
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

_SERVER_PATH = os.path.join(os.path.dirname(__file__), "../../server")
_API_PATH = os.path.join(os.path.dirname(__file__), "../../server/api")
for _p in (_SERVER_PATH, _API_PATH):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# Mock infra that isn't available outside Docker (same pattern as
# test_tasks_observability.py — the shared workers.celery_app mock is overwritten
# below, and re-imported per-test via the tasks_env fixture).
_MOCK_MODULES = [
    "celery", "celery.schedules", "celery.signals", "celery._state",
    "redis", "redis.exceptions",
    "curl_cffi", "curl_cffi.requests",
    "requests",
    "workers.celery_app",
]
for _mod in _MOCK_MODULES:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

_celery_mock = MagicMock()


def _task_decorator(*args, **kwargs):
    def decorator(fn):
        fn.name = kwargs.get("name", fn.__name__)
        fn.autoretry_for = kwargs.get("autoretry_for", ())
        fn.bind = kwargs.get("bind", False)
        fn.soft_time_limit = kwargs.get("soft_time_limit")
        fn.time_limit = kwargs.get("time_limit")
        fn.delay = MagicMock()
        fn.s = MagicMock()
        return fn
    if args and callable(args[0]):
        return _task_decorator()(args[0])
    return decorator


_celery_mock.task.side_effect = _task_decorator
_celery_app_mod = MagicMock(celery_app=_celery_mock)
sys.modules["workers.celery_app"] = _celery_app_mod

from datetime import datetime, timedelta, timezone  # noqa: E402

from database import Base  # noqa: E402
from models import (  # noqa: E402
    EMBEDDING_DIM,
    MODEL_NAME,
    MODEL_VERSION,
    Album,
    Artist,
    CatalogAlbum,
    CatalogArtist,
    CatalogEntry,
    CrawlLog,
    DJSet,
    MetricSnapshot,
    TrackEmbedding,
)
from sqlalchemy import create_engine, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402


@pytest.fixture
def task_engine():
    engine = create_engine("sqlite:///:memory:", isolation_level="AUTOCOMMIT")
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def monitoring_task(task_engine, monkeypatch):
    """Import the real monitoring task with celery mocked + engine redirected."""
    monkeypatch.setitem(sys.modules, "workers.celery_app", _celery_app_mod)
    for m in [k for k in sys.modules if k.startswith("workers.tasks")]:
        del sys.modules[m]
    import workers.db as workers_db
    monkeypatch.setattr(workers_db, "get_engine", lambda: task_engine)
    import workers.tasks.monitoring as monitoring_mod
    return SimpleNamespace(mod=monitoring_mod, engine=task_engine)


@pytest.fixture
def fake_self():
    task_self = MagicMock()
    task_self.request.id = "task-snapshot"
    return task_self


class TestSnapshotBacklogs:
    def test_writes_one_snapshot_with_domain_payload(self, monitoring_task, fake_self):
        engine = monitoring_task.engine
        with Session(engine) as s:
            # never_tried deezer backlog + a linked artwork-missing artist +
            # an active root set + a plain catalog row.
            s.add(
                CatalogEntry(
                    title="Track", artist="A", normalized_key="track - a"
                )
            )
            # BPM analysis candidate: preview + real deezer_id + no bpm + not yet
            # analyzed → bpm_analysis_candidate_filter() matches it. Also both
            # rows below are embedding-ELIGIBLE (has_preview + real deezer_id);
            # one gets an embedding seeded after commit, the other stays missing.
            s.add(
                CatalogEntry(
                    title="Preview",
                    artist="B",
                    normalized_key="preview - b",
                    has_preview=True,
                    deezer_id="dz-preview",
                )
            )
            s.add(
                CatalogEntry(
                    title="Preview2",
                    artist="C",
                    normalized_key="preview2 - c",
                    has_preview=True,
                    deezer_id="dz-preview2",
                    bpm=128,  # not a BPM candidate, but still embedding-eligible
                )
            )
            s.add(
                Artist(name="Linked", normalized_name="linked", deezer_id="dz-1")
            )  # backlog_artwork (has_artwork NULL/False)
            s.add(
                Artist(name="Unlinked", normalized_name="unlinked")
            )  # backlog_link (deezer_id NULL)
            s.add(DJSet(source="trackid", title="Root set"))  # recrawl_backlog
            # C7 albums (L8): one album missing both cover + meta, one complete.
            s.add(Album(title="No cover no meta"))  # missing_cover + missing_meta
            s.add(
                Album(
                    title="Complete",
                    has_artwork=True,
                    record_type="album",
                )
            )
            s.commit()
            # One of the two eligible rows already has an embedding for the
            # frozen v1 model → covered=1, eligible=2, missing=1.
            preview_id = s.execute(
                select(CatalogEntry.id).where(CatalogEntry.title == "Preview")
            ).scalar_one()
            s.add(
                TrackEmbedding(
                    catalog_id=preview_id,
                    model_name=MODEL_NAME,
                    model_version=MODEL_VERSION,
                    embedding=[0.0] * EMBEDDING_DIM,
                )
            )
            s.commit()

        result = monitoring_task.mod.snapshot_backlogs(fake_self)

        # Exactly one snapshot row persisted
        with Session(engine) as s:
            rows = s.execute(select(MetricSnapshot)).scalars().all()
        assert len(rows) == 1
        snap = rows[0]
        assert snap.captured_at is not None

        payload = snap.payload
        # Same object is returned by the task
        assert result == payload
        # Structured by domain
        assert set(payload) == {
            "enrich",
            "artists",
            "sets",
            "catalog",
            "albums",
            "embeddings",
            "integrity",
            "coverage",
        }
        assert set(payload["enrich"]) == {"deezer", "beatport"}
        assert set(payload["enrich"]["deezer"]) == {
            "never_tried",
            "due_retry",
            "cooldown",
            "abandoned",
            "total_missing",
            "total_linked",
        }
        # The seeded rows land in the right buckets
        assert payload["enrich"]["deezer"]["never_tried"] == 1
        assert payload["artists"]["backlog_link"] == 1
        assert payload["artists"]["backlog_artwork"] == 1
        assert payload["sets"]["recrawl_backlog"] == 1
        assert payload["catalog"]["total"] == 3
        # E2.c: only the preview-without-bpm row is a BPM-analysis candidate
        # (Preview2 carries a bpm, so it is not).
        assert payload["catalog"]["bpm_missing"] == 1
        # C9.a embeddings: 2 eligible previews, 1 already vectorised → missing=1.
        assert set(payload["embeddings"]) == {"covered", "eligible", "missing"}
        assert payload["embeddings"]["eligible"] == 2
        assert payload["embeddings"]["covered"] == 1
        assert payload["embeddings"]["missing"] == 1
        assert all(isinstance(payload["embeddings"][k], int) for k in payload["embeddings"])
        # C7/L8 albums: additive block, integer counts.
        assert set(payload["albums"]) == {"missing_cover", "missing_meta", "total"}
        assert payload["albums"]["missing_cover"] == 1
        assert payload["albums"]["missing_meta"] == 1
        assert payload["albums"]["total"] == 2
        assert all(isinstance(payload["albums"][k], int) for k in payload["albums"])
        # Observabilité L1: integrity + coverage additive blocks. The enriched
        # rows (Preview/Preview2) carry no M2M link at all → no name to diverge
        # from; all three rows have a flat artist but no catalog_artists row.
        assert payload["integrity"] == {
            "artist_divergence": 0,
            "missing_m2m_link": 3,
        }
        cov = payload["coverage"]
        assert cov["total"] == 3
        assert cov["deezer"] == {"linked": 2, "abandoned": 0}
        assert cov["beatport"] == {"linked": 0, "abandoned": 0}
        assert cov["bpm"] == {"unknown": 1}  # Preview2 has a bpm, no bpm_source
        assert cov["key"] == {}
        assert cov["preview"] == {"covered": 2}
        assert cov["artwork"] == {"covered": 0}
        assert cov["genres"] == {"covered": 0}
        assert cov["embedding"] == {"covered": 1}
        assert cov["artist_link"] == {"covered": 0}
        assert cov["album"] == {"covered": 0}
        # 8-dim histogram: Track = 0 dims, Preview = deezer+embedding,
        # Preview2 = deezer+bpm → one row at 0, two rows at 2.
        assert cov["completeness"]["0"] == 1
        assert cov["completeness"]["2"] == 2
        assert sum(cov["completeness"].values()) == 3
        # Every seeded row is incomplete → one combo per distinct flag pattern.
        assert len(cov["top_combos"]) == 3
        assert all(set(c) == {"dims", "count"} for c in cov["top_combos"])
        assert sum(c["count"] for c in cov["top_combos"]) == 3

    def test_runs_on_empty_db(self, monitoring_task, fake_self):
        result = monitoring_task.mod.snapshot_backlogs(fake_self)

        with Session(monitoring_task.engine) as s:
            assert len(s.execute(select(MetricSnapshot)).scalars().all()) == 1
        assert result["catalog"]["total"] == 0
        assert result["catalog"]["bpm_missing"] == 0
        assert result["enrich"]["deezer"]["total_missing"] == 0
        assert result["embeddings"] == {"covered": 0, "eligible": 0, "missing": 0}
        # Observabilité L1: empty DB → zeros, empty maps/lists, no exception.
        assert result["integrity"] == {
            "artist_divergence": 0,
            "missing_m2m_link": 0,
        }
        cov = result["coverage"]
        assert cov["total"] == 0
        assert cov["deezer"] == {"linked": 0, "abandoned": 0}
        assert cov["bpm"] == {}
        assert cov["key"] == {}
        assert cov["top_combos"] == []
        assert set(cov["completeness"]) == {str(i) for i in range(9)}
        assert sum(cov["completeness"].values()) == 0

    def test_task_has_no_autoretry(self, monitoring_task):
        # Loop-safe: a transient DB blip is retried next hour, never re-looped.
        assert monitoring_task.mod.snapshot_backlogs.autoretry_for == ()


class TestIntegrityBlock:
    """Observabilité L1: X4 integrity counters, snapshotted hourly (the sync
    twin of the late monitoring_service.get_integrity_counters, removed in L3 —
    the API now reads these from the snapshot payload).

    A frank divergence = enriched row whose folded flat artist and folded first
    M2M name (min position) do not contain each other; an accent-only or
    containment difference is NOT a divergence.
    """

    def test_divergence_fold_and_first_position(self, monitoring_task):
        engine = monitoring_task.engine
        with Session(engine) as s:
            radiohead = Artist(name="Radiohead", normalized_name="radiohead")
            beyonce = Artist(name="Beyonce", normalized_name="beyonce")
            first_act = Artist(name="First Act", normalized_name="first act")
            zed = Artist(name="Zed", normalized_name="zed")
            diverge = CatalogEntry(
                title="T1",
                artist="Björk",
                normalized_key="t1 - bjork",
                deezer_id="dz1",
            )
            accent_twin = CatalogEntry(
                title="T2",
                artist="Beyoncé",
                normalized_key="t2 - beyonce",
                deezer_id="dz2",
            )
            multi = CatalogEntry(
                title="T3",
                artist="First Act",
                normalized_key="t3 - first act",
                beatport_id="bp3",
            )
            unlinked = CatalogEntry(
                title="T4", artist="Solo", normalized_key="t4 - solo"
            )
            s.add_all(
                [radiohead, beyonce, first_act, zed, diverge, accent_twin,
                 multi, unlinked]
            )
            s.flush()
            # diverge: folded "bjork" vs "radiohead" → mutual non-containment.
            s.add(CatalogArtist(catalog_id=diverge.id, artist_id=radiohead.id))
            # accent_twin: differs under lower() but folds equal → no divergence.
            s.add(CatalogArtist(catalog_id=accent_twin.id, artist_id=beyonce.id))
            # multi: the MIN-position name ("First Act") matches the flat one; a
            # wrong ordering would pick "Zed" and wrongly count a divergence.
            s.add(
                CatalogArtist(catalog_id=multi.id, artist_id=zed.id, position=1)
            )
            s.add(
                CatalogArtist(
                    catalog_id=multi.id, artist_id=first_act.id, position=0
                )
            )
            s.commit()

        payload = monitoring_task.mod._run_snapshot_backlogs()

        # Only `diverge` counts; `unlinked` is the only row with a flat artist
        # and no catalog_artists link at all.
        assert payload["integrity"] == {
            "artist_divergence": 1,
            "missing_m2m_link": 1,
        }


class TestCoverageBlock:
    """Observabilité L1: per-dimension coverage + 8-dim completeness matrix."""

    def test_dimensions_histogram_and_combos(self, monitoring_task):
        engine = monitoring_task.engine
        with Session(engine) as s:
            linker = Artist(name="Linker", normalized_name="linker")
            album = Album(title="Full album", deezer_album_id="alb-1")
            full = CatalogEntry(
                title="Full",
                artist="Linker",
                normalized_key="full - linker",
                deezer_id="dz-full",
                beatport_id="bp-full",
                bpm=128,
                bpm_source="beatport",
                key="8A",
                key_source="beatport",
                genres=["Techno"],
                has_artwork=True,
                has_preview=True,
            )
            partial = CatalogEntry(
                title="Partial",
                artist="P",
                normalized_key="partial - p",
                deezer_id="dz-part",
                bpm=120,  # bpm present, bpm_source NULL → "unknown" bucket
            )
            empty = CatalogEntry(
                title="Empty", artist="E", normalized_key="empty - e"
            )
            sentinel = CatalogEntry(
                title="Sentinel",
                artist="S",
                normalized_key="sentinel - s",
                deezer_id="NOT_FOUND",  # sentinel ≠ linked for coverage
            )
            s.add_all([linker, album, full, partial, empty, sentinel])
            s.flush()
            s.add(CatalogArtist(catalog_id=full.id, artist_id=linker.id))
            s.add(CatalogAlbum(catalog_id=full.id, album_id=album.id))
            s.add(
                TrackEmbedding(
                    catalog_id=full.id,
                    model_name=MODEL_NAME,
                    model_version=MODEL_VERSION,
                    embedding=[0.0] * EMBEDDING_DIM,
                )
            )
            # Wrong model version → must NOT count as embedding coverage.
            s.add(
                TrackEmbedding(
                    catalog_id=empty.id,
                    model_name=MODEL_NAME,
                    model_version="other-version",
                    embedding=[0.0] * EMBEDDING_DIM,
                )
            )
            s.commit()

        payload = monitoring_task.mod._run_snapshot_backlogs()

        cov = payload["coverage"]
        assert cov["total"] == 4
        assert cov["deezer"]["linked"] == 2  # full + partial, sentinel excluded
        assert cov["beatport"]["linked"] == 1
        assert cov["bpm"] == {"beatport": 1, "unknown": 1}
        assert cov["key"] == {"beatport": 1}
        assert cov["preview"] == {"covered": 1}
        assert cov["artwork"] == {"covered": 1}
        assert cov["genres"] == {"covered": 1}
        assert cov["embedding"] == {"covered": 1}  # frozen model only
        assert cov["artist_link"] == {"covered": 1}
        assert cov["album"] == {"covered": 1}
        # full = 8/8, partial = deezer+bpm = 2, empty + sentinel = 0.
        assert cov["completeness"]["8"] == 1
        assert cov["completeness"]["2"] == 1
        assert cov["completeness"]["0"] == 2
        assert sum(cov["completeness"].values()) == 4
        # top_combos: INCOMPLETE rows only, count desc — the two 0-dim rows
        # group together and rank first; the complete row never appears.
        assert len(cov["top_combos"]) == 2
        first, second = cov["top_combos"]
        assert first["count"] == 2
        assert not any(first["dims"].values())
        assert second["count"] == 1
        assert second["dims"]["deezer"] is True
        assert second["dims"]["bpm"] is True
        assert set(first["dims"]) == {
            "deezer", "beatport", "bpm", "key", "genres", "artwork",
            "embedding", "artist_link",
        }
        # JSON-serialisable payload: str keys, int/bool leaves.
        assert all(isinstance(k, str) for k in cov["bpm"])
        assert all(
            isinstance(v, bool) for c in cov["top_combos"]
            for v in c["dims"].values()
        )


class TestFluxBudgetAlert:
    """C12 (L8): flux-vs-budget health signal on the Beatport source.

    A live-flux row = enrich_priority >= FLUX_BAND (100), beatport_id NULL,
    beatport_searched_at NULL. When those never-tried flux rows alone exceed the
    Beatport daily budget, the backfill is starved → payload flag + Sentry warn.
    """

    def _add_flux_rows(self, engine, n):
        with Session(engine) as s:
            for i in range(n):
                s.add(
                    CatalogEntry(
                        title=f"Flux{i}",
                        artist="A",
                        normalized_key=f"flux{i} - a",
                        enrich_priority=100,  # == FLUX_BAND, and beatport_* NULL
                    )
                )
            s.commit()

    def test_flux_over_budget_sets_flag_and_alerts(self, monitoring_task, monkeypatch):
        # Tiny budget so 2 flux rows exceed it.
        monkeypatch.setenv("ENRICH_NIGHTLY_BUDGET_BEATPORT", "1")
        self._add_flux_rows(monitoring_task.engine, 2)

        fake_sentry = MagicMock()
        monkeypatch.setitem(sys.modules, "sentry_sdk", fake_sentry)
        monkeypatch.setattr(monitoring_task.mod, "SENTRY_DSN", "fake-dsn")

        payload = monitoring_task.mod._run_snapshot_backlogs()

        bp = payload["enrich"]["beatport"]
        assert bp["flux_never_tried"] == 2
        assert bp["flux_budget"] == 1
        assert bp["flux_over_budget"] is True
        # Sentry warning raised with both numbers in the message.
        assert fake_sentry.capture_message.called
        assert fake_sentry.capture_message.call_args.kwargs.get("level") == "warning"
        msg = fake_sentry.capture_message.call_args.args[0]
        assert "2 never-tried" in msg and "> 1/day" in msg

    def test_flux_within_budget_no_alert(self, monitoring_task, monkeypatch):
        monkeypatch.setenv("ENRICH_NIGHTLY_BUDGET_BEATPORT", "6000")
        self._add_flux_rows(monitoring_task.engine, 2)

        fake_sentry = MagicMock()
        monkeypatch.setitem(sys.modules, "sentry_sdk", fake_sentry)
        monkeypatch.setattr(monitoring_task.mod, "SENTRY_DSN", "fake-dsn")

        payload = monitoring_task.mod._run_snapshot_backlogs()

        bp = payload["enrich"]["beatport"]
        assert bp["flux_never_tried"] == 2
        assert bp["flux_over_budget"] is False
        assert not fake_sentry.capture_message.called

    def test_null_priority_row_is_not_flux(self, monitoring_task, monkeypatch):
        # enrich_priority NULL coalesces to PRIORITY_BASELINE (75 < 100): the row
        # IS a Beatport never-tried backlog entry but NOT a flux row.
        monkeypatch.setenv("ENRICH_NIGHTLY_BUDGET_BEATPORT", "6000")
        with Session(monitoring_task.engine) as s:
            s.add(
                CatalogEntry(
                    title="Baseline",
                    artist="A",
                    normalized_key="baseline - a",
                    # enrich_priority left NULL
                )
            )
            s.commit()

        payload = monitoring_task.mod._run_snapshot_backlogs()

        bp = payload["enrich"]["beatport"]
        assert bp["never_tried"] == 1  # counted as a beatport never-tried row
        assert bp["flux_never_tried"] == 0  # but NOT flux
        assert bp["flux_over_budget"] is False


class TestRetentionPurge:
    """AV3: metric_snapshots + crawl_logs are purged past RETENTION_DAYS."""

    def test_purges_old_rows_keeps_recent(self, monitoring_task, fake_self):
        engine = monitoring_task.engine
        retention_days = monitoring_task.mod.RETENTION_DAYS
        now = datetime.now(timezone.utc)
        old_ts = now - timedelta(days=retention_days + 30)  # well past the cutoff
        recent_ts = now - timedelta(days=10)  # comfortably inside the window

        with Session(engine) as s:
            s.add(MetricSnapshot(captured_at=old_ts, payload={"old": True}))
            s.add(MetricSnapshot(captured_at=recent_ts, payload={"recent": True}))
            s.add(
                CrawlLog(task_type="enrich_catalog", started_at=old_ts, status="success")
            )
            s.add(
                CrawlLog(
                    task_type="enrich_catalog", started_at=recent_ts, status="success"
                )
            )
            s.commit()

        monitoring_task.mod.snapshot_backlogs(fake_self)

        with Session(engine) as s:
            snap_dates = s.execute(
                select(MetricSnapshot.captured_at)
            ).scalars().all()
            log_dates = s.execute(select(CrawlLog.started_at)).scalars().all()

        # No row older than the cutoff survives on either table. SQLite reads
        # tz-aware columns back as naive, so compare on a naive UTC basis.
        def _naive(d):
            return d.replace(tzinfo=None) if d.tzinfo else d

        cutoff = (now - timedelta(days=retention_days)).replace(tzinfo=None)
        assert all(_naive(d) >= cutoff for d in snap_dates), snap_dates
        assert all(_naive(d) >= cutoff for d in log_dates), log_dates
        # The recent seed + the snapshot the run just wrote remain; the old is gone.
        assert len(snap_dates) == 2
        assert len(log_dates) == 1

    def test_purge_is_idempotent_on_second_run(self, monitoring_task, fake_self):
        engine = monitoring_task.engine
        now = datetime.now(timezone.utc)
        old_ts = now - timedelta(days=monitoring_task.mod.RETENTION_DAYS + 30)
        with Session(engine) as s:
            s.add(MetricSnapshot(captured_at=old_ts, payload={"old": True}))
            s.commit()

        monitoring_task.mod.snapshot_backlogs(fake_self)  # purges the old row
        monitoring_task.mod.snapshot_backlogs(fake_self)  # nothing old left to purge

        with Session(engine) as s:
            rows = s.execute(select(MetricSnapshot)).scalars().all()
        # Two runs → two fresh snapshots, the pre-existing old one is gone.
        assert len(rows) == 2
        assert all(r.payload != {"old": True} for r in rows)
