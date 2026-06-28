# Diggy — Roadmap Generale

> Document maitre. Regroupe les chantiers fonctionnels (multi-user, HTTPS, design)
> et les chantiers techniques issus de l'audit backend de juin 2026.
>
> Chaque chantier est autonome et peut etre confie a une equipe independante.
> Les dependances inter-chantiers sont explicites.

---

## Vue d'ensemble

```
                         SOCLE TECHNIQUE
  =====================================================
  T1  Securite & Auth           ██████░░  URGENT       (0% fait)
  T2  Resilience Workers        █████░░░  URGENT       (0% fait)
  T3  Infra & DevOps            █████░░░  URGENT       (~20% fait — health checks)
  T4  Performance Queries       ████░░░░  HAUT         (~15% fait — preview_url cache)
  T5  Validation & Contrats API ███░░░░░  MOYEN        (0% fait)
  T6  Schema DB & Integrite     ███░░░░░  MOYEN        (genres refonde, reste CHECK/index)

                         FONCTIONNEL
  =====================================================
  F1  Multi-User (Phases 5-7)   ████░░░░  PLANIFIE     (Phase 6 ~70% fait)
  F2  HTTPS / Domaine           ██░░░░░░  EN ATTENTE
  F3  Design Realignment        ██████░░  EN COURS     (Vagues 0-2 done, 3-5 a faire)

                         LONG TERME
  =====================================================
  L1  Monitoring & Observabilite  ░░░░░░  BACKLOG
  L2  Multi-artiste par track     ░░░░░░  BACKLOG
  L3  Graphe artistes             ░░░░░░  BACKLOG
```

### Ordre recommande

```
Sprint 1 (semaine 1)     : T1 + T3 critiques (securite + infra)
Sprint 2 (semaines 2-3)  : T2 + T6 (workers + DB)
Sprint 3 (semaines 3-4)  : T4 + T5 (perf + validation)
En parallele continu     : F3 (design realignment)
Apres stabilisation      : F1 phase 5 → F2 HTTPS → F1 phases 6-7
```

### Dependances

```
T1 (securite) ──────> F1 phase 6 (enforcement auth)
T3 (infra)    ──────> F2 (HTTPS necessite docker hardening)
T6 (schema)   ──────> F1 phase 5 (trends table)
T5 (validation) ───> F1 phase 7 (import multi-user)
```

---

## T1 — Securite & Auth

**Equipe : Security**
**Priorite : URGENT — Sprint 1**
**Estimation : 3-5 jours**

### Contexte pour l'equipe

L'API FastAPI est fonctionnelle mais a ete construite en mode "single user de confiance".
Plusieurs failles empechent un deploiement multi-user serein. L'audit revele 4 problemes
critiques et 4 problemes moyens.

### Perimetre a auditer avant de coder

| Fichier | Quoi chercher |
|---------|---------------|
| `server/api/main.py` | Config CORS (lignes ~26-30), middlewares presents/absents |
| `server/api/dependencies.py` | Logique `get_current_user_optional`, fallback `_DEFAULT_USER_ID = 1` |
| `server/api/auth.py` | `JWT_SECRET` fallback, `JWT_EXPIRE_HOURS`, hashing |
| `server/api/routers/auth.py` | Schemas `RegisterIn`/`LoginIn`, validation email/password |
| `server/nginx/default.conf` | Headers securite manquants |
| `docker-compose.yml` | Port 5432 expose publiquement |

### Taches

#### Critique (bloquant)

- [ ] **Fermer CORS** : remplacer `allow_origins=["*"]` par les domaines autorises
  - `main.py` : `allow_origins=[os.environ.get("CORS_ORIGIN", "http://localhost:5173")]`
  - Ajouter `CORS_ORIGIN` dans `.env.example`
- [ ] **Supprimer port 5432 public** : retirer `ports: - "5432:5432"` de `docker-compose.yml`
  - PostgreSQL ne doit etre accessible que depuis le reseau Docker interne
  - Si besoin d'acces distant : SSH tunnel uniquement
- [ ] **Forcer auth sur mutations** : les endpoints POST/PATCH/DELETE doivent utiliser
  `get_current_user` (obligatoire), pas `get_current_user_optional`
  - Le fallback `user_id=1` fait que tous les guests modifient les donnees du meme user
  - Garder `get_current_user_optional` uniquement pour les GET en lecture
- [ ] **Supprimer le fallback JWT_SECRET** : `os.environ["JWT_SECRET"]` (crash si absent)
  au lieu de `os.environ.get("JWT_SECRET", "dev-secret-change-in-production")`

#### Haut

- [ ] **Rate limiting** : integrer `slowapi` sur `/auth/login` (5/min), `/auth/register` (3/min)
  - Middleware global `@limiter.limit("60/minute")` sur les autres routes
- [ ] **Valider email** : utiliser `pydantic.EmailStr` dans `RegisterIn`
- [ ] **Valider password** : `Field(min_length=8)` dans `RegisterIn`
- [ ] **Reduire expiration JWT** : passer de 30 jours a 7 jours (compromis usage solo)

#### Moyen

- [ ] **Headers securite Nginx** :
  ```nginx
  add_header X-Content-Type-Options "nosniff" always;
  add_header X-Frame-Options "SAMEORIGIN" always;
  add_header X-XSS-Protection "1; mode=block" always;
  add_header Referrer-Policy "strict-origin-when-cross-origin" always;
  ```
- [ ] **Handler d'exception global** : intercepter les 500 non geres pour ne pas leaker
  de details internes (stack traces, noms de tables)

### Definition of Done

```bash
# CORS bloque les origines inconnues
curl -H "Origin: https://evil.com" http://localhost/api/tracks/ → pas de Access-Control-Allow-Origin

# Mutations sans token → 401
curl -X POST http://localhost/api/tracks/bulk → 401

# Login rate limited
for i in {1..10}; do curl -X POST /api/auth/login ...; done → 429 apres 5

# Port 5432 ferme
nmap -p 5432 82.29.168.247 → filtered/closed
```

---

## T2 — Resilience Workers & Tasks Celery

**Equipe : Data Pipeline**
**Priorite : URGENT — Sprint 2**
**Estimation : 5-7 jours**

### Contexte pour l'equipe

Le layer Celery (server/workers/) gere le crawl radar, l'enrichissement Deezer/Beatport,
la synchronisation artistes et les imports de sets. ~2 750 lignes de code reparties sur
10+ fichiers. Le code *fonctionne* mais n'a aucune tolerance aux pannes : zero retry,
exceptions avalees silencieusement, race conditions sur les ecritures paralleles.

### Perimetre a auditer avant de coder

| Fichier | Lignes | Quoi chercher |
|---------|--------|---------------|
| `server/workers/tasks.py` | ~1139 | Toutes les `@celery_app.task` — aucune n'a `autoretry_for` ni `max_retries` |
| `server/workers/celery_app.py` | ~52 | Config Celery : pas de DLQ, time limits hardcodes |
| `server/workers/source_clients.py` | ~268 | `time.sleep()` manuels vs `rate_limiter.py` async |
| `server/workers/enrichment.py` | ~415 | Pipeline async Deezer/Beatport, `_known_isrcs` en memoire |
| `server/workers/async_http.py` | ~139 | Retry sur erreurs connexion mais pas sur 5xx |
| `server/workers/rate_limiter.py` | ~77 | Token bucket async (bon) mais pas utilise partout |
| `server/workers/db.py` | ~167 | Bulk ops, ISRC dedup, session management |
| `server/workers/crawl_logger.py` | ~83 | Context manager, exception suppression |
| `server/api/deezer_enrich.py` | ~250 | Version sync de l'enrichissement, image uploads |

### Taches

#### Critique

- [ ] **Ajouter retry policy Celery** sur toutes les tasks :
  ```python
  @celery_app.task(
      bind=True,
      autoretry_for=(Exception,),
      retry_kwargs={"max_retries": 3, "countdown": 60},
      retry_backoff=True,
  )
  ```
  - Exceptions metier (ex: "playlist not found") doivent etre exclues du retry
- [ ] **Re-raise les exceptions** : remplacer tous les `except Exception: return []`
  par un pattern qui log ET propage :
  ```python
  except Exception:
      logger.exception("Task failed")
      raise  # Celery doit voir l'echec
  ```
- [ ] **Lock Redis sur crawl playlist** : empecher deux crawls simultanes de la meme playlist
  ```python
  lock = redis.lock(f"crawl:{playlist_id}", timeout=900)
  if not lock.acquire(blocking=False):
      logger.info("Crawl already running, skipping")
      return
  ```
  - Le `DELETE + INSERT` de `radar_tracks` sans lock peut perdre des donnees
- [ ] **Fix race condition ISRC** : remplacer le set `_known_isrcs` en memoire par
  `ON CONFLICT DO NOTHING` au niveau SQL

#### Haut

- [ ] **Unifier le rate limiting** : supprimer les `time.sleep(0.12)` de `source_clients.py`,
  tout passer par `rate_limiter.py`
- [ ] **DLQ (Dead Letter Queue)** : configurer Celery pour router les tasks echouees
  apres 3 retries vers une queue dediee, consultable depuis l'admin
- [ ] **Gerer l'expiration TIDAL** : implementer le refresh token automatique dans
  `_get_tidal_session()`, stocker les tokens actualises
- [ ] **Refactorer image upload** : 3 implementations dupliquees
  (`deezer_enrich.py`, `async_http.py`, `enrichment.py`) → une seule fonction utilitaire

#### Moyen

- [ ] **Externaliser les hardcoded** : timeouts, bucket names, concurrency → env vars
  ```
  CELERY_WORKER_CONCURRENCY=4
  DEEZER_RATE_LIMIT=0.12
  ENRICHMENT_BATCH_SIZE=100
  ```
- [ ] **Circuit breaker Beatport** : si N echecs consecutifs Cloudflare, skip pendant 1h
- [ ] **Batch commits workers** : remplacer les `session.commit()` dans les boucles
  par des commits toutes les 100 iterations
- [ ] **Structured logging** : ajouter `task_id` dans tous les logs workers pour correlation

### Definition of Done

```bash
# Task echouee → retry visible dans Celery
celery -A workers.celery_app inspect active → retry_count > 0

# Deux crawls simultanes → un seul execute
celery call crawl_single_playlist --args='[42]' &
celery call crawl_single_playlist --args='[42]' → "skipped, already running"

# ISRC doublon → pas de crash
# (enrichment de deux tracks avec meme ISRC en parallele)
```

---

## T3 — Infrastructure & DevOps

**Equipe : Platform**
**Priorite : URGENT — Sprint 1**
**Estimation : 3-5 jours**

### Contexte pour l'equipe

L'infra Docker Compose fonctionne mais est configuree comme un environnement de dev.
Uvicorn tourne avec `--reload`, pas de restart policies, pas de health checks,
logs non rotates. Le CI/CD deploie sans verifier que l'app est up apres le deploy.

### Perimetre a auditer avant de coder

| Fichier | Quoi chercher |
|---------|---------------|
| `docker-compose.yml` | `--reload` sur api, restart policies, health checks, resource limits |
| `server/api/Dockerfile` | Single stage, pas de .dockerignore, run as root |
| `server/frontend/Dockerfile` | Multi-stage OK, mais pas de .dockerignore |
| `server/nginx/default.conf` | Timeouts manquants, pas de gzip, pas de cache headers |
| `.github/workflows/deploy.yml` | Pas de health check post-deploy, deps hardcodees |
| `server/api/alembic/env.py` | Pas de lock sur migrations concurrentes |

### Taches

#### Critique

- [ ] **Retirer `--reload`** de la commande uvicorn en production
  - `docker-compose.yml` : `command: uvicorn main:app --host 0.0.0.0 --port 8000 --workers 2`
- [ ] **Ajouter restart policies** sur tous les services :
  ```yaml
  restart: unless-stopped
  ```
- [ ] **Creer `.dockerignore`** a la racine et dans `server/api/` et `server/frontend/` :
  ```
  .env
  .git
  .github
  __pycache__
  *.pyc
  .venv
  node_modules
  _design
  docs
  tests
  .claude
  *.md
  ```
- [ ] **Log rotation Docker** sur tous les services :
  ```yaml
  logging:
    driver: json-file
    options:
      max-size: "50m"
      max-file: "3"
  ```

#### Haut

- [x] **Health checks** sur les services critiques :
  - `GET /api/health` existe dans l'API
  - Health checks Docker : postgres (`pg_isready`), redis (`redis-cli ping`), minio (`mc ready`)
  - Les services api, worker, beat dependent de `condition: service_healthy`
  - Reste a faire : health check sur api/worker/frontend eux-memes (pas juste leurs deps)
- [ ] **Health check post-deploy dans CI/CD** :
  ```yaml
  - name: Health check
    run: |
      ssh ... '
        sleep 15
        curl -sf http://localhost/api/health || exit 1
      '
  ```
- [ ] **Tests frontend dans CI/CD** : ajouter `npm run lint` (minimum) dans le workflow
- [ ] **Timeouts Nginx** :
  ```nginx
  proxy_connect_timeout 60s;
  proxy_send_timeout 180s;
  proxy_read_timeout 180s;
  ```

#### Moyen

- [ ] **Multi-stage Dockerfile API** :
  ```dockerfile
  FROM python:3.13-slim AS builder
  COPY requirements.txt .
  RUN pip install --user --no-cache-dir -r requirements.txt

  FROM python:3.13-slim
  COPY --from=builder /root/.local /root/.local
  ENV PATH=/root/.local/bin:$PATH
  WORKDIR /app
  COPY . .
  ```
- [ ] **Non-root user** dans le Dockerfile API :
  ```dockerfile
  RUN useradd -m -u 1000 diggy
  USER diggy
  ```
- [ ] **Resource limits** Docker (eviter qu'un container mange tout le VPS) :
  ```yaml
  deploy:
    resources:
      limits:
        cpus: '2'
        memory: 1G
  ```
- [ ] **Gzip Nginx** :
  ```nginx
  gzip on;
  gzip_types application/json application/javascript text/css;
  gzip_min_length 1000;
  ```
- [ ] **Cache headers** pour assets statiques frontend :
  ```nginx
  location ~* \.(js|css|png|jpg|svg|woff2)$ {
      expires 30d;
      add_header Cache-Control "public, immutable";
  }
  ```
- [ ] **Backup PostgreSQL** : cron quotidien `pg_dump` vers un volume dedie ou S3
- [ ] **Backup MinIO** : `mc mirror` periodique des buckets artworks

### Definition of Done

```bash
# Containers restart apres crash
docker kill diggy_api && sleep 10 && docker ps | grep diggy_api → running

# Logs ne grandissent pas indefiniment
docker inspect diggy_api --format='{{.HostConfig.LogConfig}}' → max-size:50m

# Health check fonctionnel
curl http://localhost/api/health → {"status": "ok"}

# CI/CD echoue si app down apres deploy
# (simuler un crash → workflow doit echouer)
```

---

## T4 — Performance Queries

**Equipe : Backend Performance**
**Priorite : HAUT — Sprint 3**
**Estimation : 5-7 jours**

### Contexte pour l'equipe

L'API a ete construite incrementalement. Certaines routes accumulent des queries complexes
(6 OUTER JOINs dans catalog, filtrage Python post-fetch dans tracks, N+1 dans radar batch).
Avec ~5 200 entries catalog et ~5 000 radar tracks, ca tient. Au-dela de 20k, ca cassera.

### Perimetre a auditer avant de coder

| Fichier | Probleme principal | Lignes |
|---------|-------------------|--------|
| `server/api/routers/catalog.py` | Mega-query 6 OUTER JOINs + subqueries | ~60-170 |
| `server/api/routers/tracks.py` | Filtrage tags en Python post-fetch (casse pagination) | `/tags` endpoint + tag filter |
| `server/api/routers/tracks.py` | `/tracks/tags` charge tous les tracks en memoire | endpoint `list_tags` |
| `server/api/routers/radar.py` | Batch update : 1 query par item dans la boucle | `batch_update_radar_state` |
| `server/api/routers/artists.py` | Charge 2686 artistes + agregation memoire | `list_artists` |
| `server/api/routers/genres.py` | Percentile BPM calcule en boucle par genre | `PERCENTILE_CONT` |
| `server/api/routers/catalog.py` | ~~Appel HTTP Deezer inline~~ FAIT : `preview_url` en DB | |

Outil recommande : activer `echo=True` sur SQLAlchemy en dev pour voir les queries generees,
ou utiliser `EXPLAIN ANALYZE` sur les routes lentes.

### Taches

#### Haut

- [ ] **Filtrage tags en SQL** : remplacer le filtrage Python par :
  ```sql
  WHERE rb_mytags::jsonb ? :tag_name
  ```
  - Le filtrage actuel casse la pagination (fetch 200 → filtre a 5 → renvoie 5)
- [ ] **`/tracks/tags` en SQL** : remplacer la boucle Python par :
  ```sql
  SELECT DISTINCT jsonb_array_elements_text(rb_mytags) AS tag
  FROM user_tracks WHERE user_id = :uid AND rb_mytags IS NOT NULL
  ORDER BY tag
  ```
- [ ] **Batch radar SQL** : remplacer le N+1 par un bulk lookup :
  ```python
  catalog_ids = [item["catalog_id"] for item in body]
  existing = await db.execute(
      select(UserRadarState).where(
          UserRadarState.user_id == uid,
          UserRadarState.catalog_id.in_(catalog_ids),
      )
  )
  existing_map = {s.catalog_id: s for s in existing.scalars()}
  # Puis boucle sans query individuelle
  ```
- [ ] **Decomposer la mega-query catalog** : splitter en 2-3 requetes separees
  plutot que 6 OUTER JOINs (risque produit cartesien)
  - Option A : requetes separees + assemblage Python
  - Option B : vue materialisee PostgreSQL rafraichie periodiquement
- [ ] **Index manquants** (migration Alembic) :
  ```sql
  CREATE INDEX ix_radar_tracks_catalog_id ON radar_tracks(catalog_id);
  CREATE INDEX ix_catalog_deezer_id ON catalog(deezer_id);
  CREATE INDEX ix_catalog_beatport_id ON catalog(beatport_id);
  ```

#### Moyen

- [ ] **Pagination sur `/sets/` et `/watchlist/`** : ces deux endpoints retournent
  tous les resultats sans limite
- [x] **Cache preview URL** : `preview_url` est maintenant une colonne sur `catalog`,
  plus de fetch Deezer live a chaque requete
- [ ] **Artistes : pagination DB** : remplacer le chargement complet par une vraie
  pagination SQL avec agrégats en subquery
- [ ] **Stats genres pre-calculees** : table ou vue materialisee pour les percentiles
  BPM par genre, rafraichie quotidiennement

### Definition of Done

```bash
# Tag filter ne casse plus la pagination
curl "/api/tracks/?tag=House&limit=20" → exactement 20 resultats (si assez de tracks)

# Batch radar : 1 round-trip DB au lieu de N
# (mesurer avec logging SQL)

# Catalog list < 200ms pour 5000 entries
# (mesurer avec EXPLAIN ANALYZE)
```

---

## T5 — Validation & Contrats API

**Equipe : API Quality**
**Priorite : MOYEN — Sprint 3**
**Estimation : 3-4 jours**

### Contexte pour l'equipe

La plupart des endpoints utilisent Pydantic, mais certains acceptent des `dict` bruts
ou des strings non valides. Les reponses d'erreur sont incoherentes (format, codes HTTP).
Pas de handler global pour les exceptions non gerees.

### Perimetre a auditer avant de coder

| Fichier | Probleme |
|---------|----------|
| `server/api/routers/radar.py` | `batch_update_radar_state` accepte `list[dict]` |
| `server/api/routers/tracks.py` | `bulk_import` sans limite de taille de liste |
| `server/api/routers/catalog.py` | Parametre `sort` non valide → fallback silencieux |
| `server/api/routers/admin.py` | `search_deezer_artist` : pas de validation sur `q` |
| Tous les routers | Reponses d'erreur : mix de `{"detail": "..."}` et schemas custom |
| `server/api/main.py` | Pas de `@app.exception_handler` global |

### Taches

- [ ] **Schemas Pydantic pour tous les inputs** :
  - `radar.py` : creer `RadarStateUpdateBatch(catalog_id: int, status: str)`,
    utiliser `list[RadarStateUpdateBatch]` au lieu de `list[dict]`
  - `tracks.py` : ajouter `max_length` au schema `TrackImport` list (ex: 5000)
- [ ] **Validation strings** : ajouter `max_length` sur tous les `Query(str)` :
  - Search : `q: str = Query("", max_length=200)`
  - Admin Deezer search : `q: str = Query(..., max_length=100)`
- [ ] **Enum pour les statuts** : remplacer `String(20)` par des Literal/Enum :
  ```python
  class RadarStatus(str, Enum):
      new = "new"
      seen = "seen"
      added = "added"
      ignored = "ignored"
  ```
- [ ] **Schema d'erreur standard** :
  ```python
  class ErrorResponse(BaseModel):
      detail: str
      code: str | None = None
  ```
  - Appliquer sur tous les `HTTPException`
- [ ] **Handler d'exception global** :
  ```python
  @app.exception_handler(Exception)
  async def global_handler(request, exc):
      logger.exception("Unhandled error")
      return JSONResponse(status_code=500, content={"detail": "Internal server error"})
  ```
- [ ] **Codes HTTP coherents** : 401 pour tous les echecs auth (pas 403 pour "account disabled")
- [ ] **Temp file cleanup** : `tracks.py` bulk import — ajouter `try/finally` sur `os.unlink()`

### Definition of Done

```bash
# Input invalide → 422 avec message clair
curl -X PATCH /api/radar/state/batch -d '[{"bad": "data"}]' → 422

# Search trop long → rejet
curl "/api/search?q=$(python -c 'print("a"*1000)')" → 422

# 500 ne leak pas de details
# (provoquer une erreur interne → reponse generique)
```

---

## T6 — Schema DB & Integrite

**Equipe : Data**
**Priorite : MOYEN — Sprint 2**
**Estimation : 2-3 jours**

### Contexte pour l'equipe

Le schema PostgreSQL est globalement solide (bonnes FK, UNIQUE constraints, index sur les PK).
Il manque des CHECK constraints sur les valeurs metier, un CASCADE sur RadarTrack,
et des index sur les colonnes frequemment filtrees.

**Evolution depuis l'audit :** le systeme de genres a ete entierement refonde :
- Tables `catalog_genres`, `artist_genres`, `set_genres` **supprimees** (migration 0013)
- Genres sur catalog : desormais un array `genres TEXT[]` directement sur la table `catalog` (migration 0018)
- Taxonomie : nouvelles tables `genre_nodes` + `genre_edges` (graphe DAG, migration 0019)
- Les index et CHECK proposes initialement pour les anciennes tables genres sont donc caducs

### Perimetre a auditer avant de coder

| Fichier | Quoi verifier |
|---------|---------------|
| `server/api/models.py` | Toutes les FK : verifier `ondelete`, `nullable`, `index` |
| `server/api/alembic/versions/` | 19 migrations existantes — verifier coherence |
| `server/workers/tasks.py` | Pattern `session.commit()` dans les boucles |

### Taches (une seule migration Alembic)

- [ ] **Fix RadarTrack FK** : ajouter `ondelete="CASCADE"` sur `watched_entity_id`
  ```python
  watched_entity_id = Column(Integer, ForeignKey("watched_entities.id", ondelete="CASCADE"))
  ```
- [ ] **CHECK constraints** :
  ```sql
  ALTER TABLE catalog ADD CONSTRAINT ck_bpm_positive
      CHECK (bpm > 0 OR bpm IS NULL);
  ALTER TABLE user_tracks ADD CONSTRAINT ck_rating_range
      CHECK (rating >= 0 AND rating <= 5 OR rating IS NULL);
  ALTER TABLE set_tracks ADD CONSTRAINT ck_position_positive
      CHECK (position >= 1);
  ALTER TABLE user_opinions ADD CONSTRAINT ck_opinion_valid
      CHECK (opinion IN ('liked', 'disliked'));
  ALTER TABLE artist_flags ADD CONSTRAINT ck_flag_status_valid
      CHECK (status IN ('pending', 'validated', 'skipped'));
  ```
- [ ] **Index sur colonnes filtrees** :
  ```sql
  CREATE INDEX ix_radar_tracks_watched_entity ON radar_tracks(watched_entity_id);
  CREATE INDEX ix_radar_tracks_catalog ON radar_tracks(catalog_id);
  CREATE INDEX ix_catalog_deezer_id ON catalog(deezer_id) WHERE deezer_id IS NOT NULL;
  CREATE INDEX ix_catalog_beatport_id ON catalog(beatport_id) WHERE beatport_id IS NOT NULL;
  CREATE INDEX ix_watched_entities_source ON watched_entities(source);
  CREATE INDEX ix_catalog_genres ON catalog USING GIN(genres);
  ```
- [ ] **Coherence DateTime** : verifier que toutes les colonnes timestamp utilisent
  `DateTime(timezone=True)` (pas `DateTime` sans timezone)

### Definition of Done

```sql
-- CHECK constraints actifs
INSERT INTO user_tracks (user_id, catalog_id, rating) VALUES (1, 1, 99);
-- → ERROR: violates check constraint "ck_rating_range"

-- CASCADE fonctionne
DELETE FROM watched_entities WHERE id = 1;
-- → radar_tracks associes supprimes automatiquement

-- Index utilises
EXPLAIN ANALYZE SELECT * FROM radar_tracks WHERE catalog_id = 42;
-- → Index Scan using ix_radar_tracks_catalog

-- Index GIN genres fonctionne
EXPLAIN ANALYZE SELECT * FROM catalog WHERE genres @> ARRAY['House'];
-- → Bitmap Index Scan using ix_catalog_genres
```

---

## F1 — Multi-User (Phases 5-7)

**Equipe : Product**
**Priorite : PLANIFIE — apres stabilisation technique**
**Document de reference : [`docs/ROADMAP_MULTIUSER.md`](ROADMAP_MULTIUSER.md)**

### Etat actuel

| Phase | Statut | Description |
|-------|--------|-------------|
| Phase 0 | SKIPPED | Resolution catalog_id (gere en Phase 2) |
| Phase 1 | DONE | Table users + auth JWT |
| Phase 2 | DONE | catalog scope + user_tracks + migration lib_tracks |
| Phase 3 | DONE | watched_entities + user_follows |
| Phase 4 | DONE | user_radar_state (per-user discovery) |
| **Phase 5** | **A FAIRE** | **radar_trends + user_collections** |
| **Phase 6** | **A FAIRE** | **Enforcement auth + drop lib_tracks** |
| **Phase 7** | **A FAIRE** | **Import multi-user** |

### Phase 5 — radar_trends + user_collections

**Depend de : T6 (schema DB clean avant d'ajouter des tables)**

Tables a creer :
- `radar_trends(catalog_id PK, trend_score, window_days, detection_count, computed_at)`
- `user_collections(id PK, user_id FK, name, type, created_at)`
- `collection_items(collection_id FK, catalog_id FK, position, added_at)`

Celery task `compute_trends` : agregation par catalog_id, decroissance temporelle half-life 14j.

API : CRUD collections, score tendance visible sur les tracks radar.

Detail complet : voir `ROADMAP_MULTIUSER.md` Phase 5.

### Phase 6 — Enforcement auth + Cleanup

**Depend de : T1 (securite deja en place)**
**Etat : ~70% FAIT**

Deja fait :
- [x] Suppression definitive de `lib_tracks` (migration 0009 `DROP TABLE`)
- [x] `LibTrack` supprime de `models.py`
- [x] Router guards frontend : redirect `/login` si pas de token (`router.beforeEach`)
- [x] Bouton logout dans la sidebar (`SidebarNav.vue`)
- [x] Gestion du 401 : auto-logout + redirect login (`api.js` intercepteur)

Reste a faire :
- [ ] Middleware auth obligatoire backend (tous les endpoints sauf `/api/auth/*` et `/api/health`)
- [ ] Migrer `get_current_user_optional` → `get_current_user` sur les routes qui le justifient
- [ ] CORS : restreindre `allow_origins` (releve de T1)
- [ ] Headers securite Nginx (releve de T1)

### Phase 7 — Import multi-user

**Depend de : T5 (validation inputs solide)**

- Endpoint `POST /api/import/rekordbox` scope au `current_user.id`
- Script `main.py` adapte pour accepter `--user-token`
- Gestion `scope='private'` + reconciliation si match ISRC
- Promotion `private → shared` quand ISRC confirme

---

## F2 — HTTPS / Domaine

**Equipe : Platform**
**Priorite : EN ATTENTE (domaine)**
**Document de reference : [`docs/PLAN_HTTPS.md`](PLAN_HTTPS.md)**
**Depend de : T3 (Docker hardening)**

### Resume du plan

- Overlay compose `docker-compose.ssl.yml` + certbot container
- Template Nginx SSL avec `${DOMAIN}` substitue par envsubst
- Provisioning initial : certbot standalone, puis renouvellement auto 12h
- CI/CD : `nginx -s reload` au lieu de `restart`

### Pre-requis restants

- [ ] Acheter et configurer le nom de domaine
- [ ] Pointer le DNS A vers 82.29.168.247
- [ ] T3 complete (restart policies, health checks) avant d'ajouter la couche SSL
- [ ] Executer le provisioning initial (voir `PLAN_HTTPS.md` section "Provisioning")

---

## F3 — Design Realignment (Wildflower DA)

**Equipe : Frontend / Design**
**Priorite : EN COURS (parallele)**
**Document de reference : [`_design/design_handoff_diggy_da/realign/ROADMAP-realign.md`](_design/design_handoff_diggy_da/realign/ROADMAP-realign.md)**

### Etat actuel

| Vague | Statut | Contenu |
|-------|--------|---------|
| Vague 0 | DONE | Decisions transversales (cible DA, admin role-gated, dark mode, densite) |
| Vague 1 | EN COURS | Kit composants partages. Player implemente. Reste : SidebarNav, PageHero, StatStrip, tables, filtres |
| Vague 2 | DONE (5/6) | Listes (Catalog, Radar, Sets, Artistes v2, Playlists). Genre Detail : maquette livree, a implementer |
| **Vague 3** | **A FAIRE** | **Pages detail** (Track, Artist, Set, Playlist) |
| **Vague 4** | **EN COURS** | Genres : maquette livree, a implementer. Login a faire |
| **Vague 5** | **A FAIRE** | **Admin panel** (sync, artworks, flags, liaison Deezer) |

### Regles a respecter (grille d'audit par ecran)

1. Zero couleur hors-tokens (tout via `var(--...)` de `diggy-tokens.css`)
2. Responsive : large → laptop → tablet → narrow
3. Admin role-gated : surface utility + bordure tiretee, deux etats (admin/user)
4. Accent discipline : `--accent` reserve aux actions/ratings, jamais en decor
5. Font mono pour les donnees (BPM, key, duree, score, dates)

### Interaction avec les chantiers techniques

- T5 (validation API) peut impacter les schemas de reponse consommes par le frontend
- T4 (performance) peut changer les endpoints utilises par les vues detail
- Coordination necessaire pour eviter les doubles refactors

---

## L1 — Monitoring & Observabilite

**Equipe : Platform**
**Priorite : BACKLOG — apres T1/T2/T3**

### Perimetre

| Composant | Outil recommande | Justification |
|-----------|-----------------|---------------|
| Error tracking | Sentry | Aggregation erreurs, alertes, contexte utilisateur |
| Metriques | Prometheus + Grafana | CPU, memoire, latence API, queue Celery |
| Uptime | UptimeRobot (gratuit) | Heartbeat HTTP toutes les 5 min |
| Logs | Loki + Grafana (ou ELK) | Centralisation, recherche, correlation |
| DB monitoring | pg_stat_statements | Slow queries, index usage |

### Taches

- [ ] **Sentry** : integrer dans FastAPI + Celery workers
  ```python
  import sentry_sdk
  sentry_sdk.init(dsn=os.environ["SENTRY_DSN"], traces_sample_rate=0.1)
  ```
- [ ] **Endpoint `/api/health`** enrichi : retourner version, uptime, status DB/Redis
- [ ] **Request logging middleware** : log method, path, status, duration
- [ ] **Celery flower** ou equivalent pour monitorer les tasks en cours
- [ ] **UptimeRobot** : configurer un check HTTP sur `/api/health`
- [ ] **pg_stat_statements** : activer + dashboard pour les slow queries
- [ ] **Alertes** : notification (email/Slack) si API down > 5 min ou erreur rate > 5%

---

## L2 — Multi-artiste par track

**Priorite : BACKLOG**

Table `catalog_artists(catalog_id, artist_id, role)` pour gerer les feats.
Permettrait d'afficher un track sur les pages de chaque artiste implique.
Impact : catalog detail, artist detail, recherche, import.
Note : 136 artistes orphelins issus de splits feat attendent cette feature.

---

## L3 — Graphe artistes

**Priorite : BACKLOG**

Visualisation des connexions entre artistes via sets communs, feats, playlists partagees.
Necessite L2 (multi-artiste) pour les connexions feat.
Stack envisagee : D3.js ou vue-flow cote frontend.

---

## Annexe A — Scores de l'audit (juin 2026)

| Domaine | Score audit (juin 2026) | Actuel (juin 2026 fin) | Cible apres T1-T6 |
|---------|------------------------|------------------------|--------------------|
| Architecture | 7/10 | 7/10 | 8/10 |
| Securite | 4/10 | 4/10 | 8/10 |
| Performance | 5/10 | 5.5/10 (preview_url cache) | 7/10 |
| Resilience Workers | 4/10 | 4/10 | 7/10 |
| Infra/DevOps | 4/10 | 5/10 (health checks + /api/health) | 8/10 |
| Base de donnees | 7/10 | 7.5/10 (refonte genres TEXT[] + taxonomy) | 8/10 |
| Tests | 3/10 | 3/10 | 5/10 |

---

## Annexe B — Fichiers cles par chantier

| Chantier | Fichiers principaux |
|----------|-------------------|
| T1 Security | `main.py`, `dependencies.py`, `auth.py`, `routers/auth.py`, `nginx/default.conf`, `docker-compose.yml` |
| T2 Workers | `workers/tasks.py`, `workers/celery_app.py`, `workers/source_clients.py`, `workers/enrichment.py`, `workers/async_http.py`, `workers/rate_limiter.py`, `workers/db.py`, `workers/crawl_logger.py` |
| T3 Infra | `docker-compose.yml`, `server/api/Dockerfile`, `server/frontend/Dockerfile`, `.github/workflows/deploy.yml`, `nginx/default.conf` |
| T4 Perf | `routers/catalog.py`, `routers/tracks.py`, `routers/radar.py`, `routers/artists.py`, `routers/genres.py`, `routers/search.py` |
| T5 Validation | Tous les `routers/*.py`, `main.py` (exception handler) |
| T6 Schema | `models.py` (incl. `GenreNode`, `GenreEdge`), `alembic/versions/` (19 migrations) |
| F1 Multi-User | `models.py`, `routers/tracks.py`, `routers/radar.py`, `dependencies.py`, `main.py` (import) |
| F3 Design | `frontend/src/views/`, `frontend/src/components/`, `frontend/src/styles/diggy-tokens.css` |
