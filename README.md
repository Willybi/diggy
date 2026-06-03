# Diggy

Web app DJ pour gérer et visualiser une bibliothèque Rekordbox — tracks, cues, tags, BPM, artworks.

## Stack

| Composant | Techno |
|---|---|
| Base de données | PostgreSQL 16 |
| API backend | FastAPI + SQLAlchemy (async) |
| Task queue | Celery + Redis |
| Stockage fichiers | MinIO (S3 compatible) |
| Frontend | Vue.js 3 + Vite + Pinia |
| Web server | Nginx (reverse proxy) |
| Containerisation | Docker Compose |
| CI/CD | GitHub Actions → SSH deploy |

## Structure

```
diggy/
├── server/
│   ├── api/              # FastAPI — modèles, schemas, routers
│   ├── workers/          # Celery workers
│   ├── frontend/         # Vue.js 3 — interface web
│   └── nginx/            # Config reverse proxy
├── worker/
│   └── rekordbox/        # Module d'extraction Rekordbox (extractor.py)
├── tests/
│   └── rekordbox/        # Tests unitaires (pytest + mocks)
├── docs/
│   └── rekordbox_exploration.ipynb  # Exploration de l'API pyrekordbox
├── main.py               # Script d'import Rekordbox → API
├── docker-compose.yml
└── .github/workflows/    # CI/CD — tests + déploiement automatique
```

## Routes API

| Méthode | Endpoint | Description |
|---|---|---|
| GET | `/api/tracks/` | Liste des tracks (filtre par artiste) |
| GET | `/api/tracks/{id}` | Détail d'un track |
| GET | `/api/tracks/existing-ids` | IDs en base + statut artwork (utilisé par l'import) |
| POST | `/api/tracks/bulk` | Import batch upsert avec artworks |
| GET | `/api/tags/` | Liste de tous les tags |
| GET | `/api/health` | Health check |
| GET | `/api/docs` | Swagger UI |

## Déploiement

### Prérequis VPS
```bash
curl -fsSL https://get.docker.com | sh
git clone https://github.com/Willybi/diggy.git /root/diggy
```

### Configuration
Créer un fichier `.env` à la racine (ne jamais le commiter) :

```env
COMPOSE_PROJECT_NAME=diggy
POSTGRES_USER=diggy
POSTGRES_PASSWORD=...
POSTGRES_DB=diggy
DATABASE_URL=postgresql+asyncpg://diggy:...@postgres:5432/diggy
REDIS_URL=redis://redis:6379/0
SECRET_KEY=...
NGINX_PORT=80
MINIO_USER=...
MINIO_PASSWORD=...
MINIO_URL=http://minio:9000
```

### Lancer
```bash
docker compose up -d --build
```

### CI/CD
Chaque push sur `master` déclenche un déploiement automatique via GitHub Actions.
Secrets requis dans le repo : `VPS_HOST`, `VPS_USER`, `VPS_PASSWORD`.

## Import Rekordbox

L'import se lance depuis le PC où Rekordbox est installé :

```bash
python main.py
```

Le script lit la base Rekordbox locale via `worker/rekordbox/extractor.py`, compare avec la base distante, et envoie les tracks + artworks par batches vers l'API. Les artworks sont stockés dans MinIO et accessibles via `/storage/artworks/{id}.jpg`.

Seuls les tracks actifs (`rb_data_status=256`) sont importés — environ 621 tracks pour une collection standard.

> Pour comprendre comment pyrekordbox a été exploré et comment les données sont structurées, voir [docs/rekordbox_exploration.ipynb](docs/rekordbox_exploration.ipynb).

## Tests

```bash
pytest tests/ -v
```

Les tests unitaires couvrent le module `worker/rekordbox/extractor.py` avec des mocks — ils tournent aussi automatiquement en CI avant chaque déploiement.
