"""E2.c — nightly BPM estimation from Deezer 30s previews (async pipeline).

Twin of the E2.a/E2.b container tool (``docs/e2a-benchmark``, ``worker/bpm_backfill``),
wired into the server runtime: for each catalog entry that has a Deezer preview
but no BPM, resolve the preview URL via the Deezer API, download the 30s MP3,
run Essentia ``RhythmExtractor2013(multifeature)`` OFF the event loop, and write
an ESTIMATED bpm (``bpm_source='analysis'``) only when the extractor's confidence
clears the E2.a gate (``>= min_conf``, default 2.0).

Data-authority invariants (CLAUDE.md #3):
  - ``bpm_source='analysis'`` is the LOWEST authority: written only where
    ``bpm IS NULL``, never over a beatport/rekordbox value, and overwritten by a
    later Beatport run. No ``analysis`` key is ever written (E2.a: NO-GO on key).

Attempt accounting mirrors E1 (``un outage n'est pas une tentative``):
  - a VERDICT (ok / low_conf / no_preview) stamps ``bpm_analyzed_at`` and
    increments ``bpm_analysis_attempts`` so the row is not analyzed forever;
  - a transient network/HTTP/download/decode failure stamps NOTHING, so the row
    is retried by the next nightly run.

Essentia is imported LAZILY inside :func:`_analyze_blocking` (the CI test env has
neither essentia nor ffmpeg): importing this module must never import essentia.
"""

import asyncio
import logging
import os
import tempfile
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session
from workers.async_http import DeezerHTTPError

logger = logging.getLogger(__name__)

# E2.a benchmark gate: keep a BPM only when RhythmExtractor2013 confidence
# clears this threshold (~84% precision over ~82% of tracks). Overridable so ops
# can re-tune without a redeploy.
DEFAULT_MIN_CONF = float(os.environ.get("ANALYSIS_BPM_MIN_CONF", "2.0"))


def select_bpm_candidates(session: Session, limit: int) -> list:
    """Catalog rows eligible for preview BPM estimation, newest first.

    Shares the backlog predicate with the admin card via
    :func:`models.catalog.bpm_analysis_candidate_filter` (has a preview, no bpm,
    a real deezer_id, never analyzed) — one source of truth for "candidate".
    ``id DESC`` = freshness proxy, same ordering as the enrich sweep.
    """
    from models import CatalogEntry
    from models.catalog import bpm_analysis_candidate_filter

    if limit <= 0:
        return []
    return list(
        session.execute(
            select(CatalogEntry)
            .where(*bpm_analysis_candidate_filter())
            .order_by(CatalogEntry.id.desc())
            .limit(limit)
        )
        .scalars()
        .all()
    )


def _analyze_blocking(path: str) -> tuple[float, float]:
    """``(bpm, confidence)`` via Essentia ``RhythmExtractor2013(multifeature)`` at 44.1 kHz.

    Blocking + CPU-bound → ALWAYS run through ``loop.run_in_executor``, never on
    the event loop. Essentia is imported HERE (lazily) so the module import stays
    dependency-free for the CI test env. A FRESH ``MonoLoader`` + extractor per
    call — Essentia algorithm instances are not safe to share across threads.
    """
    import essentia.standard as es

    audio = es.MonoLoader(filename=path, sampleRate=44100)()
    bpm, _beats, conf, _estimates, _intervals = es.RhythmExtractor2013(
        method="multifeature"
    )(audio)
    return float(bpm), float(conf)


def _record_bpm_verdict(entry, bpm: float, conf: float, min_conf: float, now) -> str:
    """Apply a completed analysis VERDICT to ``entry`` (pure, no IO).

    Stamps the attempt in ALL cases (a verdict was reached). Writes the estimated
    bpm only when confidence clears ``min_conf`` AND the entry still has no bpm
    (invariant #3 — never overwrite an authoritative value). Returns the stat
    bucket: ``estimated`` | ``low_conf`` | ``skipped``.
    """
    entry.bpm_analyzed_at = now
    entry.bpm_analysis_attempts = (entry.bpm_analysis_attempts or 0) + 1
    if conf < min_conf:
        return "low_conf"
    if entry.bpm is not None:
        # Defensive: the candidate filter guarantees bpm IS NULL, but if a higher
        # authority landed a value under us, never clobber it (invariant #3).
        return "skipped"
    entry.bpm = round(bpm, 1)
    entry.bpm_source = "analysis"
    return "estimated"


async def _analyze_one(entry, pool, executor, min_conf: float, stats: dict) -> None:
    """Resolve → download → analyze → record for a single catalog entry.

    Any transient failure (Deezer outage, download/decode error) leaves
    ``bpm_analyzed_at`` UNSET so the row is retried next night; only a verdict
    stamps it. No audio is ever persisted — the temp MP3 is deleted right after
    analysis.
    """
    now = datetime.now(timezone.utc)
    try:
        hit = await pool.deezer_get(f"/track/{entry.deezer_id}")
        preview_url = (hit.get("preview") or "").strip()
        if not preview_url:
            # Verdict: Deezer has no preview for this track → stamp so we don't
            # re-resolve it every night (has_preview may be stale).
            entry.bpm_analyzed_at = now
            entry.bpm_analysis_attempts = (entry.bpm_analysis_attempts or 0) + 1
            stats["no_preview"] += 1
            return

        # Throttle the CDN download through a dedicated limiter (NOT the "deezer"
        # API window): unlimited download volume made silent failures scale with
        # the run size (per-IP CDN rate-limiting). See rate_limiter deezer_preview.
        async with pool.limiter.acquire("deezer_preview"):
            audio_bytes = await pool.download_audio(preview_url)
        if not audio_bytes:
            # CDN/network failure on the preview itself → NOT a verdict, retry.
            stats["errors"] += 1
            return

        # Essentia runs off the event loop; the temp MP3 is always deleted.
        loop = asyncio.get_event_loop()
        tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
        try:
            tmp.write(audio_bytes)
            tmp.close()
            bpm, conf = await loop.run_in_executor(
                executor, _analyze_blocking, tmp.name
            )
        finally:
            try:
                os.unlink(tmp.name)
            except OSError:
                pass

        status = _record_bpm_verdict(entry, bpm, conf, min_conf, now)
        stats[status] += 1
    except DeezerHTTPError as e:
        # Deezer outage, not a "no preview": leave bpm_analyzed_at unset so the
        # entry is retried by the next nightly run.
        logger.warning("BPM analysis: Deezer HTTP error for catalog %s: %s", entry.id, e)
        stats["errors"] += 1
    except Exception as e:
        # Download/decode/analysis failure — transient, NOT a verdict, retry.
        logger.warning("BPM analysis failed for catalog %s: %s", entry.id, e)
        stats["errors"] += 1


async def analyze_bpm_batch(
    session: Session,
    entries: list,
    pool,
    executor,
    *,
    min_conf: float = DEFAULT_MIN_CONF,
) -> dict:
    """Estimate BPM for a batch of catalog entries concurrently.

    The rate limiter caps Deezer concurrency; the bounded ``executor`` caps the
    CPU analysis width so downloading the next preview overlaps analyzing the
    previous one. Mutates the entries in place — the caller commits.

    Args:
        entries: CatalogEntry objects (has_preview, no bpm, real deezer_id)
        pool: entered HttpPool instance
        executor: ThreadPoolExecutor for the blocking Essentia analysis
        min_conf: confidence gate below which no bpm is written
    """
    stats = {
        "estimated": 0,
        "low_conf": 0,
        "no_preview": 0,
        "skipped": 0,
        "errors": 0,
    }
    await asyncio.gather(
        *[_analyze_one(e, pool, executor, min_conf, stats) for e in entries]
    )
    return stats
