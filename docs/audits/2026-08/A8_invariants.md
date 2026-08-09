# A8 — Invariants projet (audit global 2026-08)

> Passe de non-régression MÉCANIQUE sur les règles que le projet s'est données dans `CLAUDE.md`.
> HEAD audité : `9b305d6` (2026-08-08). Dimension inaugurée par cet audit (absente de 2026-07).
> Méthode : lecture code + grep, aucun accès prod nécessaire. Un verdict par puce, preuve obligatoire.

## Ce qui va bien

**Décompte global : 45 TENU / 5 VIOLÉ / 0 INVÉRIFIABLE.**

Les 5 VIOLÉ sont tous partiels ou à la lettre (aucun invariant n'est violé dans son intention centrale au
niveau du serveur) : 2 divergences documentation/code, 1 trou E1 côté Beatport async, 1 dette locks sur
les tâches longues hors beat critique, 1 écart CSS mineur. Tenues remarquables :

- **Le cœur data-authority est béton** : `same_track`/`fold_if_platform_id_taken` (asymétrie de merge),
  la chaîne BPM `analysis` (gate conf ≥ 2.0, `bpm IS NULL`, jamais de key, écrasée par Beatport, stampe
  attempt sur verdict seulement), la séparation `rb_bpm` user-side / catalog partagé — chaque règle du
  bloc « Data Authority » se retrouve mot pour mot dans le code, souvent avec le commentaire d'invariant.
- **C3 discipline** : `resolve_import_catalog_entry` refuse explicitement la promotion private→shared sur
  collision de nom (le cas sanctionné — confirmation plateforme — est le seul qui promeut) ; les
  primitives `catalog_visible`/`catalog_visible_sql` gardent leur contrat `:viewer_id` documenté.
- **Les pièges « appris à la dure » n'ont pas régressé** : chord + errback (jamais `result.get()`),
  `CADENCE_SLACK_DAYS` 0.25 aux deux endroits, `PlaylistGoneError` typée par source, rate-limit Redis
  fixed-window fail-open, aucun `asyncio.gather` de `db.execute` sur une même AsyncSession côté API
  (les 6 sites commentent même l'anti-pattern), StringArray compilé PG **et** SQLite, conftest xdist
  par-worker + Redis self-sufficient, aucun `create_all` côté API.
- **Frontend discipliné** : 0 couleur hex hors tokens (seule exception : le logo Google multicolore de
  LoginView), 0 handler inline multi-statements, `setInterval` uniquement dans `useTaskPoll`, pagination
  exclusivement via `usePaginatedList`/`useWindowedList` (7 vues), `RouterLinkStub` via
  `global.components` partout, `minmax(0,1fr)` sur les mosaïques contraintes.

---

## Tableau maître

### 1. Data Authority Principles

| Invariant | Verdict | Preuve (fichier:ligne) |
|---|---|---|
| 1. Rekordbox read-only depuis Diggy | **VIOLÉ** (à la lettre, outil local) | `worker/relocate_tracks.py:117-128` : `shutil.move` + `track.FolderPath = target_path` + `db.session.commit()` sur la DB Rekordbox 6 (pyrekordbox). Côté serveur : TENU — l'import lit le XML uniquement (`services/rekordbox_xml.py`, aucun write-back). → [A8-01] |
| 2. Rekordbox BPM autoritaire pour les données user | TENU | Import : `workers/tasks/import_rb.py:156-157` écrit `rb_bpm`/`rb_key` dans `user_tracks`, jamais dans `catalog`. Lecture : `services/catalog_service.py:412-418` (`bpm=ut_bpm if ut_bpm is not None else entry.bpm`, `bpm_source="rekordbox"` si coalesce), idem `:641-643` et `artist_service.py:379-381`. |
| 3. Beatport canonique bpm/key ; `analysis` = autorité la plus basse | TENU | Beatport écrase tout sauf lui-même : `api/beatport/enrich.py:40-50` (`entry.bpm_source != "beatport"` → écrit, donc écrase un `analysis`). Analysis : `workers/bpm_analysis.py:95-103` (gate `conf < min_conf` [2.0, ligne 40], garde défensive `entry.bpm is not None → skipped`, `bpm_source="analysis"`) ; aucune écriture de key (`key`/`key_source` absents du module) ; `bpm_analyzed_at` stampé sur VERDICT seulement (`:114-157`, outage → `errors`, rien stampé). Merge : `workers/catalog_merge.py:349-356` NULL-fill only. |
| 4. Asymétrie de merge (err toward separation) | TENU | `workers/catalog_merge.py:95-112` (`same_track` : ISRC égal sinon titre remix-aware ; doute → False), `:59-92` (`normalize_track_title` conservatif, commentaire « merge asymmetry »), `workers/catalog_dedup.py:60-64` (aucun holder confirmé → pas de merge), `workers/tasks/artists.py:705-731` (`_assign_deezer_id` refuse la collision → NULL), `:659-682` (merge artiste séquentiel, commit isolé, rollback → orphelin E1-eligible). |
| 5. LLMs = language-boundary only (jamais de score, jamais de write DB) | TENU | Grep `openai\|anthropic\|claude\|gpt-\|mistral\|llm` sur `server/` : **1 seul hit**, le commentaire `services/recommendation_service.py:7` (« No LLM: the aggregation is fully deterministic »). Aucun client LLM dans le runtime — invariant trivialement tenu. |

### 2. Database

| Invariant | Verdict | Preuve |
|---|---|---|
| `catalog` = hub unique via `catalog_id` | TENU | `workers/catalog_merge.py:214-331` repointe les 9 tables enfants (catalog_artists, user_tracks, collection_items, user_radar_state, set_tracks, radar_tracks, artist_activity, radar_trends, user_opinions pseudo-FK) — l'inventaire même des FK vers catalog. |
| Dédup `normalized_key`/`isrc` à l'ingestion + gate `same_track` (X1) | TENU | `models/catalog.py:29-30` (`normalized_key` UNIQUE, `isrc` unique) ; `workers/tasks/import_rb.py:106-108` (lookup normalized_key) ; gate X1 : `workers/catalog_dedup.py:28-64` branché aux 2 points d'écriture (`workers/enrichment.py:296-298`, `api/beatport/enrich.py:31-34`). |
| Jamais de dédup sur id plateforme seul ; pas d'index unique dessus | TENU | `models/catalog.py:74-84` : `ix_catalog_deezer_id`/`ix_catalog_beatport_id` = index partiels NON uniques (absence délibérée, résidu accepté) ; `fold_if_platform_id_taken` exige `same_track` avant tout merge (`catalog_dedup.py:60-64`). |
| `user_tracks` : PK composite + FK catalog `ON DELETE RESTRICT` | TENU | `models/catalog.py:151-166` : `user_id`+`catalog_id` primary_key, `ForeignKey("catalog.id", ondelete="RESTRICT")`. |
| TIMESTAMPTZ (UTC) ; durées en ms | TENU | Grep `Column\(DateTime(?!\(timezone=True\))` sur `models/` : **0 hit** (46 colonnes DateTime, toutes timezone=True) ; `duration_ms = Column(Integer)` (`catalog.py:35`), Deezer `duration_s * 1000` (`enrichment.py:323-325`). |
| `has_artwork` = fichier MinIO ; jamais d'URL d'image externe en DB | TENU (nuance) | `enrichment.py:334-345` (download → `ImageService.upload_bytes` → `has_artwork=True`), `tasks/artists.py:1302-1307`, commentaire modèle `models/artist.py:146` (« Never store external image URLs here »). Nuance hors périmètre artwork : `users.picture_url` (`models/user.py:12`) stocke l'URL d'avatar Google OAuth — design auth délibéré, à documenter si on veut la lettre stricte. |
| Sentinel `deezer_id = "NOT_FOUND"` | TENU | `models/artist.py:42-53` (index unique partiel sentinel-aware), `tasks/monitoring.py:19`, `models/catalog.py:127` (exclu du filtre candidats BPM), `tasks/artists.py:596-608` (exclu du holder_map). |
| Sets : roots-only (`parent_set_id IS NULL`) dans listings et trends | TENU | `routers/sets.py:164`, `tasks/trends.py:187` (branche set_tracks du scoring), `services/similarity_service.py:261-274` (`_load_set_map` roots-only), `services/search_service.py:192,203`, `services/genre_service.py:480`, `services/artist_service.py:411`, `tasks/monitoring.py:77-81`. |
| E1 : retry 30/90j, abandon à 3 attempts, un échec HTTP ne stampe jamais `*_searched_at` | **VIOLÉ** (partiel — Beatport async) | Tiers : `workers/enrichment.py:34-36,74-131` (30/90/3) ✓. Deezer : `deezer_get` lève `DeezerHTTPError` sur non-200 (`async_http.py:131-142`), catch sans `_mark_searched` (`enrichment.py:431-435`) ✓. **MAIS** Beatport async : `beatport_get` ne lève JAMAIS sur non-200 (`async_http.py:146-165`, pas de raise_for_status) → `_do_search` retourne `[]` sur 500/503/403 (`enrichment.py:507-508,533-534`) → `bp_track is None` → `not_found` + `_mark_searched` (`enrichment.py:676-678`). Le jumeau SYNC fait `resp.raise_for_status()` (`api/beatport/client.py:242`). → [A8-02] |
| C6.b : `completion_pct` is_id-only ; recrawl_count consécutif ; final à 3 stales ou >90j ; cap 500 newest-first | TENU | `tasks/sets.py:209-219` (`_completion_pct` is_id only, docstring explique le reset catalog_id), `:247-270` (`_apply_recrawl_outcome` : reset sur progression, final à `recrawl_count >= 3` ou `new_pct >= 1.0`), `:222-244` (>90j → final), `:322` (`RECRAWL_MAX_SETS_PER_RUN` défaut 500), `:389-400` (newest first, cap drop les plus vieux). |
| C6.c : unique `(artist_id, activity_type, source, external_id)` ; cap fan-out 40 ; C6.e : crawl TOUTE la watchlist, cadence adaptative jamais final, cap 200, `is_initial_detection` | TENU | `models/artist.py:150-158` (`uq_artist_activity_ext`), `tasks/artists.py:302` (`ARTIST_ACTIVITY_MAX_TRACKS_PER_RELEASE = 40`) ; `tasks/radar.py:24-42` (toute `watched_entities`, follower = signal), `:69-97` (`_crawl_decision` <14d/14-60d/>60d, « No 'final' state »), `:180` (`CRAWL_RADAR_MAX_DISPATCH` défaut 200), `:148-159` + `:381-401` (initial = jamais crawlé ou dormant >30j, exclu de la vélocité via `is_initial_crawl`). |

### 3. Auth & Multi-User

| Invariant | Verdict | Preuve |
|---|---|---|
| OAuth Google ONLY ; state Redis TTL 5min one-shot | TENU | `routers/auth.py:33` (`setex(f"oauth_state:{state}", 300, "1")`), `:57` (`redis.delete` = consommation one-shot avant échange) ; grep `password` sur `routers/` : 0 hit — aucun login email/password. |
| Cookie `auth_callback` : 60s, Secure, SameSite=Lax, httponly=False — flux non « simplifié » | TENU | `routers/auth.py:122-128` : `set_cookie("auth_callback", …, max_age=60, httponly=False, secure=True, samesite="lax")` + 302 vers `/login/callback`. Aucun fragment/sessionStorage réintroduit. |
| `uid()` → None pour guests ; aucun fallback `user_id=1` | TENU | `dependencies.py:67-69` (`return user.id if user else None`) ; grep `user_id\s*=\s*1\b` sur `server/api` : 0 hit. |
| Primitives `catalog_visible`/`catalog_visible_sql` existent, contrat `:viewer_id` intact | TENU | `services/catalog_service.py:49-77` (prédicat ORM 3 clauses : shared / owner / user_track EXISTS, branche explicite guest) ; `:80-95` (jumelle SQL, bind `:viewer_id` réutilisé par l'EXISTS, docstring du contrat). Couverture path-par-path → A6. |
| Jamais de flip private→shared sur collision de nom | TENU | `services/catalog_service.py:125-141` (`resolve_import_catalog_entry` : foreign private « reuse as-is, WITHOUT any mutation — no promotion »), repris à l'import `tasks/import_rb.py:111-123`. Le SEUL flip existant est sur confirmation plateforme (`enrichment.py:347-350`, `beatport/enrich.py:92-95`) — le cas sanctionné (« a name collision is not a platform match »). |
| `require_admin` + `admin_audit_log` sur le destructif | TENU | `dependencies.py:59-64` ; `routers/admin.py` : `Depends(require_admin)` sur les ~30 endpoints (lignes 79→702), helper `_audit` (`:55-72`) appelé aux 6 sites destructifs (162, 310, 464, 487, 533, 562). |

### 4. Known Pitfalls / Nginx

| Invariant | Verdict | Preuve |
|---|---|---|
| `add_header` : assets nested dans `location /` sans add_header propre | TENU | `server/nginx/default.ssl.conf.template:65-82` : les 2 locations regex assets sont imbriquées dans `location /` et ne portent que `proxy_pass`/`expires` — les headers serveur (33-37, `always`) sont hérités. |
| `^~` sur /api/, /storage/, /minio/ | TENU | `default.ssl.conf.template:45,54,60` : les trois en `location ^~`. |
| `default.ssl.conf.template` actif ; `default.conf` vide | TENU | `docker-compose.ssl.yml:7-8` : template monté dans `/etc/nginx/templates/`, `empty.conf` écrase `default.conf` ; `server/nginx/default.conf` = 73 octets, un commentaire (« intentionally empty »). |
| CSP `upgrade-insecure-requests` conservé | TENU | `default.ssl.conf.template:37` : la CSP commence par `upgrade-insecure-requests;`. |
| `client_max_body_size` 12M couplé au 10M app | TENU | `default.ssl.conf.template:20-23` (12M + commentaire de couplage) vs `routers/import_rb.py:17,40-41` (`MAX_FILE_SIZE = 10 MB`, 413 français « Fichier trop volumineux (max 10 Mo) »). |

### 5. Known Pitfalls / Docker & Backup

| Invariant | Verdict | Preuve |
|---|---|---|
| Image unique `./server` pour api/worker/worker_enrich/beat | TENU | `docker-compose.yml` : les 4 services ont `build: context: ./server, dockerfile: Dockerfile` ; `server/Dockerfile:17-18` (`COPY api/ /app/` + `COPY workers/ /app/workers/`), ffmpeg E2.c en :10-12. |
| `server/.dockerignore` cohérent avec le runtime | TENU | `server/.dockerignore` : exclut `frontend/ nginx/ scripts/ deezer/` (racine contexte seulement — `api/scripts/` reverify N'EST PAS matché et ship bien) ; commentaire garde-fou « Do NOT exclude api/alembic/ ». |
| Mount rclone jamais `:ro` | TENU | `docker-compose.yml:287-289` : `/root/.config/rclone:/root/.config/rclone` sans `:ro`, commentaire « Read-write on purpose: rclone rewrites its OAuth token ». |

### 6. Known Pitfalls / Workers & Celery

| Invariant | Verdict | Preuve |
|---|---|---|
| Toute tâche longue = lock `SET NX EX` atomique, TTL > time_limit, release conditionnelle | **VIOLÉ** (partiel) | **Conformes (10)** : `enrich_catalog_beatport` (TTL 3900 > 3300, `tasks/catalog.py:17,174-188`), `analyze_bpm_previews` (3900 > 3300, `tasks/bpm.py:32,74-88`), `link_artists_deezer` (1800 > 1500, `tasks/artists.py:281,530-544`), `fetch_artist_artworks` (3600 > 3300, `:282,1198-1214`), `check_followed_artists` (4200 > 3900, `:306,1967-1983`), `resolve_set_tracks` (2700 > 2400, `tasks/sets.py:17,128-142`), `recrawl_incomplete_sets` (4200 > 3900, `:20,293-309`), `backfill_trackid_sets` (4200 > 3900, `:23,700-702`), `crawl_single_playlist` (`r.lock` timeout 4600 > 4500, acquire non-bloquant + `LockNotOwnedError`, `tasks/radar.py:264-277`), `import_rekordbox_xml` (3700 > 3600 acquis par le router `routers/import_rb.py:21,53-54`, release conditionnelle `tasks/import_rb.py:222-226`). **Sans lock alors que longues (6)** : `enrich_catalog` Deezer (time_limit 9000), `sync_artists` (4500), `backfill_multi_artists` (9000), `crawl_trackid_latest` (~15-17 min obs., limites globales 1800/3600), `link_set_artists`, `reclassify_genres_chunk` (16200). → [A8-03] |
| Rate limits partagés via Redis fixed window, fail-open | TENU | `workers/rate_limiter.py:43-46` (`_SHARED_WINDOWS` deezer/beatport), `:105-163` (INCR+EXPIRE, fenêtre horloge murale), `:229-237` et `:256-264` (fail-open vers le bucket local, warn once, timeouts 1s `:49`). |
| Cleanup destructif watched playlist sur `PlaylistGoneError` typée uniquement | TENU | `workers/source_clients.py:41-45` (classe), `:71-76` (Deezer : code erreur API, pas de string-match), `:309-324` (TIDAL : `ObjectNotFound`/404 réels uniquement, « anything else propagates ») ; consommée par type `tasks/radar.py:316-343`. |
| Jamais `result.get()` dans une task ; pattern chord | TENU | Grep `result\.get\|AsyncResult` sur `workers/` : seul hit = le commentaire `tasks/genres.py:188` ; orchestration par `chord(group(...))(callback.on_error(errback))` (`genres.py:224-229`) + errback `reclassify_genres_error` (`:273`). |
| Cadence gate : slack `CADENCE_SLACK_DAYS` 0.25 | TENU | `tasks/radar.py:21` (définition + rationale) appliqué `:97` ; `tasks/sets.py:31` appliqué `:244`. |
| Routing enrich vs celery/crawl conforme au tableau beat | TENU | `workers/celery_app.py:90-100` : beatport/catalog/bpm/check_followed/link_artists/fetch_artworks → `enrich` ; `crawl_single_playlist` → `crawl` ; défaut `celery` (snapshot_backlogs sans route, comme documenté). Horaires beat `:103-179` = tableau CLAUDE.md (02:00, 03:00, 03:30, 04:00, 04:45, 05:00, 05:10, 05:20, 6-23×550, 07:00, :30, 0-3×2000). Compose : `-Q celery,crawl -c 3` / `-Q enrich -c 2`. |
| Backlog artistes loop-safe : budget, batch-commit, lock, PAS d'autoretry | TENU (mais cf. [A8-04]) | `tasks/artists.py:509-524` et `:1174-1192` : les deux tâches sans `autoretry_for`, budgets 1500/10000 (`:272-277`), batch 100 (`:286`), locks conformes. Le décorateur `autoretry_for=(Exception,)` survit ailleurs, dont le jumeau `enrich_catalog` Deezer (soft-limit 2h) tracké en mémoire projet. → [A8-04] |

### 7. Known Pitfalls / Database & Alembic

| Invariant | Verdict | Preuve |
|---|---|---|
| Aucun `create_all` côté API (Alembic only) | TENU | Grep `create_all` sur `server/` : `api/main.py:71` = commentaire (« Schema is managed by Alembic only »), `models/artist.py:46` = commentaire ; les `create_all` des conftest tests = résidu accepté AU3. |
| Tests parallel-safe xdist ; `tests/api` self-sufficient Redis | TENU | `tests/api/conftest.py:32-53` (DB par worker `diggy_test_gwN`, réécriture `DATABASE_URL` AVANT import app), `:82-108` (CREATE DATABASE sous advisory lock autocommit), `:179-237` (FakeRedis + `_AllowAllRateLimitRedis` préréglé sur `rate_limit._redis`, pas de dépendance à un mock d'un autre module), `:290-292` (clear par test, pas d'état partagé). |
| Jamais `asyncio.gather` de plusieurs `db.execute` sur une même AsyncSession | TENU | Grep `asyncio.gather` sur `server/api` : 1 seul gather réel, `services/external_search_service.py:116-118` = 2 requêtes **HTTP** (Deezer/TIDAL), aucun `db.execute` dedans ; les 5 autres hits sont des commentaires anti-pattern (artist_service:426, monitoring_service:9, routers/sets:269, similarity_service:331, watchlist_service:152). Côté workers, le merge artiste diffère explicitement les DELETE/UPDATE hors gather (`tasks/artists.py:611-664`). |
| `StringArray` : comparator compile sur PG ET SQLite | TENU | `models/base.py:8-33` (`array_any` compilé défaut `= ANY(col)` + variante sqlite `json_each` EXISTS), `:42-45` (`comparator_factory.any`). |
| (Affirmation CLAUDE.md) `uq_artists_deezer_id` existe UNIQUEMENT en prod, hors migrations | **VIOLÉ** (doc stale) | `api/alembic/versions/0034_uq_artists_deezer_id.py:14-19` : la migration 0034 crée l'index (`CREATE UNIQUE INDEX IF NOT EXISTS`, no-op en prod) ; le modèle le déclare aussi (`models/artist.py:42-53`, `sqlite_where` pour les tests). L'affirmation « ONLY in prod, created outside migrations » n'est plus vraie. → [A8-05] |

### 8. Known Pitfalls / Frontend

| Invariant | Verdict | Preuve |
|---|---|---|
| Container queries partout ; `@media` UNIQUEMENT pour `position: fixed` | **VIOLÉ** (mineur) | 31 `@container`/`container-type` sur 10+ fichiers ✓. `@media` breakpoints : BottomNav (`fixed`), PlayerBar (`fixed`), modals Import/External (`position: fixed` confirmé `ExternalImportModal.vue:192`, `ImportRekordboxModal.vue:269`), WatchlistView bottom-sheet (exception commentée `:1330`) ✓ ; les `prefers-reduced-motion` = accessibilité, pas du layout ✓. **MAIS** `assets/table.css:123-131` : `@media (max-width: 640px)` sur `table.dt .pbtn/.act` (opacity) et `table.dt` (min-width) — éléments non-fixed. → [A8-06] |
| Zéro couleur hardcodée hors tokens | TENU (exception logo) | Grep hex sur `*.css` : 0 hit ; sur `*.vue` : 4 hits = les fills du « G » Google (`LoginView.vue:16-28`), couleurs de marque du logo SVG, identiques dans les 2 thèmes — non tokenisables par nature. |
| Pas de handlers inline multi-statements | TENU | Grep `@(click\|change\|input\|submit)="[^"]*;[^"]*"` sur `src/` : 0 hit. |
| Polling via `useTaskPoll` ; pagination via `usePaginatedList`/`useWindowedList` ; jamais de setInterval/fetch offset maison | TENU | Grep `setInterval` : 1 hit, `composables/useTaskPoll.js:65` (le wrapper sanctionné) ; `usePaginatedList`/`useWindowedList` consommés par les 7 vues listées ; tous les `hasMore` des vues proviennent des composables (destructuring, ex. `SetsView.vue:682`). |
| `.state`/`@keyframes spin` globaux dans `assets/page.css` | TENU | Grep `@keyframes spin` : unique définition `assets/page.css:24` (+ son commentaire :23 rappelant la règle). |
| Vitest : `RouterLinkStub` via `global.components` | TENU | 10+ fichiers de test, tous en `components: { RouterLink: RouterLinkStub }` (ex. `BottomNav.test.js:27`, `LoginCallbackView.test.js:38`, `ArtistCard.test.js:37`) ; aucun `stubs: { RouterLink: true }`. |
| `minmax(0,1fr)` sur les mosaïques/grilles contraintes | TENU | `GenreDetailView.vue:1088,1287,1457,1510,1518` (+ commentaire :1116), `ArtistDetailView.vue:530`, `ExplorerView.vue:1042-1412` (grilles table), `HubView.vue:1664-1669` (commentaire rationale). |

### 9. Language

| Invariant | Verdict | Preuve |
|---|---|---|
| Code en anglais, UI en français | TENU | Identifiants/API 100% EN (fichiers récents : `bpm_analysis.py`, `AdminOverview`, `radar_service`) ; textes UI FR : « Fichier trop volumineux (max 10 Mo) » (`import_rb.py:41`), « Un import est déjà en cours pour ce compte » (`routers/import_rb.py:56`), « Fin des résultats » (`ExplorerView.vue:357`). Note : commentaires/docstrings mixtes FR/EN (`tasks/catalog.py:63`, beat schedule) — pratique historique constante, la règle vise identifiants + UI. |

---

## Findings

### [A8-01] `worker/relocate_tracks.py` écrit dans la base Rekordbox (invariant #1 à la lettre)
- **Type** : doc
- **Sévérité** : basse
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** : `worker/relocate_tracks.py:117-128` —
  ```python
  shutil.move(current_path, target_path)
  track.OrgFolderPath = target_path
  track.FolderPath = target_path
  ...
  db.session.commit()
  ```
  et docstring `:5` : « met à jour FolderPath dans Rekordbox ». CLAUDE.md (§ Architecture, local tooling) affirme pourtant que ces outils « read the local Rekordbox library », et l'invariant #1 dit « Rekordbox is read-only from Diggy's perspective ».
- **Constat** : le serveur honore l'invariant (l'import ne fait que lire le XML), mais le repo versionne un outil local qui écrit dans la DB Rekordbox 6 via pyrekordbox (mutation FolderPath + commit). Deux textes de CLAUDE.md sont donc inexacts à la lettre : la description des outils locaux et le périmètre de l'invariant #1.
- **Recommandation** : re-scoper l'invariant #1 dans CLAUDE.md (« le RUNTIME SERVEUR ne modifie jamais Rekordbox ; l'outil local `relocate_tracks.py` est l'unique exception assumée, dry-run par défaut ») et corriger la phrase « they read the local Rekordbox library ». Alternative si l'outil est obsolète : l'archiver dans `docs/completed/`.
- **Dépendances** : aucune.
- **Tags** : —

### [A8-02] Beatport async : une réponse non-200 est comptée comme « not found » et stampe `beatport_searched_at`
- **Type** : bug
- **Sévérité** : moyenne
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** : `workers/async_http.py:146-165` (`beatport_get` retourne la réponse telle quelle, aucun raise sur non-200, contrairement à `deezer_get` :140-141 qui lève `DeezerHTTPError`) ; `workers/enrichment.py:507-508` et `:533-534` (`if resp.status_code != 200: return []`) ; `:676-678` — `bp_track` None → `not_found += 1` puis `_mark_searched(entry, "beatport", …)`. Le jumeau sync fait `resp.raise_for_status()` (`api/beatport/client.py:242`).
- **Constat** : viole l'invariant E1 « An HTTP failure never stamps `*_searched_at` (an outage is not an attempt) » pour la source Beatport dans le chemin ASYNC — celui utilisé par le drain horaire (jusqu'à 550 lignes/run). Un après-midi de 403 Cloudflare ou de 5xx consomme une « attempt » sur chaque candidat du run ; à 3 événements de ce genre, des lignes basculent `abandoned` à tort (récupérables uniquement via `POST /api/admin/reset-beatport`). Seules les exceptions réseau (curl) sont correctement comptées en `errors` sans stamp.
- **Recommandation** : faire lever `beatport_get` (ou `_do_search`/`_do_release_search`/`_fetch_release_tracks`) une `BeatportHTTPError` typée sur statut non-200 (au minimum 403/429/5xx), la catcher dans `_enrich_one` comme le fait le chemin Deezer (`errors += 1`, PAS de `_mark_searched`) — symétrie exacte avec `DeezerHTTPError`.
- **Dépendances** : renvoie à A3 (workers) si ce chemin y est déjà creusé ; cohérent avec le suivi mémoire `enrich-beatport-autoretry`.
- **Tags** : —

### [A8-03] Six tâches longues sans lock Redis single-instance
- **Type** : dette
- **Sévérité** : moyenne
- **Effort estimé** : M
- **Confiance** : haute
- **Preuve** : aucun `r.set(..., nx=True, ex=...)` ni `r.lock` dans : `enrich_catalog` Deezer (`tasks/catalog.py:52-153`, time_limit 9000), `sync_artists` (`tasks/artists.py:734-741`, 4500), `backfill_multi_artists` (`:1435-1442`, 9000), `crawl_trackid_latest` (`tasks/sets.py:529-535`, ~15-17 min observés, limites globales), `link_set_artists` (`tasks/artists.py:1335-1341`), `reclassify_genres_chunk` (`tasks/genres.py:15-22`, time_limit 16200). Grep de contrôle sur `workers/tasks/` (motifs `r.set(`/`lock_key`) : 10 tâches lockées, ces 6 absentes.
- **Constat** : l'invariant « Every long-running task holds a Redis lock » n'est tenu que par 10 tâches sur 16. Le risque concret : `task_acks_late=True` + `task_reject_on_worker_lost=True` (`celery_app.py:83-85`) re-délivrent une tâche tuée par un déploiement → double exécution concurrente possible (double trafic API externe, double écriture). Atténuants réels : `crawl_trackid_latest` a un curseur Redis, `enrich_catalog` Deezer tourne en secondes en régime établi, `sync_artists`/`backfill_multi_artists`/`reclassify` sont admin-triggered — mais tous combinent en plus `autoretry_for=(Exception,)` (cf. A8-04), ce qui multiplie les occasions de chevauchement.
- **Recommandation** : appliquer le pattern de référence (`tasks/catalog.py` beatport : SET NX EX, TTL > time_limit, release conditionnelle) aux 6 tâches, en priorité `enrich_catalog` Deezer (fenêtre 05:00, la plus exposée aux déploiements matinaux) et `crawl_trackid_latest` (la plus longue en beat quotidien).
- **Dépendances** : [A8-04] (même familles de tâches, à traiter dans le même lot).
- **Tags** : —

### [A8-04] `autoretry_for=(Exception,)` résiduel sur des tâches à soft-limit — le footgun documenté de l'incident 2026-07-13
- **Type** : bug
- **Sévérité** : moyenne
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** : `tasks/catalog.py:55-59` (`enrich_catalog` Deezer : `autoretry_for=(Exception,)` + `soft_time_limit=7200`/`time_limit=9000`) ; même décorateur sur `sync_artists` (`tasks/artists.py:737`), `backfill_multi_artists` (`:1438`), `link_set_artists` (`:1338`), `check_followed_artists` (`:1948`), `crawl_trackid_latest` (`tasks/sets.py:532`), `recrawl_incomplete_sets` (`:276`), `crawl_single_playlist` (`tasks/radar.py:253`), `compute_trends` (`tasks/trends.py:120`), chaîne genres (`tasks/genres.py:18,181,237`). CLAUDE.md documente pourtant : « SoftTimeLimitExceeded IS an Exception » = le décorateur qui a transformé le timeout du 2026-07-13 en boucle de re-téléchargement.
- **Constat** : le pitfall est éradiqué des tâches backlog artistes et des drains (bpm/beatport/backfill/resolve — « Deliberately NO autoretry ») mais survit sur 11 tâches. Le cas le plus exposé est `enrich_catalog` Deezer : pas de budget-cap serré côté durée, soft-limit 2h, PAS de lock (A8-03) et autoretry → un run qui tape le soft-limit est re-exécuté (max 3, countdown 60s + backoff) en re-consommant l'API. Ce jumeau est déjà tracké comme reliquat connu (mémoire projet `enrich-autoretry`) — le présent finding le formalise dans le ledger d'audit.
- **Recommandation** : retirer `autoretry_for=(Exception,)` des tâches à soft-limit (remplacer par un catch `SoftTimeLimitExceeded` + flush partiel, pattern `enrich_catalog_beatport`/`analyze_bpm_previews`) ; là où un retry réseau est réellement voulu, restreindre à des exceptions typées (`DeezerHTTPError`, erreurs de connexion).
- **Dépendances** : [A8-03] (mêmes tâches), suivi mémoire `enrich-beatport-autoretry`.
- **Tags** : —

### [A8-05] CLAUDE.md stale : `uq_artists_deezer_id` est désormais porté par la migration 0034
- **Type** : doc
- **Sévérité** : basse
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** : `api/alembic/versions/0034_uq_artists_deezer_id.py:14-19` (`CREATE UNIQUE INDEX IF NOT EXISTS uq_artists_deezer_id … WHERE deezer_id IS NOT NULL AND deezer_id <> 'NOT_FOUND'`, docstring : « The index already exists in prod … on a fresh DB it creates it ») + déclaration modèle `models/artist.py:42-53` (avec `sqlite_where` pour le harnais). CLAUDE.md (§ Database & Alembic) affirme : « exists ONLY in prod, created outside migrations ».
- **Constat** : l'affirmation était vraie avant AU3 ; depuis 0034 l'index est versionné (migration idempotente + modèle). Le pointeur vers le « MANUAL block » de `docs/database-schema.md` est probablement périmé lui aussi. Risque : un dev suit la doc, croit l'index absent des migrations et le recrée/écarte à tort.
- **Recommandation** : mettre à jour la puce CLAUDE.md (« porté par la migration 0034, idempotent — historiquement créé à la main en prod ») et vérifier le bloc MANUAL de `docs/database-schema.md` via `/schema_doc`.
- **Dépendances** : aucune.
- **Tags** : QW-c (correction de doc pure, risque nul).

### [A8-06] `assets/table.css` : un `@media` viewport sur des éléments non-fixed
- **Type** : dette
- **Sévérité** : basse
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** : `server/frontend/src/assets/table.css:122-131` —
  ```css
  /* ============ MOBILE ============ */
  @media (max-width: 640px) {
    table.dt .pbtn, table.dt .act { opacity: 1; }
    table.dt { min-width: 0; }
  }
  ```
  Aucun de ces sélecteurs n'est `position: fixed` (règle CLAUDE.md : « @media ONLY for position: fixed elements »). Tous les autres `@media` breakpoints du front sont conformes (BottomNav, PlayerBar, modals, bottom-sheet Watchlist — tous fixed, cf. tableau §8).
- **Constat** : unique écart à la règle container-queries. L'intention (toujours montrer play/actions au tactile, où le hover n'existe pas) est légitime mais exprimée en largeur viewport alors que les tables vivent dans des contextes container (paliers Explorer 1000/860/700/640).
- **Recommandation** : soit convertir en `@container` (cohérent avec les paliers existants), soit — plus juste sémantiquement pour l'affordance tactile — `@media (pointer: coarse)`, soit documenter l'exception d'un commentaire comme WatchlistView:1330.
- **Dépendances** : aucune.
- **Tags** : —

---

## Observations hors décompte (pas des violations)

- **`users.picture_url`** (`models/user.py:12`) : URL d'image externe (avatar Google OAuth) en DB. Hors périmètre de l'invariant artwork/MinIO (design auth délibéré, rafraîchi au login `routers/auth.py:102-103`), mais mérite une ligne dans CLAUDE.md si on veut la lettre stricte de « Never store external image URLs in DB ».
- **Logo Google** (`LoginView.vue:16-28`) : 4 couleurs hex de marque dans le SVG du bouton OAuth — exception légitime à « zero hardcoded colors » (non tokenisable, identique aux 2 thèmes).
- **Commentaires/docstrings mixtes FR/EN** dans le backend : pratique historique constante (CLAUDE.md est lui-même bilingue) ; la règle « Code in English » est lue comme portant sur les identifiants/API, tenue partout.
- **Résidus acceptés vérifiés non comptés** (conformes à la consigne) : `/storage/*` non authentifié, absence d'index unique plateforme, chaîne Alembic non bootstrappable, `create_all` des conftest, endpoints taxonomy réservés.
