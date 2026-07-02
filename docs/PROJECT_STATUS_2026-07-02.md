# Diggy — Statut Projet Complet

> Date : 2 juillet 2026
> Document destine a une session de planification long terme.
> Contient : architecture, etat du code, base de donnees, fonctionnalites livrees, roadmap restante.

---

## 1. Vision & Contexte

**Diggy** est une web app personnelle de DJ pour gerer et visualiser une bibliotheque musicale Rekordbox. Elle centralise les tracks, artistes, sets, genres, et surveille des playlists externes (Deezer, TIDAL, Spotify) pour decouvrir de nouvelles tracks ("radar").

- **Utilisateur actuel** : 1 seul (le createur, DJ)
- **Ouverture prevue** : bientot a un cercle d'amis DJs (5-10 personnes)
- **URL** : https://diggy-music.fr
- **Projet demarre** : debut 2026 (~416 commits a ce jour)
- **Langue** : code en anglais, UI en francais

---

## 2. Architecture Technique

### 2.1 Stack

| Couche | Technologie | Version |
|--------|-------------|---------|
| API | FastAPI + SQLAlchemy async | FastAPI 0.115, SQLAlchemy 2.0.36 |
| Base de donnees | PostgreSQL | 16 |
| Migrations | Alembic | 1.14 (25 migrations) |
| Queue/Workers | Celery + Redis | Celery 5.4 |
| Stockage fichiers | MinIO (S3-compatible) | |
| Frontend | Vue.js 3 + Vite + Pinia | Vue 3, Vite |
| Proxy | Nginx | HTTPS (Let's Encrypt, certbot auto-renew) |
| Monitoring | Sentry SDK integre (DSN pas encore configure) | |
| CI/CD | GitHub Actions | lint + test + deploy |
| Hebergement | VPS Hostinger (Ubuntu 24.04) | |

### 2.2 Infrastructure Docker

10 services dans `docker-compose.yml` :

| Service | Role |
|---------|------|
| `postgres` | Base de donnees PostgreSQL 16 |
| `redis` | Broker Celery + cache (locks, progression import, trends) |
| `api` | FastAPI (uvicorn) |
| `worker` | Celery worker principal (crawl, enrichissement, import) |
| `worker_enrich` | Celery worker dedie enrichissement (Deezer, Beatport) |
| `beat` | Celery Beat (scheduler cron) |
| `frontend` | Vue.js (Vite dev server en prod pour l'instant) |
| `minio` | Stockage S3 pour artworks |
| `nginx` | Reverse proxy HTTPS + headers securite + CSP |
| `backup` | Backup PostgreSQL automatise |

**Note** : le frontend tourne encore via Vite dev server en production (pas de build statique nginx). C'est un point a ameliorer.

### 2.3 CI/CD Pipeline

Fichier : `.github/workflows/deploy.yml`

Jobs (sur push master) :
1. `lint-frontend` — ESLint
2. `lint-python` — Ruff
3. `test` — pytest sur PostgreSQL reel (CI)
4. `audit` — pip-audit (warning only)
5. `test-frontend` — Vitest
6. `deploy` — SSH vers VPS, `docker compose up -d --build`

Un push sur master = deploiement automatique.

### 2.4 Celery Beat Schedule (taches cron)

| Tache | Horaire | Description |
|-------|---------|-------------|
| `crawl_radar` | 3h00 | Crawl toutes les playlists surveillees, detecte les nouvelles tracks |
| `crawl_followed_sets` | 4h00 | Crawl les sets DJ suivis |
| `enrich_catalog` | 5h00 | Enrichissement Deezer (previews, artworks, metadata) |
| `enrich_catalog_beatport` | 6h00 | Enrichissement Beatport (BPM, key, genre) |
| `compute_trends` | 7h00 | Calcul des scores de tendance radar |

---

## 3. Structure du Code

### 3.1 Metriques

| Zone | Fichiers | LOC | Detail |
|------|----------|-----|--------|
| Backend (API) | ~30 .py | 11 340 | routers + services + models + deps |
| Frontend | 14 views + 25 components | 15 758 | .vue + .js |
| Workers | 8 task modules | 3 784 | |
| Tests | ~40 fichiers | 7 016 | 549 fonctions de test |
| **Total** | | **~37 900** | |

### 3.2 Backend — `server/api/`

#### Routers (16 fichiers, 3 384 LOC, 93 endpoints)

| Router | LOC | Endpoints | Role |
|--------|-----|-----------|------|
| `admin.py` | 461 | 22 | Panel admin (sync artistes, flags, merge, Deezer linking, genres) |
| `watchlist.py` | 432 | 11 | CRUD playlists surveillees + triggers crawl |
| `search.py` | 408 | 1 | Recherche unifiee multi-entites |
| `taxonomy.py` | 360 | 11 | Taxonomie genres (Wikidata graph) |
| `sets.py` | 358 | 4 | Sets DJ + tracklists |
| `tracks.py` | 350 | 5 | Bibliotheque utilisateur (user_tracks) |
| `collections.py` | 215 | 6 | Collections personnalisees |
| `genres.py` | 194 | 11 | Genres enrichis (cartes, voisins, stats) |
| `auth.py` | 149 | 3 | Google OAuth login/callback + JWT |
| `radar.py` | 121 | 7 | Tracks radar avec filtres |
| `catalog.py` | 107 | 5 | Catalogue master |
| `opinions.py` | 92 | 2 | Like/dislike (avis utilisateur) |
| `import_rb.py` | 87 | 2 | Import Rekordbox XML (upload + status) |
| `artists.py` | 50 | 3 | Pages artistes + recherche |

#### Services (6 fichiers, 2 525 LOC)

| Service | LOC | Role |
|---------|-----|------|
| `genre_service.py` | 680 | Hierarchie, classification, stats, voisins |
| `artist_service.py` | 679 | Sync, flags, merge, stats, resolution |
| `catalog_service.py` | 611 | Listing enrichi, detail, queries complexes |
| `radar_service.py` | 320 | Listing enrichi radar, filtres, tendances |
| `image_service.py` | 141 | Client S3 unifie (upload/download artworks) |
| `rekordbox_xml.py` | 94 | Parser XML Rekordbox |

#### Autres fichiers cles

| Fichier | Role |
|---------|------|
| `main.py` | Entrypoint FastAPI, monte les routers |
| `models.py` | Tous les modeles SQLAlchemy (25 classes) |
| `dependencies.py` | `get_current_user`, `require_admin` |
| `deezer_enrich.py` | Recherche + enrichissement Deezer |
| `rate_limit.py` | Rate limiting par IP/endpoint |
| `trackid/importer.py` | Import depuis TrackID.net (sets) |

### 3.3 Frontend — `server/frontend/src/`

#### Vues (14 fichiers, 10 896 LOC)

| Vue | LOC | Route | Description |
|-----|-----|-------|-------------|
| `AdminView.vue` | 1 725 | `/admin` | Panel admin complet |
| `HubView.vue` | 1 373 | `/` | Page d'accueil vitrine + recherche universelle |
| `GenreDetailView.vue` | 1 166 | `/style/:genre` | Detail genre (hero, shelves, tracks, voisins) |
| `CatalogView.vue` | 1 146 | `/catalog` | Browse catalogue + filtres (aussi `/tracks` et `/radar` via query params) |
| `ArtistDetailView.vue` | 939 | `/artist/:id` | Detail artiste (tracks, sets, genres) |
| `SetsView.vue` | 846 | `/sets` | Liste sets DJ (grille anneaux %) |
| `WatchlistView.vue` | 831 | `/playlists` | Playlists surveillees CRUD |
| `SetDetailView.vue` | 690 | `/set/:id` | Detail set (tracklist, anneau, stats) |
| `TrackDetailView.vue` | 643 | `/catalog/:id` | Detail track (hero, stats, relations) |
| `PlaylistDetailView.vue` | 616 | `/playlists/:id` | Detail playlist (tracks, stats) |
| `GenresView.vue` | 371 | `/genres` | Grille cartes genres riches |
| `ArtistsView.vue` | 308 | `/artists` | Repertoire artistes |
| `LoginView.vue` | 144 | `/login` | Auth Google OAuth |
| `TagsView.vue` | 98 | `/tags` | Redirect vers genres |

#### Composants reutilisables (25 fichiers, 3 736 LOC)

Composants structurels : `PageHero`, `SearchBox`, `SegFilter`, `FamilyChips`, `StatStrip`, `RelBlock`, `AdminCard`, `SkeletonGrid`

Composants metier : `PlayerBar` (lecteur audio), `ArtistCard`, `GenreCard`, `GenreTrackRow`, `ShelfCard`, `HeroPlayer`, `ImportRekordboxModal`, `RingPct` (anneau %), `LikeDislike`, `LibDot`, `InLibBadge`, `SourceBadge`, `StyleTag`, `ScorePill`, `AppearRow`, `ArtistLinks`

Navigation : `SidebarNav`

#### Composables

| Composable | Role |
|------------|------|
| `useInfiniteScroll.js` | Sentinel + IntersectionObserver |
| `useStyleMap.js` | Mapping genre → couleur famille |
| `useTheme.js` | Toggle dark/light theme |

#### Stores Pinia

| Store | Role |
|-------|------|
| `auth.js` | Etat utilisateur, token JWT, login/logout |
| `audioPlayer.js` | Lecteur audio (preview Deezer 30s) |
| `opinions.js` | Cache opinions like/dislike |

#### Styles & Utils

| Fichier | Role |
|---------|------|
| `styles/diggy-tokens.css` | Design tokens (TOUTES les couleurs/espacements, zero hardcode) |
| `styles/diggy-style-map.js` | Mapping genre → hue pour la colorisation |
| `utils/api.js` | Client Axios avec intercepteur 401 + injection token |
| `utils/format.js` | `fmtNum()`, `pl()` (formatage nombres/pluriel) |
| `assets/buttons.css` | Classes boutons partagees (`.btn`, `.btn--accent`, `.btn--ghost`, etc.) |
| `assets/table.css` | Styles tables partagees |

### 3.4 Workers — `server/workers/`

#### Modules de taches (7 fichiers, 3 784 LOC)

| Module | Taches | Role |
|--------|--------|------|
| `radar.py` | `crawl_radar`, `crawl_single_playlist` | Crawl playlists multi-source |
| `catalog.py` | `enrich_catalog`, `enrich_catalog_beatport` | Enrichissement metadata |
| `artists.py` | `sync_artists`, `fetch_artist_artworks`, `link_set_artists` | Gestion artistes |
| `genres.py` | `reclassify_genres_chunk`, `reclassify_all_genres` | Classification genres |
| `import_rb.py` | `import_rekordbox_xml` | Import XML async |
| `sets.py` | `resolve_set_tracks`, `enrich_set_tracks`, `crawl_followed_sets` | Sets DJ |
| `trends.py` | `compute_trends` | Score tendance radar |

#### Source clients multi-plateforme (`source_clients.py`)

| Source | Methode | ISRC disponible |
|--------|---------|-----------------|
| Deezer | API officielle | Oui |
| TIDAL | `tidalapi` (OAuth device flow) | Oui |
| Spotify | `spotifyscraper` (scraping, zero auth) | Non — cross-search via Deezer |

Flux : Playlist externe → `crawl_single_playlist` → `source_clients.get_fetchers()` → RadarTracks → enrichissement Deezer → stockage catalog + radar_tracks.

### 3.5 Tests (549 fonctions)

| Zone | Tests | Couverture |
|------|-------|-----------|
| API (routers, models, validation) | ~330 | catalog (22), radar (21), watchlist (20), opinions (20), tracks (18), admin (17), models (17), collections (15), artists (15), auth (14+8+7), rate_limit (14), sets (13), search (11), utils (13), validation (21), deezer (25), beatport (43), trackid (24+5+5) |
| Services | ~42 | genre (9), catalog (9), image (9), radar (8), artist (7) |
| Workers | ~101 | tasks_new (26), task_refactor (21), relocate (20), rate_limiter (11), deezer checks (22), resolve_sets (7), link_set_artists (5), crawl_sets (5) |
| Frontend (Vitest) | ~15 | Stores Pinia + utils |

Infrastructure : PostgreSQL reel en CI, SQLite fallback en local.

---

## 4. Base de Donnees

### 4.1 Schema (25 modeles SQLAlchemy, 25 migrations Alembic)

#### Tables principales

| Table | Role | Volume estime |
|-------|------|---------------|
| `catalog` | Hub central, referentiel unique de tout morceau connu | ~5 200+ |
| `user_tracks` | Bibliotheque Rekordbox de l'utilisateur (PK composite user_id + catalog_id) | ~600 |
| `radar_tracks` | Tracks decouvertes via playlists surveillees | ~5 000+ |
| `artists` | Referentiel artistes (99% lies a Deezer) | ~2 700 |
| `sets` | Sets DJ avec metadata | ~27 |
| `set_tracks` | Tracks individuelles dans un set | ~428 |
| `watched_entities` | Playlists surveillees (Deezer/TIDAL/Spotify) | ~29 |
| `genre_nodes` | Taxonomie genres (noeud graph Wikidata) | ~26 |
| `users` | Comptes utilisateur (Google OAuth) | 1 |

#### Tables relationnelles / association

| Table | Relation |
|-------|----------|
| `catalog_artists` | catalog <-> artists (many-to-many, role + position) — ~7 200 |
| `genre_edges` | genre_nodes <-> genre_nodes (graph oriente) |
| `genre_mappings` | raw genre string → genre_node (normalisation) |
| `artist_aliases` | Noms alternatifs pour resolution artiste |
| `artist_flags` | Flags artistes a resoudre (admin workflow) |
| `set_artists` | sets <-> artists |

#### Tables utilisateur

| Table | Role |
|-------|------|
| `user_opinions` | Like/dislike sur toute entite (tracks, artistes, etc.) |
| `user_follows` | Follow d'entites (playlists, artistes) |
| `user_set_follows` | Follow de sets |
| `user_radar_state` | Etat per-user des tracks radar (vu/pas vu) |
| `user_collections` | Collections personnalisees |
| `collection_items` | Tracks dans une collection (PK composite) |
| `radar_trends` | Score tendance par track radar |

#### Tables systeme

| Table | Role |
|-------|------|
| `admin_audit_log` | Trace des actions admin destructrices |
| `crawl_logs` | Logs de crawl playlists |

### 4.2 Conventions DB

- `catalog` est le **seul hub** — tout pointe dessus via `catalog_id`
- Dedup via `normalized_key` (artist|title normalise) ou `isrc`
- `has_artwork` = fichier existe dans MinIO (jamais d'URL externe en DB)
- Timestamps : `TIMESTAMPTZ` (UTC)
- Durees : millisecondes (integer)
- Sentinel : `deezer_id = "NOT_FOUND"` pour artistes confirmes absents de Deezer
- FK `ON DELETE SET NULL` sur les refs catalog, `ON DELETE CASCADE` sur les tables enfant

### 4.3 Taxonomie Genres

Systeme de genres en **graphe** (pas arbre plat) :
- `genre_nodes` : noeuds avec `wikidata_id` (ex: Q20502 → "Tech House")
- `genre_edges` : aretes orientees (subgenre → parent)
- `genre_mappings` : mapping raw string ("tech-house", "TECH HOUSE") → noeud normalise
- Classification automatique via Celery task `reclassify_all_genres`
- Familles visuelles : House, Techno, Trance, D&B, Hardcore, Hard Dance, Autre

---

## 5. Fonctionnalites Livrees

### 5.1 Core — Bibliotheque

- **Import Rekordbox** : drag-and-drop XML depuis l'interface web, traitement async via Celery, barre de progression, anti-doublon (Redis lock)
- **Catalogue master** : browse/filtre/tri sur ~5200 tracks, recherche textuelle, filtres genre/BPM/key/source
- **Vue "In Lib"** : filtre sur la bibliotheque personnelle (~600 tracks Rekordbox)
- **Detail track** : hero, StatStrip, blocs relationnels ("Detecte dans X playlists", "Du meme artiste", "Apparait dans X sets")
- **Audio player** : preview Deezer 30s integre, barre de lecture persistante

### 5.2 Radar — Decouverte

- **Playlists surveillees** : 29 playlists (Deezer, TIDAL, Spotify) crawlees quotidiennement
- **Radar tracks** : ~5000 tracks decouvertes, avec date de detection, source, playlist d'origine
- **Tendances** : score de tendance calcule quotidiennement (half-life decay, detection_count)
- **Avis** : like/dislike sur les tracks radar pour tracker les preferences
- **Etat per-user** : suivi vu/pas vu par utilisateur

### 5.3 Artistes

- **Referentiel** : ~2700 artistes, 99% lies a Deezer (artwork, bio)
- **Multi-artiste** : table `catalog_artists` (many-to-many avec role + position) — ~7200 liens
- **Detail artiste** : hero banner, stats, grille tracks (catalog + lib), sets, genres
- **Admin workflow** : flags artistes ambigus, resolution (split/merge), liaison Deezer manuelle, aliases

### 5.4 Sets DJ

- **27 sets** importes (TrackID.net + manuels)
- **Tracklists** : ~428 tracks avec position, anneau % identification
- **Sets suivis** : crawl quotidien des sets suivis
- **Detail set** : hero, anneau global, tracklist, stats

### 5.5 Genres

- **Taxonomie graph** : basee sur Wikidata, noeuds + aretes + mappings
- **Classification auto** : Celery task reclassifie les tracks par genre
- **Grille cartes riches** : collage 4 covers, stats (tracks, artistes, BPM range, in lib count)
- **Detail genre** : hero mosaique, StatStrip, shelves artistes/sets/playlists, tracks completes, genres voisins (indice Jaccard)
- **Familles** : chips filtre par famille (House, Techno, Trance, D&B, etc.)

### 5.6 Hub / Recherche

- **Page d'accueil vitrine** : sections highlights (derniers ajouts, tendances, sets recents)
- **Recherche universelle** : multi-entites (tracks, artistes, sets, genres), scope configurable
- **Gating visiteur** : cap 6 resultats pour non-connectes

### 5.7 Collections

- **CRUD collections** : creer, renommer, supprimer des collections personnalisees
- **Ajouter/retirer** des tracks dans les collections
- **API complete** : 6 endpoints (router `collections.py`)
- Tables en place : `user_collections`, `collection_items`

### 5.8 Admin

- **Panel admin** (`/admin`, 1725 LOC) — la plus grosse vue
- **Sync artistes** : extraction auto depuis le catalogue, dedup, liaison Deezer
- **Flags artistes** : workflow resolution (split multi-artistes, merge doublons)
- **Liaison Deezer manuelle** : renomme avec nom officiel + cree alias + merge si doublon
- **Genres admin** : rename, merge, auto-classify
- **Audit log** : tracabilite des actions destructrices
- **Watchlist admin** : ajout/suppression playlists, trigger crawl manuel

### 5.9 Securite

- **Auth** : Google OAuth uniquement (plus de login email/password)
- **JWT** : tokens signes, intercepteur 401 cote frontend
- **Rate limiting** : par IP et par endpoint (login, OAuth callback, API)
- **CSP headers** : Content-Security-Policy strict dans Nginx
- **MinIO console bloquee** : `/minio/` retourne 403
- **Backups chiffres** : `pg_dump | gzip | gpg` quotidien
- **Git history clean** : `.env` scrub de l'historique
- **Admin guard** : `require_admin` dependency sur toutes les routes sensibles

### 5.10 Qualite

- **549 tests** (pytest + vitest)
- **Linting** : ESLint (frontend) + Ruff (Python)
- **Coverage** : tracking via pytest-cov (seuil 55%)
- **CI PostgreSQL** : tests sur PG reel en CI
- **Structured logging** : `python-json-logger` pour logs JSON
- **Prettier** : formatage frontend

---

## 6. MinIO — Stockage Artworks

| Bucket | Contenu | Format cle |
|--------|---------|------------|
| `artworks` | Covers bibliotheque utilisateur | `{track_id}.jpg` |
| `catalog-artworks` | Covers catalogue master | `{catalog_id}.jpg` |
| `artist-artworks` | Photos artistes | `{artist_id}.jpg` |
| `import-jobs` | Fichiers XML temporaires (import Rekordbox) | `{user_id}/{task_id}.xml` |

URLs servies via Nginx : `/storage/{bucket}/{file}` → proxy MinIO.

---

## 7. Design System

- **Direction artistique** : "Wildflower" — dark mode par defaut, accents colores par famille genre
- **Tokens** : fichier unique `diggy-tokens.css`, zero couleur hardcodee dans le code
- **Familles couleur** : chaque famille genre a une hue dediee (House=jaune, Techno=violet, etc.)
- **Tokens speciaux** : `--neg` (terracotta, negatif), `--warn` (ambre), `--accent` (principal)
- **Composants kit** : PageHero, SearchBox, SegFilter, FamilyChips, StatStrip, AdminCard, RingPct, SkeletonGrid, etc.
- **Pages detail** : toutes suivent le pattern Hero → StatStrip → Blocs relationnels → Contenu principal
- **Responsive** : desktop uniquement actuellement (pas de support mobile)

---

## 8. Roadmap — Etat au 2 juillet 2026

### 8.1 Chantiers termines (12/15)

| # | Chantier | Description |
|---|----------|-------------|
| S1 | Securite & Hardening | Git scrub, backups chiffres, rate limit, CSP, MinIO bloque |
| S2 | Qualite & CI Pipeline | Ruff, pytest-cov, PG en CI, vitest frontend, prettier |
| A1 | Service Layer Backend | 6 services extraits des routers (artist, catalog, genre, radar, image, rekordbox) |
| A2 | Refactor Workers | `tasks.py` monolithique scinde en 7 modules |
| A3 | Frontend Perf & Accessibilite | Lazy loading routes, composables extraits, aria-labels |
| D1 | FIX Design immediats | Tokens neg/warn, fixes sets, couleurs hardcodees, player round 2 |
| D2 | Genres — Refonte complete | Backend enrichi + frontend cartes riches + detail genre + voisins |
| D3 | Hub / Search | Page vitrine + recherche universelle multi-entites |
| D4 | Pages Detail (Vague 3) | Track, Artist, Set, Playlist detail — refonte complete DA Wildflower |
| D5 | Refactor Composants partages | Kit composants (PageHero, SearchBox, SegFilter, etc.) |
| F4 | Import Rekordbox Web | Drag-and-drop XML, traitement async Celery, progression |
| — | Multi-User Phases 0-4 | Comptes, auth Google, tracks per-user, radar per-user, opinions |

### 8.2 Chantiers restants

#### R1 — Responsive / Support Mobile (HAUTE priorite)

**Estimation : 3-4 jours**

L'app est inutilisable sur telephone. Sidebar deborde, tables illisibles, interactions tactiles pas pensees.

Taches prevues :
- Sidebar → bottom nav en dessous de 640px (`BottomNav.vue`)
- Tables : masquer colonnes secondaires (BPM, Key, Duree, Rating) sur mobile
- Modales : full-screen sheet sur mobile
- Filtres/chips : scroll horizontal
- Player : ajuster position avec bottom nav
- Cibles tactiles : `min-height: 44px` sur tous les boutons
- Verifier chaque vue sur 375px (iPhone SE)

#### F2 — Multi-User Phases 5-7 (BASSE priorite)

Utile uniquement quand un 2e utilisateur actif rejoint Diggy.

**Phase 5 — Trends + Collections** (partiellement fait)
- Tables `radar_trends`, `user_collections`, `collection_items` : **deja en place**
- Task `compute_trends` : **deja active** (cron 7h)
- API CRUD collections : **deja live** (6 endpoints)
- Frontend CollectionsView : **a faire** (pas de vue dediee encore)
- Recommandation intelligente : **pas prevu** — trends = simple popularite temporelle

**Phase 6 — Auth obligatoire** (pas pertinent en solo)
- Forcer auth sur tous les endpoints (sauf `/api/auth/*`, `/api/health`)
- Migrer `get_current_user_optional` → `get_current_user` partout

**Phase 7 — Import multi-user** (pas pertinent en solo)
- Import Rekordbox scope par user
- Gestion `scope='private'` + reconciliation ISRC
- Promotion `private → shared`

**Verdict** : Phase 5 est deja a ~70% faite cote backend. Phases 6-7 inutiles tant qu'on est seul.

#### F3 — Graphe Artistes (BASSE priorite, exploratoire)

**Estimation : 5-7 jours**

Visualiser les connexions entre artistes via :
- Sets communs (deja dans `set_artists`)
- Feats / collabs (deja dans `catalog_artists` avec role + position)
- Playlists partagees (calculable depuis `radar_tracks`)

Taches :
- Endpoint `/api/artists/:id/connections` avec poids de connexion
- Composant GraphView (D3.js force-directed ou vue-flow)
- Integration depuis la page Artist Detail
- Potentiellement : base pour un moteur de recommandation (artistes similaires → tracks a decouvrir)

#### F1 — Monitoring (REPORTE, long terme)

Sentry DSN a configurer, Flower pour Celery, UptimeRobot, pg_stat_statements. A faire quand le projet grandit.

### 8.3 Points ouverts / decisions

| Point | Contexte |
|-------|----------|
| R1 vs F3 en priorite | R1 (mobile) = fondamental manquant, surtout si les amis utilisent sur telephone. F3 (graphe) = feature exploratoire cool. A trancher. |
| F2 redefinition | Phases 6-7 deviennent pertinentes avec l'ouverture aux amis (auth obligatoire, import multi-user). Phase 5 deja a ~70%. Fusionner F3 + recommandation ? |
| Frontend build prod | Vite dev server en prod — passer a un build statique (nginx serve) |
| Admin panel refonte | AdminView = 1725 LOC, pas de brief designer pour la DA Wildflower |
| Ouverture amis | Prevu bientot (5-10 amis DJs). Impacte : responsive mobile (ils seront sur telephone), F2 phases 6-7 (auth, privacy, import per-user), onboarding (comment un nouvel utilisateur decouvre l'app) |

---

## 9. Dependances Cles

### Backend (Python)

```
fastapi==0.115.0        uvicorn==0.32.0
sqlalchemy==2.0.36      asyncpg==0.30.0
celery==5.4.0           redis==5.2.0
pydantic==2.10.0        alembic==1.14.0
boto3==1.35.0           httpx==0.27.0
tidalapi==0.8.11        spotifyscraper==3.7.0
sentry-sdk==2.29.1      python-json-logger==3.3.0
python-jose==3.3.0      google-auth>=2.0
curl_cffi==0.7.4        psycopg2-binary==2.9.10
```

### Frontend (npm)

```
vue@3  vue-router  pinia  axios
---
devDeps: vite, vitest, @vue/test-utils, eslint, prettier, rollup-plugin-visualizer
```

---

## 10. Points Forts & Points Faibles

### Forces

- **Architecture propre** : separation routers/services/workers, modeles centralises
- **CI/CD solide** : lint + tests + deploy automatique sur push master
- **549 tests** avec PG reel en CI
- **Design system coherent** : tokens centralises, zero hardcode, kit composants
- **Multi-source** : Deezer + TIDAL + Spotify pour le radar
- **Taxonomie genres avancee** : graph Wikidata, classification auto, familles colorees
- **Import Rekordbox moderne** : web-based, async, progression

### Faiblesses / Dette technique

- **Pas de responsive mobile** — l'app est desktop-only
- **Frontend en dev server en prod** — pas de build statique optimise
- **AdminView monolithique** (1725 LOC) — pas encore refactorise
- **Pas de monitoring actif** — Sentry integre mais DSN pas configure
- **1 seul utilisateur** — infrastructure multi-user partiellement en place mais pas testee en reel
- **Pas de PWA / offline** — aucun service worker
- **SearchBox (search.py) = 408 LOC** — router search assez lourd
- **Pas de websocket** — polling pour la progression import (toutes les 2s)
- **Tests frontend limites** (~15 tests Vitest) — surtout stores, pas de tests composants

---

## 11. Donnees Volumetriques

| Metrique | Valeur |
|----------|--------|
| Tracks catalogue | ~5 200+ |
| Tracks bibliotheque | ~600 |
| Tracks radar | ~5 000+ |
| Artistes | ~2 700 |
| Liens catalog-artistes | ~7 200 |
| Sets DJ | ~27 |
| Tracks dans sets | ~428 |
| Playlists surveillees | ~29 |
| Genres (noeuds) | ~26 |
| Commits git | 416 |
| Migrations Alembic | 25 |

---

## 12. Arborescence Resumee

```
diggy/
├── .github/workflows/deploy.yml          # CI/CD pipeline
├── _design/                              # Briefs et handoffs designer
├── docs/
│   ├── ROADMAP.md                        # Roadmap active
│   ├── completed/                        # Roadmaps archivees (4 fichiers)
│   ├── database-schema.md               # Schema DB documente
│   └── prompts/                          # Prompts de reference
├── server/
│   ├── api/
│   │   ├── main.py                       # FastAPI entrypoint
│   │   ├── models.py                     # 25 modeles SQLAlchemy
│   │   ├── dependencies.py               # Auth deps
│   │   ├── rate_limit.py                 # Rate limiting
│   │   ├── deezer_enrich.py              # Enrichissement Deezer
│   │   ├── routers/                      # 16 routers (93 endpoints)
│   │   ├── services/                     # 6 services metier
│   │   ├── alembic/versions/             # 25 migrations
│   │   └── trackid/                      # Import TrackID.net
│   ├── workers/
│   │   ├── celery_app.py                 # Config Celery + beat schedule
│   │   ├── source_clients.py             # Abstraction multi-source
│   │   └── tasks/                        # 7 modules de taches
│   ├── frontend/
│   │   └── src/
│   │       ├── views/                    # 14 vues
│   │       ├── components/               # 25 composants
│   │       ├── composables/              # 3 composables
│   │       ├── stores/                   # 3 stores Pinia
│   │       ├── styles/                   # Tokens + style map
│   │       ├── utils/                    # api.js, format.js
│   │       └── assets/                   # buttons.css, table.css
│   ├── nginx/default.conf                # Config Nginx
│   └── scripts/                          # Scripts utilitaires
├── tests/
│   ├── api/                              # ~330 tests API
│   ├── worker/                           # ~101 tests workers
│   ├── deezer/                           # ~22 tests Deezer
│   └── frontend/                         # ~15 tests Vitest
├── docker-compose.yml                    # 10 services
├── CLAUDE.md                             # Instructions projet pour Claude Code
└── pyproject.toml                        # Config Ruff
```
