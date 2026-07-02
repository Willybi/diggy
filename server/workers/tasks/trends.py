"""
Celery task for computing radar trend scores (v2).

Formula v2:
  base_score = SUM(decay * source_weight * size_weight)
  velocity   = recent_7d / max(previous_7d, 1) - 1   (clamped 0..5)
  convergence = 1 + 0.3 * (distinct_sources - 1)
  final      = base_score * convergence * (1 + 0.5 * velocity)

Rank computed per genre family and globally.
"""

import logging

from workers.celery_app import celery_app

logger = logging.getLogger(__name__)

# Root genres -> pillar (mirrors genre_service._ROOT_TO_PILLAR)
_ROOT_TO_PILLAR = {
    "house music": "house",
    "disco": "house",
    "UK garage": "house",
    "techno": "techno",
    "trance": "trance",
    "drum and bass": "dnb",
    "dubstep": "dnb",
    "breakbeat": "dnb",
    "hardcore": "hardcore",
    "hard dance": "harddance",
}


def _build_pillar_cache(session):
    """Build genre_name -> pillar mapping from genre_nodes/edges/mappings (sync)."""
    from sqlalchemy import text

    root_labels = list(_ROOT_TO_PILLAR.keys())
    rows = session.execute(
        text("""
        WITH RECURSIVE mapped AS (
            SELECT gm.raw_name, gm.node_id, gn.label AS node_label
            FROM genre_mappings gm
            JOIN genre_nodes gn ON gn.id = gm.node_id
        ),
        anc AS (
            SELECT m.raw_name, m.node_id, ge.to_node_id AS ancestor_id, 1 AS depth
            FROM mapped m
            JOIN genre_edges ge ON ge.from_node_id = m.node_id AND ge.type = 'parent'
            UNION ALL
            SELECT a.raw_name, a.node_id, ge.to_node_id, a.depth + 1
            FROM anc a
            JOIN genre_edges ge ON ge.from_node_id = a.ancestor_id AND ge.type = 'parent'
            WHERE a.depth < 10
        ),
        ancestor_match AS (
            SELECT a.raw_name, gn.label AS ancestor_label, MIN(a.depth) AS depth
            FROM anc a
            JOIN genre_nodes gn ON gn.id = a.ancestor_id
            WHERE gn.label = ANY(:root_labels)
            GROUP BY a.raw_name, gn.label
        ),
        best AS (
            SELECT DISTINCT ON (raw_name) raw_name, ancestor_label, depth
            FROM ancestor_match
            ORDER BY raw_name, depth
        )
        SELECT m.raw_name, m.node_label,
               b.ancestor_label, b.depth AS ancestor_depth
        FROM mapped m
        LEFT JOIN best b ON b.raw_name = m.raw_name
    """),
        {"root_labels": root_labels},
    ).fetchall()

    cache = {}
    for r in rows:
        if r.node_label in _ROOT_TO_PILLAR:
            cache[r.raw_name] = _ROOT_TO_PILLAR[r.node_label]
        elif r.ancestor_label and r.ancestor_label in _ROOT_TO_PILLAR:
            cache[r.raw_name] = _ROOT_TO_PILLAR[r.ancestor_label]
        else:
            cache[r.raw_name] = "autres"

    logger.info("Trend pillar cache: %d genres", len(cache))
    return cache


def _genre_to_family(genres, pillar_cache):
    """Return the family for a list of genre names. Uses first match."""
    if not genres:
        return None
    for g in genres:
        family = pillar_cache.get(g)
        if family and family != "autres":
            return family
    # If all mapped to "autres" or not found, use first mapping
    return pillar_cache.get(genres[0])


@celery_app.task(
    name="workers.tasks.compute_trends",
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 60},
    retry_backoff=True,
)
def compute_trends(self, window_days=30):
    """Compute trend scores v2 for radar catalog entries."""
    import sys

    from sqlalchemy import text
    from sqlalchemy.orm import Session
    from workers.db import get_engine

    sys.path.insert(0, "/app")

    engine = get_engine()
    with Session(engine) as session:
        from workers.crawl_logger import CrawlLogger

        with CrawlLogger(
            session, task_type="compute_trends", celery_task_id=self.request.id
        ) as clog:
            # Build pillar cache for genre->family mapping
            try:
                pillar_cache = _build_pillar_cache(session)
            except Exception:
                logger.warning("Could not build pillar cache, families will be null")
                pillar_cache = {}

            # Main query: scores + velocity in a single pass
            rows = session.execute(
                text("""
                WITH detections AS (
                    -- Radar tracks (playlists surveillées)
                    SELECT
                        rt.catalog_id,
                        'radar:' || rt.watched_entity_id::text AS entity_key,
                        rt.source,
                        rt.detected_at,
                        rt.is_initial_detection,
                        we.type AS entity_type,
                        we.track_count,
                        c.genres,
                        c.release_date
                    FROM radar_tracks rt
                    JOIN watched_entities we ON we.id = rt.watched_entity_id
                    JOIN catalog c ON c.id = rt.catalog_id
                    WHERE rt.catalog_id IS NOT NULL
                      AND rt.detected_at >= NOW() - MAKE_INTERVAL(days => :window)
                      AND rt.removed_at IS NULL

                    UNION ALL

                    -- Set tracks (tracklists DJ — poids 3x)
                    SELECT
                        st.catalog_id,
                        'set:' || st.set_id::text AS entity_key,
                        'set' AS source,
                        COALESCE(s.played_date::timestamptz, s.created_at) AS detected_at,
                        false AS is_initial_detection,
                        'set' AS entity_type,
                        (SELECT COUNT(*) FROM set_tracks st2 WHERE st2.set_id = s.id) AS track_count,
                        c.genres,
                        c.release_date
                    FROM set_tracks st
                    JOIN sets s ON s.id = st.set_id
                    JOIN catalog c ON c.id = st.catalog_id
                    WHERE st.catalog_id IS NOT NULL
                      AND COALESCE(s.played_date::timestamptz, s.created_at)
                          >= NOW() - MAKE_INTERVAL(days => :window)
                ),
                scores AS (
                    SELECT
                        catalog_id,
                        genres,
                        COUNT(DISTINCT source) AS source_count,
                        SUM(
                            POWER(0.5, EXTRACT(EPOCH FROM (NOW() - detected_at))
                                       / 86400.0 / 14.0)
                            * CASE WHEN entity_type = 'set' THEN 3.0 ELSE 1.0 END
                            * (1.0 / SQRT(GREATEST(track_count, 1)))
                        )
                        -- Freshness: non-linear decay by release age
                        -- 0-5y: 1.0→0.70 | 5-20y: 0.70→0.50 | 20y+: 0.50→0.10 floor
                        * CASE
                            WHEN release_date IS NULL THEN 1.0
                            WHEN EXTRACT(EPOCH FROM (NOW() - release_date::timestamptz)) / 86400.0 / 365.0 <= 5
                              THEN 1.0 - 0.06 * EXTRACT(EPOCH FROM (NOW() - release_date::timestamptz)) / 86400.0 / 365.0
                            WHEN EXTRACT(EPOCH FROM (NOW() - release_date::timestamptz)) / 86400.0 / 365.0 <= 20
                              THEN 0.70 - (0.20 / 15.0) * (EXTRACT(EPOCH FROM (NOW() - release_date::timestamptz)) / 86400.0 / 365.0 - 5)
                            ELSE GREATEST(0.50 - 0.01 * (EXTRACT(EPOCH FROM (NOW() - release_date::timestamptz)) / 86400.0 / 365.0 - 20), 0.10)
                          END
                        AS base_score,
                        COUNT(DISTINCT entity_key) AS detection_count
                    FROM detections
                    GROUP BY catalog_id, genres, release_date
                ),
                velocity AS (
                    SELECT
                        catalog_id,
                        COUNT(*) FILTER (
                            WHERE detected_at >= NOW() - INTERVAL '7 days'
                              AND NOT is_initial_detection
                        ) AS recent,
                        COUNT(*) FILTER (
                            WHERE detected_at >= NOW() - INTERVAL '14 days'
                              AND detected_at < NOW() - INTERVAL '7 days'
                              AND NOT is_initial_detection
                        ) AS previous
                    FROM detections
                    GROUP BY catalog_id
                )
                SELECT
                    s.catalog_id,
                    s.genres,
                    s.detection_count,
                    s.source_count,
                    s.base_score
                        * (1 + 0.3 * (s.source_count - 1))
                        * (1 + 0.5 * LEAST(
                            GREATEST(
                                v.recent::float / GREATEST(v.previous, 1) - 1,
                                0
                            ), 5
                          ))
                    AS trend_score,
                    LEAST(
                        GREATEST(
                            v.recent::float / GREATEST(v.previous, 1) - 1,
                            0
                        ), 5
                    ) AS velocity
                FROM scores s
                LEFT JOIN velocity v ON v.catalog_id = s.catalog_id
            """),
                {"window": window_days},
            ).fetchall()

            if not rows:
                clog.set_stats({"upserted": 0})
                return {"upserted": 0}

            # Assign family + compute ranks
            from datetime import datetime, timezone

            from models import RadarTrend
            from sqlalchemy.dialects.postgresql import insert as pg_insert

            now = datetime.now(timezone.utc)

            # Build scored entries with family
            entries = []
            for r in rows:
                genres = r.genres if r.genres else []
                family = _genre_to_family(genres, pillar_cache)
                entries.append({
                    "catalog_id": r.catalog_id,
                    "trend_score": round(r.trend_score, 4),
                    "window_days": window_days,
                    "detection_count": r.detection_count,
                    "source_count": r.source_count,
                    "velocity": round(r.velocity or 0, 4),
                    "family": family,
                    "computed_at": now,
                })

            # Sort by score desc for global rank
            entries.sort(key=lambda e: e["trend_score"], reverse=True)
            for i, e in enumerate(entries, 1):
                e["rank_global"] = i

            # Rank within each family
            from collections import defaultdict

            by_family = defaultdict(list)
            for e in entries:
                if e["family"]:
                    by_family[e["family"]].append(e)
            for family_entries in by_family.values():
                # Already sorted by score desc (global sort)
                for i, e in enumerate(family_entries, 1):
                    e["rank_in_family"] = i

            # Entries without family get no family rank
            for e in entries:
                e.setdefault("rank_in_family", None)

            # UPSERT
            stmt = pg_insert(RadarTrend).values(entries)
            stmt = stmt.on_conflict_do_update(
                index_elements=["catalog_id"],
                set_={
                    "trend_score": stmt.excluded.trend_score,
                    "window_days": stmt.excluded.window_days,
                    "detection_count": stmt.excluded.detection_count,
                    "source_count": stmt.excluded.source_count,
                    "velocity": stmt.excluded.velocity,
                    "family": stmt.excluded.family,
                    "rank_in_family": stmt.excluded.rank_in_family,
                    "rank_global": stmt.excluded.rank_global,
                    "computed_at": stmt.excluded.computed_at,
                },
            )
            session.execute(stmt)
            session.commit()

            logger.info("compute_trends v2: upserted %d entries", len(entries))
            clog.set_stats({"upserted": len(entries)})

    return {"upserted": len(entries)}
