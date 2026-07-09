# Audit 2026-07 — Phase 0 : Inventaire outillé

> Généré le 2026-07-09. Sorties brutes des outils mécaniques, fournies en contexte aux agents d'audit.
> AVERTISSEMENT : ces sorties sont des CANDIDATS. Chaque agent doit vérifier avant de retenir un finding.

## 1. Ruff

`ruff check server/ --statistics` → **0 violation**. Le lint est propre.

## 2. Vulture (dead code candidats)

### min-confidence 80 (hors alembic) — 8 hits, tous triviaux (variables de signature)

```
server\api\schemas\radar.py:40: unused variable '__context' (100%)
server\workers\async_http.py:59: unused variable 'exc_tb' (100%)
server\workers\celery_app.py:138-140: unused variables 'traceback', 'einfo', 'kw' (100%)
server\workers\crawl_logger.py:61: unused variable 'exc_tb' (100%)
server\workers\rate_limiter.py:113,128: unused variable 'exc_tb' (100%)
```

### min-confidence 60 — 285 candidats (hors alembic)

Fichier complet : voir la sortie ci-dessous (extraits les plus significatifs ; les colonnes de modèles SQLAlchemy et les endpoints FastAPI sont des FAUX POSITIFS structurels de vulture — les décorateurs les rendent "utilisés"). Candidats à vérifier réellement :

```
server\api\main.py:105: unused function 'health' (60%)          # probablement utilisé par healthcheck docker
server\api\models\genre.py:6: unused class 'GenreNode' (60%)    # faux positif probable (taxonomy router)
server\api\opinion_sync.py:83: unused attribute 'updated_at'
```

Les ~50 hits sur `routers/admin.py` sont des endpoints FastAPI (faux positifs vulture par construction, MAIS à croiser avec les appels frontend — voir §6).

Sortie complète conservée dans la session ; commande reproductible :
`vulture server/ --min-confidence 60 | grep -v alembic`

## 3. Deptry (dépendances)

Beaucoup de faux positifs DEP001 (`services`, `workers`, `models`, `trackid`, `utils` = packages locaux importés en absolu depuis le contexte container). Signal utile :

```
DEP002 (déclaré mais non importé) :
  pyproject.toml: 'asyncpg'        # FAUX POSITIF probable : driver chargé via URL sqlalchemy postgresql+asyncpg://
  pyproject.toml: 'mutagen'        # à vérifier : aucun import trouvé
  pyproject.toml: 'python-dotenv'  # à vérifier : load_dotenv appelé quelque part ?
  pyproject.toml: 'uvicorn'        # FAUX POSITIF probable : lancé par CMD docker

DEP003 (transitives importées, non déclarées directement) :
  httpx (partout), jose, starlette, pythonjsonlogger, boto3, botocore
  → dépendances réelles du code non listées comme dépendances directes dans pyproject.toml
```

## 4. Coverage backend (pytest --cov, 848 passed / 3 skipped, 23.9s, TOTAL 52%)

Modules critiques faiblement couverts :

```
Name                                        Stmts   Miss  Cover
api\routers\admin.py                          260    164   37%
api\routers\tracks.py                         127     91   28%
api\routers\watchlist.py                      191    137   28%
api\routers\import_rb.py                       46     29   37%
api\routers\search.py                         125     64   49%
api\routers\sets.py                           101     56   45%
api\routers\taxonomy.py                        67     38   43%
api\routers\genres.py                          79     45   43%
api\routers\auth.py                            62     27   56%
api\services\genre_service.py                 179    135   25%
api\services\artist_service.py                277    154   44%
api\services\image_service.py                  92     42   54%
api\beatport\client.py                        133     72   46%
workers\async_http.py                          82     82    0%
workers\celery_app.py                          54     54    0%
workers\crawl_logger.py                        41     41    0%
workers\db.py                                  87     87    0%
workers\enrichment.py                         272    272    0%
workers\source_clients.py                     190    190    0%
workers\tasks\artists.py                      404    391    3%
workers\tasks\radar.py                        167    153    8%
workers\tasks\sets.py                         374    342    9%
workers\tasks\genres.py                       108     98    9%
workers\tasks\import_rb.py                     93     75   19%
workers\tasks\trends.py                        74     59   20%
workers\tasks\catalog.py                      106     82   23%
```

Bien couverts (>=83%) : tous les schemas (100%), models (100%), auth.py, auth_middleware.py, rate_limit.py, beatport/enrich.py, set_dedup_service (83%), similarity_service (92%), artist_connection_service (86%), rate_limiter (98%), deezer/sync_checker (93%).

NOTE : `workers/enrichment.py` (272 stmts, 0%) et `workers/db.py` (87 stmts, 0%) et `workers/source_clients.py` (190 stmts, 0%) — jamais importés par les tests. À croiser avec l'usage réel (dead code potentiel pour enrichment.py ?).

## 5. Endpoints backend (extraction @router.*, 103 matches)

Format `fichier:ligne METHODE path` (préfixe de montage à ajouter selon main.py) :

```
admin.py:71 POST /artists/sync                          admin.py:78 GET /artists/sync/status/{task_id}
admin.py:93 POST /artists/fetch-artworks                admin.py:100 POST /artists/backfill-multi-artists
admin.py:107 GET /artists/search-deezer                 admin.py:134 PATCH /artists/{artist_id}/deezer
admin.py:161 PATCH /artists/{artist_id}/no-deezer       admin.py:180 POST /artists/flags/manual
admin.py:210 GET /artists/flags                         admin.py:224 POST /artists/flags/{flag_id}/resolve
admin.py:242 POST /sets/link-artists                    admin.py:249 POST /sets/enrich-tracks
admin.py:256 POST /sets/{set_id}/artists                admin.py:284 DELETE /sets/{set_id}/artists/{artist_id}
admin.py:310 GET /set-flags                             admin.py:379 POST /set-flags/{flag_id}/attach
admin.py:461 POST /set-flags/{flag_id}/reject           admin.py:495 POST /sets/{set_id}/detach
admin.py:535 POST /enrich-beatport                      admin.py:547 POST /reset-beatport
admin.py:559 POST /enrich-beatport/{catalog_id}         admin.py:576 GET /genres/unclassified-count
admin.py:593 POST /genres/auto-classify                 admin.py:605 POST /genres/reclassify
admin.py:624 GET /deezer-genre/{catalog_id}             admin.py:643 POST /playlists/fetch-artworks
admin.py:655 GET /crawl-logs
artists.py:18 GET /                                     artists.py:37 GET /random-track
artists.py:50 GET /{artist_id}/connections              artists.py:66 GET /{artist_id}
auth.py:29 GET /google/login                            auth.py:48 GET /google/callback
auth.py:134 GET /me
catalog.py:40 GET /genres                               catalog.py:60 GET /
catalog.py:85 GET /{catalog_id}/similar                 catalog.py:105 GET /{catalog_id}
catalog.py:117 GET /{catalog_id}/preview-url            catalog.py:126 PATCH /{catalog_id}/avis
collections.py:20 GET /                                 collections.py:42 POST /
collections.py:66 GET /{collection_id}                  collections.py:169 DELETE /{collection_id}/items/{catalog_id}
collections.py:192 DELETE /{collection_id}              (+ POST /{collection_id}/items non capté par la regex — vérifier)
genres.py:37 GET /random-track                          genres.py:50 GET (root)
genres.py:66 POST /merge                                genres.py:81 GET /detail/{name:path}
genres.py:94 GET /artists/{name:path}                   genres.py:109 GET /sets/{name:path}
genres.py:123 GET /playlists/{name:path}                genres.py:137 GET /tracks/{name:path}
genres.py:158 GET /neighbors/{name:path}                genres.py:171 POST /refresh-pillars
genres.py:182 PATCH /rename/{name:path}
import_rb.py:22 POST /rekordbox-xml                     import_rb.py:73 GET /status/{task_id}
opinions.py:15 GET /                                    opinions.py:31 PATCH /
radar.py:25 GET /trends                                 radar.py:86 GET /full
radar.py:111 GET /new-count                             radar.py:119 PATCH /{catalog_id}/state
radar.py:129 PATCH /state/batch                         radar.py:140 DELETE /{entry_id}
search.py:300 GET /search
sets.py:40 GET /search                                  sets.py:82 GET /
sets.py:153 POST /import                                sets.py:233 GET /{set_id}
taxonomy.py:23 GET /nodes                               taxonomy.py:61 GET /nodes/{node_id}
taxonomy.py:74 GET /nodes/{node_id}/children            taxonomy.py:113 GET /nodes/{node_id}/parents
taxonomy.py:143 GET /nodes/{node_id}/ancestors          taxonomy.py:176 GET /nodes/{node_id}/descendants
taxonomy.py:209 GET /nodes/{node_id}/neighbors          taxonomy.py:247 GET /roots
taxonomy.py:267 GET /stats                              taxonomy.py:300 GET /mappings
taxonomy.py:343 PUT /mappings/{raw_name}
tracks.py:18 GET /existing-ids                          tracks.py:34 POST /bulk
tracks.py:188 GET /tags                                 tracks.py:206 GET /
tracks.py:289 GET /{track_id}
watchlist.py:83 GET /                                   watchlist.py:102 GET /active
watchlist.py:118 GET /browse                            watchlist.py:149 GET /{entry_id}
watchlist.py:199 POST /                                 watchlist.py:256 POST /{entry_id}/follow
watchlist.py:288 POST /{entry_id}/crawl                 watchlist.py:316 PATCH /{entry_id}/crawled
watchlist.py:334 GET /{entry_id}/crawl-status           watchlist.py:377 POST /{entry_id}/fetch-artwork
watchlist.py:408 DELETE /{entry_id}                     
```

## 6. Appels API du frontend (grep `api.<verbe>(` + `fetch(` dans src/)

Endpoints appelés (dédupliqués, avec compte d'occurrences) :

```
GET  /api/artists/ (x4), /api/artists/{id}, /api/artists/{id}/connections, /api/artists/random-track
GET  /api/admin/artists/sync/status/{task_id} (x5), /api/admin/artists/search-deezer (x2), /api/admin/artists/flags
GET  /api/admin/set-flags?status=pending, /api/admin/genres/unclassified-count, /api/admin/crawl-logs
GET  /api/admin/deezer-genre/{id} (+?apply=true)
GET  /api/taxonomy/mappings (x3), /api/taxonomy/nodes
GET  /api/genres, /api/genres/, /api/genres/random-track, /api/genres/{detail,artists,sets,playlists,tracks,neighbors}/{name}
GET  /api/catalog/ (x2), /api/catalog/{id}, /api/catalog/{id}/similar, /api/catalog/{id}/preview-url, /api/catalog/genres
GET  /api/collections/ (x2), /api/collections/{id}
GET  /api/sets/, /api/sets/{id} (x2), /api/sets/search
GET  /api/watchlist/browse, /api/watchlist/{id}, /api/watchlist/{id}/crawl-status (x2)
GET  /api/search, /api/radar/trends, /api/opinions/, /api/import/status/{taskId}
GET  /radar/new-count        # NOTE: sans préfixe /api — utilise l'instance axios `api` (baseURL /api ?) à vérifier
POST /api/sets/import (x2), /api/admin/artists/flags/manual (x2), /api/admin/artists/{sync,fetch-artworks}
POST /api/admin/artists/flags/{id}/resolve (x2), /api/admin/sets/{link-artists,enrich-tracks}
POST /api/admin/sets/{id}/artists, /api/admin/set-flags/{id}/{attach,reject}, /api/admin/genres/{auto-classify,reclassify}
POST /api/admin/enrich-beatport (+/{id}), /api/admin/playlists/fetch-artworks
POST /api/watchlist/, /api/watchlist/{id}/{follow,crawl,fetch-artwork}
POST /api/collections/, /api/collections/{id}/items, /api/genres/merge, /api/opinions/{id}
POST fetch('/api/import/rekordbox-xml'), fetch(`${API}/google/login`)
PATCH /api/opinions/, /api/catalog/{id}/avis, /api/genres/rename/{name}
PATCH /api/admin/artists/{id}/deezer (x3), /api/admin/artists/{id}/no-deezer
PUT  /api/taxonomy/mappings/{rawName}
DELETE /api/watchlist/{id}, /api/collections/{id}, /api/collections/{id}/items/{cid}, /api/admin/sets/{id}/artists/{aid}
```

**Endpoints backend SANS appel frontend détecté** (candidats — vérifier usage par workers/scripts/curl avant de conclure) :

```
admin.py:100 POST /artists/backfill-multi-artists       admin.py:161 PATCH .../no-deezer → appelé (vu)
admin.py:495 POST /sets/{set_id}/detach                 admin.py:547 POST /reset-beatport
admin.py:576→appelé  auth.py:134 GET /me → vérifier stores/auth.js
genres.py:171 POST /refresh-pillars
radar.py:86 GET /full        radar.py:119 PATCH /{catalog_id}/state       radar.py:129 PATCH /state/batch
radar.py:140 DELETE /{entry_id}
taxonomy.py: children/parents/ancestors/descendants/neighbors/roots/stats/nodes/{id} (8 endpoints, seuls /nodes et /mappings vus)
tracks.py:18 GET /existing-ids    tracks.py:34 POST /bulk    tracks.py:188 GET /tags    tracks.py:206 GET /    tracks.py:289 GET /{track_id}
watchlist.py:83 GET /    watchlist.py:102 GET /active    watchlist.py:149 GET /{entry_id}→appelé    watchlist.py:316 PATCH /{entry_id}/crawled
collections.py DELETE /{collection_id}/items → appelé
```

(Le HubView appelle peut-être radar/full ou state — grep partiel, les agents doivent re-vérifier chaque candidat.)

## 7. Composants Vue — références croisées

Composants avec 0 référence (candidats morts) :

```
components/AppearRow.vue   → 0 import trouvé
views/TagsView.vue         → 0 import (déjà connu comme "dead view" dans CLAUDE.md)
```

Tous les autres composants/vues ont >=1 référence (1 = import unique, typiquement le router pour les vues).

## 8. Bundle frontend (vite build, 1.9s)

```
index-DVwQTgZA.js       191.55 kB │ gzip: 72.18 kB   # bundle principal
AdminView-BwcNEI7M.js    32.27 kB │ gzip:  9.86 kB
CatalogView-CAvt3nYY.js  18.46 kB │ gzip:  6.47 kB
GenreDetailView          14.79 kB │ TrackDetailView 14.64 kB │ ArtistDetailView 11.28 kB
index-CEgGMVIR.css       40.51 kB │ gzip:  7.61 kB
AdminView css            23.92 kB │ CatalogView css 16.35 kB
```

Le code-splitting par vue fonctionne (chunks séparés). HubView n'apparaît pas en chunk séparé → probablement dans index (route par défaut ?) — à vérifier.

## 9. Base de données (prod, lecture seule via SSH, 2026-07-09)

### Lignes par table (pg_stat_user_tables, n_live_tup)

```
catalog_artists 18922    catalog 15836      set_tracks 10396   artists 9997
radar_trends 9172        radar_tracks 6806  genre_edges 729    user_tracks 631
sets 608                 genre_nodes 540    crawl_logs 221     set_artists 110
artist_flags 81          genre_mappings 71  admin_audit_log 71 watched_entities 56
user_opinions 25         watched_playlists 24 (!)              artist_aliases 22
set_flags 16             user_follows 12    user_set_follows 11 users 6
user_radar_state 5       user_collections 0 collection_items 0
```

**ANOMALIE** : `watched_playlists` (24 lignes) existe en DB mais n'apparaît PAS dans les 25 tables de `docs/database-schema.md` ni dans les modèles → table legacy orpheline probable (à confirmer par A2 : quelle migration l'a créée, laquelle aurait dû la dropper).

### Colonnes ~100% NULL (pg_stats, null_frac >= 0.999)

```
artists: bio, country, real_name, soundcloud_id, trackid_id (0.9999)
catalog: fingerprint, preview_url (!)   # preview_url 100% NULL avec has_preview existant — vérifier
sets: description, event, venue
radar_tracks: removed_at                # attendu (lifecycle) ou signe que la logique ne tourne pas ?
user_tracks: avis, created_at
```

### FK sans index (leading column)

```
collection_items.catalog_id      set_flags.resolved_by      user_follows.entity_id
user_radar_state.catalog_id      user_set_follows.set_id    user_tracks.catalog_id
```

### Alembic

`alembic_version` = 0030 (aligné avec la dernière migration du repo).

## 10. VPS (lecture seule)

- **crontab root** : UNE seule entrée = reload nginx à 03:00. **AUCUN cron de backup** alors que `server/scripts/backup.sh` existe → à instruire par A5 (le backup tourne-t-il ailleurs ? dernier dump ?).
- `/root/diggy/backups` : n'existe pas (ls vide).

## 11. Hygiène repo (git ls-files, 347 fichiers hors lockfiles)

Fichiers/dossiers notables versionnés :

```
server/scripts/.tidal_tokens.json   # TOKENS OAUTH TIDAL RÉELS COMMITÉS (access_token JWT visible) — SÉCURITÉ
.coverage                           # artefact binaire de test commité (77 Ko)
out/canonical_edges.csv, out/canonical_nodes.csv   # exports de travail commités (2026-06-28)
worker/__init__.py, worker/import_rekordbox.py, worker/relocate_tracks.py  # dossier `worker/` (singulier) legacy,
                                    # distinct de server/workers/ — dernier commit 2026-06-01/05
scripts/import_taxonomy.py          # script racine one-shot (2026-06-28)
design-decisions.md                 # à la racine, 8.5 Ko — placement à évaluer (docs/ ?)
```

- `.gitignore` ignore `_design/` et `docs/prompts` (donc prompts non versionnés — vérifier si voulu vs convention "prompts actifs dans docs/prompts/").
- `docs/prompts/` est actuellement VIDE sur le disque.
- Inventaire complet date|fichier : `scratchpad/gitfiles.txt` (347 lignes), plus vieux fichiers = worker/ (2026-06-01).

## 12. Volumétrie code (LOC)

```
Routers (3605 total) : admin 665, watchlist 435, taxonomy 370, search 365, tracks 350, sets 341
Services (4445 total) : set_dedup 1082, genre 681, artist 679, catalog 633, similarity 502, radar 328
Views Vue (11401 total) : HubView 1511, GenreDetailView 1255, CatalogView 1193, ArtistDetailView 1018,
                          TrackDetailView 944, SetsView 860, WatchlistView 834
NOTE : le brief mentionne "search.py 408 LOC pour 1 endpoint" → réalité 365 LOC, 1 endpoint GET /search. 
NOTE : le brief mentionne "AdminView 1725 LOC" → réalité : AdminView.vue éclaté en components/admin/* (6 fichiers), plus que ~? LOC — A4 doit vérifier l'état réel post-refactor.
Celery : 17 tasks définies dans 7 modules (artists x4, catalog x2, genres x2, import_rb x1, radar x2, sets x5, trends x1)
```
