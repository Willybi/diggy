# Audit 2026-08-24 — Phase 0 : inventaire outillé

> ⚠️ **CANDIDATS, PAS FINDINGS.** Chaque ligne ci-dessous est une sortie brute d'outil, à vérifier
> par lecture du code avant d'être retenue. Faux positifs structurels connus : vulture sur colonnes
> SQLAlchemy / schémas Pydantic / endpoints FastAPI / `health` (healthcheck Docker) / `GenreNode`
> (SQL brut) / API de calibration C2 (`sim_bpm`/`sim_key`/`sim_cooc`/`reset_similarity_context_cache`/
> `pillar_map`, brief C2.d « ne pas supprimer ») ; deptry DEP001 sur les packages locaux
> (`models`/`services`/`utils`/`trackid`), DEP002 sur `asyncpg`/`uvicorn`.
>
> Nommage dossier : l'audit précédent occupe `docs/audits/2026-08/` (2026-08-09, même mois) →
> ce cycle vit dans `2026-08-24/`, clé de finding `2026-08-24/Ax-nn`.

## Bornage du delta

- **HEAD audité précédent** : `9b305d6` (2026-08-08, audit 2026-08).
- **HEAD de ce cycle** : `52a506f` (2026-08-24).
- **Delta** : **102 commits, 314 fichiers, +59 011 / −7 439 lignes**.
- Ventilation : `server/api` 67 fichiers (+6 707/−1 330) · `server/workers` 22 (+1 922/−241) ·
  `server/frontend/src` 85 (+8 084/−4 382) · `tests/` 70 (+9 498/−493) · `worker/` (outils locaux)
  9 (+1 856) · infra (compose/nginx/CI/postgres) 5 (+141/−25).
- Chantiers livrés dans le delta : série **AV1→AV7** (audit 2026-08), incident 504 reco
  (`precompute_recommendations`), **X4** (intégrité artiste), hygiène artistes (pivot N3 + sweep
  2026-08-24), **N4** (majeurs frontend vite8/pinia4/vue-router5), **D8** (voir-plus), **D9**
  (KeepAlive+prefetch), **C8** (fiabilité sets), **C7** (albums), **C5 v2** (collections polymorphes
  + dossiers), **AV8** (robustesse workers v3), **AV9** (deadline drains), **AV10** (throttle CPU),
  **C9.0/C9.a/C9.b** (embeddings pgvector + « sonne comme »), monitoring (auto-heal, courbes),
  fixes BPM throttle, Redis persisté.
- Zones NEUVES jamais auditées : `models/album.py`, `models/embedding.py`, `routers/albums.py`,
  `services/album_service.py`, `trackid/reliability.py`, collections polymorphes
  (`models/collection.py`, `services/collection_service` ?, router), `postgres/Dockerfile` (pgvector),
  `worker/embedding_backfill/`, endpoint « sonne comme » (C9.b), `AddToCollectionButton`,
  `CollectionDetailView`/`CollectionsView` (dossiers), `AlbumView`, KeepAlive D9, hub lazy AV5,
  `TrackTable.vue` partagé, `scripts/cleanup_artists.py`, `scripts/backfill_albums.py`,
  `scripts/backfill_set_reliability.py`, `scripts/cleanup_orphan_artists` (0174825).

## ruff

```
ruff check server/ --statistics  →  0 erreur (exit 0), sortie vide
```

## vulture (min-confidence 60, hors alembic) — 293 lignes brutes

Dominées par les FP structurels (modèles SQLAlchemy, schémas Pydantic `model_config`/champs de
réponse, endpoints FastAPI de `routers/admin.py`, hooks Celery `init_sentry`/`on_task_failure`,
outils locaux `server/deezer/extractor.py`/`sync_checker.py`). Candidats NON structurels à vérifier :

- `server/api/services/similarity_service.py:850` — `similar_from_context` sans caller (déjà
  documenté « caller-less » dans CLAUDE.md depuis AV7 — candidat suppression, décision à poser)
- `server/api/routers/sets.py:45` — `search_trackid_sets` (GET /sets/search : vérifier consommateur front)
- `server/api/services/set_dedup_service.py:222` — variable `total_identified`
- `server/workers/crawl_logger.py:52` — `update_stats` ; `:104` — propriété `log_id`
- `server/workers/celery_app.py:207-208` — variables `traceback`/`einfo` (100 %) — signature hook, FP probable
- `server/workers/tasks/genres.py:422` — variable `traceback` (100 %)

## deptry (0.25.1)

531 issues, quasi intégralement **DEP001 sur les packages locaux** (`models`, `services`, `utils`,
`trackid`, `sentry_sdk` importé au runtime worker) = FP structurel connu (exécuté hors contexte
conteneur). Rien de nouveau exploitable.

## pip-audit (requirements.txt épinglé, hors essentia — wheel Linux-only irrésoluble sur Windows)

```
python -m pip_audit -r <reqs sans essentia> --no-deps --ignore-vuln PYSEC-2025-185 --ignore-vuln PYSEC-2026-1325
→ No known vulnerabilities found, 1 ignored
```

## npm audit / npm outdated (server/frontend)

```
npm audit → found 0 vulnerabilities
npm outdated → minors seulement (axios 1.19, eslint 10.9, vite 8.2.2, vitest 4.1.11, vue 3.5.41,
prettier 3.9.6, eslint-plugin-vue 10.10) + 2 majors DEV-only : jsdom 26→29, rollup-plugin-visualizer 5→7
```

## TODO/FIXME/XXX/HACK (server/, hors package-lock)

1 seul : `server/frontend/src/components/PlatformLink.vue:38` — TODO logos officiels (placeholders
tracés, connu/assumé).

## Top fichiers par LOC (hors node_modules, alembic/versions)

```
2275 server/workers/tasks/artists.py          ← +~800 lignes ce cycle (hygiène artistes, tiers, résurrection)
1579 server/frontend/src/views/SetsView.vue
1499 server/frontend/src/views/GenreDetailView.vue
1404 server/api/services/similarity_service.py
1396 server/api/services/set_dedup_service.py
1248 server/frontend/src/views/DesignSystemView.vue   (dev-only, réfuté R7 2026-08)
1245 server/api/services/catalog_service.py
1221 server/frontend/src/views/WatchlistView.vue
1131 server/workers/tasks/sets.py
1051 server/frontend/src/views/TrackDetailView.vue
1020 server/api/services/artist_service.py
 993 server/frontend/src/views/RadarView.vue
 877 server/frontend/src/views/ExplorerView.vue
 810 server/frontend/src/components/admin/AdminArtists.vue
 803 server/workers/enrichment.py
 790 server/api/scripts/reverify_platform_ids.py
 754 server/frontend/src/components/TrackTable.vue
 680 server/api/scripts/backfill_albums.py
```

## Top churn (6 mois, server/)

```
61 views/CatalogView.vue (renommé ExplorerView)   49 routers/catalog.py     46 routers/admin.py
42 views/TrackDetailView.vue                      40 views/ArtistDetailView.vue
38 api/main.py    36 WatchlistView.vue    36 SetsView.vue    34 routers/radar.py
29 services/artist_service.py    28 workers/celery_app.py    28 router.js
27 routers/sets.py    26 workers/tasks/artists.py    26 services/catalog_service.py
```

Lecture churn×LOC : `workers/tasks/artists.py` (2275 LOC, churn élevé, +3 features ce cycle) est le
point chaud n°1 ; `routers/admin.py` et `artist_service.py` suivent.
