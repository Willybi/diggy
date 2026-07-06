# A1 -- Service Layer Backend

## Objectif

Extraire la logique metier des routers FastAPI dans des services testables.
Chaque endpoint doit devenir un passe-plat de 10-20 lignes : validation -> appel service -> response.
Les services sont des fonctions async pures (pas de dependance FastAPI).

## Architecture cible

```
server/api/
  services/
    __init__.py
    artist_service.py      (sync, flags, merge, linking, stats)
    catalog_service.py     (list, detail, preview, queries complexes)
    genre_service.py       (hierarchie, classification, neighbors, pillar cache)
    radar_service.py       (listing enrichi, state management, opinion sync)
    image_service.py       (S3 unifie -- remplace la duplication storage.py / deezer_enrich.py)
  routers/                 (alleges, chaque endpoint = 10-20 LOC)
```

## Routers a refactorer

### 1. admin.py (864 LOC -> ~250 LOC)

Endpoints complexes a extraire vers `artist_service.py` :

| Endpoint | Ligne | LOC | Methode service |
|----------|-------|-----|-----------------|
| `link_artist_deezer` | 188 | 153 | `artist_service.link_to_deezer(db, artist_id, deezer_id)` |
| `resolve_flag` | 406 | 63 | `artist_service.resolve_flag(db, flag_id, action)` |
| `reset_beatport` | 506 | 43 | `artist_service.reset_beatport(db, catalog_id)` |
| `enrich_single_beatport` | 551 | 48 | `artist_service.enrich_single_beatport(db, catalog_id)` |
| `deezer_genre_lookup` | 601 | 42 | `genre_service.lookup_deezer_genres(db, catalog_id)` |
| `fetch_all_playlist_artworks` | 759 | 48 | `image_service.fetch_playlist_artworks(db, playlist_ids)` |
| `get_crawl_logs` | 812 | 52 | `catalog_service.get_crawl_logs(db, page, filter)` |

Les endpoints simples (< 20 LOC) comme `sync_artists`, `fetch_artworks`, `mark_no_deezer` restent dans le router, ils ne font que dispatcher vers Celery ou faire un update simple.

L'audit logging (`_audit()` helper) reste dans le router car c'est du HTTP context (user, request).

### 2. catalog.py (668 LOC -> ~150 LOC)

| Endpoint | Ligne | LOC | Methode service |
|----------|-------|-----|-----------------|
| `list_catalog` | 79 | 303 | `catalog_service.list_catalog(db, user_id, filters, sort, page)` |
| `get_catalog_detail` | 384 | 211 | `catalog_service.get_detail(db, catalog_id, user_id)` |
| `get_preview_url` | 597 | 34 | `catalog_service.get_preview_url(db, catalog_id)` |
| `update_avis` | 633 | 35 | `catalog_service.update_avis(db, catalog_id, user_id, opinion)` |

### 3. genres.py (797 LOC -> ~200 LOC)

| Endpoint | Ligne | LOC | Methode service |
|----------|-------|-----|-----------------|
| `list_genres` | 164 | 152 | `genre_service.list_genres(db, user_id, family, sort, search, page)` |
| `get_genre_detail` | 384 | 105 | `genre_service.get_detail(db, genre_name, user_id)` |
| `get_genre_tracks` | 627 | 74 | `genre_service.list_tracks(db, genre_name, user_id, sort, search, page)` |
| `get_genre_artists` | 491 | 44 | `genre_service.list_artists(db, genre_name, page)` |
| `get_genre_sets` | 537 | 44 | `genre_service.list_sets(db, genre_name, page)` |
| `get_genre_playlists` | 584 | 41 | `genre_service.list_playlists(db, genre_name, page)` |
| `get_genre_neighbors` | 703 | 44 | `genre_service.get_neighbors(db, genre_name)` |
| `merge_genres` | 353 | 26 | `genre_service.merge(db, source, target)` |
| `rename_genre` | 760 | 37 | `genre_service.rename(db, old_name, new_name)` |
| `random_genre_track` | 130 | 32 | `genre_service.random_track(db, genre_name, exclude_id)` |

Le pillar cache (`_PILLAR_CACHE`, `_ensure_pillar_cache`, `genre_pillar`) va dans `genre_service.py` car c'est de la logique metier partagee (utilisee aussi par `catalog.py` et `artists.py`).

### 4. artists.py (462 LOC -> ~150 LOC)

| Endpoint | Ligne | LOC | Methode service |
|----------|-------|-----|-----------------|
| `list_artists` | 34 | 230 | `artist_service.list_artists(db, user_id, family, sort, search, page)` |
| `get_artist_detail` | 301 | 161 | `artist_service.get_detail(db, artist_id, user_id)` |
| `random_artist_track` | 266 | 33 | `artist_service.random_track(db, artist_id, exclude_id)` |

### 5. radar.py (416 LOC -> ~150 LOC)

| Endpoint | Ligne | LOC | Methode service |
|----------|-------|-----|-----------------|
| `list_radar_full` | 43 | 172 | `radar_service.list_full(db, user_id, status, sort, search, page)` |
| `radar_new_count` | 220 | 22 | `radar_service.new_count(db, user_id)` |
| `update_radar_state` | 247 | 36 | `radar_service.update_state(db, user_id, catalog_id, status)` |
| `batch_update_radar_state` | 288 | 49 | `radar_service.batch_update_state(db, user_id, items)` |
| `add_radar_track` | 357 | 45 | `radar_service.add_track(db, user_id, track_data)` |

### 6. image_service.py (unifie storage.py + deezer_enrich.py S3)

Actuellement le code S3/MinIO est duplique :
- `storage.py` (40 LOC) : client singleton + `ensure_bucket()` + `upload_artwork()`
- `deezer_enrich.py` lignes 31-54 : `_get_s3()` factory + `_ensure_bucket()` (meme logique)
- `deezer_enrich.py` lignes 266-297 : `upload_image_bytes_to_bucket()`, `upload_image_to_bucket()`, `upload_cover_from_url()`

Unifier dans `image_service.py` :
```python
class ImageService:
    _client = None

    @classmethod
    def _get_s3(cls):
        if cls._client is None:
            cls._client = boto3.client("s3", ...)
        return cls._client

    @classmethod
    def ensure_bucket(cls, bucket: str): ...

    @classmethod
    async def upload_from_url(cls, url: str, bucket: str, key: str) -> str: ...

    @classmethod
    async def upload_bytes(cls, data: bytes, bucket: str, key: str) -> str: ...

    @classmethod
    def upload_file(cls, file_path: str, bucket: str, key: str) -> str: ...
```

Puis supprimer `storage.py` et les fonctions S3 de `deezer_enrich.py`.
Mettre a jour les imports dans : `admin.py`, `tracks.py`, `deezer_enrich.py`, `workers/tasks.py`.

## Regles

- Chaque service est une collection de fonctions async (pas de classe sauf ImageService)
- Signature : `async def method(db: AsyncSession, ...) -> dict | list | Model`
- Les services levent `ValueError` ou des exceptions custom, jamais `HTTPException`
- Le router attrape les exceptions service et les convertit en HTTP responses
- Les schemas Pydantic restent dans les routers (validation request/response)
- Le pillar cache est gere par `genre_service` et expose via `genre_service.get_pillar(name)`
- Ne pas changer la logique metier, uniquement deplacer le code
- Garder les memes noms de variables et queries SQL

## Tests

Creer `tests/api/test_services/` avec des tests unitaires pour chaque service.
Objectif : 30+ tests minimum.

Les services sont testables sans FastAPI : `await catalog_service.list_catalog(db_session, ...)`.

Les tests existants (481+) dans `tests/api/` ne doivent PAS casser -- ils testent les endpoints qui appellent maintenant les services.

## Verification

```bash
# Aucun router ne depasse 300 LOC
wc -l server/api/routers/*.py

# Services existent
ls server/api/services/

# Tests services
pytest tests/api/test_services/ -v

# Zero regression
pytest tests/ -v

# Ruff clean
ruff check server/
```

## Fichiers a creer

| Fichier | Contenu |
|---------|---------|
| `server/api/services/__init__.py` | Exports |
| `server/api/services/artist_service.py` | Logique artistes (admin + artists routers) |
| `server/api/services/catalog_service.py` | Logique catalog (list, detail, preview) |
| `server/api/services/genre_service.py` | Logique genres + pillar cache |
| `server/api/services/radar_service.py` | Logique radar (list, state, opinion sync) |
| `server/api/services/image_service.py` | S3 unifie (remplace storage.py + deezer_enrich S3) |
| `tests/api/test_services/__init__.py` | |
| `tests/api/test_services/test_artist_service.py` | |
| `tests/api/test_services/test_catalog_service.py` | |
| `tests/api/test_services/test_genre_service.py` | |
| `tests/api/test_services/test_radar_service.py` | |
| `tests/api/test_services/test_image_service.py` | |

## Fichiers a modifier

| Fichier | Modification |
|---------|-------------|
| `server/api/routers/admin.py` | Remplacer logique par appels services |
| `server/api/routers/catalog.py` | Idem |
| `server/api/routers/genres.py` | Idem + supprimer pillar cache (va dans genre_service) |
| `server/api/routers/artists.py` | Idem |
| `server/api/routers/radar.py` | Idem |
| `server/api/deezer_enrich.py` | Supprimer fonctions S3 (_get_s3, _ensure_bucket, upload_*), importer image_service |
| `server/api/storage.py` | Supprimer (remplace par image_service) |

## Contraintes

- Code en anglais, UI en francais
- Ne PAS changer les schemas Pydantic (server/api/schemas.py)
- Ne PAS changer les modeles SQLAlchemy (server/api/models.py)
- Ne PAS changer les tests existants (sauf imports si storage.py est supprime)
- Les workers (server/workers/) importent `deezer_enrich` -- verifier que les imports S3 sont mis a jour
