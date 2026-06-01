# Diggy

Web app DJ pour gérer et visualiser une bibliothèque Rekordbox — tracks, cues, tags, BPM, artworks..

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
│   ├── workers/          # Celery — import Rekordbox → PostgreSQL + MinIO
│   ├── frontend/         # Vue.js 3 — interface web
│   └── nginx/            # Config reverse proxy
├── worker/               # Exploration Rekordbox (Jupyter)
├── docker-compose.yml
└── .github/workflows/    # CI/CD déploiement automatique
```

## Routes API

| Méthode | Endpoint | Description |
|---|---|---|
| GET | `/api/tracks/` | Liste des tracks (filtre par artiste) |
| GET | `/api/tracks/{id}` | Détail d'un track avec cues et tags |
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
```bash
cp .env.example .env
nano .env  # remplir les mots de passe
```

Variables requises : `POSTGRES_PASSWORD`, `DATABASE_URL`, `MINIO_USER`, `MINIO_PASSWORD`, `SECRET_KEY`

### Lancer
```bash
docker compose up -d --build
```

### CI/CD
Chaque push sur `master` déclenche un déploiement automatique via GitHub Actions.
Secrets requis dans le repo : `VPS_HOST`, `VPS_USER`, `VPS_PASSWORD`.

## Import Rekordbox

L'import de la bibliothèque Rekordbox (tracks + artworks) se fait via une tâche Celery :

```python
from workers.tasks import import_rekordbox
import_rekordbox.delay("/chemin/vers/master.db")
```

Les artworks sont automatiquement uploadés dans MinIO et accessibles via `/storage/artworks/{id}.jpg`.
