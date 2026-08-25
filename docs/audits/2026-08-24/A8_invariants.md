# A8 — Invariants projet (audit global 2026-08-24)

Passe mécanique : chaque invariant/pitfall de `CLAUDE.md` vérifié un par un contre le code (grep + lecture ciblée). Périmètre : repo `c:\Users\willi\Desktop\diggy`, lecture seule.

**Compte final : 40 TENU / 2 VIOLÉ / 0 INVÉRIFIABLE**

---

## Ce qui va bien

### Data Authority (5/5 tenus)
- **#1 Rekordbox read-only (serveur)** : aucun `pyrekordbox` / `Rekordbox6Database` dans `server/` (grep vide). Le seul writer est l'outil LOCAL `worker/relocate_tracks.py` — exception documentée.
- **#2 RB BPM autoritaire (données de perf user)** : le BPM Rekordbox vit dans `user_tracks.rb_bpm` et OVERRIDE la valeur catalog à la lecture — `catalog_service.py:436` (`bpm_source="rekordbox" if ut_bpm is not None`), `catalog_service.py:666`, `artist_service.py:555`. Aucun writer externe ne touche `user_tracks`.
- **#3 Beatport canonique / analysis autorité basse** : `bpm_analysis.py:97-102` — write gaté `entry.bpm is not None → skipped` (défensif en PLUS du candidate filter) ; `beatport/enrich.py:38-50` — Beatport écrase toute source ≠ beatport (donc écrase `analysis`, conforme) ; `catalog_merge.py:375-382` — fill-only avec provenance. Le feed de `similarity_service` par `analysis` est le résidu accepté.
- **#4 Asymétrie merge** : gate `same_track` au point de merge (`workers/catalog_merge.py`), scripts OPS tous dry-run-par-défaut, cas ambigus flaggés sans action (`cleanup_artists`, `dedup_artists_deezer`, `resync_catalog_artist` partial-overlap intact). Aucun auto-merge sur signal faible trouvé.
- **#5 LLM language-boundary only** : aucun client LLM dans `server/` (grep openai/anthropic/mistral vide) ; `recommendation_service.py:7` l'affirme explicitement (« No LLM: the aggregation is fully deterministic »).

### C3 — catalog_visible (focus endpoints post-2026-08-09)
- **Album detail (C7)** : `album_service.py:54` — tracklist sous `catalog_visible(user_id)`.
- **« Sonne comme » (C9.b)** : `similarity_service.py:1385` — pgvector cosine scopé `catalog_visible` ; router `catalog.py:135-149` (`/content-similar`) le documente, JWT-optional + shelf admin-gaté front.
- **Collections detail (C5 v2)** : `routers/collections.py:381` (résolution track unitaire) et `:415` (batch `item_type='track'`) portent `catalog_visible(user_id)`.
- **Search scope `album`** : `_search_albums` (`search_service.py:272`) ne retourne AUCUNE ligne catalog (entité album seule) → pas de fuite ; les scopes track gardent `catalog_visible` (`search_service.py:72`).

### Nginx (5/5)
- `add_header` UNIQUEMENT au niveau server (`default.ssl.conf.template:33-37`) ; les locations assets imbriquées (l.70-81) n'en portent aucun → héritage CSP intact.
- `^~` sur `/api/` (l.45), `/storage/` (l.54), `/minio/` (l.60).
- `default.conf` = 1 ligne de commentaire « intentionally empty ».
- CSP contient `upgrade-insecure-requests` (l.37).
- `client_max_body_size 12M` (l.23) > `MAX_FILE_SIZE` 10 MB (`import_rb.py:18`), couplage commenté dans la conf.

### Docker & Backup (3/3)
- UNE image partagée : `api`/`worker`/`worker_enrich`/`beat` buildent tous `context: ./server` (`docker-compose.yml:79/110/155/195`).
- `.dockerignore` exclut `frontend/ nginx/ scripts/ deezer/` et préserve `api/alembic/` (commentaire explicite).
- Mount rclone du service `backup` en RW avec le commentaire « Read-write on purpose » (`docker-compose.yml:342-344`) ; `shm_size: 256mb` postgres (l.18) et postgres custom pgvector (l.5-6) présents.

### Workers & Celery
- **Locks SET NX EX, TTL > time_limit, release conditionnelle** — vérifié paire par paire : deezer 9300>9000, beatport 3900>3300, bpm 3900>3300, reco 2100>1800, resolve_set_tracks 2700>2400, recrawl 4200>3900, backfill_trackid 4200>3900, crawl_trackid_latest 4200>3600 (global), link_artists 1800>1500, artworks 3600>3300, sync_artists 4800>4500, link_set_artists 4200>3600, backfill_multi 9300>9000, check_followed 4200>3900, reclassify orchestrateur 21600 (jamais sur le chunk).
- **Aucun `autoretry_for=(Exception,)`** dans `server/workers/` : les 20 hits du grep sont tous des COMMENTAIRES « NO autoretry_for » — zéro occurrence active.
- **Deadline interne AV9 sur les 4 drains** : `tasks/catalog.py:138` (Deezer) + `:300` (Beatport), `tasks/bpm.py:134`, `tasks/sets.py:894-1009` (backfill, gardée en tête des DEUX boucles collecte+import) — `time.monotonic()` = soft − `DEADLINE_MARGIN`, stat `deadline_hit`, constantes module partagées décorateur+garde.
- **Outage HTTP ≠ tentative** : `enrichment.py:522-526` (`DeezerHTTPError` → `errors+=1`, PAS de `_mark_searched`) et `:789-792` (Beatport, même motif) ; `ObjectDeletedError` mid-batch pareil (`:527-535`).
- **Cadence slack** : `CADENCE_SLACK_DAYS = 0.25` appliqué en soustraction du seuil — `tasks/sets.py:54,267` et `tasks/radar.py:21,97`.
- **Jamais `result.get()` dans une tâche** : grep vide (seule mention = commentaire `genres.py:307` documentant le pattern chord).
- **Routing enrich vs celery** : `celery_app.py:90-106` conforme à la table CLAUDE.md (beatport/deezer/bpm/artistes/reclassify_chunk → `enrich`, `crawl_single_playlist` → `crawl`, défaut `celery`).

### Database & Alembic
- **API sans `create_all`** : `main.py:72` (commentaire « Schema is managed by Alembic only ») ; aucun appel `create_all` hors harness de tests et event-listener CREATE EXTENSION (`models/embedding.py`).
- **Tests parallel-safe xdist** : `tests/api/conftest.py:37,121,273` — DB par worker `diggy_test_gwN` via `_create_worker_database` ; le test PG-only worker (`tests/worker/test_import_rb_upsert.py:154`) réplique le pattern.
- **SAEnum name==value** : `AlbumType` (`album.py:21-25` : `album/single/ep/compile`), `SetFlagType` (`sets.py:155-158`), `SetFlagStatus` (`sets.py:161-164`) — tous les membres minuscules name==value.
- **Jamais `asyncio.gather` sur une même AsyncSession** : seul gather dans `server/api/services/` = `external_search_service.py:124` (2 appels HTTP Deezer/TIDAL, aucune session) ; similarity/monitoring/artist/watchlist/set_service portent tous le commentaire « never gather on db » et awaitent séquentiellement.
- **StringArray both-dialects** : `models/base.py` — `array_any` (l.8-28) et `array_is_empty` (l.36-57) compilés `@compiles` défaut PG + variante `sqlite` ; `comparator_factory` explicite (l.68, l.102).
- **Index HNSW exclu de l'autogenerate** : `alembic/env.py:26-31` `_AUTOGEN_SKIP_INDEXES = {"ix_track_embeddings_hnsw"}` + `include_object` câblé offline (l.41) ET online (l.53).

### Frontend
- **`@media` fixed-only** : tous les hits viewport sont sanctionnés — overlays modaux `position: fixed` (`ImportRekordboxModal.vue:269`, `ExternalImportModal.vue:192`), `PlayerBar`/`BottomNav` (fixed), `AddModal.vue:112` (exception documentée), `table.css:127` `(hover: none)` (exception documentée). Les `@media (prefers-reduced-motion)` (App/ArtistsView/GenresView/PlayerBar/SetsView/WatchlistView/SkeletonGrid/ArtistSegmentSplitter) sont des feature-queries de préférence utilisateur, inexprimables en `@container` — hors lettre stricte mais conformes à l'esprit (la règle vise les media-queries viewport), non comptés.
- **`setInterval`** : unique occurrence = `composables/useTaskPoll.js:72` (le composable sanctionné lui-même). Aucun poll ad-hoc en vue.
- **Pas de fetch offset/hasMore maison** : tous les `hasMore` des vues proviennent de `usePaginatedList`/`useWindowedList` (destructuring, aucune implémentation locale).
- **Gardes KeepAlive `ownPath`** : `useFilterState.js:106,161` et `useUrlSync.js:39,80` (`if (route.path !== ownPath) return`) ; les 6 vues listes + `useVirtualWindow`/`useScrollRestore` portent `onDeactivated`/`onActivated` ; allowlist `CACHED_VIEWS` (`App.vue:41-48`) = exactement les 6 vues listes, `:max=6`, `AlbumView`/vues détail absentes.
- **Routes `/collections/folders` avant `/{collection_id}`** : `routers/collections.py` — folders déclarées l.89/111/135/164, `/{collection_id}` à partir de l.184.
- **Pas de multi-statement inline handlers** : grep `@click="…;…"` vide sur `src/`.
- **Zéro couleur hardcodée** : quasi-tenu — seul écart : logo Google (voir A8-02).

### Auth & Multi-User
- **OAuth state Redis one-shot** : `routers/auth.py:33` (`setex oauth_state:{state} 300`) + `:57` (`redis.delete` = consommation one-shot).
- **`uid()` None pour guests** : `dependencies.py:67-69` ; `catalog_visible(user_id: int | None)` (`catalog_service.py:49`) gère `None` (branche guest `scope='shared'`).
- **Cookie `auth_callback`** : `routers/auth.py:123` — flow cookie intact, pas de fragment/localStorage réintroduit.

### E1 — re-scan
- `enrichment.py:35-37` : `RESCAN_TIER2_DAYS = 30`, `RESCAN_TIER3_DAYS = 90`, `MAX_SEARCH_ATTEMPTS = 3` ; tiering never/due/cooldown/abandoned (l.159-201).
- Budgets : `ARTIST_LINK_NIGHTLY_BUDGET` / `ARTIST_ARTWORK_NIGHTLY_BUDGET` (`artists.py:334,341`), `ENRICH_NIGHTLY_BUDGET[_DEEZER/_BEATPORT]` (`catalog.py:48-69`), `ANALYSIS_BPM_NIGHTLY_BUDGET` (`bpm.py:38`).

### Sets C8 — fiabilité
- Prédicat `set_reliable()` / `set_reliable_sql()` ajouté EN PLUS du roots-only aux sites listés : `compute_trends` (`trends.py:154-198`), `similarity_service._load_set_map` (`:295-296`), `artist_connection_service` (`:101`), `catalog_service` `nb_radar_sets` (`:201`) + `set_appearances` (`:555`), `set_service.list_sets` (`:75`), `search_service` items+count (`:195-208`), `artist_service.get_detail` (`:589-590`), `genre_service` ×3 (`:358,489` + set_count), `_check_new_sets` follow-feed (`artists.py:2145`).
- PAS d'exclusion sur le recrawl : `tasks/sets.py:503-509` — flag rafraîchi par `import_audiostream`, délibérément pas de re-filtre ; PAS d'exclusion sur `get_set_detail` (`routers/sets.py:231-246`, accès mono-id sans prédicat).

---

## Tableau des verdicts

| # | Invariant / pitfall | Verdict | Preuve clé |
|---|---|---|---|
| 1 | #1 Rekordbox read-only serveur | TENU | grep pyrekordbox `server/` vide |
| 2 | #2 RB BPM autoritaire | TENU | catalog_service.py:436,666 ; artist_service.py:555 |
| 3 | #3 Beatport canonique / analysis basse | TENU | bpm_analysis.py:97-102 ; beatport/enrich.py:38-50 |
| 4 | #4 Asymétrie merge | TENU | catalog_merge same_track ; scripts dry-run/flag-only |
| 5 | #5 LLM language-boundary only | TENU | grep LLM vide ; recommendation_service.py:7 |
| 6 | C3 album detail | TENU | album_service.py:54 |
| 7 | C3 sonne-comme C9.b | TENU | similarity_service.py:1385 |
| 8 | C3 collections detail | TENU | collections.py:381,415 |
| 9 | C3 search scope album | TENU | search_service.py:272 (aucune ligne catalog) |
| 10 | Nginx add_header/location | TENU | default.ssl.conf.template:33-37 vs 70-81 |
| 11 | Nginx ^~ /api /storage /minio | TENU | l.45,54,60 |
| 12 | Nginx default.conf vide | TENU | 73 octets, commentaire |
| 13 | CSP upgrade-insecure-requests | TENU | l.37 |
| 14 | 12M nginx > 10M app | TENU | l.23 ; import_rb.py:18 |
| 15 | Une image partagée ×4 services | TENU | docker-compose.yml:79/110/155/195 |
| 16 | .dockerignore | TENU | server/.dockerignore |
| 17 | Backup rclone mount RW | TENU | docker-compose.yml:342-344 |
| 18 | Locks SET NX EX, TTL>time_limit | TENU | 15 paires vérifiées (cf. section) |
| 19 | Jamais autoretry_for=(Exception,) | TENU | grep = 20 commentaires, 0 actif |
| 20 | Deadline AV9 sur les 4 drains | TENU | catalog.py:138,300 ; bpm.py:134 ; sets.py:894+ |
| 21 | Deadline AV9 sur nouvelle tâche drain asyncio | **VIOLÉ** | recommendations.py:120-133 (A8-01) |
| 22 | Outage HTTP ≠ tentative | TENU | enrichment.py:522-526,789-792 |
| 23 | Cadence slack | TENU | sets.py:54,267 ; radar.py:21,97 |
| 24 | Jamais result.get() en tâche | TENU | grep vide |
| 25 | Routing enrich vs celery | TENU | celery_app.py:90-106 |
| 26 | API sans create_all | TENU | main.py:72, aucun appel runtime |
| 27 | Tests parallel-safe xdist | TENU | tests/api/conftest.py:121,273 |
| 28 | SAEnum name==value | TENU | album.py:21-25 ; sets.py:155-164 |
| 29 | Jamais gather sur une AsyncSession | TENU | seul gather = HTTP (external_search:124) |
| 30 | StringArray both-dialects | TENU | base.py:8-57, comparator_factory:68,102 |
| 31 | HNSW exclu autogenerate | TENU | env.py:26-31,41,53 |
| 32 | @media fixed-only (+exceptions) | TENU | tous hits sanctionnés (fixed / AddModal / hover:none) |
| 33 | Zéro couleur hardcodée | **VIOLÉ** (mineur) | LoginView.vue:16-28 (A8-02) |
| 34 | Pas de setInterval hors useTaskPoll | TENU | useTaskPoll.js:72 seul hit |
| 35 | Pas de pagination maison en vue | TENU | hasMore uniquement via composables |
| 36 | Gardes ownPath KeepAlive | TENU | useFilterState.js:161 ; useUrlSync.js:80 |
| 37 | /collections/folders avant /{collection_id} | TENU | collections.py:89-164 < 184 |
| 38 | Pas de multi-statement inline handlers | TENU | grep vide |
| 39 | OAuth state Redis one-shot | TENU | auth.py:33,57 |
| 40 | uid() None géré | TENU | dependencies.py:67 ; catalog_visible(None) |
| 41 | E1 30/90j, 3 tentatives, budgets | TENU | enrichment.py:35-37 ; budgets catalog/artists/bpm |
| 42 | C8 prédicat aux sites + pas sur recrawl/detail | TENU | 11 sites vérifiés ; sets.py:503 ; routers/sets.py:231 |

---

## Findings

### [A8-01] `precompute_recommendations` : drain asyncio sans deadline interne AV9
- **Type** : bug
- **Sévérité** : basse
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** : `server/workers/tasks/recommendations.py:120-133` — boucle `for uid in user_ids:` sur asyncio (`rs._compute` awaité, ~30 s/user), protection = seul `except SoftTimeLimitExceeded` per-user (l.126) ; aucun `time.monotonic()` deadline (grep `DEADLINE_MARGIN|time.monotonic` vide sur ce fichier), contrairement aux 4 drains gardés (`tasks/catalog.py:138,300`, `tasks/bpm.py:134`, `tasks/sets.py:894`).
- **Constat** : le pitfall AV9 (CLAUDE.md, Workers & Celery) exige que « toute NOUVELLE tâche à drain long par batches sur asyncio » double le catch signal d'une deadline interne `time.monotonic()` = soft limit − marge, car le `SoftTimeLimitExceeded` peut être avalé par le handler du transport asyncio (prouvé Sentry DIGGY-APP-J) → run jusqu'au hard limit 1800 s puis SIGKILL. `precompute_recommendations` (ajoutée 2026-08-13, 4 jours avant la consigne AV9) n'a jamais été rétrofittée. Impact borné : chaque user est caché individuellement (travail partiel conservé), lock `lock:precompute_reco` auto-heal en ≤ 2100 s — d'où la sévérité basse, mais le motif de défaillance est exactement celui qu'AV9 corrige.
- **Recommandation** : ajouter en tête de la boucle user une garde `if time.monotonic() >= deadline: break` avec `deadline = start + RECO_SOFT_TIME_LIMIT - DEADLINE_MARGIN` (soft limit extrait en constante module partagée décorateur+garde, comme `DEEZER_SOFT_TIME_LIMIT`), + stat `deadline_hit` dans le retour. Pattern à copier de `tasks/bpm.py`.
- **Dépendances** : aucune.
- **Tags** : —

### [A8-02] Couleurs hardcodées : logo Google dans LoginView (exception non documentée)
- **Type** : doc
- **Sévérité** : basse
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** : `server/frontend/src/views/LoginView.vue:16-28` — SVG inline avec `fill="#4285F4"`, `#34A853`, `#FBBC05`, `#EA4335` (les 4 couleurs de marque du bouton « Sign in with Google »). Seuls hits du grep `#[0-9a-fA-F]{3,8}` / `rgba?\(` sur les `.vue` (les autres matches sont des entités HTML `&#8239;`).
- **Constat** : la règle frontend « Zero hardcoded colors: everything via `var(--...)` from diggy-tokens.css » est violée à la lettre. En pratique c'est un choix correct (les brand guidelines Google imposent ces couleurs exactes, elles ne doivent PAS suivre le thème), mais l'exception n'est consignée nulle part — un futur lint/audit la re-signalera à chaque passe.
- **Recommandation** : ne PAS tokeniser ; documenter l'exception (une ligne dans le pitfall frontend de CLAUDE.md : « exception : couleurs de marque du logo Google dans LoginView ») ou un commentaire dans le SVG.
- **Dépendances** : aucune.
- **Tags** : QW-c

---

*Agent A8 — passe invariants, 2026-08-24. Sources : CLAUDE.md (racine), code `server/`, `tests/`, `docker-compose.yml`.*
