"""Celery task: hourly time-series snapshot of enrichment/crawl backlog sizes.

The throughput / error / duration history already lives in ``crawl_logs`` (every
run writes its stats there). The one thing it cannot give is the *size* of each
backlog sampled over time — that is what this task adds, as a single
``metric_snapshots`` row per run.
"""

import logging
import os
import sys
from datetime import datetime, timedelta, timezone

from workers.celery_app import celery_app

logger = logging.getLogger(__name__)

# Artist deezer_id sentinel for "confirmed absent from Deezer" — a non-NULL
# value, so it never falls into the id-missing (link) backlog on its own.
_ARTIST_NOT_FOUND = "NOT_FOUND"

# Retention window (AV3) for the append-only time-series tables purged by this
# task: metric_snapshots + crawl_logs grow one row per run forever. ~13 months
# keeps a full year of history plus a month of slack for year-over-year reads.
RETENTION_DAYS = 396

# C12 (L8) — priority band that marks a catalog row as "live-flux" (a freshly
# crawled live set, stamped enrich_priority = FLUX_PRIORITY = 100 by
# tasks/sets.py). Redefined locally (same C12_FLUX_PRIORITY env default 100) on
# purpose: importing workers.tasks.sets just to read one int would drag in its
# whole celery/asyncio/importer surface. Kept in sync with tasks.sets.FLUX_PRIORITY
# by reading the same env var. A row with enrich_priority NULL coalesces to
# PRIORITY_BASELINE (75 < 100) → correctly NOT flux.
FLUX_BAND = int(os.environ.get("C12_FLUX_PRIORITY", "100"))

# Sentry Cron monitor for this hourly heartbeat. If the check-in stops arriving
# — i.e. the celery-queue worker (diggy_worker) died and stopped sampling, as
# happened 2026-08-10→14 when a wedged worker left a ~90 h hole in
# metric_snapshots with NO alert — Sentry raises a "missed check-in" issue.
# Self-upserting via monitor_config; a no-op when SENTRY_DSN is unset (guarded)
# and in tests (which call _run_snapshot_backlogs directly).
SENTRY_DSN = os.environ.get("SENTRY_DSN", "")
_SENTRY_MONITOR_SLUG = "snapshot-backlogs"
_SENTRY_MONITOR_CONFIG = {
    "schedule": {"type": "crontab", "value": "30 * * * *"},
    "checkin_margin": 10,  # minutes late tolerated before "missed"
    "max_runtime": 10,  # minutes before "timed out"
    "timezone": "Etc/UTC",
    "failure_issue_threshold": 1,
    "recovery_threshold": 1,
}


@celery_app.task(name="workers.tasks.snapshot_backlogs", bind=True)
def snapshot_backlogs(self):
    """Sample every enrichment/crawl backlog and persist one MetricSnapshot row.

    Read-only over the domain tables (no external API), so it is loop-safe and
    carries NO autoretry — a transient DB blip is simply retried next hour.

    Wrapped in a Sentry Cron check-in (when SENTRY_DSN is set) so a silent stop
    of this heartbeat is alerted proactively, instead of only surfacing as a gap
    on the admin monitoring chart once someone looks.
    """
    if SENTRY_DSN:
        from sentry_sdk.crons import monitor

        with monitor(
            monitor_slug=_SENTRY_MONITOR_SLUG, monitor_config=_SENTRY_MONITOR_CONFIG
        ):
            return _run_snapshot_backlogs()
    return _run_snapshot_backlogs()


def _run_snapshot_backlogs():
    from sqlalchemy import and_, delete, func, select
    from sqlalchemy.orm import Session

    sys.path.insert(0, "/app")
    from models import (
        MODEL_NAME,
        MODEL_VERSION,
        Album,
        Artist,
        CatalogEntry,
        CrawlLog,
        DJSet,
        MetricSnapshot,
        TrackEmbedding,
        bpm_analysis_candidate_filter,
    )
    from workers.db import get_engine
    from workers.enrichment import count_enrich_backlog
    from workers.tasks.catalog import _nightly_budget

    engine = get_engine()
    now = datetime.now(timezone.utc)

    with Session(engine) as session:

        def _count(count_col, *predicates) -> int:
            return (
                session.execute(
                    select(func.count(count_col)).where(*predicates)
                ).scalar()
                or 0
            )

        # C9.a embeddings coverage. Eligible = rows with a Deezer preview to embed
        # (real deezer_id, not the NOT_FOUND sentinel). Covered = already
        # vectorised for the frozen v1 model. `missing` mirrors the backfill's own
        # PULL (eligible LEFT JOIN track_embeddings … te.id IS NULL) so the
        # "à vectoriser" curve burns down in lockstep with the local salvos, rather
        # than the cheaper eligible-covered which would drift if an embedding
        # outlives an eligibility change.
        _emb_eligible = (
            CatalogEntry.has_preview.is_(True),
            CatalogEntry.deezer_id.isnot(None),
            CatalogEntry.deezer_id != "NOT_FOUND",
        )
        _emb_model = (
            TrackEmbedding.model_name == MODEL_NAME,
            TrackEmbedding.model_version == MODEL_VERSION,
        )
        emb_eligible = _count(CatalogEntry.id, *_emb_eligible)
        emb_covered = _count(TrackEmbedding.id, *_emb_model)
        emb_missing = (
            session.execute(
                select(func.count(CatalogEntry.id))
                .outerjoin(
                    TrackEmbedding,
                    and_(
                        TrackEmbedding.catalog_id == CatalogEntry.id, *_emb_model
                    ),
                )
                .where(*_emb_eligible, TrackEmbedding.id.is_(None))
            ).scalar()
            or 0
        )

        # C12 (L8) — flux-vs-budget health signal on the Beatport source. The
        # daily live-set flux stamps fresh catalog rows at FLUX_BAND priority; if
        # those never-tried flux rows ALONE exceed the Beatport daily budget, the
        # backfill never gets a turn AND the backlog keeps growing. Reuse
        # count_enrich_backlog with priority_floor=FLUX_BAND so the count is
        # EXACTLY the never-tried predicate the priority-floored drain would pick
        # up (beatport_id NULL + never searched + coalesce(enrich_priority,
        # PRIORITY_BASELINE) >= FLUX_BAND). This is a SIGNAL only — no action.
        beatport_backlog = count_enrich_backlog(session, source="beatport", now=now)
        flux_never_tried = count_enrich_backlog(
            session, source="beatport", now=now, priority_floor=FLUX_BAND
        )["never_tried"]
        beatport_budget = _nightly_budget("beatport")
        flux_over_budget = flux_never_tried > beatport_budget
        # Additive keys on the existing beatport dict (older snapshots don't carry
        # them; the front stays .get()/Number.isFinite defensive). Always written
        # — not only on alert — so the curve is historised for the admin page.
        beatport_backlog["flux_never_tried"] = flux_never_tried
        beatport_backlog["flux_budget"] = beatport_budget
        beatport_backlog["flux_over_budget"] = flux_over_budget

        payload = {
            "enrich": {
                "deezer": count_enrich_backlog(session, source="deezer", now=now),
                "beatport": beatport_backlog,
            },
            "artists": {
                # deezer_id IS NULL already excludes the NOT_FOUND sentinel
                # (a non-NULL value), so these are the artists still to link.
                "backlog_link": _count(Artist.id, Artist.deezer_id.is_(None)),
                # Linked (real id, not the sentinel) but still missing artwork.
                # has_artwork is nullable with no server_default → isnot(True)
                # counts both False and NULL (mirror of tasks/artists.py).
                "backlog_artwork": _count(
                    Artist.id,
                    Artist.deezer_id.isnot(None),
                    Artist.deezer_id != _ARTIST_NOT_FOUND,
                    Artist.has_artwork.isnot(True),
                ),
            },
            "sets": {
                # Root sets (parent_set_id IS NULL) still eligible for re-crawl.
                "recrawl_backlog": _count(
                    DJSet.id,
                    DJSet.parent_set_id.is_(None),
                    DJSet.recrawl_status != "final",
                ),
                # C8: TrackID sets flagged low-trust (mostly ID, no source_url,
                # placeholder). Hidden/excluded everywhere; tracked here so its
                # evolution shows up on the monitoring page — every (re-)import
                # recomputes the flag, so the count drifts over time.
                "unreliable": _count(DJSet.id, DJSet.unreliable.is_(True)),
            },
            "catalog": {
                "total": _count(CatalogEntry.id),
                # BPM analysis backlog (E2.c): time-series twin of the live
                # count exposed by /admin/backlog. Same shared predicate
                # (bpm_analysis_candidate_filter): preview but no BPM, real
                # deezer_id, never analyzed.
                "bpm_missing": _count(
                    CatalogEntry.id, *bpm_analysis_candidate_filter()
                ),
            },
            # C7 albums (L8): backfill cron rattrape covers + record_type/
            # release_date/label. Additive key — anciens snapshots ne la portent
            # pas, le front garde Number.isFinite/.get() défensif.
            "albums": {
                # has_artwork nullable, sans server_default → isnot(True) compte
                # False ET NULL (null-safe, comme le bloc artists).
                "missing_cover": _count(Album.id, Album.has_artwork.isnot(True)),
                "missing_meta": _count(Album.id, Album.record_type.is_(None)),
                "total": _count(Album.id),
            },
            # C9.a audio embeddings coverage. Additive block — older snapshots
            # don't carry it, the front keeps Number.isFinite/.get() defensive.
            # `missing` (LEFT JOIN) feeds the burn-down curve, covered/eligible the
            # coverage-% tile.
            "embeddings": {
                "covered": emb_covered,
                "eligible": emb_eligible,
                "missing": emb_missing,
            },
        }

        session.add(MetricSnapshot(captured_at=now, payload=payload))
        session.commit()

    logger.info("snapshot_backlogs wrote a metric_snapshots row at %s", now)

    # C12 (L8) — raise a Sentry warning when the live-set flux alone would starve
    # the Beatport backfill. Same guard/style as the rest of the worker (no-op
    # when SENTRY_DSN is unset, e.g. in tests calling _run_snapshot_backlogs
    # directly). Signal only: nothing is throttled or rescheduled here.
    if flux_over_budget and SENTRY_DSN:
        import sentry_sdk

        sentry_sdk.capture_message(
            "C12 flux backlog exceeds Beatport budget: "
            f"{flux_never_tried} never-tried flux rows (priority >= {FLUX_BAND}) "
            f"> {beatport_budget}/day budget — backfill starved, backlog will grow",
            level="warning",
        )

    # Retention purge (AV3): metric_snapshots + crawl_logs are append-only and
    # would grow without bound. Drop everything older than RETENTION_DAYS. This
    # is a SEPARATE step run AFTER the snapshot is committed above, so a purge
    # failure never costs us the freshly-written snapshot (it stays committed).
    # Idempotent by construction: the next run finds nothing old enough left.
    # admin_audit_log is deliberately NOT purged (audit trail kept indefinitely).
    cutoff = now - timedelta(days=RETENTION_DAYS)
    try:
        with Session(engine) as session:
            purged_snapshots = session.execute(
                delete(MetricSnapshot).where(MetricSnapshot.captured_at < cutoff)
            ).rowcount
            purged_logs = session.execute(
                delete(CrawlLog).where(CrawlLog.started_at < cutoff)
            ).rowcount
            session.commit()
        logger.info(
            "snapshot_backlogs purged %d metric_snapshots + %d crawl_logs "
            "older than %s",
            purged_snapshots or 0,
            purged_logs or 0,
            cutoff,
        )
    except Exception:
        # A purge blip must never mask an already-written snapshot; retried next
        # hour. No autoretry on this task, so we swallow and log rather than fail.
        logger.warning(
            "snapshot_backlogs retention purge failed (snapshot kept)",
            exc_info=True,
        )

    return payload
