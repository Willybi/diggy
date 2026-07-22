# Re-export all tasks for Celery autodiscover
from workers.tasks.artists import (
    backfill_multi_artists,
    check_followed_artists,
    fetch_artist_artworks,
    link_artists_deezer,
    link_set_artists,
    sync_artists,
)
from workers.tasks.catalog import enrich_catalog, enrich_catalog_beatport
from workers.tasks.genres import (
    finalize_reclassify,
    reclassify_all_genres,
    reclassify_genres_chunk,
    reclassify_genres_error,
)
from workers.tasks.import_rb import import_rekordbox_xml
from workers.tasks.monitoring import snapshot_backlogs
from workers.tasks.radar import crawl_radar, crawl_single_playlist
from workers.tasks.sets import (
    backfill_trackid_sets,
    crawl_trackid_latest,
    enrich_set_tracks,
    recrawl_incomplete_sets,
    resolve_set_tracks,
)
from workers.tasks.trends import compute_trends

__all__ = [
    "crawl_radar",
    "crawl_single_playlist",
    "enrich_catalog",
    "enrich_catalog_beatport",
    "resolve_set_tracks",
    "enrich_set_tracks",
    "recrawl_incomplete_sets",
    "crawl_trackid_latest",
    "backfill_trackid_sets",
    "sync_artists",
    "fetch_artist_artworks",
    "link_artists_deezer",
    "link_set_artists",
    "reclassify_genres_chunk",
    "reclassify_all_genres",
    "finalize_reclassify",
    "reclassify_genres_error",
    "compute_trends",
    "import_rekordbox_xml",
    "backfill_multi_artists",
    "check_followed_artists",
    "snapshot_backlogs",
]
