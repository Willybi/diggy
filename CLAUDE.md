# Diggy - Project Context

> DJ web app to manage and visualize a Rekordbox library: tracks, radar, sets, artists, genres.
> Last verified: 2026-07-07
> If you notice a divergence between this file and the actual code, SAY SO explicitly instead of silently working around it. Suggest the fix for this file.

## Tech Stack

| Layer | Tech |
|-------|------|
| API | FastAPI 0.115 + SQLAlchemy 2.0 async + Alembic (29 migrations) |
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
│   ├── models/              # SQLAlchemy models (27 classes, 10 modules):
│   │                        # catalog, user, artist, radar, sets, genre,
│   │                        # collection, opinion, admin (+ base, __init__)
│   │                        # sets module gained: SetFlag, SetFlagType, SetFlagStatus
│   ├── dependencies.py      # get_current_user, require_admin
│   ├── deezer_enrich.py     # Deezer search + enrichment
│   ├── rate_limit.py        # Per-IP/endpoint rate limiting
│   ├── alembic/             # Migrations (alembic.ini is in server/api/)
│   ├── trackid/             # TrackID.net set importer
│   ├── routers/             # 16 routers, 93 endpoints:
│   │                        # tracks, catalog, radar, watchlist, artists, sets,
│   │                        # genres, taxonomy, search, collections, opinions,
│   │                        # import_rb, auth, admin
│   └── services/            # Business logic lives HERE, not in routers:
│                            # genre, artist, catalog, radar, image, rekordbox_xml,
│                            # set_dedup (normalize_set_title, match_set, materialize_parent)
├── workers/
│   ├── celery_app.py        # Celery config + beat schedule
│   ├── source_clients.py    # Multi-source abstraction (Deezer/TIDAL/Spotify)
│   └── tasks/               # 7 modules: radar, catalog, artists, genres,
│                            # import_rb, sets, trends
├── frontend/src/
│   ├── views/               # 17 views (16 routed + 1 dead TagsView)
│   ├── components/          # 25 shared components
│   ├── composables/         # useInfiniteScroll, useStyleMap, useTheme
│   ├── stores/              # Pinia: auth, audioPlayer, opinions
│   └── styles/diggy-tokens.css  # ALL colors/spacing (zero hardcoded)
└── nginx/                   # default.ssl.conf.template = active prod config
```

Rule: new business logic goes in a service, routers stay thin. New Celery tasks go in the matching `tasks/` module.

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
- Admin: `is_admin` flag + `require_admin` dependency. Destructive admin actions are logged in `admin_audit_log`.

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

# Alembic (alembic.ini lives in server/api/)
cd server/api && python -m alembic revision --autogenerate -m "description"
cd server/api && python -m alembic upgrade head
# Prod: CI runs `alembic upgrade head` automatically on deploy

# Local stack (override mounts ./server/api:/app for hot reload)
docker compose up -d --build
cd server/frontend && npm run dev     # frontend dev server
```

Env vars: see `.env.example` at repo root. Required: `POSTGRES_USER/PASSWORD/DB`, `DATABASE_URL`, `JWT_SECRET`, `MINIO_USER/PASSWORD`. Prod adds `COMPOSE_FILE=docker-compose.yml:docker-compose.ssl.yml` and `DOMAIN`. `ENV=production` disables permissive CORS.

## Celery Beat Schedule

| Task | Time | Module |
|------|------|--------|
| `crawl_radar` | 03:00 | tasks/radar.py |
| `crawl_followed_sets` | 04:00 | tasks/sets.py |
| `enrich_catalog` (Deezer) | 05:00 | tasks/catalog.py |
| `enrich_catalog_beatport` | 06:00 | tasks/catalog.py |
| `compute_trends` | 07:00 | tasks/trends.py |

Enrichment tasks run on the dedicated `diggy_worker_enrich` (slow, rate-limited external APIs); everything else on `diggy_worker`. Keep that separation when adding tasks.

## Known Pitfalls

### Nginx
- `add_header` in a `location` block REMOVES all server-level headers. Asset locations must be nested inside `location /` without their own `add_header` to inherit the CSP.
- `/api/`, `/storage/`, `/minio/` use `^~` prefix priority so they are not captured by the assets regex `\.(js|css|jpg)$`.
- The active prod config is `default.ssl.conf.template`. `default.conf` is intentionally empty.
- Keep CSP `upgrade-insecure-requests` as long as any `http://` request can arrive.

### Frontend
- Container queries everywhere; `@media` ONLY for `position: fixed` elements.
- Zero hardcoded colors: everything via `var(--...)` from `diggy-tokens.css`.
- No multi-statement inline handlers in templates (`@click="a = 1; b = 2"`): Prettier reformats them across lines, which breaks the Vue compiler. Extract to a method.
- Responsive tables: columns hidden progressively across 6 breakpoints (CatalogView). At 375px only Play / Track / Key / InLib remain.
- BottomNav (mobile <640px): 5 items + conditional Admin; PlayerBar repositions above it.

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

Prefer these over ad-hoc equivalents. Suggest them to the user when relevant.

## Deploy

- Domain: `diggy-music.fr`. VPS project path: `/root/diggy`. `.env` lives ONLY on the VPS, never in git.
- Push to `master` → GitHub Actions (ruff + eslint + pytest on real PG + vitest + pip-audit) → SSH → `docker compose up -d --build` + `alembic upgrade head`. A failing lint blocks everything.
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
| UI change on an existing view | `_design/PAGES_REFERENCE.md` (view→handoff index), then the matching handoff folder |
| Anything about past decisions | `docs/completed/` contains FROZEN archives: read-only, never treat as current state, NEVER modify |

## Maintaining This File

- This file contains only stable invariants and commands. Volatile state (metrics, chantier progress) lives in the pointed docs.
- When a convention changes or a new pitfall is discovered the hard way, propose adding it here.
- Update the `Last verified` date whenever the file is audited against the code.
