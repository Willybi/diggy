# A2 -- Refactor Workers

## Objectif

Scinder `server/workers/tasks.py` (1897 LOC, 13 tasks Celery) en modules thematiques
dans `server/workers/tasks/`. Chaque module est independant et testable.

## Architecture cible

```
server/workers/
  tasks.py                    SUPPRIMER (remplace par tasks/)
  tasks/
    __init__.py               Re-exports pour Celery autodiscover
    radar.py                  crawl_radar, crawl_single_playlist, _crawl_single_playlist_inner
    catalog.py                enrich_catalog, enrich_catalog_beatport
    sets.py                   resolve_set_tracks, enrich_set_tracks, crawl_followed_sets
    artists.py                sync_artists, fetch_artist_artworks, link_set_artists
    genres.py                 reclassify_genres_chunk, reclassify_all_genres
    trends.py                 compute_trends
  celery_app.py               NE PAS MODIFIER (sauf autodiscover si necessaire)
  source_clients.py           NE PAS MODIFIER
  enrichment.py               NE PAS MODIFIER
  async_http.py               NE PAS MODIFIER
  rate_limiter.py             NE PAS MODIFIER
  crawl_logger.py             NE PAS MODIFIER
  db.py                       NE PAS MODIFIER
```

## Repartition des tasks

### tasks/radar.py (~340 LOC)

Tasks :
- `crawl_radar` (ligne 21-91) : orchestrateur, liste les playlists, dispatch crawl_single_playlist
- `crawl_single_playlist` (ligne 94-118) : acquiert lock Redis, appelle inner
- `_crawl_single_playlist_inner` (ligne 121-368) : helper, fetch playlist, bulk create catalog, enrichissement async

Imports necessaires :
```python
from workers.celery_app import celery_app
from workers.source_clients import get_fetchers
from workers.db import get_engine, bulk_get_or_create_catalog, bulk_insert_radar_tracks
from workers.crawl_logger import CrawlLogger
from workers.enrichment import enrich_deezer_batch, enrich_beatport_batch
from workers.async_http import HttpPool
from workers.rate_limiter import RateLimiter
```

### tasks/catalog.py (~200 LOC)

Tasks :
- `enrich_catalog` (ligne 618-713) : enrichit les entries sans deezer_id via Deezer (async, 5 paralleles)
- `enrich_catalog_beatport` (ligne 1488-1589) : enrichit via Beatport scraping (async, 2 scrapers, cache Redis)

### tasks/sets.py (~280 LOC)

Tasks :
- `resolve_set_tracks` (ligne 369-509) : resout set_tracks -> catalog via bulk lookup + enrichissement
- `enrich_set_tracks` (ligne 510-617) : enrichit catalog entries liees aux sets
- `crawl_followed_sets` (ligne 1360-1487) : re-crawl sets suivis avec tracklists incompletes

### tasks/artists.py (~650 LOC)

Tasks :
- `sync_artists` (ligne 714-1124) : Phase A dedup local + Phase B disambiguation Deezer (la plus grosse task, 411 LOC)
- `fetch_artist_artworks` (ligne 1125-1272) : Pass 1 link Deezer IDs + Pass 2 download artworks MinIO
- `link_set_artists` (ligne 1273-1359) : parse titres sets -> extraction noms artistes -> matching

### tasks/genres.py (~235 LOC)

Tasks :
- `reclassify_genres_chunk` (ligne 1590-1742) : reclassifie un chunk (Beatport -> fallback Deezer)
- `reclassify_all_genres` (ligne 1743-1822) : orchestrateur, split en N chunks, dispatch en parallele

### tasks/trends.py (~75 LOC)

Tasks :
- `compute_trends` (ligne 1823-1897) : calcul score tendance decay half-life 14 jours

### tasks/__init__.py

```python
# Re-export all tasks for Celery autodiscover
from workers.tasks.radar import crawl_radar, crawl_single_playlist
from workers.tasks.catalog import enrich_catalog, enrich_catalog_beatport
from workers.tasks.sets import resolve_set_tracks, enrich_set_tracks, crawl_followed_sets
from workers.tasks.artists import sync_artists, fetch_artist_artworks, link_set_artists
from workers.tasks.genres import reclassify_genres_chunk, reclassify_all_genres
from workers.tasks.trends import compute_trends

__all__ = [
    "crawl_radar", "crawl_single_playlist",
    "enrich_catalog", "enrich_catalog_beatport",
    "resolve_set_tracks", "enrich_set_tracks", "crawl_followed_sets",
    "sync_artists", "fetch_artist_artworks", "link_set_artists",
    "reclassify_genres_chunk", "reclassify_all_genres",
    "compute_trends",
]
```

## Celery autodiscover

Verifier dans `celery_app.py` que l'autodiscover pointe vers le bon module.
Actuellement (ligne ~85) :
```python
celery_app.autodiscover_tasks(["workers"])
```

Modifier si necessaire pour :
```python
celery_app.autodiscover_tasks(["workers.tasks"])
```

Ou bien s'assurer que `tasks/__init__.py` re-exporte tout pour que `workers.tasks` reste le point d'entree.

Le beat schedule dans `celery_app.py` reference les tasks par nom complet :
```python
"task": "workers.tasks.crawl_radar"
```
Verifier que ces noms correspondent toujours apres le split. Si les tasks sont decorees avec
`@celery_app.task(name="workers.tasks.crawl_radar")`, le nom explicite garantit la compatibilite.
Sinon, ajouter `name=` explicitement a chaque task pour eviter les regressions.

## Retry policies

Verifier que toutes les 13 tasks ont une retry policy. Pattern attendu :
```python
@celery_app.task(bind=True, autoretry_for=(Exception,), max_retries=3, retry_backoff=True)
```

Si certaines tasks n'ont pas de retry, l'ajouter. Ne pas ajouter de retry aux orchestrateurs
(`crawl_radar`, `reclassify_all_genres`) qui dispatched d'autres tasks.

## Tests

Les tests existants dans `tests/worker/` (48 tests, 6 fichiers) ne doivent PAS casser.
Verifier les imports dans :
- `tests/worker/test_resolve_set_tracks.py` -- importe depuis `workers.tasks`
- `tests/worker/test_tasks_crawl_sets.py` -- importe depuis `workers.tasks`
- `tests/worker/test_tasks_link_set_artists.py` -- importe depuis `workers.tasks`

Si les tests importent `from workers.tasks import X`, le `__init__.py` avec les re-exports
doit garantir la compatibilite.

Ajouter 20+ tests supplementaires dans `tests/worker/` :
- Scenarios d'echec (DB down, API timeout, lock Redis deja pris)
- Orchestration (fan-out crawl_radar -> crawl_single_playlist)
- Retry behavior

## Procedure

1. Creer `server/workers/tasks/` avec `__init__.py`
2. Copier chaque groupe de tasks dans son module
3. Ajuster les imports internes (chaque module importe ce dont il a besoin)
4. Mettre a jour `__init__.py` avec les re-exports
5. Verifier/ajouter `name=` explicite sur chaque `@celery_app.task`
6. Supprimer l'ancien `server/workers/tasks.py`
7. Verifier autodiscover dans `celery_app.py`
8. Lancer les tests

## Verification

```bash
# Modules existent
ls server/workers/tasks/

# L'ancien fichier n'existe plus
test ! -f server/workers/tasks.py

# Tests existants passent
pytest tests/worker/ -v

# Tous les tests passent
pytest tests/ -v

# Ruff clean
ruff check server/

# Import check : celery peut trouver les tasks
python -c "from workers.tasks import crawl_radar, sync_artists, compute_trends; print('OK')"
```

## Contraintes

- Code en anglais
- Ne PAS modifier celery_app.py sauf autodiscover si necessaire
- Ne PAS modifier les autres modules workers (source_clients, enrichment, etc.)
- Ne PAS changer la logique metier des tasks, uniquement deplacer
- Garder les memes noms de tasks Celery (important pour le beat schedule)
- Les imports lazy (dans les fonctions) restent lazy -- ne pas les remonter en top-level
