# Diggy - Project Context

> DJ web app to manage and visualize a Rekordbox library: tracks, radar, sets, artists, genres.
> Last verified: 2026-08-09 (E2.c — task VPS nocturne `analyze_bpm_previews` (queue `enrich`, drain horaire 00h→03h, batch 2000 ≈ 8000/nuit, lock `lock:analyze_bpm`, budget `.env` auto-tapering) qui DÉRIVE le BPM estimé des previews Deezer et SUPERSÈDE l'outil local `worker/bpm_backfill/` comme mécanisme principal ; réutilise le cœur d'analyse (fetch `deezer_get` + `download_audio` + Essentia hors boucle async `run_in_executor` + gate conf≥2.0 + garde `bpm IS NULL` + `bpm_source='analysis'`, stampe `bpm_analyzed_at` sur VERDICT seulement — pas sur outage). Essentia+ffmpeg ajoutés à l'IMAGE worker partagée (~doublée à 312 Mo ; pin `essentia==2.1b6.dev1389`, seul wheel cp313, vérifié behaviorally = BPM 123.53 sur HBFS). Migration 0043 : colonnes `catalog.bpm_analyzed_at`/`bpm_analysis_attempts` (marqueur d'attempt, `bpm_analysis_candidate_filter()` = source unique du prédicat, partagée task+admin). 12e carte admin Aperçu « À analyser (BPM) » (renvoi neutre → Monitoring) + E2.c.2 : courbe backlog BPM (`catalog.bpm_missing`, série horaire via `snapshot_backlogs`, garde `Number.isFinite` côté front) sur la page Monitoring. Prior E2.b Analyse audio previews — backfill BPM ESTIMÉ depuis les previews Deezer 30s pour les catalog sans bpm : outillage LOCAL `worker/bpm_backfill/` (Essentia RhythmExtractor2013 en conteneur Docker, gate confiance>=2.0, écrit `bpm_source='analysis'` via ssh-psql, garde `bpm IS NULL`), 3 lots (backfill local + label UI « estimé » quand `bpm_source==='analysis'` + alimentation `bpm_source` dans les builders list/detail avec override `rekordbox`). Benchmark E2.a (`docs/e2a-benchmark/`) : BPM GO ~84% gaté (TempoCNN ~+2pts mais TensorFlow écarté), KEY NO-GO (edma/shaath/real libkeyfinder tous insuffisants). `bpm_source='analysis'` = autorité la plus basse (jamais prioritaire sur beatport/rekordbox, un run Beatport ultérieur l'écrase) et alimente désormais `similarity_service` (bpm = feature de scoring). Prior : D6.0 Suppression Rating — dernier volet transverse de D6 : la note étoile Rekordbox `user_tracks.rating` (0-5) est RETIRÉE de tout le backend (le front l'était déjà, purge incrémentale D6.a/D6.c). L1 (purge applicative, non destructif) : `avg_rating` retiré du détail artiste (`artist_service`, dict `stats`) ; les 2 tris `rating.desc()` (top-tracks artiste + related « même artiste » de Track Detail) remplacés par « en-lib d'abord » (`catalog_id.desc().nulls_last()`, déterministe — purge PURE, PAS de pondération par l'avis) ; champ `TrackImport.rating`, parsing de l'attribut XML `Rating` (`rekordbox_xml`), écriture à l'import (`import_rb`) et clause `rating = COALESCE(...)` du merge (`catalog_merge`) supprimés. L2 (drop colonne, destructif) : `UserTrack.rating` retiré du modèle + migration 0042 (DROP COLUMN + DROP CONSTRAINT `ck_rating_range`, downgrade symétrique recréant l'un et l'autre). `server/deezer/sync_checker.py` (outillage local, note Rekordbox brute pour dédup) HORS périmètre, intact. 1559 tests verts, schema doc régénéré. Reste sur D6 : revue design Phase 5 de Genre Detail. Prior (Refonte Genre Detail, dernière page D6) — comptage composants 57→56 : GenreTrackRow/LibDot/StatStrip purgés ; `usePaginatedList.endpoint` accepte désormais un MaybeRefOrGetter, lu via `toValue` au fetch — no-op pour une chaîne. Audit précédent 2026-07-31 : Sanity check crawl/backlogs — l'hypothèse « inflow ~5000/j » du 2026-07-27 était FAUSSE : à `TRACKID_BACKFILL_SETS_PER_DAY=1000` l'inflow réel MESURÉ = **~12000 tracks/j** (backfill 1000 sets + `crawl_trackid_latest` ~450 sets, ~7,6 tracks/set), AU-DESSUS de la capacité Beatport **~9900/j** (18 runs × 550, saturés à 100 % — chaque run tape `total=550`, 0 idle, 0 soft-limit) → le backlog Beatport `never_tried` s'accumulait **~+2000/j** (plancher nocturne 663→2758→4839 les 28→30/07 ; `cooldown` not-found +~1500/j, vague `due_retry` attendue ~fin août à J+30). Remède : `TRACKID_BACKFILL_SETS_PER_DAY` prod ramené **1000→600** le 2026-07-31 (~800 sets = break-even ; 600 laisse une marge de drainage ; le défaut CODE reste 1000, prod override via `.env`) — live sets + Deezer inchangés (`never_tried` Deezer = 0). Recréation CIBLÉE du seul service `worker` (`docker compose up -d --no-deps worker`) : les 5 services partagent `env_file: .env`, un `up -d` global aurait recréé `worker_enrich` PENDANT un run Beatport actif = lock orphelin (cf. pitfall). Système sain par ailleurs : 10/10 conteneurs healthy, 0 run en échec/3j. Prior (Dédup artistes Deezer + NFC) — diagnostic prod : ~205 des 965 artistes `deezer_id IS NULL` sont des DOUBLONS du même artiste écrit sous orthographe/forme Unicode différente (« Nick León »/« Nick Leon », « Zoë » NFD vs NFC) : le matcher Deezer folde les accents (`_norm_artist_name`, NFKD+ASCII) mais la clé d'identité `artists.normalized_name` (UNIQUE) est accent-sensible (`utils.normalize`) → 2 lignes créées, l'une se lie, la jumelle bloquée à jamais par `uq_artists_deezer_id`. Fix 3 volets, AUCUN modèle/migration : (1) primitive SYNC `workers/artist_merge.merge_artist_into` (réassigne catalog_artists/set_artists conflict-aware + déplace alias + delete — jumelle sync de la branche merge de `artist_service.link_to_deezer`, mais emporte AUSSI les alias existants de la source) ; (2) `utils.normalize` applique NFC (unifie précomposé/décomposé, ex. exports Rekordbox macOS NFD ; PAS de folding d'accent — collapserait des `normalized_key` catalog distincts, invariant #4) ; (3) `_link_artist_deezer` renvoie `("merge", holder_id)` sur un match dont l'id est déjà détenu (au lieu de laisser l'orphelin pourrir jusqu'à `abandoned`) → l'orchestrateur COLLECTE les couples pendant le `gather` puis fusionne SÉQUENTIELLEMENT hors gather (la session sync est partagée — un DELETE/UPDATE+flush pendant le gather la corromprait), chaque merge dans son propre commit, nouveau compteur stats `merged` (déjà agrégé par `monitoring_service`). Cleanup one-shot `scripts/dedup_artists_deezer.py` (dry-run/`--apply`/`--no-verify`, confirmation Deezer, paires ambiguës/non-confirmées laissées intactes — invariant #4). Prior (Radar) — nouvelle page `/radar` = surface de reco bi-score : `GET /api/radar/feed` (`radar_service.list_bi_score`) fusionne top-N Tendance par famille (`radar_trends.rank_in_family`) ∪ ≤100 reco perso (`recommendation_service`) par `catalog_id`, 2 notes /10 max-normalisées PAR COLONNE (« — » si absente sur un axe), filtres/tri façon Explorer, `catalog_visible`, JWT ; `catalog_service.list_catalog` gagne un param ADDITIF `catalog_ids` (défaut None = comportement inchangé) réutilisé comme builder canonique des lignes Tendance ; nouvelle vue `RadarView.vue` (réutilise composables + famille `filters/` + `ScoreRing` ×2, tri Tendance défaut, cold-start, responsive préservant les 2 scores), entrée nav Sidebar+Bottom, « voir plus » Hub (« Ça sort »/« Pour toi ») → /radar ; AUCUN modèle ni migration. Prior (MON) — monitoring + scheduler Beatport horaire : `enrich_catalog_beatport` passe de 2 passes (06:00/15:00) à un DRAIN HORAIRE borné `crontab(minute=0, hour="6-23")` `batch_size=550` (réduit de 800 le 2026-07-23, commit 21d0a7f — à 800 la majorité des runs tapaient le soft/hard time-limit ; time_limit 3300s, BEATPORT_LOCK_TTL 3900s, autoretry retiré → un kill de déploiement coûte ≤1h au lieu de ~8h). Nouvelle table `metric_snapshots` (migration 0041) + tâche `snapshot_backlogs` (`tasks/monitoring.py`, `count_enrich_backlog` fidèle aux tiers E1) + `monitoring_service` + `GET /admin/monitoring` + page `AdminMonitoring` (composants SVG maison `components/charts/`). Prior (X3) — enrichment match validation: `deezer_enrich._deezer_hit_matches` (ISRC-or-remix-aware title + folded artist) and `beatport/client._release_title_matches` gate id-stamping in BOTH the sync and async twins of each searcher; a non-match stamps nothing and the row stays E1-eligible. New OPS script `scripts/reverify_platform_ids.py` (dry-run/`--apply`) clears pre-X3 ids shared across distinct recordings for E1 re-enrichment. No model/migration change — the platform-id unique index stays deliberately ABSENT. Prior (2026-07-21): D6 p.1 Explorer rebuild — `components/filters/` family (12) + windowing composables, migration 0039)
> If you notice a divergence between this file and the actual code, SAY SO explicitly instead of silently working around it. Suggest the fix for this file.

## Tech Stack

| Layer | Tech |
|-------|------|
| API | FastAPI 0.115 + SQLAlchemy 2.0 async + Alembic (43 migrations) |
| Database | PostgreSQL 16 |
| Queue | Celery 5.4 + Redis (2 workers: `diggy_worker` + `diggy_worker_enrich`) |
| Storage | MinIO (S3-compatible) |
| Frontend | Vue 3 + Vite + Pinia (static build served by Nginx in prod) |
| Proxy | Nginx (HTTPS Let's Encrypt, certbot auto-renew) |
| Deploy | Docker Compose on Hostinger VPS (Ubuntu 24.04), push to master = auto-deploy |

## Architecture

```
server/
├── api/
│   ├── main.py              # FastAPI entrypoint
│   ├── models/              # SQLAlchemy models (31 classes, 12 modules):
│   │                        # catalog, user, artist, radar, sets, genre,
│   │                        # collection, opinion, admin, monitoring (+ base, __init__)
│   │                        # sets module gained: SetFlag, SetFlagType, SetFlagStatus
│   │                        # artist module gained: FollowedArtist, ArtistActivity (C6.c)
│   ├── dependencies.py      # get_current_user, require_admin
│   ├── rate_limit.py        # Per-IP/endpoint rate limiting
│   ├── alembic/             # Migrations (alembic.ini is in server/api/)
│   ├── trackid/             # TrackID.net set importer
│   ├── routers/             # 15 routers, 105 endpoints (admin gained GET /admin/backlog — Aperçu backlog dashboard):
│   │                        # catalog, radar, watchlist, artists, following, sets,
│   │                        # genres, taxonomy, search, collections, opinions,
│   │                        # import_rb, auth, admin, recommendations (taxonomy = 11
│   │                        # reserved endpoints, not wired to the frontend: future genre
│   │                        # explorer. search gained GET /search/external, catalog gained
│   │                        # POST /import — manual external import, F5. recommendations =
│   │                        # GET /api/recommendations, JWT-only, personalized reco, C4)
│   └── services/            # Business logic lives HERE, not in routers:
│                            # genre, artist, catalog, radar, image, search, watchlist,
│                            # following, similarity (C4: load_similarity_context +
│                            # similar_from_context multi-seed primitive — NB: NOT catalog-only,
│                            # also consumes DJ-set co-occurrence via _load_set_map, so sets are
│                            # a similarity/reco input; _load_set_map is roots-only since the
│                            # C4 pooling fix, 2026-07-16; similar_sets aggregates the engine
│                            # at set level — overlap + proximity, D4 p.3), artist_connection,
│                            # opinion_sync, rekordbox_xml, set_dedup (normalize_set_title,
│                            # match_set, materialize_parent), external_search (Deezer+TIDAL
│                            # manual import), recommendation (C4: reco perso = likes/lib ×
│                            # similarity, on-the-fly + Redis cache), monitoring (MON:
│                            # agrégation crawl_logs débit/erreurs/durées + série
│                            # metric_snapshots pour la page admin de monitoring)
├── workers/
│   ├── celery_app.py        # Celery config + beat schedule
│   ├── deezer_enrich.py     # Deezer search + enrichment
│   ├── source_clients.py    # Multi-source abstraction (Deezer/TIDAL/Spotify)
│   └── tasks/               # 8 modules: radar, catalog, artists, genres,
│                            # import_rb, sets, trends, monitoring (MON: snapshot_backlogs)
├── frontend/src/
│   ├── views/               # 18 views (all routed; RadarView added D6; CatalogView renamed ExplorerView, D6)
│   ├── components/          # 58 components (49 shared + 9 admin, AdminOverview = admin Aperçu backlog; GenreTrackRow/LibDot/
│   │                        # StatStrip purged with the Genre Detail rebuild; BeatportEmbed = preview
│   │                        # fallback via the official Beatport iframe embed, Track Detail hero ONLY,
│   │                        # CSP frame-src embed.beatport.com). The filter family
│   │                        # lives in components/filters/ (12: FilterBar/Chip/Panel/
│   │                        # Drawer + SearchInput/RangeSlider/CamelotSelect/
│   │                        # StyleMultiSelect/ArtistTypeAhead/SegmentedFilter/
│   │                        # ToggleChip/SortSelect) + camelot.js/criteria.js helpers.
│   │                        # The charts family = components/charts/ (3: TimeSeriesChart/
│   │                        # SparkLine/StatTile, SVG maison token-driven) → admin
│   │                        # AdminMonitoring page (MON)
│   ├── composables/         # useInfiniteScroll, usePaginatedList, useTaskPoll,
│   │                        # useStyleMap, useTheme, useVirtualWindow, useWindowedList,
│   │                        # useFilterState (last 3 = Explorer/D6, reused by Radar)
│   ├── stores/              # Pinia: auth, audioPlayer, opinions, toast
│   └── styles/diggy-tokens.css  # ALL colors/spacing (zero hardcoded)
└── nginx/                   # default.ssl.conf.template = active prod config
```

Rule: new business logic goes in a service, routers stay thin. New Celery tasks go in the matching `tasks/` module.

Local tooling (A7-07): `worker/` (`relocate_tracks.py`) + `server/deezer/` (`extractor.py`, `sync_checker.py`) run on the PC where Rekordbox is installed — they read the local Rekordbox library, outside the server runtime. `worker/bpm_backfill/` (E2.b) is another local tool run on the PC in a Docker Linux container (Essentia doesn't install on Windows): it derives an estimated BPM from Deezer previews (`RhythmExtractor2013`, confidence-gated >=2.0) and writes `bpm_source='analysis'` to prod via the `ssh diggy-vps … psql` channel — dry-run by default, `--apply` to write, `bpm IS NULL` guard so a trusted bpm is never overwritten. **Since E2.c this local tool is an OPTIONAL manual accelerator** — the main mechanism is the nightly VPS Celery task `analyze_bpm_previews` (essentia+ffmpeg are now in the shared worker image; see Celery Beat Schedule). `worker/import_rekordbox.py` is archived in `docs/completed/` (the official import flow is the web XML upload via the `import_rb` router).

## Database

`catalog` is the ONLY hub. Everything points to it via `catalog_id`.

- Dedup via `normalized_key` (artist|title) or `isrc` at ingestion. Since X1 (2026-07-22) enrichment also folds a row into a pre-existing one **only when it is the same recording** — guard `workers/catalog_merge.same_track` (equal ISRC, else remix-aware `normalize_track_title`); the FK-safe merge primitive `merge_catalog_entries` (+ `pick_canonical`) is wired at the enrichment write points by `workers/catalog_dedup.py`. **Platform ids (`deezer_id`/`beatport_id`) are NOT a per-recording identity** — pre-X3, Deezer search stamped `hits[0]` unchecked (a remix inherited the original's deezer_id) and the Beatport release fallback shared one beatport_id across an EP; ~77%/94% of those id-groups are DISTINCT recordings. So NEVER dedup/cluster on a platform id alone, and there is deliberately **no unique index** on them. Since X3 (2026-07-22) enrichment VALIDATES the match before stamping an id: Deezer hits are checked against the entry (`deezer_enrich._deezer_hit_matches` — equal ISRC, else remix-aware `normalize_track_title` + folded artist) and the Beatport release fallback requires a remix-aware title match (`beatport/client._release_title_matches`); the gate lives in BOTH the sync and async twins of each searcher, and a non-match stamps nothing so the row stays E1-eligible (better no id than a wrong id). Two cleanups for pre-X3 rows (both dry-run/`--apply`, `same_track` clustering): `scripts/dedup_catalog.py` merges TRUE duplicates, `scripts/reverify_platform_ids.py` clears ids shared across DISTINCT recordings so E1 re-enriches them with the corrected matcher (it resets the id + search state on both passes; the beatport pass ALSO nulls beatport-sourced `bpm`/`key` — never a rekordbox/deezer-sourced value, invariant #2 — and the deezer pass ALSO resets stale `has_preview` to False when no `deezer` radar source still backs the row [`has_preview` is a Deezer-only signal → an orphaned True with a cleared `deezer_id` makes the frontend offer a Play button that 404s; a first prod run left ~2.3k such rows, fixed 2026-07-22], so E1 re-derives them; other mis-derived metadata like cover is a known residual).
- `user_tracks`: composite PK `(user_id, catalog_id)`, FK to catalog is `ON DELETE RESTRICT`
- `catalog_artists`: many-to-many with `role` + `position` (~7200 rows). Never assume a single artist per track.
- Genres: `catalog.genres` is a `TEXT[]` of raw names; normalization goes through the graph `genre_nodes` / `genre_edges` / `genre_mappings` (Wikidata-based). The legacy tables `genres`, `catalog_genres`, `artist_genres`, `set_genres` were DROPPED in migration 0013 and no longer exist.
- Artist genres are computed dynamically from their catalog tracks (`artist_service._artist_genres()`), there is no association table.
- Timestamps: TIMESTAMPTZ (UTC). Durations: milliseconds (integer).
- `has_artwork` = file exists in MinIO. Never store external image URLs in DB.
- Deezer sentinel: `deezer_id = "NOT_FOUND"` marks artists confirmed absent from Deezer.
- Sets dedup (C6.0): `sets.parent_set_id` (self-referential FK, ON DELETE SET NULL) + `is_virtual` model virtual parents. Only roots (`parent_set_id IS NULL`) appear in listings and trend scoring. `set_flags` table tracks ambiguous pairs for admin review. Service: `services/set_dedup_service.py`.
- Enrichment re-scan (E1): a not-found catalog entry is retried after 30 then 90 days, abandoned after 3 attempts (`deezer_search_attempts` / `beatport_search_attempts`). An HTTP failure never stamps `*_searched_at` (an outage is not an attempt). Deezer runs one nightly sweep (05:00); Beatport is an **hourly bounded drain** (6h→23h, `batch_size=550`/run — reduced from 800 on 2026-07-23) since MON. `batch_size` (550) is the effective per-run cap: it always binds under the per-source `ENRICH_NIGHTLY_BUDGET` (default 6000) via `min()`, and there is NO cross-run daily accounting — so the real daily ceiling is 18 runs × 550 ≈ **9900/day** (rate-bound ~940/h), NOT 6000. Observed idle (`total: 0`) once the actionable backlog hits 0. Same idea on `artists.deezer_searched_at` (30-day retry; the `NOT_FOUND` sentinel stays a human decision).
- Monitoring (MON): `metric_snapshots` (migration 0041, `captured_at` + `payload` JSON) = échantillon horaire des tailles de backlog écrit par la tâche `snapshot_backlogs` ; les comptes d'éligibilité viennent de `workers/enrichment.count_enrich_backlog` (fidèle aux tiers E1 : never/due/cooldown/abandoned partitionnent, `total_missing` autoritaire). L'historique débit/erreurs/durées vit déjà dans `crawl_logs` (chaque run y écrit `stats`). Agrégé par `services/monitoring_service.py` (en Python, dialect-neutre) → `GET /admin/monitoring` → page admin `AdminMonitoring`.
- Sets re-crawl (C6.b): `sets.completion_pct` is **is_id-based only** (`catalog_id` is reset by every re-import, it cannot back a stable metric); `recrawl_count` = CONSECUTIVE re-crawls without progression (3 stale runs or age > 90 days → `recrawl_status='final'`, no more crawls). Cap per run: `RECRAWL_MAX_SETS_PER_RUN` (default 500, newest first).
- Artist follow (C6.c): `followed_artists` (composite PK user/artist) + `artist_activity` feed; unique `(artist_id, activity_type, source, external_id)` is the worker's idempotence guarantee. Per-user "seen" marker = `users.settings["artist_activity_seen_at"]`. Follow ≠ like: decorrelated by design (acted product decision), no sync with `user_opinions`.
- Release crawl (C6.c v2, 2026-07-13): a detected Deezer release is now **fully crawled into the catalog** — the album is expanded into its tracklist and **each track** becomes its own `artist_activity` (`external_id` = Deezer **track** id, not album id) linked via `catalog_id` to a freshly created `scope='shared'` catalog entry (cover, preview, artists, `release_date`), so the "Nouveautés" shelf renders it like any other track (`worker._crawl_track` reuses `deezer_enrich.enrich_entry` + `link_catalog_artist_from_hit`). Fan-out capped at `ARTIST_ACTIVITY_MAX_TRACKS_PER_RELEASE` (40, logged when hit). A track whose `/track/{id}` fetch fails still gets a **link-only** activity (`catalog_id` NULL → external Deezer link fallback). The pre-crawl album-level card (`external_id` = album id) is self-healingly deleted when the album is reprocessed. `get_activity` LEFT JOINs the catalog (through `catalog_visible`) and returns the track fields (`has_artwork/has_preview/bpm/key/duration_ms/artist/release_date`); the Hub formats a "Sorti il y a Nj" age. Stats gained `catalog_created` + `crawl_errors`.
- Playlist auto-crawl (C6.e): `crawl_radar` crawls EVERY `watched_entities` row — a `user_follows` follower is a priority signal (daily floor + cap priority), NOT a filter. Adaptive cadence from `watched_entities.last_changed_at` (stamped only when a crawl inserts/removes tracks; fallback `created_at`): changed <14d → daily, 14-60d → weekly, >60d → monthly, never `final` (a playlist can always come back to life). Fan-out cap `CRAWL_RADAR_MAX_DISPATCH` (default 200, followed first then most recently changed). Reactivation guard: never crawled OR dormant >30d → inserts flagged `is_initial_detection` (excluded from trend velocity).

→ Before any model change, migration, or query joining 3+ tables: read `docs/database-schema.md`.

## Data Authority Principles

These are project invariants. Never propose code that violates them.

1. **Rekordbox is read-only** from Diggy's perspective. All write operations stay within Rekordbox itself.
2. **Rekordbox BPM is authoritative** over all external sources for the user's performance data.
3. **Beatport is the canonical authority** for BPM and key in the shared catalog (`bpm_source` / `key_source` track provenance). Since E2.b, `bpm_source='analysis'` is a **lower-authority** estimated BPM derived from Deezer preview audio (Essentia `RhythmExtractor2013`, confidence-gated ≥2.0) — written only where `bpm IS NULL`, never over a beatport/rekordbox value, and overwritten by a later Beatport enrichment. It DOES feed `similarity_service` (bpm is a scoring feature, accepted). No `analysis` key is ever written (E2.a benchmark: NO-GO on key).
4. **Merge asymmetry**: duplicate rows (false negatives) are cheap storage debt; bad merges (false positives) are expensive data corruption. Always err toward separation.
5. **LLMs handle language-boundary tasks only** (normalization, classification assistance, explanation, extraction). They never compute similarity scores and never write directly to DB.

## Auth & Multi-User

- Auth: Google OAuth ONLY. There is no email/password login. OAuth `state` is validated server-side via Redis (`oauth_state:{state}`, TTL 5min, one-shot delete). No localStorage.
- Token delivery: temporary `auth_callback` cookie (base64url no padding, 60s TTL, Secure, SameSite=Lax, httponly=False). Backend 302s to `/login/callback`, frontend reads then deletes the cookie.
- This cookie flow exists because of Safari iOS: hash fragments are dropped on 302 redirects, CSP `script-src 'self'` blocks inline scripts, sessionStorage is lost on cross-origin navigation. Do not "simplify" it back to fragments or storage.
- `uid()` returns `None` for guests. There is no `user_id=1` fallback anymore. Every user-conditional query must handle `None`.
- Catalog read visibility (C3): every query returning `catalog` rows to a reader MUST apply `catalog_service.catalog_visible(user_id)` (ORM predicate) or `catalog_visible_sql(user_id[, alias])` (raw `text()` fragment — bind `:viewer_id` ONLY when `user_id is not None`; the same bind is reused by the `user_track` EXISTS, no extra param). Guests see `scope='shared'` only; an authenticated user sees `shared` rows, their own `owner_id` private rows, **plus any row they hold a `user_track` for** (their imported library). A foreign private row therefore stays hidden UNLESS the viewer imported that same track. Guests keep browsing (no login wall — deliberate: discovery stays open). This third `user_track` clause is what un-blinds a Rekordbox importer: RB import dedups on the globally-UNIQUE `normalized_key`, so a user importing a track that collides with another user's private row is bound (via `user_track`) to that existing row and sees it through this clause — the foreign row is NEVER promoted or mutated. Do NOT "fix" the collision by flipping the foreign private row to `shared`/`owner_id=NULL` (a rejected design: it leaks the owner's private track to guests and every user — a name collision is not a platform match). NOT filtered (accepted residual, non-identifying or disproportionate): aggregate-only counts (genre stats, artist `nb_catalog`) and set tracklists (ORM `set_track.catalog` traversal). Any new catalog read path must add the predicate.
- `/storage/*` artworks are served unauthenticated by nginx (proxied MinIO), IDs sequentially enumerable — a deliberate C3 deferral: cover images only, enumeration reveals existence, not private data. `<img :src>` cannot carry a Bearer header, so protecting them needs a cookie `auth_request` or signed MinIO URLs (future work).
- Admin: `is_admin` flag + `require_admin` dependency. Destructive admin actions are logged in `admin_audit_log`.
- Admin/ops endpoints with no UI (curl only, Q1b-4): `POST /api/admin/reset-beatport` (reset Beatport enrichment state), `POST /api/admin/artists/backfill-multi-artists` (re-split multi-artist strings), `POST /api/watchlist/` (register a new source playlist by URL — `GET /api/watchlist/` itself backs WatchlistView and is not admin-only).

## Dev Commands

```bash
# Backend tests (SQLite in-memory by default, no PG needed; deps in requirements-test.txt)
pytest tests/ -q                                                       # quick serial local run
pytest tests/ -q -n auto --dist loadscope --cov=server --cov-report= --cov-fail-under=55  # exact CI command (parallel via pytest-xdist)
DATABASE_URL=postgresql+asyncpg://test:test@localhost:5432/diggy_test pytest tests/ -q  # PG like CI

# Frontend tests
cd server/frontend && npx vitest run

# Lint - ALL must pass before any commit (push to master deploys to prod)
ruff check server/
cd server/frontend && npm run lint          # eslint
cd server/frontend && npm run format:check  # prettier (gated in CI since 2026-08-06)

# Alembic (alembic.ini lives in server/api/). Use the `alembic` binary: `python -m alembic`
# breaks outside the container (the local alembic/ migrations dir shadows the package)
cd server/api && alembic revision --autogenerate -m "description"
cd server/api && alembic upgrade head
# Prod: CI runs `alembic upgrade head` automatically on deploy

# Local stack (override bind-mounts server/api + server/workers for hot reload; prod runs the image code)
docker compose up -d --build
cd server/frontend && npm run dev     # frontend dev server
```

Full-stack local dev is NOT a supported flow (Q6): the official path is push → CI → prod. `npm run dev` (port 5173) is frontend-only in ALL cases — its Vite `/api` proxy targets `http://api:8000` (a Docker-internal hostname, a leftover from the old containerized dev server) which does not resolve from the host, so API calls fail even with the Docker stack up. They fail cleanly: the page never crashes (the boot swallows network errors — `refreshUser()` and `opinions.load()` both catch). The full local app (static frontend + API + `/api/docs`) is served by nginx on http://localhost:8080.

**Command hygiene (Claude — avoid needless permission prompts):** the Bash tool's cwd **persists** across calls, so `cd` into a subdir in its OWN call — never `cd server/frontend && npx vitest …` inline. The inline `cd X && cmd` form makes the whole command start with `cd`, which no longer matches the command's allow-list prefix (`Bash(npx vitest:*)`, `Bash(ruff check:*)`, …) and forces a prompt. Frontend commands (`npx vitest run`, `npm run lint`) run from `server/frontend`; backend (`pytest`, `ruff check server/`, `alembic`) from the repo root. Same idea for the VPS: use `ssh diggy-vps "…"`, not the raw `-i` key form.

Env vars: see `.env.example` at repo root. Required: `POSTGRES_USER/PASSWORD/DB`, `DATABASE_URL`, `JWT_SECRET`, `MINIO_USER/PASSWORD`. Prod adds `COMPOSE_FILE=docker-compose.yml:docker-compose.ssl.yml` and `DOMAIN`. `ENV=production` disables permissive CORS and the API docs (`/api/docs`, `/api/redoc`, `/api/openapi.json` are not registered).

## Celery Beat Schedule

Heures en `Europe/Paris` (timezone Celery beat). Depuis MON (2026-07-22), Beatport n'est plus 2 grosses passes mais un **drain horaire borné** 6h→23h (`batch_size=550`/run, réduit de 800 le 2026-07-23 ; plafond réel ~9900/j = 18×550, pas 6000) — résilient aux redéploiements (un kill coûte ≤1h au lieu de ~8h) et remplit les heures creuses ; no-op en secondes quand le backlog éligible est vide (auto-throttle).

| Task | Time | Worker (queue) | Durée obs. | Module |
|------|------|----------------|-----------|--------|
| `backfill_trackid_sets` | 02:00 | `diggy_worker` (celery) | ~30 min | tasks/sets.py |
| `crawl_radar` | 03:00 | `diggy_worker` (celery) | qq sec | tasks/radar.py |
| `crawl_trackid_latest` | 03:30 | `diggy_worker` (celery) | ~15-17 min | tasks/sets.py |
| `recrawl_incomplete_sets` | 04:00 | `diggy_worker` (celery) | qq min | tasks/sets.py |
| `check_followed_artists` | 04:45 | `diggy_worker_enrich` (enrich) | court | tasks/artists.py |
| `enrich_catalog` (Deezer) | 05:00 | `diggy_worker_enrich` (enrich) | qq sec | tasks/catalog.py |
| `link_artists_deezer` | 05:10 | `diggy_worker_enrich` (enrich) | court (budget) | tasks/artists.py |
| `fetch_artist_artworks` | 05:20 | `diggy_worker_enrich` (enrich) | court (budget) | tasks/artists.py |
| `enrich_catalog_beatport` (drain horaire) | 06:00→23:00 (chaque h) | `diggy_worker_enrich` (enrich) | ≤55 min/run (batch 550, ~9900/j max) | tasks/catalog.py |
| `compute_trends` | 07:00 | `diggy_worker` (celery) | court | tasks/trends.py |
| `snapshot_backlogs` | :30 (chaque h) | `diggy_worker` (celery) | qq sec | tasks/monitoring.py |
| `analyze_bpm_previews` (drain horaire, E2.c) | 00:00→03:00 (chaque h) | `diggy_worker_enrich` (enrich) | ≤55 min/run (batch 2000, ~8000/nuit) | tasks/bpm.py |

Deux workers consomment le broker : `diggy_worker` (`-Q celery,crawl -c 3`) et `diggy_worker_enrich` (`-Q enrich -c 2`) ; `diggy_beat` ordonnance seulement (n'exécute rien). Les tâches d'enrichissement (APIs externes rate-limitées) sont routées vers la queue `enrich` → `diggy_worker_enrich` ; tout le reste va sur `celery`/`crawl` → `diggy_worker`. Keep that separation when adding tasks. **Overlap** : les deux workers tournent en parallèle (queues distinctes) — une tâche `diggy_worker` (backfill/crawl) et une tâche `enrich` s'exécutent simultanément ; sur un même worker, la concurrence max est le `-c` (3 vs 2). Le **drain Beatport horaire** (6h→23h) est single-instance via le lock Redis `lock:enrich_beatport` (TTL 3900s ≥ `time_limit` 3300s) : un créneau ne peut pas chevaucher le suivant (le 2e skip si le 1er court encore), et le TTL court fait qu'un **lock orphelin** (worker tué par un déploiement) s'auto-guérit en ≤1h au lieu de bloquer ~8h. `snapshot_backlogs` tourne sur la queue `celery` (pas d'API externe) décalé à :30. Le **drain BPM E2.c** (`analyze_bpm_previews`, 00h→03h, queue `enrich`) est single-instance via `lock:analyze_bpm` (TTL 3900s ≥ time_limit 3300s), no-op en secondes quand le backlog `bpm_analysis_candidate_filter()` est vide (auto-tapering), pas d'`autoretry` ; Essentia (CPU-bloquant) tourne HORS boucle async via `run_in_executor` (ThreadPoolExecutor borné). Placé 00h→03h pour éviter la fenêtre Deezer (05h) et le drain Beatport (6h→23h).

Artist backlog (loop-safe, C-lot): `link_artists_deezer` (budget `ARTIST_LINK_NIGHTLY_BUDGET`=1500) and `fetch_artist_artworks` (budget `ARTIST_ARTWORK_NIGHTLY_BUDGET`=10000, `budget` kwarg overrides for an ad-hoc drain) are budget-capped, batch-committing and Redis-locked, with **NO `autoretry_for=(Exception,)`** — that decorator turned the 2026-07-13 soft timeout into an infinite re-download loop (`SoftTimeLimitExceeded` IS an `Exception`). The budget cap (dimensioned well under the soft limit) is the primary loop guard; both are placed at 05:10/05:20 in the Deezer-idle window (enrich_catalog finishes in seconds, enrich_beatport uses the separate Beatport rate window). Since the artist-dedup chantier (2026-07-24), `link_artists_deezer` no longer ORPHANS an accent/Unicode duplicate: when a valid match's id is already held by another artist row (the SAME real artist under a different spelling — the Deezer matcher `_norm_artist_name` folds accents, the identity key `artists.normalized_name` UNIQUE does not), `_link_artist_deezer` returns `("merge", holder_id)` and the orchestrator folds the orphan into the holder via `workers/artist_merge.merge_artist_into`. The merge is COLLECTED during the concurrent `gather` but executed SEQUENTIALLY after it — the batch shares one sync Session, so a mid-gather DELETE/UPDATE+flush would corrupt it — each merge in its OWN commit (a failed one is rolled back, orphan stays E1-eligible; stats key `merged`). `utils.normalize` now NFC-normalizes (kills composition-only twins going forward, e.g. Rekordbox macOS NFD exports) but deliberately does NOT accent-fold. One-shot backfill of the pre-existing orphans: `scripts/dedup_artists_deezer.py` (dry-run/`--apply`, Deezer-confirmed, ambiguous pairs left intact — invariant #4). Fold guard: `_norm_artist_name` (NFKD+ASCII) collapses a fully non-Latin name (Japanese/Hebrew/…) to a BLANK string — so the fold branch of every Deezer name-match is gated on a non-empty fold (`name_norm and …`) in BOTH `_link_artist_deezer` and `sync_artists` Phase B; a blank fold would otherwise match ANY other non-Latin name (all fold to blank) and wrongly link/merge them. The raw exact-name match stays active for all names, so a verbatim non-Latin Deezer hit still links/dedups correctly.

## Known Pitfalls

### Nginx
- `add_header` in a `location` block REMOVES all server-level headers. Asset locations must be nested inside `location /` without their own `add_header` to inherit the CSP.
- `/api/`, `/storage/`, `/minio/` use `^~` prefix priority so they are not captured by the assets regex `\.(js|css|jpg)$`.
- The active prod config is `default.ssl.conf.template`. `default.conf` is intentionally empty.
- Keep CSP `upgrade-insecure-requests` as long as any `http://` request can arrive.
- `client_max_body_size` (12M) is coupled to the Rekordbox XML import limit (`MAX_FILE_SIZE` 10MB in `import_rb.py`): keep nginx slightly above the app limit so the app returns its French 413 message, and raise both together.

### Docker & Backup
- api/worker/worker_enrich/beat share ONE image built from context `./server` (`server/Dockerfile` copies `api/` + `workers/`). Prod runs the code baked into the image — hot reload only exists through the local override bind mounts.
- `server/.dockerignore` excludes `frontend/`, `nginx/`, `scripts/`, `deezer/` from the build context: a new directory under `server/` needed at runtime must be removed from that file, or it silently won't ship.
- The `backup` service mounts `/root/.config/rclone` read-write (VPS-only path): rclone rewrites its OAuth token on refresh — never make this mount `:ro`. Offsite = encrypted PG dumps only (MinIO mirror stays local by design).

### Workers & Celery
- Every long-running task holds a Redis lock: atomic `SET NX EX`, TTL strictly above the task's `time_limit`, release conditional on still owning the lock (reference pattern: `tasks/catalog.py`). Never check-then-set, never a TTL below the time_limit.
- Deezer/Beatport rate limits are shared across worker processes via a Redis fixed window inside `rate_limiter.py` (fail-open to the local bucket if Redis is down). Instantiating `RateLimiter()` per task is fine — the global cap holds anyway.
- Destructive cleanup of a watched playlist triggers ONLY on `PlaylistGoneError` (typed per source in `source_clients.py`), never on string-matching an exception message.
- Never `result.get()` inside a task (blocks a worker slot for the whole run) — use a `chord` with a finalize callback + errback (pattern: `tasks/genres.py`).
- A cadence gate compared against a daily beat needs slack: the beat fires every 24h sharp but the reference timestamp is stamped DURING the previous run, so a strict `elapsed > 1d` check skips every other run (daily tier → every other day). Subtract `CADENCE_SLACK_DAYS` (0.25) from the threshold — pattern: `tasks/radar.py` + `tasks/sets.py`.
- Un déploiement (`docker compose up -d`) qui recrée les workers **pendant** un run enrich tue le process (SIGKILL) sans exécuter la release conditionnelle du lock → `lock:enrich_beatport` orphelin qui fait skip la tâche suivante jusqu'à expiration du TTL (MON, constaté 2026-07-22). Mitigé par le TTL court (3900s depuis le drain horaire) : au pire 1 créneau sauté. Remédiation à chaud : `redis-cli DEL lock:enrich_beatport` **seulement si** `celery … inspect active` ne montre aucune tâche. Éviter de pousser sur master pendant les fenêtres enrich (Beatport 6h→23h, Deezer 05:00).

### Database & Alembic
- Since AU3 the API never runs `create_all`: the schema comes from Alembic ONLY (test harnesses keep their own `create_all` in `tests/*/conftest.py`). In local dev, the compose override runs `alembic upgrade head` before uvicorn.
- **CI runs pytest under xdist** (`-n auto --dist loadscope`, since bf141ed / 2026-07-24): every backend test must be **parallel-safe**. `tests/api` gives each xdist worker its OWN PostgreSQL database (`diggy_test_gwN`, created at session start via an autocommit maintenance connection under a shared advisory lock; `DATABASE_URL` is rewritten per worker BEFORE the app imports so every engine is isolated). Never reintroduce shared-DB serial assumptions (a per-test `TRUNCATE` on one shared DB corrupts sibling workers) or module-global mutable state. Keep `tests/api` self-sufficient re: Redis — it ships its own in-memory rate-limit stand-in; do NOT rely on another module's `sys.modules` redis mock (before the fix, `pytest tests/api` alone took ~5 min on slowapi's absent-Redis timeouts, "saved" only in the full run by `tests/worker/test_rate_limiter.py`). The SQLite path (default, per-process `:memory:`) is naturally isolated.
- The migration chain is NOT replayable from an empty database: 0001 assumes the pre-Alembic tables historically created by `create_all`. A fresh local PG volume must be seeded from a prod dump (`docs/restore.md`); an old dev volume created by `create_all` must be stamped once (`alembic stamp head`). A baseline/squash migration is a known follow-up.
- `uq_artists_deezer_id` (partial unique on `artists.deezer_id`, sentinel-aware) exists ONLY in prod, created outside migrations — see the MANUAL block of `docs/database-schema.md` before touching artist deezer_id uniqueness.
- NEVER `asyncio.gather` several `db.execute` on the SAME `AsyncSession`: a session is not safe for concurrent access. SQLite masks it, but asyncpg (PostgreSQL/CI) wedges a connection ("non-checked-in connection … will be terminated") and the suite HANGS. Await DB loaders sequentially on one session; if you truly need parallel DB reads, use separate sessions/connections. Bit us in C4 (`load_similarity_context`, `get_connections` — both since serialized).
- `StringArray` (custom `TypeDecorator`, `catalog.genres`) needs an explicit `comparator_factory` for `.any()`/`.in_()`: the base `TypeDecorator.Comparator` does NOT inherit `ARRAY`'s membership ops, so `genres.any(x)` raised `AttributeError` at query-build (a 500, latent since no code path exercised it until the Explorer genre filter). The fix (`models/base.py`) is a per-dialect-compiled `array_any` (`= ANY(col)` on PG, correlated `EXISTS json_each` on SQLite); its sibling `array_is_empty` (`coalesce(array_length(col,1),0)=0` on PG, `coalesce(json_array_length(col),0)=0` on SQLite; added for the admin genre-only enrich filter, AV1) follows the same shape — any new membership/predicate op on a custom array type must compile on BOTH dialects (SQLite backs the test suite).

### Frontend
- Container queries everywhere; `@media` ONLY for `position: fixed` elements.
- Zero hardcoded colors: everything via `var(--...)` from `diggy-tokens.css`.
- No multi-statement inline handlers in templates (`@click="a = 1; b = 2"`): Prettier reformats them across lines, which breaks the Vue compiler. Extract to a method.
- Responsive tables: columns hidden progressively (ExplorerView: 4 container-query paliers 1000/860/700/640). At <640px only Play / Track / BPM / Avis remain (Key drops before BPM — DJs favor BPM on mobile), play & avis always visible (touch).
- BottomNav (mobile <640px): 6 items + conditional Admin (Radar added D6 → 7 with Admin, tight on ≤360px); PlayerBar repositions above it.
- Celery task polling goes through `composables/useTaskPoll.js` (keyed timers, onUnmounted cleanup built in). Two sanctioned paginated-fetch patterns, NEVER a hand-rolled offset/hasMore fetch in a view: card grids with an IntersectionObserver sentinel → `usePaginatedList.js`; virtualised tables (windowing, no sentinel, page-built repeated params) → `useWindowedList.js` paired with `useVirtualWindow.js` (Explorer/D6, reused by Radar). Never reintroduce an ad-hoc `setInterval` poll either.
- The `.state` empty/loading message and `@keyframes spin` are global utilities in `assets/page.css`; views only keep scoped overrides for real divergences (mono, centered, fs-sm...). Don't redeclare the full block locally.
- Vitest: when `vue-router` is mocked, `stubs: { RouterLink: true }` is a no-op (VTU ignores string-name stubs for unresolved components) — register `RouterLinkStub` via `global.components` (pattern: BottomNav.test.js, LoginCallbackView.test.js).
- Grid `1fr` means `minmax(auto, 1fr)`: tracks can NOT shrink below their content's min-content (an `<img>` at natural aspect wins over the fr distribution). For image mosaics constrained to a fixed box, use `minmax(0, 1fr)` + `overflow: hidden` on the box. Corollary: positioned elements paint ABOVE later in-flow siblings — overflowing absolute content silently covers them (Artist Detail hero, 2026-07-20: a complete, correctly-styled DOM was invisible under the overflowing tiles). Neither vitest (no layout) nor static CSS reading catches this — verify RENDERING (headless screenshot) after any layout-sensitive change.

### Language
- Code in English, UI text in French.

## Slash Commands (.claude/commands/)

| Command | Use |
|---------|-----|
| `/work_manager` | Orchestrates a full chantier: analysis, batching, agent prompts, delivery control, closing commit |
| `/deploy_verify` | Post-deploy verification on the VPS: container health, HTTP smoke tests, feature checks |
| `/roadmap_status` | Reads the roadmap, reports pending chantiers, recommends the next one |
| `/roadmap_update` | Updates roadmap statuses after a finished chantier (cross-checks session + git log) |
| `/schema_doc` | Regenerates `docs/database-schema.md` from models and shows the diff |
| `/refonte_page <page>` | Full page-redesign pipeline (fiche → Claude Design prompt/handoff → work_manager lots → deploy → design review round → FIX triage → closure), with the guardrails learned on Track Detail |
| `/audit_global [périmètre]` | Periodic codebase health audit (tech debt, security, perf, dead code): tooled inventory → parallel dimension agents → consolidation → arbitrage → roadmap proposal. Reports in `docs/audits/<AAAA-MM>/`, cross-audit tracking in `docs/audits/LEDGER.md` |

Prefer these over ad-hoc equivalents. Suggest them to the user when relevant. `.claude/commands/` is versioned in the repo (the command definitions ship with the code).

## Deploy

- Domain: `diggy-music.fr`. VPS project path: `/root/diggy`. `.env` lives ONLY on the VPS, never in git.
- Push to `master` → GitHub Actions (ruff + eslint + pytest on real PG + vitest + pip-audit) → SSH → `docker compose build` → `alembic upgrade head` (on the NEW image, before the switch) → `docker compose up -d`. A failing lint blocks everything; a failing build or migration aborts the deploy (old code keeps serving).
- SSH from Claude: **prefer the alias `ssh diggy-vps "…"`** — it matches the skill/allow-list rules (`Bash(ssh diggy-vps:*)`) so it won't prompt; the explicit form `ssh -i /c/Users/willi/.ssh/claude_diggy root@82.29.168.247` also works (dedicated key) but is more verbose.
- Prod read-only SQL (VPS): `ssh diggy-vps "cd /root/diggy && docker compose exec -T postgres sh -c 'psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -c \"SELECT …\"'"`. Gotchas: the DB service is **`postgres`** (not `db`); env vars must expand **inside** the container → wrap the psql call in `sh -c '…'`; table names are the SQLAlchemy `__tablename__` (e.g. `sets`, `set_tracks`, `catalog_artists` — NOT `dj_sets`).
- Local vs prod: local = `docker-compose.yml` + override (hot reload, port 8080 HTTP); prod = `COMPOSE_FILE` chains `docker-compose.ssl.yml` (ports 80/443, certbot container).
- After deploying, run `/deploy_verify`.

## Documentation Pointers (read on trigger)

| Trigger | Read |
|---------|------|
| Model change, migration, 3+ table query | `docs/database-schema.md` (generated — run `/schema_doc` after any model/migration change) |
| Proposing features, choosing next work | `docs/ROADMAP.md` (or run `/roadmap_status`) |
| Starting work on a chantier | Its agent prompt in `docs/prompts/` and its brief in `docs/`. If none exist yet for the target chantier, create them via `/work_manager`. |
| Similarity/scoring work (C2) | `docs/similarity_calibration.ipynb` |
| UI change on an existing view | Historical design handoffs are archived in `docs/completed/design/` (read-only, frozen); new handoffs come from the Claude Design project |
| Backup/restore operation, data incident | `docs/restore.md` (GPG + psql + offsite fetch; keep the "last tested" date honest) |
| Code health audit (running one, or checking a finding's status) | `docs/audits/README.md` + `docs/audits/LEDGER.md` (run `/audit_global`; first historical audit: `docs/audit_2026-07/`) |
| Anything about past decisions | `docs/completed/` contains FROZEN archives: read-only, never treat as current state, NEVER modify |

## Maintaining This File

- This file contains only stable invariants and commands. Volatile state (metrics, chantier progress) lives in the pointed docs.
- When a convention changes or a new pitfall is discovered the hard way, propose adding it here.
- Update the `Last verified` date whenever the file is audited against the code.
