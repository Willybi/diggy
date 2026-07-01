# Re-export all tasks for Celery autodiscover
from workers.tasks.artists import fetch_artist_artworks, link_set_artists, sync_artists
from workers.tasks.catalog import enrich_catalog, enrich_catalog_beatport
from workers.tasks.genres import reclassify_all_genres, reclassify_genres_chunk
from workers.tasks.radar import crawl_radar, crawl_single_playlist
from workers.tasks.sets import (
    crawl_followed_sets,
    enrich_set_tracks,
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
    "crawl_followed_sets",
    "sync_artists",
    "fetch_artist_artworks",
    "link_set_artists",
    "reclassify_genres_chunk",
    "reclassify_all_genres",
    "compute_trends",
]
