# Diggy — Roadmap

> Document maitre. Chaque chantier est autonome et assignable a un dev/agent independant.
> Les dependances inter-chantiers sont explicites.
>
> **Roadmaps archivees** : voir `docs/completed/`
> - `ROADMAP_2026-06.md` — audit technique T1-T6, chantiers C1-C13 (100%)
> - `ROADMAP_2026-06-backlog.md` — ancien backlog L1-L3, F3-F4 (absorbe ici)
> - `ROADMAP_MULTIUSER.md` — multi-user phases 0-4 (100%)
> - `ROADMAP_AUDIT_2026-07.md` — rapport d'audit CTO complet (reference)
>
> **Derniere mise a jour** : 2026-07-01

---

## Vue d'ensemble

```
 #    Chantier                           Priorite    Estimation   Statut
────  ─────────────────────────────────  ──────────  ──────────   ──────
 S1   Securite & Hardening              CRITIQUE    1-2 jours    TERMINE
 S2   Qualite & CI Pipeline             CRITIQUE    2-3 jours    TERMINE
 A1   Service Layer Backend             HAUT        5-7 jours    TERMINE
 A2   Refactor Workers                  HAUT        3-5 jours    TERMINE
 A3   Frontend Perf & Accessibilite     MOYEN       2-3 jours    TERMINE
 D1   FIX Design immediats             HAUT        1-2 jours    TERMINE
 D2   Genres — Refonte complete         HAUT        5-7 jours    TERMINE
 D3   Hub / Search                      MOYEN       3-5 jours    TERMINE
 D4   Pages Detail (Vague 3)            MOYEN       5-7 jours    BLOQUE (briefs)
 D5   Refactor Composants partages      MOYEN       3-4 jours    TERMINE
 F1   Monitoring & Observabilite        BAS         2-3 jours    REPORTE (long terme)
 F2   Multi-User Phases 5-7             BAS         7-10 jours   A FAIRE
 F3   Graphe artistes                   BAS         5-7 jours    A FAIRE
 F4   Import Rekordbox Web              MOYEN       3-4 jours    A FAIRE
 R1   Responsive / Support Mobile       HAUT        3-4 jours    A FAIRE
```

### Dependances

```
S1 ──────────────> Tout (prerequis securite) ✅ TERMINE
S2 ──────────────> A1, A2 (refactors securises par CI) ✅ TERMINE
A1 (services) ──> D2, D3 (endpoints genres/search) ✅ TERMINE
D1 (FIX) ───────> D2, D4, D5 (base propre) ✅ TERMINE
D5 (kit) ───────> D2, D3, D4 (composants reutilisables) ✅ TERMINE
```

### Decisions a trancher (willi)

> Ces points bloquent certains chantiers. A trancher avant de lancer les equipes.

| #  | Question | Impacte | Options |
|----|----------|---------|---------|
| Q1 | Sets : anneau 100% | D1 | **TRANCHE** : calme neutre (check + "100%") |
| Q2 | Radar : wording FR | D1 | **TRANCHE** : francais |
| Q3 | Hub : direction | D3 | **TRANCHE** : C (Vitrine) |
| Q4 | Hub : GUEST_CAP | D3 | **TRANCHE** : 6 resultats |
| Q5 | TypeScript frontend | Long terme | **TRANCHE** : rester JS — migration TS tres basse priorite |

---

## S1 — Securite & Hardening ✅

**Equipe : Platform / DevOps**
**Priorite : CRITIQUE — Semaine 1**
**Estimation : 1-2 jours**
**Depend de : rien**
**Statut : TERMINE**

### Contexte

Le fichier `.env` a ete committe dans l'historique git. Meme si les mots de passe
ont deja ete changes et que `.env` est dans `.gitignore`, l'historique contient encore
les anciens secrets en clair. Plusieurs autres points de hardening sont necessaires.

### Taches

#### Critique

- [x] **Scrub git history** : supprimer `.env` de tout l'historique
  ```bash
  pip install git-filter-repo
  git filter-repo --path .env --invert-paths
  git push --force --all
  ```
  - Apres : tous les contributeurs doivent re-cloner le repo
  - Verifier : `git log --all --full-history -- ".env"` → vide

- [x] **Chiffrer les backups** : ajouter `gpg -c` dans `server/scripts/backup.sh`
  - Ajouter `BACKUP_ENCRYPTION_KEY` dans `.env` VPS
  - Chiffrer le dump : `pg_dump ... | gzip | gpg --batch --passphrase "$BACKUP_ENCRYPTION_KEY" -c > backup.sql.gz.gpg`
  - Verifier le restore : `gpg --batch --passphrase "$KEY" -d backup.sql.gz.gpg | gunzip | psql`

#### Haut

- [x] **Rate limiting OAuth callback** : ajouter `/api/auth/google/callback` dans `rate_limit.py`
  ```python
  RATE_LIMITS = {
      ...
      "/api/auth/google/callback": (5, 60),  # 5 req/min
  }
  ```

- [x] **Restreindre MinIO console** : bloquer `/minio/` dans Nginx
  ```nginx
  location /minio/ {
      return 403;
  }
  ```

- [x] **Automatiser certbot renewal** : hook post-renewal dans `docker-compose.ssl.yml`
  ```yaml
  certbot:
    entrypoint: >
      /bin/sh -c 'trap exit TERM;
      while :; do certbot renew --deploy-hook "nginx -s reload" && sleep 12h; done'
  ```

- [x] **Ajouter CSP header Nginx** :
  ```nginx
  add_header Content-Security-Policy "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src https://fonts.gstatic.com; img-src 'self' data: blob:;" always;
  ```

#### Moyen

- [x] **Beat schedule persistant** : ajouter volume Docker pour le fichier schedule Celery Beat
  ```yaml
  beat:
    volumes:
      - beat_schedule:/var/spool/celery
    command: celery -A workers.celery_app beat -s /var/spool/celery/schedule ...
  volumes:
    beat_schedule:
  ```

- [x] **Connection pool SQLAlchemy** : configurer dans `database.py`
  ```python
  engine = create_async_engine(
      DATABASE_URL,
      pool_size=10,
      max_overflow=5,
      pool_pre_ping=True,
  )
  ```

- [x] **Audit logging admin** : table `admin_audit_log(id, user_id, action, target_type, target_id, details, created_at)` pour tracer les actions destructrices (merge artistes, delete set, rename genre, etc.)

### Definition of Done

```bash
# Git history propre
git log --all --full-history -- ".env" → vide

# Backups chiffres
file /backups/postgres/latest.sql.gz.gpg → "GPG symmetrically encrypted data"

# MinIO console bloquee
curl https://diggy-music.fr/minio/ → 403

# Rate limit OAuth
for i in {1..10}; do curl -s /api/auth/google/callback; done → 429 apres 5
```

---

## S2 — Qualite & CI Pipeline ✅

**Equipe : Platform / QA**
**Priorite : CRITIQUE — Semaine 1-2**
**Estimation : 2-3 jours**
**Depend de : rien**
**Statut : TERMINE**

### Contexte

430+ tests existent mais sans tracking de couverture, sans linting Python, et sans tests
sur PostgreSQL reel (SQLite uniquement en CI). Le frontend n'a aucun test unitaire.
Ces lacunes empechent de refactorer en confiance.

### Taches

#### Critique

- [x] **Linting Python avec ruff** :
  - Ajouter la config dans `pyproject.toml` :
    ```toml
    [tool.ruff]
    line-length = 88
    target-version = "py313"
    select = ["E", "F", "W", "I"]
    ```
  - Ajouter le job dans `.github/workflows/deploy.yml` :
    ```yaml
    lint-python:
      runs-on: ubuntu-latest
      steps:
        - uses: actions/checkout@v4
        - run: pip install ruff && ruff check server/
    ```
  - Corriger les erreurs existantes (batch initial)

- [x] **Tracking de couverture avec pytest-cov** :
  - Ajouter `pytest-cov` dans les dev dependencies
  - Modifier le job test CI :
    ```yaml
    - run: pytest tests/ -v --cov=server --cov-report=term-missing --cov-fail-under=55
    ```
  - Seuil initial : 55% (a augmenter progressivement)

- [x] **Reactiver PostgreSQL dans CI** :
  - Decommenter le bloc `services: postgres:` dans `deploy.yml`
  - Ajouter `DATABASE_URL` en env du job test
  - Accepter le surcout (~3min vs ~1min)

#### Haut

- [x] **Scan vulnerabilites deps** : ajouter `pip-audit` dans CI (warning, pas bloquant)
  ```yaml
  - run: pip install pip-audit && pip-audit --desc || true
  ```

- [x] **Tests frontend basiques** : installer vitest + @vue/test-utils
  - Tester les 3 stores Pinia : `auth.js`, `audioPlayer.js`, `opinions.js`
  - Tester `utils/api.js` (intercepteur 401, injection token)
  - Objectif : 10-15 tests unitaires minimum
  - Job CI :
    ```yaml
    test-frontend:
      runs-on: ubuntu-latest
      steps:
        - uses: actions/checkout@v4
        - run: cd server/frontend && npm ci && npx vitest run
    ```

#### Moyen

- [x] **Prettier frontend** : `.prettierrc` + integration ESLint
- [x] **Structured logging** : `structlog` ou `python-json-logger` pour logs JSON

### Fichiers a modifier

| Fichier | Modification |
|---------|-------------|
| `pyproject.toml` | Ajouter `[tool.ruff]` config |
| `.github/workflows/deploy.yml` | Jobs `lint-python`, `test-frontend`, decommenter PG service |
| `server/api/requirements.txt` | Ajouter `pytest-cov` (dev) |
| `server/frontend/package.json` | Ajouter `vitest`, `@vue/test-utils`, `jsdom` (devDeps) |

### Definition of Done

```bash
# Ruff passe
ruff check server/ → All checks passed

# Coverage visible
pytest --cov → 55%+ avec rapport

# CI PG active
# deploy.yml services postgres → tests passent sur PG reel

# Frontend tests
cd server/frontend && npx vitest run → 10+ tests passed
```

---

## A1 — Service Layer Backend ✅

**Equipe : Backend**
**Priorite : HAUT — Sprint 2**
**Estimation : 5-7 jours**
**Depend de : S2 (CI solide avant refactor)**
**Statut : TERMINE**

### Contexte

Les routers FastAPI contiennent trop de logique metier melangee avec le handling HTTP.
Les plus gros : `admin.py` (725 LOC), `genres.py` (703 LOC), `catalog.py` (591 LOC).
Les queries SQL sont complexes (10+ subqueries imbriquees dans `list_catalog()`).
Ce melange rend le code difficile a tester unitairement et a maintenir.

L'objectif : extraire la logique dans des services testables. Chaque endpoint devient
un "passe-plat" de 10-20 lignes : validation → appel service → response.

### Services a creer

| Service | Extrait de | Methodes principales |
|---------|-----------|---------------------|
| `ArtistService` | `admin.py` + `artists.py` | `sync_artists()`, `resolve_flag()`, `merge_artists()`, `list_with_stats()` |
| `CatalogService` | `catalog.py` | `list_catalog()` (10 subqueries), `get_detail()` |
| `GenreService` | `genres.py` | `get_hierarchy()`, `classify_tracks()`, `get_stats()` |
| `RadarService` | `radar.py` | `list_enriched()` (8 subqueries) |
| `ImageService` | `deezer_enrich.py` + `storage.py` | `upload()`, `download()` — unifie les 2 clients S3 dupliques |

### Architecture cible

```
server/api/
├── services/                    ← NOUVEAU
│   ├── __init__.py
│   ├── artist_service.py        (sync, flags, merge, stats)
│   ├── catalog_service.py       (list, detail, queries complexes)
│   ├── genre_service.py         (hierarchie, classification)
│   ├── radar_service.py         (enriched listing)
│   └── image_service.py         (S3 unifie)
├── routers/                     ← ALLEGE
│   ├── admin.py                 725 → ~200 LOC
│   ├── catalog.py               591 → ~150 LOC
│   ├── genres.py                703 → ~200 LOC
│   ├── artists.py               412 → ~150 LOC
│   └── radar.py                 374 → ~150 LOC
```

### Exemple concret

```python
# ─── AVANT : admin.py ligne 316+ (logique metier dans le router) ───
@router.post("/artists/flags/{flag_id}/resolve")
async def resolve_flag(flag_id: int, body: ResolveIn, db = Depends(get_db)):
    flag = await db.execute(select(ArtistFlag).where(ArtistFlag.id == flag_id))
    flag = flag.scalar_one_or_none()
    if not flag:
        raise HTTPException(404)
    names = flag.tokens if body.action == "split" else [flag.raw_artist_string]
    created_ids = []
    for name in names:
        artist = await get_or_create_artist(db, name)
        if not artist.deezer_id and deezer_map.get(name):
            artist.deezer_id = deezer_map[name]
        created_ids.append(artist.id)
    # ... encore 20 lignes de linking, merge, cleanup
    await db.commit()
    return {"resolved": len(created_ids)}

# ─── APRES : admin.py (thin router, 5 lignes) ───
@router.post("/artists/flags/{flag_id}/resolve")
async def resolve_flag(flag_id: int, body: ResolveIn, db = Depends(get_db)):
    result = await artist_service.resolve_flag(db, flag_id, body.action)
    return result

# ─── services/artist_service.py (logique testable sans HTTP) ───
async def resolve_flag(db: AsyncSession, flag_id: int, action: str) -> dict:
    flag = await db.execute(select(ArtistFlag).where(ArtistFlag.id == flag_id))
    flag = flag.scalar_one_or_none()
    if not flag:
        raise ValueError(f"Flag {flag_id} not found")
    # ... toute la logique ici
    # Testable avec : await resolve_flag(mock_db, 42, "split")
```

### Taches

- [ ] **Creer `server/api/services/`** avec `__init__.py`
- [ ] **Extraire `ArtistService`** : deplacer toute la logique artiste depuis admin.py + artists.py
- [ ] **Extraire `CatalogService`** : deplacer `list_catalog()` et ses 10 subqueries
- [ ] **Extraire `GenreService`** : deplacer la logique hierarchie et classification
- [ ] **Extraire `RadarService`** : deplacer `list_radar_full()` et ses 8 subqueries
- [ ] **Unifier `ImageService`** : fusionner `deezer_enrich._get_s3()` et `storage._get_s3()` en un seul client
- [ ] **Refactorer les routers** : chaque endpoint = validation + appel service + response (10-20 LOC max)
- [ ] **Tests unitaires services** : 30+ tests dans `tests/api/test_services/`

### Definition of Done

```bash
# Aucun router ne depasse 300 LOC
wc -l server/api/routers/*.py → tous < 300

# Services testables independamment de FastAPI
pytest tests/api/test_services/ → 30+ tests passed

# Zero regression sur les tests existants
pytest tests/ → 430+ tests passed
```

---

## A2 — Refactor Workers ✅

**Equipe : Backend / Data Pipeline**
**Priorite : HAUT — Sprint 2-3**
**Estimation : 3-5 jours**
**Depend de : S2 (CI solide avant refactor)**
**Statut : TERMINE**

### Contexte

`server/workers/tasks.py` fait 1487 LOC avec 11 Celery tasks qui melangent
orchestration, enrichissement et acces DB. Le code alterne sync (Celery) et
async (`asyncio.run()`), ce qui complique le debug.

### Taches

- [ ] **Scinder `tasks.py`** en modules dans `server/workers/tasks/` :

  | Module | Tasks | LOC estimees |
  |--------|-------|-------------|
  | `orchestration.py` | `crawl_radar`, `crawl_single_playlist` | ~300 |
  | `enrichment.py` | `enrich_deezer_batch`, `enrich_beatport_batch` | ~250 |
  | `artists.py` | `sync_artists`, `fetch_artist_artworks`, `link_set_artists` | ~300 |
  | `genres.py` | `populate_artist_genres` | ~100 |
  | `sets.py` | `resolve_set_tracks` | ~150 |
  | `__init__.py` | Re-exports pour Celery autodiscover | ~10 |

- [ ] **Uniformiser retry policies** : verifier que les 11 tasks ont toutes :
  ```python
  @celery_app.task(bind=True, autoretry_for=(Exception,), max_retries=3, retry_backoff=True)
  ```

- [ ] **Backup via Celery Beat** : ajouter une task `backup_daily` declenchee par le scheduler
  - Remplace le script shell manuel `server/scripts/backup.sh`
  - Schedule : tous les jours a 3h

- [ ] **Tests supplementaires** : 20+ tests dans `tests/worker/`
  - Scenarios d'echec (DB down, API timeout, lock Redis deja pris)
  - Orchestration (fan-out crawl_radar → crawl_single_playlist)

### Definition of Done

```bash
# tasks.py scinde en modules
ls server/workers/tasks/ → orchestration.py, enrichment.py, artists.py, genres.py, sets.py

# Tests workers
pytest tests/worker/ → 70+ tests (vs 54 actuels)
```

---

## A3 — Frontend Perf & Accessibilite ✅

**Equipe : Frontend**
**Priorite : MOYEN — Sprint 3**
**Estimation : 2-3 jours**
**Statut : TERMINE**
**Depend de : rien**

### Contexte

Les 14 vues sont importees eagerly (pas de lazy loading). Certains patterns sont
dupliques (debounce de recherche copie 5+ fois, infinite scroll copie 2+ fois).
L'accessibilite est partielle (6/10).

### Taches

#### Code splitting

- [ ] **Lazy loading des routes** : remplacer les imports statiques par des imports dynamiques
  ```javascript
  // router.js — AVANT
  import CatalogView from './views/CatalogView.vue'

  // router.js — APRES
  const CatalogView = () => import('./views/CatalogView.vue')
  ```
  Appliquer a toutes les routes sauf `HubView` (page d'accueil, toujours chargee).
  Gain attendu : ~20% reduction du bundle initial.

- [ ] **Analyse de bundle** : ajouter `vite-plugin-visualizer`
  ```bash
  npm install -D rollup-plugin-visualizer
  ```
  Generer un rapport pour identifier les gros morceaux.

- [ ] **Production build** : verifier que Docker utilise le stage `production` (nginx)
  et non `development` (Vite dev server) sur le VPS.

#### Composables (DRY)

- [ ] **`composables/useDebounce.js`** : extraire le pattern debounce repete dans 5+ vues
  ```javascript
  export function useDebounce(fn, delay = 300) {
    let timer
    return (...args) => { clearTimeout(timer); timer = setTimeout(() => fn(...args), delay) }
  }
  ```

- [ ] **`composables/useInfiniteScroll.js`** : extraire le pattern IntersectionObserver
  repete dans ArtistsView, GenresView
  ```javascript
  export function useInfiniteScroll(fetchMore, options = {}) {
    const sentinel = ref(null)
    // ... IntersectionObserver setup
    return { sentinel, loading }
  }
  ```

#### Accessibilite (quick wins)

- [ ] **`aria-label`** sur tous les boutons icone sans texte (player, search, filters, close)
- [ ] **`aria-live="polite"`** sur les zones de resultats dynamiques (search, radar count)
- [ ] **Skip link** "Aller au contenu" en haut de chaque page (avant la sidebar)
- [ ] **Keyboard navigation** sur les chips de filtre (Tab + Enter/Space)

### Definition of Done

```bash
# Lazy loading actif
# Network tab : chunks .js separees au changement de route

# Composables extraits
ls src/composables/ → useDebounce.js, useInfiniteScroll.js, useTheme.js, useStyleMap.js

# A11y : zero bouton icone sans aria-label
grep -r "<button" src/ --include="*.vue" | grep -v "aria-label" → vide (sauf si texte visible)
```

---

## D1 — FIX Design Immediats ✅

**Equipe : Frontend**
**Priorite : HAUT — Sprint 2**
**Estimation : 1-2 jours**
**Depend de : rien**
**Statut : TERMINE**
**Ref design : `_design/handoff-sets-fix/BRIEF-sets-fix.md`, `_design/design_handoff_diggy_da/realign/PROMPT-claude-code-player-round2.md`**

### Contexte

Plusieurs correctifs design livres par le designer ne sont pas encore appliques.
Quick wins qui ameliorent la coherence visuelle sans refonte.

### Taches

#### Tokens manquants dans `diggy-tokens.css`

- [ ] **Token `--neg`** (hue 28 terracotta) : utilise par Radar dislike et Sets anneau faible %
  ```css
  :root {
    --neg: oklch(0.65 0.14 28);
    --neg-soft: oklch(0.92 0.04 28);
    --neg-ink: oklch(0.50 0.14 28);
  }
  [data-theme="dark"] {
    --neg: oklch(0.72 0.12 28);
    --neg-soft: oklch(0.25 0.04 28);
    --neg-ink: oklch(0.80 0.10 28);
  }
  ```

- [ ] **Tokens `--warn`** (hue 70 ambre) : meme pattern que `--neg`

#### Sets (4 FIX — ref `BRIEF-sets-fix.md`)

- [ ] **FIX #1** : Boutons "Importer + Suivre" — reintegrer CSS `.btn-follow` / `.btn-follow.done` (manquant apres refacto)
- [ ] **FIX #2** : Anneau 100% — **decision Q1 a trancher** (calme neutre vs vert plein)
- [ ] **FIX #3** : Compteur en-tete — afficher `{total} sets · {filtre} affiches` au lieu du seul filtre
- [ ] **FIX #4** : Vocabulaire "Suivre" → actions Avis (like/dislike) pour coherence avec Radar

#### Couleurs hardcodees a corriger

- [ ] `HubView.vue` (~ligne 696) : `#fff` → `var(--on-accent)`
- [ ] `ArtistCard.vue` (~lignes 279, 304) : `oklch(...)` hardcodes → tokens `--overlay-dark` / `--overlay-light`

#### Player round 2 (ref `PROMPT-claude-code-player-round2.md`)

- [ ] Icone pause sur la ligne du track actif dans les tables
- [ ] Gestion erreur si `preview_url` absent ou invalide (afficher message, pas crash)
- [ ] Ajouter token `--sidebar-w` (largeur sidebar) pour positionnement player

### Definition of Done

```bash
# Zero couleur hardcodee hors Google branding
grep -rn "#[0-9a-fA-F]\{3,8\}" server/frontend/src/ --include="*.vue" → seulement LoginView

# Tokens neg/warn presents dans les 2 themes
grep -c "neg-ink\|warn-ink" server/frontend/src/styles/diggy-tokens.css → 4+
```

---

## D2 — Genres : Refonte Complete ✅

**Equipe : Fullstack (Backend + Frontend)**
**Priorite : HAUT — Sprint 3**
**Estimation : 5-7 jours**
**Statut : TERMINE**
**Depend de : A1 (GenreService), D1 (tokens), D5 (composants)**
**Ref design : `_design/design_handoff_diggy_da/realign/BRIEF-genres.md`, `BRIEF-genre-detail.md`**

### Contexte

Le designer a livre des maquettes completes pour `/genres` (grille de cartes riches)
et `/style/:genre` (page detail avec shelves). Le code actuel est une grille plate
simpliste qui ne suit pas le design.

### Taches Backend

- [ ] **Endpoint `/api/genres/` enrichi** retournant pour chaque genre :
  ```json
  {
    "name": "Tech House",
    "pillar": "house",
    "trackCount": 312,
    "artistCount": 87,
    "bpmLo": 122,
    "bpmHi": 128,
    "inLibCount": 45,
    "covers": ["url1.jpg", "url2.jpg", "url3.jpg", "url4.jpg"],
    "topArtists": [
      {"id": 12, "name": "Fisher", "photo": "url.jpg"}
    ]
  }
  ```
  - Pagination serveur + tri (tracks desc, A-Z) + filtre famille + recherche
  - Compteurs famille independants de la pagination

- [ ] **Endpoint `/api/genres/:name/neighbors`** : genres voisins par proximite
  - Metrique : indice de Jaccard sur les artistes communs
  - `|artists(A) ∩ artists(B)| / |artists(A) ∪ artists(B)|`
  - Retourne : `[{name, pillar, score, trackCount}]` — limit 6

- [ ] **Endpoints admin** :
  - `PATCH /api/genres/:name` (rename)
  - `POST /api/genres/merge` (fusion de 2 genres)

### Taches Frontend — GenresView `/genres`

- [ ] **Grille de cartes riches** : `display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr))`
- [ ] **Carte genre** : collage 2x2 covers (fallback teinte famille), stats (Tracks, Artistes, BPM range, In lib badge)
- [ ] **Chips famille** : Tous / House / Techno / Trance / D&B / Hardcore / Hard Dance / Autre (avec compteurs)
- [ ] **Search** + tri (Tracks desc / A-Z) + scroll infini (IntersectionObserver)
- [ ] **Admin bloc** (role-gated) : tracks sans genre + bouton auto-classify

### Taches Frontend — GenreDetailView `/style/:genre`

- [ ] **Hero** : mosaique 3x2 covers, avatars top 3 artistes, play button, titre couleur famille
- [ ] **StatStrip** : Tracks · Artistes · BPM (p5-p95) · En bib
- [ ] **Shelves horizontales** : Artistes (cartes portrait), Sets (anneau %), Playlists (source-badge)
- [ ] **Tracks** : liste complete (play, cover, titre+artiste, BPM, Key, duree, lib toggle)
- [ ] **Genres voisins** : 6 chips avec score commun
- [ ] **Admin** : rename + merge (role-gated)

### Definition of Done

```bash
# Endpoint genres enrichi
curl /api/genres/?limit=5 → chaque genre a trackCount, covers[], topArtists[]

# Genres voisins
curl /api/genres/House/neighbors → [{name: "Tech House", score: 0.73}, ...]

# Frontend : visual check cartes riches + dark mode
```

---

## D3 — Hub / Search ✅

**Equipe : Fullstack**
**Priorite : MOYEN — Sprint 4**
**Estimation : 3-5 jours**
**Depend de : A1 (SearchService), decision Q3/Q4**
**Statut : TERMINE** (Q3 = Vitrine, Q4 = GUEST_CAP 6)
**Statut : BLOQUE — en attente decision direction (Q3)**
**Ref design : `_design/handoff-hub/BRIEF-hub.md`**

### Contexte

Le designer a livre 3 directions pour la page d'accueil / recherche universelle.
L'implementation necessite un endpoint `/api/search` unifie multi-entites.

### Taches Backend

- [ ] **Endpoint `/api/search`** :
  - Params : `?q=&scope=all|tracks|artists|sets|genres&limit=20&cursor=`
  - Recherche multi-entites triee par pertinence
  - Public (non-auth) avec cap visiteur configurable (`GUEST_CAP`)
  - Reponse typee : chaque resultat a un `type` (track/artist/set/genre)

### Taches Frontend

- [ ] **Implementer HubView** selon la direction choisie (Q3)
- [ ] **Resultats types** : badges icones par type d'entite
- [ ] **Gating visiteur vs connecte** : cap sur le nombre de resultats (Q4)
- [ ] **Lien genre** = nom brut URL-encode

---

## D4 — Pages Detail (Vague 3 Design)

**Equipe : Frontend**
**Priorite : MOYEN — Sprint 4-5**
**Estimation : 5-7 jours**
**Depend de : D5 (composants partages)**
**Statut : BLOQUE — en attente briefs designer pour Track/Playlist detail**
**Ref design : `_design/design_handoff_diggy_da/realign/ROADMAP-realign.md` (Vague 3)**

### Contexte

Les pages detail existent en code mais ne suivent pas la DA Wildflower.
Track Detail et Playlist Detail n'ont pas encore de brief designer (vague 3).
Les FIX rounds 3-4 sont partiellement appliques sur Artist/Set Detail.

### Taches

- [ ] **Verifier FIX appliques** sur Artist Detail et Set Detail :
  - `artist.name` affiche le nom brut (pas le slug)
  - MiniTrackTable (colonnes style, BPM, key, rating)
  - Bouton source en `btn-ghost` (pas accent)
  - Titre long : `font-size: clamp(20px, 2.2vw, 34px)`
  - LibDot fusionne (pas 2 colonnes Statut + Lib)

- [ ] **Track Detail** `/catalog/:id` (quand brief livre) :
  - Hero + StatStrip + blocs relationnels ("Detecte dans", "Apparait dans", "Du meme artiste")
  - Bloc admin inline (beatport_id, bouton enrichir)

- [ ] **Playlist Detail** `/playlists/:id` (quand brief livre) :
  - Hero square + StatStrip + table tracks

- [ ] **Vague 5 — Admin panel** `/admin` (quand brief livre) :
  - Refonte visuelle selon DA Wildflower

---

## D5 — Refactor Composants Partages ✅

**Equipe : Frontend**
**Priorite : MOYEN — Sprint 3**
**Estimation : 3-4 jours**
**Depend de : D1 (tokens corriges)**
**Statut : TERMINE**
**Ref design : `_design/handoff-refactor/REFACTOR-audit.md`**

### Contexte

L'audit du designer identifie 12 clusters de composants dupliques ou inline
qui devraient etre extraits dans un kit partage. Certains existent deja (StyleTag,
LikeDislike, LibDot), d'autres sont a creer.

### Lot A — Fondations

- [ ] **`utils/format.js`** : `fmtNum(n)` (separateur milliers), `pl(n, singular, plural)` (pluriel)
- [ ] **Purger fallbacks hex** : remplacer tout `var(--x, #hex)` par `var(--x)` pur

### Lot B — Composants structurels

- [ ] **`PageHeader.vue`** : titre + sous-titre + compteur (remplace les headers dupliques dans 8+ vues)
- [ ] **`SearchBox.vue`** : input recherche avec debounce + bouton clear + `aria-label`
- [ ] **`SegFilter.vue`** : filtre segmente (onglets toggle type Tous/New/Liked/Disliked)
- [ ] **`FamilyChips.vue`** : chips selection famille genre (Tous/House/Techno/...)

### Lot C — Composants metier

- [ ] **`AdminCard.vue`** : conteneur admin unifie (surface-2, border dashed --line-2, role-gated)
- [ ] **`SourceBadge.vue`** : badge source Deezer/TIDAL/Spotify (extraire de WatchlistView)
- [ ] **`RingPct.vue`** : anneau pourcentage SVG + pill texte (extraire de SetsView)
- [ ] **`SkeletonGrid.vue`** : placeholder chargement (grille de cartes fantome)

### Lot D — Patterns

- [ ] **`composables/useInfiniteScroll.js`** : sentinel + IntersectionObserver (cf. A3)
- [ ] **Verifier `assets/table.css`** : styles table partages (header mono, hover surface-2, tri)
- [ ] **Verifier `assets/buttons.css`** : `.btn`, `.btn--accent`, `.btn--ghost-accent`, `.btn--sm`, `.btn--danger`

### Definition of Done

```bash
# Composants crees
ls server/frontend/src/components/ → PageHeader, SearchBox, SegFilter, FamilyChips, AdminCard, SourceBadge, RingPct, SkeletonGrid

# Plus de duplication header
grep -rn "class=\"page-title\"" src/views/ → tous utilisent <PageHeader>
```

---

## F1 — Monitoring & Observabilite (REPORTE)

**Equipe : Platform**
**Priorite : BAS — Long terme**
**Estimation : 2-3 jours**
**Statut : REPORTE** — Sentry DSN configure, code integre. Activer Flower/pg_stat/UptimeRobot quand le projet grandira.

### Contexte

Sentry est integre dans le code (FastAPI + Celery workers) mais `SENTRY_DSN`
n'est pas configure sur le VPS. Le reste du monitoring est absent.

### Taches

- [ ] **Configurer Sentry en prod** : ajouter `SENTRY_DSN=https://...@sentry.io/...` dans `.env` VPS
  - Creer un projet Sentry (gratuit, tier dev)
  - Redemarrer les containers pour prise en compte
  - Verifier : provoquer une erreur 500 → visible dans Sentry

- [ ] **UptimeRobot** : creer un check HTTP gratuit sur `https://diggy-music.fr/api/health`
  - Alerte email si down > 5 min
  - Aucun code, config web uniquement

- [ ] **Celery Flower** : ajouter un service Docker pour monitorer les tasks
  ```yaml
  flower:
    build: ./server/api
    command: celery -A workers.celery_app flower --port=5555
    ports: []  # Pas expose publiquement
    networks: [diggy_network]
    depends_on: [redis]
  ```
  - Accessible via tunnel SSH : `ssh -L 5555:localhost:5555 root@VPS`

- [ ] **pg_stat_statements** : activer l'extension PostgreSQL pour identifier les slow queries
  ```sql
  CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
  -- Consulter : SELECT * FROM pg_stat_statements ORDER BY mean_exec_time DESC LIMIT 20;
  ```

- [ ] **Backup externe** (optionnel) : sync `/backups/` vers un S3 externe pour disaster recovery

---

## F2 — Multi-User Phases 5-7

**Equipe : Backend + Frontend**
**Priorite : BAS — plus tard**
**Estimation : 7-10 jours**
**Ref : `docs/completed/ROADMAP_MULTIUSER.md`**

### Contexte

Les phases 0-4 multi-user sont terminees (comptes, auth, tracks per-user, radar per-user).
Les phases restantes ne sont utiles que quand un deuxieme utilisateur actif rejoint Diggy.

### Phase 5 — Trends + Collections

- [ ] Tables : `radar_trends`, `user_collections`, `collection_items`
- [ ] Celery task `compute_trends` : score tendance avec decroissance half-life 14j
- [ ] API : CRUD collections + score tendance sur tracks radar
- [ ] Frontend : CollectionsView + modal "Ajouter a une collection"

### Phase 6 — Enforcement auth complet

- [ ] Middleware auth obligatoire backend (tous endpoints sauf `/api/auth/*`, `/api/health`)
- [ ] Migrer `get_current_user_optional` → `get_current_user` sur les routes appropriees

### Phase 7 — Import multi-user

- [ ] Endpoint `POST /api/import/rekordbox` scope au `current_user.id`
- [ ] Gestion `scope='private'` + reconciliation ISRC
- [ ] Promotion `private → shared` quand ISRC confirme

---

## F3 — Graphe Artistes

**Equipe : Frontend + Backend**
**Priorite : BAS — plus tard**
**Estimation : 5-7 jours**

### Contexte

Visualisation des connexions entre artistes via sets communs, feats (table `catalog_artists`
deja en place), et playlists partagees. Feature exploratoire.

### Taches

- [ ] **Endpoint `/api/artists/:id/connections`** : artistes connectes + poids de connexion
- [ ] **Composant GraphView** : D3.js force-directed graph ou vue-flow
- [ ] **Integration** : accessible depuis la page Artist Detail

---

## F4 — Import Rekordbox Web

**Equipe : Fullstack (Backend + Frontend)**
**Priorite : MOYEN**
**Estimation : 3-4 jours**
**Depend de : rien (infrastructure deja en place)**
**Statut : A FAIRE**

### Contexte

Le process d'import Rekordbox existe depuis l'origine du projet sous forme d'un script
CLI local (`main.py` + `worker/rekordbox/extractor.py`). Ce script lit la base SQLite
propriétaire de Rekordbox (via `pyrekordbox`) et pousse les tracks vers l'API.

Ce process est desormais depasse :
- La DB Rekordbox 6 est chiffree (cle derivee du hardware, non portable)
- L'auth email+password utilisee par le script est cassee (modele User = Google OAuth uniquement)
- Le script est incompatible multi-user par design

La cible : **drag-and-drop d'un export XML Rekordbox** depuis l'interface web,
import asynchrone, progression visible, multi-user natif.

### Perimetre et decisions

| Decision | Choix retenu |
|----------|-------------|
| Format fichier | XML export Rekordbox (officiel Pioneer, non chiffre) |
| Artworks | Hors scope — enrichissement Deezer existant suffit |
| MyTags | Hors scope — non filtres, importes tels quels dans `rb_mytags` |
| Processing | Asynchrone via Celery (pas de blocage HTTP) |
| Stockage temp | MinIO bucket `import-jobs` (supprime apres traitement) |
| Anti-doublon | Redis lock `import:lock:{user_id}` pendant le traitement |
| Script CLI | Depreciee et supprimee dans cette meme iteration |

### Architecture cible

```
[Browser]
    │  drag-and-drop XML
    ▼
POST /api/import/rekordbox-xml   (multipart, auth required)
    │  1. valide format XML (noeud racine <DJ_PLAYLISTS>)
    │  2. upload vers MinIO bucket "import-jobs/{user_id}/{task_id}.xml"
    │  3. pose Redis lock import:lock:{user_id}
    │  4. enqueue Celery task import_rekordbox_xml(task_id, user_id)
    │  5. retourne {"task_id": "..."}
    ▼
Celery worker
    │  1. telecharge XML depuis MinIO
    │  2. parse XML → liste TrackImport
    │  3. appelle logique bulk_import par batch de 50
    │  4. met a jour Redis : import:{task_id} → {status, inserted, updated, total}
    │  5. supprime le fichier MinIO
    │  6. libere Redis lock
    ▼
GET /api/import/status/{task_id}   (poll toutes les 2s)
    │  retourne {status, inserted, updated, total, errors[]}
    ▼
Frontend : barre de progression → redirect /tracks a la fin
```

### Taches Backend

#### Parser XML (nouveau fichier `server/api/services/rekordbox_xml.py`)

- [ ] Parser le XML avec `xml.etree.ElementTree` (stdlib, safe XXE par defaut)
- [ ] Extraire les noeuds `<TRACK>` de la collection (ignorer les playlists)
- [ ] Mapping champs XML → `TrackImport` :
  - `TrackID` → `id` (rekordbox_id)
  - `Name` → `title`
  - `Artist` → `artist`
  - `AverageBpm` → `bpm`
  - `Tonality` → `key`
  - `TotalTime` (secondes) → `duration` (ms, x1000)
  - `Rating` → `rating` (Rekordbox : 0/51/102/153/204/255 → 0-5)
  - `DateAdded` → `date_added`
  - `Location` → `file_path` (stocke tel quel, jamais utilise cote serveur)
- [ ] `image_base64 = None` systematiquement (artworks hors scope)
- [ ] Valider : fichier XML avec noeud racine `<DJ_PLAYLISTS Version="1.0.0">`, taille max 10MB

#### Endpoint upload (`POST /api/import/rekordbox-xml`)

- [ ] Accepte `multipart/form-data` avec champ `file`
- [ ] Verifie Redis lock — si `import:lock:{user_id}` existe : retourne 409 "Import deja en cours"
- [ ] Valide format XML (noeud racine) avant upload
- [ ] Upload vers MinIO `import-jobs/{user_id}/{task_id}.xml`
- [ ] Pose Redis lock `import:lock:{user_id}` TTL 10 minutes
- [ ] Enqueue Celery task `import_rekordbox_xml`
- [ ] Retourne `{"task_id": "...", "status": "queued"}`

#### Celery task `import_rekordbox_xml`

- [ ] Telecharge XML depuis MinIO
- [ ] Appelle le parser XML → liste de `TrackImport`
- [ ] Traite par batch de 50 via la logique existante de `bulk_import`
- [ ] Ecrit progression dans Redis : `import:{task_id}` (JSON, TTL 1h)
  ```json
  {"status": "running", "total": 600, "inserted": 120, "updated": 30, "errors": []}
  ```
- [ ] Supprime le fichier MinIO apres traitement (succes ou echec)
- [ ] Libere Redis lock dans tous les cas (try/finally)
- [ ] En cas d'erreur : status → "error", message stocke dans Redis

#### Endpoint status (`GET /api/import/status/{task_id}`)

- [ ] Lit Redis `import:{task_id}`, retourne le JSON
- [ ] Si cle absente : 404 "Import inconnu ou expire"

### Taches Frontend

#### `ImportRekordboxModal.vue`

- [ ] Zone drag-and-drop + click (accepte `.xml` uniquement)
- [ ] Validation cote client : extension `.xml`, taille < 10MB
- [ ] Instructions inline :
  > "Dans Rekordbox : Fichier > Exporter la collection dans la liste des pistes > XML"
- [ ] Etats : idle → uploading → processing (barre de progression) → done / error
- [ ] Poll `GET /api/import/status/{task_id}` toutes les 2s pendant processing
- [ ] Affichage final : `{inserted} nouveaux · {updated} mis a jour`
- [ ] Bouton "Voir ma bibliotheque" → redirect `/tracks` a la fin

#### Point d'entree UI

- [ ] Bouton "Importer depuis Rekordbox" dans la vue `/tracks` (visible si bibliotheque vide ou en header)
- [ ] Ouvre `ImportRekordboxModal`

### Suppression du code local (dead features)

- [ ] Supprimer `main.py` (script CLI)
- [ ] Supprimer `worker/rekordbox/` (extractor + `__init__`)
- [ ] Verifier qu'aucun import ne reference ces modules (`grep -r "from worker.rekordbox"`)
- [ ] Mettre a jour `CLAUDE.md` : retirer les refs au script CLI et au process local
- [ ] Mettre a jour `README` si existant

### Definition of Done

```bash
# Upload XML → import asynchrone
curl -X POST /api/import/rekordbox-xml \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@export.xml" \
  → {"task_id": "abc123", "status": "queued"}

# Progression
curl /api/import/status/abc123 \
  → {"status": "done", "total": 600, "inserted": 580, "updated": 20, "errors": []}

# Anti-doublon
# Second upload pendant traitement → 409

# Dead features absentes
ls main.py worker/rekordbox/ → No such file or directory

# CI verte
pytest tests/ → all passed
```

---

## R1 — Responsive / Support Mobile

**Equipe : Frontend**
**Priorite : HAUT**
**Estimation : 3-4 jours**
**Depend de : D5 (composants partages), D1 (tokens)**
**Statut : A FAIRE**

### Contexte

Diggy est actuellement concu pour desktop (sidebar fixe, tables denses, modales larges).
Sur telephone vertical, la sidebar deborde, les tables sont illisibles, et les
interactions tactiles ne sont pas pensees. L'objectif : rendre l'app utilisable
confortablement sur mobile sans refonte de l'architecture — responsive progressif,
pas de version separee.

Breakpoints cibles :
- `< 640px` : telephone vertical (priorite principale)
- `640px–1024px` : tablette / telephone paysage (amelioration secondaire)
- `> 1024px` : desktop (comportement actuel preserve)

### Taches

#### Navigation (critique)

- [ ] **Sidebar → bottom nav sur mobile** : en dessous de 640px, masquer la sidebar et
  afficher une barre de navigation basse avec les 5-6 destinations principales
  (Hub, Catalog, Artistes, Sets, Genres, + Admin si admin)
  ```css
  @media (max-width: 640px) {
    .sidebar { display: none; }
    .bottom-nav { display: flex; }
  }
  ```
- [ ] **`BottomNav.vue`** : composant barre bas (icones + label court, highlight route active)
- [ ] **Token `--bottom-nav-h`** dans `diggy-tokens.css` (hauteur ~56px) pour que le
  contenu principal ne soit pas cache derriere la barre

#### Layout global

- [ ] **Meta viewport** : verifier que `index.html` a `<meta name="viewport" content="width=device-width, initial-scale=1">`
- [ ] **Padding lateral mobile** : token `--page-px-mobile` (16px) applique sur toutes
  les vues via une classe `.page-container` ou le layout principal
- [ ] **Supprimer les `min-width` fixes** : reperer et corriger les conteneurs avec
  `min-width` hardcode qui cassent le layout mobile

#### Tables (TrackTable, MiniTrackTable)

- [ ] **Colonnes masquees sur mobile** : `BPM`, `Key`, `Duree`, `Rating` masques sous 640px
  — seuls `Cover`, `Titre + Artiste`, `Actions` restent visibles
  ```css
  @media (max-width: 640px) {
    .col-bpm, .col-key, .col-duration, .col-rating { display: none; }
  }
  ```
- [ ] **Scroll horizontal en fallback** : si une table doit rester complete, wrapper
  avec `overflow-x: auto` pour eviter le debordement

#### Composants

- [ ] **Modales** : `max-width: 100%; border-radius: 0` sur mobile (full-screen sheet
  du bas) — appliquer sur toutes les modales (`ImportRekordboxModal`, modales admin, etc.)
- [ ] **Filtres / chips** : scroll horizontal (`overflow-x: auto; white-space: nowrap`)
  sur les barres de filtres (`FamilyChips`, `SegFilter`) plutot que retour a la ligne
- [ ] **Player** : verifier que le mini-player ne cache pas le contenu ni la bottom nav ;
  ajuster `bottom` en fonction de `--bottom-nav-h`
- [ ] **Boutons d'action** : `min-height: 44px` sur tous les elements interactifs
  (cibles tactiles, recommandation Apple/Google)

#### Vues prioritaires a verifier

| Vue | Probleme attendu | Fix |
|-----|-----------------|-----|
| `CatalogView` | Table trop large, filtres debordent | Colonnes masquees + filtres scroll |
| `ArtistDetailView` | Hero image + grille tracks | Grille 1 col, hero full-width |
| `SetDetailView` | Anneau + table tracks | Anneau centré, table allégée |
| `GenresView` | Grille cartes | `minmax(150px, 1fr)` déjà OK si pas de min-width fixe |
| `HubView` | Search bar + resultats | A verifier |
| `SetsView` | Grille anneaux | Verifier wrapping |

#### Tokens a ajouter dans `diggy-tokens.css`

```css
:root {
  --bottom-nav-h: 56px;
  --page-px-mobile: 16px;
}
```

### Definition of Done

```bash
# Visual check sur Chrome DevTools → iPhone SE (375px)
# - Navigation bas visible et fonctionnelle
# - Aucune scrollbar horizontale sur le body
# - CatalogView lisible (titre + artiste visible)
# - Modales full-screen
# - Boutons >= 44px de hauteur

# Zero overflow horizontal
# Ouvrir chaque vue en 375px → pas de debordement body
```

---

## Methode de travail

Chaque chantier suit le cycle :

1. **Brief** : ce document sert de brief — chaque section est autonome et assignable
2. **Execution** : le dev/agent execute selon le perimetre defini
3. **Review** : relecture du code + tests CI (`pytest tests/ -v`)
4. **Deploy** : `git push origin master` → GitHub Actions → SSH → rebuild Docker
5. **Verification** : smoke tests VPS + validation visuelle
6. **Update** : cocher les taches dans ce document

**Commit naming** : `type(scope): description` (conventional commits)

```
fix(frontend): add --neg token to diggy-tokens.css
refactor(api): extract ArtistService from admin router
feat(api): add genres neighbors endpoint
chore(ci): enable PostgreSQL service in deploy workflow
```

**Regles** :
- Un chantier = un delivrable deployable. On ne passe pas au suivant tant que le precedent n'est pas deploye et verifie.
- Les tests CI doivent passer a chaque commit.
- Zero couleur hardcodee dans le frontend — tout via `var(--...)`.
- Code en anglais, UI en francais.
