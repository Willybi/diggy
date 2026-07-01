# Diggy — Project Context

> DJ web app to manage and visualize a Rekordbox library — tracks, cues, tags, BPM, artworks, radar, sets, artists.

## Architecture

```
diggy/
├── server/
│   ├── api/                 # FastAPI backend (async)
│   │   ├── main.py          # App entrypoint, mounts routers
│   │   ├── models.py        # All SQLAlchemy models (single file)
│   │   ├── dependencies.py  # get_current_user, require_admin
│   │   ├── deezer_enrich.py # Deezer search + catalog enrichment
│   │   ├── trackid/         # TrackID.net importer (sets)
│   │   │   └── importer.py  # get_or_create_artist, import_audiostream
│   │   └── routers/
│   │       ├── tracks.py    # User library (user_tracks)
│   │       ├── catalog.py   # Master catalog (all known tracks)
│   │       ├── radar.py     # Radar tracks from watched playlists
│   │       ├── watchlist.py # Watched playlists CRUD + crawl triggers
│   │       ├── artists.py   # Artist pages + search
│   │       ├── sets.py      # DJ sets + tracklists
│   │       ├── genres.py    # Genre hierarchy
│   │       ├── opinions.py  # Like/dislike (user_track_opinions)
│   │       ├── admin.py     # Admin-only: sync artists, Deezer linking, flags
│   │       └── auth.py      # JWT auth (email/password)
│   ├── workers/
│   │   ├── tasks/           # Celery tasks: crawl_radar, sync_artists, import_rekordbox_xml, ...
│   │   └── source_clients.py # Multi-source abstraction (Deezer/TIDAL/Spotify)
│   ├── frontend/            # Vue.js 3 SPA
│   │   └── src/
│   │       ├── views/       # One view per route (see Routes below)
│   │       ├── components/  # Reusable components (TrackTable, LikeDislike, etc.)
│   │       ├── stores/      # Pinia stores (auth, etc.)
│   │       └── styles/
│   │           └── diggy-tokens.css  # Design tokens (ALL colors/spacing here)
│   └── nginx/               # Reverse proxy config
├── docker-compose.yml
└── .github/workflows/       # CI/CD: test + deploy
```

## Tech Stack

| Layer | Tech |
|-------|------|
| API | FastAPI + SQLAlchemy async + Alembic |
| Database | PostgreSQL 16 |
| Queue | Celery + Redis |
| Storage | MinIO (S3-compatible) |
| Frontend | Vue.js 3 + Vite + Pinia |
| Proxy | Nginx |
| Deploy | Docker Compose on Hostinger VPS (Ubuntu 24.04) |
| CI/CD | GitHub Actions -> SSH -> `docker compose up -d --build` |

## Database (key tables)

The **`catalog`** table is the central hub. Every track from any source resolves to a catalog entry.

| Table | Role | ~Rows |
|-------|------|-------|
| `catalog` | Master reference for all known tracks | 5200+ |
| `user_tracks` | User's Rekordbox library (PK: user_id + catalog_id) | 600 |
| `radar_tracks` | Tracks discovered from watched playlists | 5000+ |
| `watched_entities` | Playlists being monitored (Deezer/TIDAL/Spotify) | 29 |
| `sets` | DJ sets with tracklists | 27 |
| `set_tracks` | Individual tracks in a set | 428 |
| `artists` | Artist reference (99% linked to Deezer) | 2686 |
| `artist_aliases` | Alternative spellings for artist resolution | |
| `genres` | Hierarchical genre taxonomy | 26 |
| `users` | User accounts with `is_admin` flag | |

Association tables: `catalog_genres`, `artist_genres`, `set_genres`, `set_artists`.

Full schema: `docs/database-schema.md`

### Key conventions
- `catalog` is the ONLY hub — everything points to it via `catalog_id`
- Dedup via `normalized_key` (artist|title) or `isrc`
- `has_artwork` = file exists in MinIO, never external URLs in DB
- All timestamps are TIMESTAMPTZ (UTC)
- Durations in milliseconds (integer)

## Frontend Routes

| Route | View | Description |
|-------|------|-------------|
| `/catalog` | CatalogView | Browse full catalog with filters |
| `/tracks` | (in CatalogView) | User's library subset |
| `/radar` | (in CatalogView) | Radar discoveries |
| `/tags` | TagsView | Browse by tags |
| `/artists` | ArtistsView | Artist directory |
| `/artist/:id` | ArtistDetailView | Artist page (tracks, sets, genres) |
| `/sets` | SetsView | DJ sets list |
| `/set/:id` | SetDetailView | Set tracklist |
| `/genres` | GenresView | Genre hierarchy |
| `/genre/:id` | GenreDetailView | Tracks in a genre |
| `/admin` | AdminView | Admin panel (artist sync, Deezer linking) |
| `/login` | LoginView | Authentication |

## MinIO Buckets

| Bucket | Content | Key format |
|--------|---------|------------|
| `artworks` | User library covers | `{track_id}.jpg` |
| `catalog-artworks` | Catalog covers | `{catalog_id}.jpg` |
| `artist-artworks` | Artist photos | `{artist_id}.jpg` |

URLs served via: `/storage/{bucket}/{file}`

## Celery Tasks (server/workers/tasks.py)

- `crawl_radar` — daily 8h: crawl all watched playlists, detect new tracks
- `sync_artists` — extract artists from catalog, deduplicate, link Deezer
- `fetch_artist_artworks` — download artist photos from Deezer
- `link_set_artists` — parse set titles to link artists
- `populate_artist_genres` — infer artist genres from their catalog tracks

## Multi-Source Playlists (server/workers/source_clients.py)

| Source | Method | ISRC |
|--------|--------|------|
| Deezer | Official API | Yes |
| TIDAL | `tidalapi` (OAuth device flow) | Yes |
| Spotify | `spotifyscraper` (no auth) | No — cross-search via Deezer |

All sources go through `crawl_single_playlist` -> `get_fetchers()` -> RadarTracks -> Deezer enrichment.

## Code Conventions

- **Language**: Code in English, UI in French
- **Frontend tokens**: Zero hardcoded colors — everything via `var(--...)` from `diggy-tokens.css`
- **User preference**: Modular, short focused files, simple blocks
- **Admin**: `is_admin` flag on User model, `require_admin` dependency, admin routes in `admin.py`
- **Deezer sentinel**: `deezer_id = "NOT_FOUND"` marks artists confirmed absent from Deezer
- **Artist linking**: Rename uses official Deezer name + creates alias for old name + merges duplicates
- **Vue handlers**: No multi-statement inline handlers in templates (`@click="a = 1; b = 2"`) — extract to a method. Prettier reformats them on multiple lines which breaks the Vue compiler.

## Workflow — Avant chaque commit

Toujours vérifier le linting avant de proposer un nom de commit ou de valider une implémentation.
Un push sur master déclenche le déploiement — un lint qui échoue en CI bloque tout.

```bash
# Backend
pip install ruff --quiet && ruff check server/

# Frontend
cd server/frontend && npm run lint
```

Les deux doivent passer avant de committer.

## Deploy

- Domain: `diggy-music.fr` (HTTPS, Let's Encrypt, certbot auto-renew)
- VPS: Hostinger, Ubuntu 24.04, ports 80 (redirect) + 443 (HTTPS)
- `.env` only on VPS, never in git
- Docker containers: `diggy_api`, `diggy_worker`, `diggy_beat`, `diggy_frontend`, `diggy_nginx`, `diggy_redis`, `diggy_postgres`, `diggy_minio`, `diggy_certbot`
- CI/CD: push to `master` -> GitHub Actions (lint + test + deploy) -> SSH -> rebuild

## Roadmap

- **Active roadmap**: `docs/ROADMAP.md` — backlog and pending items only
- **Completed roadmaps**: `docs/completed/` — archived, DO NOT modify unless explicitly asked
- **Future ideas**: Multi-artist per track (feat support), artist connection graph, Soundcloud/Bandcamp sources
