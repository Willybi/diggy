# Diggy

Web app pour DJ qui gère et visualise une bibliothèque Rekordbox : catalogue de tracks,
radar de nouveautés, sets (tracklists), artistes, genres et tendances. Le backend agrège
un catalogue partagé enrichi via des sources externes (Deezer, Beatport, TrackID.net) ;
le frontend offre l'exploration (catalogue, hub de tendances, pages détail) et la curation
(collections, watchlist, opinions).

> Conventions détaillées, invariants et pièges du projet : voir [CLAUDE.md](CLAUDE.md).

## Stack

| Couche | Techno |
|--------|--------|
| API | FastAPI 0.115 + SQLAlchemy 2.0 (async) + Alembic |
| Base de données | PostgreSQL 16 |
| Queue | Celery 5.4 + Redis (2 workers : `diggy_worker` + `diggy_worker_enrich`) |
| Stockage fichiers | MinIO (S3 compatible) |
| Frontend | Vue 3 + Vite + Pinia (build statique servi par Nginx en prod) |
| Reverse proxy | Nginx (HTTPS Let's Encrypt, certbot auto-renew) |
| Déploiement | Docker Compose sur VPS Hostinger (Ubuntu 24.04), push `master` = déploiement auto |
| CI/CD | GitHub Actions (ruff + eslint + pytest + vitest + pip-audit) → SSH deploy |

## Structure du dépôt

```
diggy/
├── server/
│   ├── api/           # FastAPI : main.py, models/, schemas/, routers/, services/, alembic/, trackid/
│   ├── workers/       # Celery : celery_app.py, deezer_enrich.py, source_clients.py, tasks/
│   ├── frontend/      # Vue 3 + Vite + Pinia (interface web)
│   ├── nginx/         # Config reverse proxy (default.ssl.conf.template = config prod active)
│   ├── deezer/        # Outillage LOCAL Rekordbox : extractor.py, sync_checker.py
│   └── scripts/       # backup.sh, bootstrap_tidal_tokens.py, generate_schema_doc.py
├── worker/            # Outillage LOCAL Rekordbox : relocate_tracks.py
├── scripts/           # import_taxonomy.py + data/ (seeds CSV genres Wikidata)
├── tests/             # Suite pytest (backend)
├── docs/              # ROADMAP.md, database-schema.md, restore.md, completed/ (archives gelées)
├── docker-compose.yml            # Stack de base
├── docker-compose.override.yml   # Hot reload dev (bind mounts, alembic upgrade au boot)
├── docker-compose.ssl.yml        # Ports 80/443 + certbot (prod)
└── .env.example
```

`server/deezer/` et `worker/` sont de l'**outillage local** : ces scripts tournent sur le
PC où Rekordbox est installé (lecture de la base Rekordbox, relocalisation de fichiers),
hors runtime serveur. L'import officiel d'une bibliothèque se fait par **upload XML** via
l'interface web (routeur `import_rb`), pas par ces scripts.

## Démarrage local

Prérequis : Docker + Docker Compose.

```bash
# 1. Configuration : créer le .env depuis le modèle, puis renseigner les variables
cp .env.example .env

# 2. Lancer la stack (postgres, redis, api, workers, beat, minio, nginx, frontend)
docker compose up -d --build

# 3. Frontend en dev (hot reload Vite, port 5173)
cd server/frontend && npm install && npm run dev
```

Variables requises dans `.env` (voir `.env.example` pour la liste complète et les options) :

| Variable | Rôle |
|----------|------|
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | PostgreSQL |
| `DATABASE_URL` | DSN async SQLAlchemy (`postgresql+asyncpg://…`) |
| `JWT_SECRET` | Signature des tokens JWT (l'API le lit au démarrage) |
| `MINIO_USER` / `MINIO_PASSWORD` | Identifiants MinIO |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` / `GOOGLE_REDIRECT_URI` | OAuth Google (seule méthode de connexion) |

> **Le dev full-stack en local n'est pas le flux officiel** (voir CLAUDE.md → *Dev Commands*).
> Le flux normal est : push `master` → CI → prod. La stack Docker complète (frontend statique
> + API + `/api/docs`) se consulte sur **http://localhost:8080** (nginx). `npm run dev` (port 5173)
> n'est qu'une visualisation du frontend : ses appels API échouent dans tous les cas (le proxy
> Vite `/api` vise `http://api:8000`, un hostname interne au réseau Docker non joignable depuis
> le host), mais proprement — le boot avale les erreurs réseau et la page ne plante pas.

## Tests & lint

```bash
# Tests backend (SQLite en mémoire par défaut, aucun PG requis)
pytest tests/ -q

# Tests frontend
cd server/frontend && npx vitest run

# Lint — les DEUX doivent passer avant tout commit (push master = déploie en prod)
ruff check server/
cd server/frontend && npm run lint
```

## Déploiement

- Domaine : **diggy-music.fr**. Chemin projet VPS : `/root/diggy`. Le `.env` vit
  uniquement sur le VPS, jamais dans git.
- Un push sur `master` déclenche GitHub Actions : lint (ruff + eslint) + tests
  (pytest sur PostgreSQL réel + vitest) + `pip-audit`, puis SSH → `docker compose build`
  → `alembic upgrade head` (sur la nouvelle image, avant la bascule) → `docker compose up -d`.
- Un lint qui échoue bloque tout ; un build ou une migration qui échoue avorte le déploiement
  (l'ancien code continue de servir).

## Documentation

| Sujet | Fichier |
|-------|---------|
| Conventions, invariants, pièges | [CLAUDE.md](CLAUDE.md) |
| Schéma de base de données (généré) | [docs/database-schema.md](docs/database-schema.md) |
| Roadmap et chantiers | [docs/ROADMAP.md](docs/ROADMAP.md) |
| Sauvegarde / restauration | [docs/restore.md](docs/restore.md) |
| Routes API (en dev) | `/api/docs` (Swagger, désactivé en prod) |
| Scripts de maintenance backend | [server/api/scripts/README.md](server/api/scripts/README.md) |
