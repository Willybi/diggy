# Diggy - Project Context

> DJ web app to manage and visualize a Rekordbox library: tracks, radar, sets, artists, genres.
> Last verified: 2026-07-13 (C4 — personalized reco: GET /api/recommendations (JWT-only) crosses the user's likes/library with the C2 similarity engine, on-the-fly + Redis cache; similarity_service gained a shared-context multi-seed primitive; "Pour toi" shelf on the Hub. Same day: C3 closed, /storage protection dropped as accepted risk)
> If you notice a divergence between this file and the actual code, SAY SO explicitly instead of silently working around it. Suggest the fix for this file.

## Tech Stack

| Layer | Tech |
|-------|------|
| API | FastAPI 0.115 + SQLAlchemy 2.0 async + Alembic (37 migrations) |
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
│   ├── models/              # SQLAlchemy models (30 classes, 11 modules):
│   │                        # catalog, user, artist, radar, sets, genre,
│   │                        # collection, opinion, admin (+ base, __init__)
│   │                        # sets module gained: SetFlag, SetFlagType, SetFlagStatus
│   │                        # artist module gained: FollowedArtist, ArtistActivity (C6.c)
│   ├── dependencies.py      # get_current_user, require_admin
│   ├── rate_limit.py        # Per-IP/endpoint rate limiting
│   ├── alembic/             # Migrations (alembic.ini is in server/api/)
│   ├── trackid/             # TrackID.net set importer
│   ├── routers/             # 15 routers, 100 endpoints:
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
│                            # similar_from_context multi-seed primitive), artist_connection,
│                            # opinion_sync, rekordbox_xml, set_dedup (normalize_set_title,
│                            # match_set, materialize_parent), external_search (Deezer+TIDAL
│                            # manual import), recommendation (C4: reco perso = likes/lib ×
│                            # similarity, on-the-fly + Redis cache)
├── workers/
│   ├── celery_app.py        # Celery config + beat schedule
│   ├── deezer_enrich.py     # Deezer search + enrichment
│   ├── source_clients.py    # Multi-source abstraction (Deezer/TIDAL/Spotify)
│   └── tasks/               # 7 modules: radar, catalog, artists, genres,
│                            # import_rb, sets, trends
├── frontend/src/
│   ├── views/               # 17 views (all routed)
│   ├── components/          # 34 components (28 shared + 6 admin)
│   ├── composables/         # useInfiniteScroll, usePaginatedList, useTaskPoll,
│   │                        # useStyleMap, useTheme
│   ├── stores/              # Pinia: auth, audioPlayer, opinions, toast
│   └── styles/diggy-tokens.css  # ALL colors/spacing (zero hardcoded)
└── nginx/                   # default.ssl.conf.template = active prod config
```

Rule: new business logic goes in a service, routers stay thin. New Celery tasks go in the matching `tasks/` module.

Local tooling (A7-07): `worker/` (`relocate_tracks.py`) + `server/deezer/` (`extractor.py`, `sync_checker.py`) run on the PC where Rekordbox is installed — they read the local Rekordbox library, outside the server runtime. `worker/import_rekordbox.py` is archived in `docs/completed/` (the official import flow is the web XML upload via the `import_rb` router).

## Database

`catalog` is the ONLY hub. Everything points to it via `catalog_id`.

- Dedup via `normalized_key` (artist|title) or `isrc`
- `user_tracks`: composite PK `(user_id, catalog_id)`, FK to catalog is `ON DELETE RESTRICT`
- `catalog_artists`: many-to-many with `role` + `position` (~7200 rows). Never assume a single artist per track.
- Genres: `catalog.genres` is a `TEXT[]` of raw names; normalization goes through the graph `genre_nodes` / `genre_edges` / `genre_mappings` (Wikidata-based). The legacy tables `genres`, `catalog_genres`, `artist_genres`, `set_genres` were DROPPED in migration 0013 and no longer exist.
- Artist genres are computed dynamically from their catalog tracks (`artist_service._artist_genres()`), there is no association table.
- Timestamps: TIMESTAMPTZ (UTC). Durations: milliseconds (integer).
- `has_artwork` = file exists in MinIO. Never store external image URLs in DB.
- Deezer sentinel: `deezer_id = "NOT_FOUND"` marks artists confirmed absent from Deezer.
- Sets dedup (C6.0): `sets.parent_set_id` (self-referential FK, ON DELETE SET NULL) + `is_virtual` model virtual parents. Only roots (`parent_set_id IS NULL`) appear in listings and trend scoring. `set_flags` table tracks ambiguous pairs for admin review. Service: `services/set_dedup_service.py`.
- Enrichment re-scan (E1): a not-found catalog entry is retried after 30 then 90 days, abandoned after 3 attempts (`deezer_search_attempts` / `beatport_search_attempts`). An HTTP failure never stamps `*_searched_at` (an outage is not an attempt). Nightly sweeps are capped by `ENRICH_NIGHTLY_BUDGET` (default 6000, per source). Same idea on `artists.deezer_searched_at` (30-day retry; the `NOT_FOUND` sentinel stays a human decision).
- Sets re-crawl (C6.b): `sets.completion_pct` is **is_id-based only** (`catalog_id` is reset by every re-import, it cannot back a stable metric); `recrawl_count` = CONSECUTIVE re-crawls without progression (3 stale runs or age > 90 days → `recrawl_status='final'`, no more crawls). Cap per run: `RECRAWL_MAX_SETS_PER_RUN` (default 500, newest first).
- Artist follow (C6.c): `followed_artists` (composite PK user/artist) + `artist_activity` feed; unique `(artist_id, activity_type, source, external_id)` is the worker's idempotence guarantee. Per-user "seen" marker = `users.settings["artist_activity_seen_at"]`. Follow ≠ like: decorrelated by design (acted product decision), no sync with `user_opinions`.
- Release crawl (C6.c v2, 2026-07-13): a detected Deezer release is now **fully crawled into the catalog** — the album is expanded into its tracklist and **each track** becomes its own `artist_activity` (`external_id` = Deezer **track** id, not album id) linked via `catalog_id` to a freshly created `scope='shared'` catalog entry (cover, preview, artists, `release_date`), so the "Nouveautés" shelf renders it like any other track (`worker._crawl_track` reuses `deezer_enrich.enrich_entry` + `link_catalog_artist_from_hit`). Fan-out capped at `ARTIST_ACTIVITY_MAX_TRACKS_PER_RELEASE` (40, logged when hit). A track whose `/track/{id}` fetch fails still gets a **link-only** activity (`catalog_id` NULL → external Deezer link fallback). The pre-crawl album-level card (`external_id` = album id) is self-healingly deleted when the album is reprocessed. `get_activity` LEFT JOINs the catalog (through `catalog_visible`) and returns the track fields (`has_artwork/has_preview/bpm/key/duration_ms/artist/release_date`); the Hub formats a "Sorti il y a Nj" age. Stats gained `catalog_created` + `crawl_errors`.
- Playlist auto-crawl (C6.e): `crawl_radar` crawls EVERY `watched_entities` row — a `user_follows` follower is a priority signal (daily floor + cap priority), NOT a filter. Adaptive cadence from `watched_entities.last_changed_at` (stamped only when a crawl inserts/removes tracks; fallback `created_at`): changed <14d → daily, 14-60d → weekly, >60d → monthly, never `final` (a playlist can always come back to life). Fan-out cap `CRAWL_RADAR_MAX_DISPATCH` (default 200, followed first then most recently changed). Reactivation guard: never crawled OR dormant >30d → inserts flagged `is_initial_detection` (excluded from trend velocity).

→ Before any model change, migration, or query joining 3+ tables: read `docs/database-schema.md`.

## Data Authority Principles

These are project invariants. Never propose code that violates them.

1. **Rekordbox is read-only** from Diggy's perspective. All write operations stay within Rekordbox itself.
2. **Rekordbox BPM is authoritative** over all external sources for the user's performance data.
3. **Beatport is the canonical authority** for BPM and key in the shared catalog (`bpm_source` / `key_source` track provenance).
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
pytest tests/ -q
pytest tests/ -q --cov=server --cov-report= --cov-fail-under=55        # CI coverage gate
DATABASE_URL=postgresql+asyncpg://test:test@localhost:5432/diggy_test pytest tests/ -q  # PG like CI

# Frontend tests
cd server/frontend && npx vitest run

# Lint - BOTH must pass before any commit (push to master deploys to prod)
ruff check server/
cd server/frontend && npm run lint

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

Env vars: see `.env.example` at repo root. Required: `POSTGRES_USER/PASSWORD/DB`, `DATABASE_URL`, `JWT_SECRET`, `MINIO_USER/PASSWORD`. Prod adds `COMPOSE_FILE=docker-compose.yml:docker-compose.ssl.yml` and `DOMAIN`. `ENV=production` disables permissive CORS and the API docs (`/api/docs`, `/api/redoc`, `/api/openapi.json` are not registered).

## Celery Beat Schedule

| Task | Time | Module |
|------|------|--------|
| `backfill_trackid_sets` | 02:00 | tasks/sets.py |
| `crawl_radar` | 03:00 | tasks/radar.py |
| `crawl_trackid_latest` | 03:30 | tasks/sets.py |
| `recrawl_incomplete_sets` | 04:00 | tasks/sets.py |
| `check_followed_artists` | 04:45 | tasks/artists.py |
| `enrich_catalog` (Deezer) | 05:00 | tasks/catalog.py |
| `link_artists_deezer` | 05:10 | tasks/artists.py |
| `fetch_artist_artworks` | 05:20 | tasks/artists.py |
| `enrich_catalog_beatport` | 06:00 | tasks/catalog.py |
| `compute_trends` | 07:00 | tasks/trends.py |

Enrichment tasks run on the dedicated `diggy_worker_enrich` (slow, rate-limited external APIs); everything else on `diggy_worker`. Keep that separation when adding tasks.

Artist backlog (loop-safe, C-lot): `link_artists_deezer` (budget `ARTIST_LINK_NIGHTLY_BUDGET`=1500) and `fetch_artist_artworks` (budget `ARTIST_ARTWORK_NIGHTLY_BUDGET`=10000, `budget` kwarg overrides for an ad-hoc drain) are budget-capped, batch-committing and Redis-locked, with **NO `autoretry_for=(Exception,)`** — that decorator turned the 2026-07-13 soft timeout into an infinite re-download loop (`SoftTimeLimitExceeded` IS an `Exception`). The budget cap (dimensioned well under the soft limit) is the primary loop guard; both are placed at 05:10/05:20 in the Deezer-idle window (enrich_catalog finishes in seconds, enrich_beatport uses the separate Beatport rate window).

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

### Database & Alembic
- Since AU3 the API never runs `create_all`: the schema comes from Alembic ONLY (test harnesses keep their own `create_all` in `tests/*/conftest.py`). In local dev, the compose override runs `alembic upgrade head` before uvicorn.
- The migration chain is NOT replayable from an empty database: 0001 assumes the pre-Alembic tables historically created by `create_all`. A fresh local PG volume must be seeded from a prod dump (`docs/restore.md`); an old dev volume created by `create_all` must be stamped once (`alembic stamp head`). A baseline/squash migration is a known follow-up.
- `uq_artists_deezer_id` (partial unique on `artists.deezer_id`, sentinel-aware) exists ONLY in prod, created outside migrations — see the MANUAL block of `docs/database-schema.md` before touching artist deezer_id uniqueness.
- NEVER `asyncio.gather` several `db.execute` on the SAME `AsyncSession`: a session is not safe for concurrent access. SQLite masks it, but asyncpg (PostgreSQL/CI) wedges a connection ("non-checked-in connection … will be terminated") and the suite HANGS. Await DB loaders sequentially on one session; if you truly need parallel DB reads, use separate sessions/connections. Bit us in C4 (`load_similarity_context`, `get_connections` — both since serialized).

### Frontend
- Container queries everywhere; `@media` ONLY for `position: fixed` elements.
- Zero hardcoded colors: everything via `var(--...)` from `diggy-tokens.css`.
- No multi-statement inline handlers in templates (`@click="a = 1; b = 2"`): Prettier reformats them across lines, which breaks the Vue compiler. Extract to a method.
- Responsive tables: columns hidden progressively across 6 breakpoints (CatalogView). At 375px only Play / Track / Key / InLib remain.
- BottomNav (mobile <640px): 5 items + conditional Admin; PlayerBar repositions above it.
- Celery task polling goes through `composables/useTaskPoll.js` (keyed timers, onUnmounted cleanup built in); paginated infinite-scroll lists through `usePaginatedList.js`. Never reintroduce an ad-hoc `setInterval` poll or a hand-rolled offset/hasMore fetch in a view.
- The `.state` empty/loading message and `@keyframes spin` are global utilities in `assets/page.css`; views only keep scoped overrides for real divergences (mono, centered, fs-sm...). Don't redeclare the full block locally.
- Vitest: when `vue-router` is mocked, `stubs: { RouterLink: true }` is a no-op (VTU ignores string-name stubs for unresolved components) — register `RouterLinkStub` via `global.components` (pattern: BottomNav.test.js, LoginCallbackView.test.js).

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

Prefer these over ad-hoc equivalents. Suggest them to the user when relevant. `.claude/commands/` is versioned in the repo (the command definitions ship with the code).

## Deploy

- Domain: `diggy-music.fr`. VPS project path: `/root/diggy`. `.env` lives ONLY on the VPS, never in git.
- Push to `master` → GitHub Actions (ruff + eslint + pytest on real PG + vitest + pip-audit) → SSH → `docker compose build` → `alembic upgrade head` (on the NEW image, before the switch) → `docker compose up -d`. A failing lint blocks everything; a failing build or migration aborts the deploy (old code keeps serving).
- SSH from Claude: `ssh -i /c/Users/willi/.ssh/claude_diggy root@82.29.168.247` (dedicated key required).
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
| Anything about past decisions | `docs/completed/` contains FROZEN archives: read-only, never treat as current state, NEVER modify |

## Maintaining This File

- This file contains only stable invariants and commands. Volatile state (metrics, chantier progress) lives in the pointed docs.
- When a convention changes or a new pitfall is discovered the hard way, propose adding it here.
- Update the `Last verified` date whenever the file is audited against the code.
