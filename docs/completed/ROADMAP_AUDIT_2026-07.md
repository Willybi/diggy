# Diggy — Roadmap Audit (Juillet 2026)

> Audit CTO complet du projet Diggy.
> Chaque chantier est autonome et peut etre confie a une equipe de dev independante.
> Les dependances inter-chantiers sont explicites.

---

## Scores de l'audit

| Domaine | Score | Commentaire |
|---------|-------|-------------|
| Architecture backend | 7/10 | Solide base async, mais routers trop gros, pas de service layer |
| Frontend | 8/10 | Excellent design system, stores propres, zero hardcoded colors |
| Infrastructure | 7/10 | Docker bien configure, SSL OK, mais failles securite critiques |
| Qualite / Tests | 6/10 | 430+ tests mais zero coverage tracking, zero linting Python, zero TypeScript |
| Design alignment | 6/10 | ~60% des handoffs implementes, 40% en attente |
| Securite | 5/10 | Secrets exposes dans git history, rate limiting incomplet, backups non chiffres |

**Score global : 6.5/10** — Fondations solides, dette technique a adresser avant scaling.

---

## Vue d'ensemble des chantiers

```
                     CRITIQUE (Sprint 1)
  =====================================================
  S1  Securite & Secrets Rotation     ░░░░░░  URGENT
  S2  Qualite & CI Pipeline           ░░░░░░  URGENT

                     ARCHITECTURE (Sprint 2-3)
  =====================================================
  A1  Service Layer Backend            ░░░░░░  HAUT
  A2  Refactor Workers                 ░░░░░░  HAUT
  A3  Frontend Code Splitting + Perf   ░░░░░░  MOYEN

                     DESIGN (Sprint 3-4)
  =====================================================
  D1  FIX Design immediats            ░░░░░░  HAUT
  D2  Genres — Refonte complete        ░░░░░░  HAUT
  D3  Hub / Search — Implementation    ░░░░░░  MOYEN
  D4  Pages Detail (Vague 3)           ░░░░░░  MOYEN
  D5  Refactor Composants partages     ░░░░░░  MOYEN

                     FONCTIONNEL (Sprint 4-5)
  =====================================================
  F1  Multi-User Phases 5-7            ░░░░░░  BACKLOG
  F2  Monitoring & Observabilite       ░░░░░░  BACKLOG
  F3  Graphe artistes                  ░░░░░░  BACKLOG
```

### Dependances

```
S1 (secrets) ──────────> Tout le reste (prerequis deploiement serein)
S2 (CI pipeline) ─────> A1, A2 (refactors securises par tests + linting)
A1 (service layer) ───> D2, D3 (endpoints genres/search dependant de services)
D1 (FIX immediats) ───> D2, D4, D5 (base propre avant refonte)
D5 (composants) ──────> D2, D3, D4 (kit reutilisable)
```

---

## S1 — Securite & Secrets Rotation

**Equipe : Platform / DevOps**
**Priorite : CRITIQUE — Semaine 1**
**Estimation : 1-2 jours**

### Contexte

L'audit revele que le fichier `.env` a ete committe dans l'historique git avec des credentials reels.
Meme si `.env` est maintenant dans `.gitignore`, l'historique contient les secrets en clair.
Plusieurs autres failles de securite doivent etre corrigees immediatement.

### Taches

#### Critique (Jour 1)

- [ ] **Rotation de TOUS les secrets** : DB password, MinIO credentials, JWT secret, Google OAuth secret
  - Generer de nouveaux secrets forts (32+ caracteres)
  - Mettre a jour `.env` sur le VPS uniquement
  - Verifier que l'app redemarre correctement
- [ ] **Scrub git history** : `git-filter-repo --path .env` pour supprimer les anciennes versions
  - Force push apres nettoyage
  - Informer tous les contributeurs de re-cloner
- [ ] **Chiffrer les backups** : ajouter `gpg -c` dans `server/scripts/backup.sh`
  - Cle de chiffrement dans `.env` VPS
  - Verifier restore avec dechiffrement

#### Haut (Jour 2)

- [ ] **Rate limiting OAuth callback** : ajouter `/api/auth/google/callback` dans `rate_limit.py` (5/min)
- [ ] **Restreindre MinIO console** : bloquer `/minio/` dans Nginx (ou whitelist IP admin)
- [ ] **Automatiser certbot renewal** : ajouter hook post-renewal dans `docker-compose.ssl.yml`
  ```yaml
  certbot:
    entrypoint: "/bin/sh -c 'trap exit TERM; while :; do certbot renew --deploy-hook \"nginx -s reload\" && sleep 12h; done'"
  ```
- [ ] **Ajouter CSP header** dans Nginx : `Content-Security-Policy: default-src 'self'; ...`

#### Moyen

- [ ] **Beat schedule persistant** : volume nomme pour `/tmp/celerybeat-schedule`
- [ ] **Connection pool SQLAlchemy** : configurer `pool_size=10`, `pool_pre_ping=True`, `max_overflow=5`
- [ ] **Audit logging admin** : table `admin_audit_log` pour tracer les actions destructrices (merge artistes, delete, etc.)

### Definition of Done

```bash
# Anciens secrets ne fonctionnent plus
curl -H "Authorization: Bearer <OLD_JWT>" /api/auth/me → 401

# Git history propre
git log --all --full-history -- ".env" → vide

# Backups chiffres
file /backups/postgres/*.sql.gz → "GPG symmetrically encrypted data"

# MinIO console bloquee
curl https://diggy-music.fr/minio/ → 403 ou redirect
```

---

## S2 — Qualite & CI Pipeline

**Equipe : Platform / QA**
**Priorite : CRITIQUE — Semaine 1-2**
**Estimation : 2-3 jours**

### Contexte

Le projet a 430+ tests mais aucun tracking de couverture, aucun linting Python dans la CI,
aucun type checking. Le frontend est en JavaScript sans TypeScript.
Ces lacunes empechent de refactorer en confiance.

### Taches

#### Critique

- [ ] **Ajouter ruff dans CI** : linting + formatting Python
  ```toml
  # pyproject.toml
  [tool.ruff]
  line-length = 88
  target-version = "py313"
  select = ["E", "F", "W", "I"]
  ```
  - Job CI : `ruff check server/`
  - Corriger les erreurs existantes (batch initial)

- [ ] **Ajouter pytest-cov** : tracking de couverture
  ```bash
  pytest tests/ --cov=server --cov-report=xml --cov-report=term-missing
  ```
  - Seuil minimum : 60% global (actuel estime ~50-55%)
  - Publier rapport dans CI artifacts

- [ ] **Reactiver PostgreSQL dans CI** : decommenter le service PG dans `deploy.yml`
  - Tests CI avec `DATABASE_URL=postgresql+asyncpg://...`
  - Accepter le surcout (~3min vs ~1min) pour fiabilite

#### Haut

- [ ] **Ajouter pip-audit** : scan de vulnerabilites dependances Python
  - Job CI : `pip-audit --desc` (warning, pas bloquant au debut)

- [ ] **Ajouter Prettier** : formatting frontend coherent
  - `.prettierrc` + pre-commit hook
  - Integration avec ESLint

- [ ] **Tests frontend basiques** : installer vitest + @vue/test-utils
  - Tester les 3 stores Pinia (auth, audioPlayer, opinions)
  - Tester les utils (api.js, format helpers)
  - Objectif : 10-15 tests unitaires frontend minimum

#### Moyen

- [ ] **Structured logging Python** : `structlog` ou `python-json-logger`
  - Logs JSON pour Sentry/ELK
  - Request ID dans chaque log

- [ ] **Coverage badge README** : afficher le % de couverture

### Definition of Done

```bash
# Ruff passe sans erreur
ruff check server/ → All checks passed

# Coverage visible
pytest --cov → Coverage: 60%+ with report

# CI PostgreSQL active
# deploy.yml services block uncommented → tests pass on PG

# Frontend tests
cd server/frontend && npx vitest run → 10+ tests passed
```

---

## A1 — Service Layer Backend

**Equipe : Backend**
**Priorite : HAUT — Sprint 2**
**Estimation : 5-7 jours**

### Contexte

Les routers FastAPI contiennent trop de logique metier. `admin.py` fait 725 LOC,
`catalog.py` 591 LOC, `genres.py` 703 LOC. Les queries SQL sont complexes (10+ subqueries
imbriquees dans `list_catalog()`). Ce melange rend le code difficile a tester et a maintenir.

L'objectif est d'extraire la logique dans un service layer testable.

### Perimetre

| Router actuel | LOC | Service(s) a creer |
|---------------|-----|--------------------|
| `admin.py` | 725 | `ArtistService`, `FlagService`, `EnrichmentService` |
| `catalog.py` | 591 | `CatalogService` (queries complexes) |
| `genres.py` | 703 | `GenreService` (hierarchie, classification) |
| `artists.py` | 412 | `ArtistService` (stats, queries) |
| `radar.py` | 374 | `RadarService` (enriched listing) |
| `deezer_enrich.py` | 328 | `SearchService`, `ImageService` |

### Taches

- [ ] **Creer `server/api/services/`** : nouveau dossier pour la logique metier
- [ ] **Extraire `ArtistService`** depuis admin.py + artists.py :
  - `sync_artists()`, `resolve_flag()`, `link_artists_to_catalog()`, `merge_artists()`
  - `get_artist_stats()`, `list_artists_with_stats()`
- [ ] **Extraire `CatalogService`** depuis catalog.py :
  - `list_catalog()` avec ses 10 subqueries → methode unique testable
  - `get_catalog_detail()` avec blocs relationnels
- [ ] **Extraire `GenreService`** depuis genres.py :
  - `get_genre_hierarchy()`, `classify_tracks()`, `get_genre_stats()`
- [ ] **Extraire `ImageService`** : unifier `deezer_enrich._get_s3()` + `storage._get_s3()`
  - Un seul client S3 partage, plus de duplication
- [ ] **Refactorer routers** : chaque endpoint = 10-20 LOC max (validation + appel service + response)
- [ ] **Tests unitaires services** : 30+ tests pour les services extraits
  - Tester la logique metier independamment de FastAPI

### Architecture cible

```python
# AVANT — admin.py (725 LOC, logique melangee)
@router.post("/artists/flags/{flag_id}/resolve")
async def resolve_flag(flag_id, body, db, user):
    flag = await db.execute(select(ArtistFlag)...)
    for name in names:
        artist = await get_or_create_artist(db, name)
        # ... 30+ lignes de logique

# APRES — admin.py (thin router)
@router.post("/artists/flags/{flag_id}/resolve")
async def resolve_flag(flag_id, body, db, user):
    return await artist_service.resolve_flag(db, flag_id, body.action)

# services/artist_service.py (testable, reutilisable)
class ArtistService:
    async def resolve_flag(self, db, flag_id, action):
        # Toute la logique ici — testable sans HTTP
```

### Definition of Done

```
# Aucun router ne depasse 300 LOC
wc -l server/api/routers/*.py → max 300 chacun

# Services testables
pytest tests/api/test_services/ → 30+ tests passed

# Pas de regression
pytest tests/ → meme nombre de tests qu'avant (430+)
```

---

## A2 — Refactor Workers

**Equipe : Backend / Data Pipeline**
**Priorite : HAUT — Sprint 2-3**
**Estimation : 3-5 jours**

### Contexte

`tasks.py` fait 1487 LOC avec 11 Celery tasks qui melangent orchestration, enrichissement,
et acces DB. Le code alterne sync (Celery) et async (`asyncio.run()`), ce qui complique le debug.

### Taches

- [ ] **Scinder `tasks.py`** en modules :
  - `tasks/orchestration.py` : `crawl_radar`, `crawl_single_playlist` (fan-out)
  - `tasks/enrichment.py` : `enrich_deezer_batch`, `enrich_beatport_batch`
  - `tasks/artists.py` : `sync_artists`, `fetch_artist_artworks`, `link_set_artists`
  - `tasks/genres.py` : `populate_artist_genres`
  - `tasks/sets.py` : `resolve_set_tracks`
- [ ] **Uniformiser retry policies** : verifier que toutes les tasks ont `autoretry_for`, `max_retries=3`, `retry_backoff=True`
- [ ] **Externaliser backups** : ajouter une task Celery Beat `backup_daily` au lieu du script shell manuel
- [ ] **Ajouter tests workers** : 20+ tests supplementaires pour les tasks refactorees
  - Scenarios d'echec (DB down, API timeout, lock Redis)
  - Orchestration (fan-out, DLQ)

### Definition of Done

```
# tasks.py n'existe plus comme monolithe
ls server/workers/tasks/ → orchestration.py, enrichment.py, artists.py, genres.py, sets.py

# Tests workers
pytest tests/worker/ → 70+ tests (vs 54 actuels)
```

---

## A3 — Frontend Code Splitting & Performance

**Equipe : Frontend**
**Priorite : MOYEN — Sprint 3**
**Estimation : 2-3 jours**

### Contexte

Toutes les 14 vues sont importees eagerly (pas de lazy loading). Le frontend n'a pas de
code splitting, pas d'optimisation d'images, pas d'analyse de bundle.

### Taches

- [ ] **Route-based code splitting** : `defineAsyncComponent()` sur toutes les routes
  ```javascript
  const CatalogView = () => import('./views/CatalogView.vue')
  ```
  - Gain attendu : ~20% reduction du bundle initial

- [ ] **Composable `useInfiniteScroll`** : extraire le pattern repete dans ArtistsView, GenresView
- [ ] **Composable `useDebounce`** : extraire le debounce de recherche (repete 5+ fois)
- [ ] **Analyser le bundle** : ajouter `vite-plugin-visualizer` pour identifier les gros morceaux
- [ ] **Production build frontend** : s'assurer que Docker utilise le stage `production` (nginx) et non `development` (Vite dev server)

#### Accessibilite (quick wins)

- [ ] **`aria-label`** sur tous les boutons icone (search, filters, player controls)
- [ ] **`aria-live="polite"`** sur les resultats de recherche dynamiques
- [ ] **Skip link** "Aller au contenu" en debut de page
- [ ] **Keyboard navigation** sur les chips de filtre (genre, famille)

### Definition of Done

```bash
# Bundle analyse
npx vite build --mode analyze → rapport genere

# Lazy loading actif
# Network tab : chunks separees pour chaque route

# A11y basique
# axe-core scan → 0 violations critiques
```

---

## D1 — FIX Design Immediats

**Equipe : Frontend**
**Priorite : HAUT — Sprint 2**
**Estimation : 1-2 jours**

### Contexte

Plusieurs correctifs design livres par le designer ne sont pas encore appliques.
Ce sont des quick wins qui ameliorent la coherence visuelle.

### Taches

#### Sets (4 FIX du BRIEF-sets-fix.md)

- [ ] **FIX #1** : Boutons "Importer + Suivre" — reintegrer CSS `.btn-follow` / `.btn-follow.done`
- [ ] **FIX #2** : Anneau 100% — passer de vert plein a neutre calme (check + "100%")
  - **Decision a trancher** (willi) : calme neutre vs vert
- [ ] **FIX #3** : Compteur en-tete — afficher total + sous-compte filtre
- [ ] **FIX #4** : Vocabulaire "Suivre" → actions Avis (like/dislike) pour coherence Radar

#### Tokens manquants

- [ ] **Token `--neg`** : ajouter dans `diggy-tokens.css` (hue 28 terracotta, light + dark)
  - Utilise par Radar (dislike) et Sets (anneau faible %)
- [ ] **Tokens `--warn / --warn-soft / --warn-ink`** : ajouter (hue 70 ambre)

#### Corrections ponctuelles

- [ ] **Couleurs hardcodees** : corriger `#fff` dans HubView.vue (ligne ~696) → `var(--on-accent)`
- [ ] **Badge overlays ArtistCard** : extraire `oklch(...)` hardcodes vers tokens
- [ ] **Player round 2** : appliquer les 5 correctifs de `PROMPT-claude-code-player-round2.md`
  - Icone pause sur la ligne active
  - Gestion erreurs preview manquante
  - Token `--sidebar-w`

### Definition of Done

```
# Zero couleur hardcodee hors Google logo
grep -r "#[0-9a-fA-F]\{3,6\}" src/ --include="*.vue" → seulement LoginView (Google branding)

# Tokens neg/warn presents
grep "neg-ink\|warn-ink" src/styles/diggy-tokens.css → present light + dark
```

---

## D2 — Genres : Refonte Complete

**Equipe : Fullstack (Backend + Frontend)**
**Priorite : HAUT — Sprint 3**
**Estimation : 5-7 jours**
**Depend de : A1 (GenreService), D1 (tokens), D5 (composants partages)**

### Contexte

Le designer a livre une maquette complete pour `/genres` (grille de cartes riches avec
collage 2x2 covers, stats, chips famille) et `/style/:genre` (shelves horizontales,
genres voisins). Le code actuel est une grille plate simpliste qui ne suit pas le design.

### Taches Backend

- [ ] **Endpoint `/api/genres` enrichi** : retourner pour chaque genre :
  - `trackCount`, `artistCount`, `bpmLo` (p5), `bpmHi` (p95), `inLibCount`
  - `covers[]` (4 URLs artwork pour collage 2x2)
  - `topArtists[]` (3 artistes avec photo)
  - Pagination serveur + tri (tracks desc, A-Z) + filtre famille + recherche
- [ ] **Genres voisins** : concevoir la metrique de proximite
  - Approche proposee : artistes en commun (`|artists(genreA) ∩ artists(genreB)| / |artists(genreA) ∪ artists(genreB)|`)
  - Endpoint : `GET /api/genres/:name/neighbors?limit=6`
- [ ] **Admin endpoints** : `PATCH /api/genres/:name` (rename), `POST /api/genres/merge` (fusion)

### Taches Frontend

- [ ] **Refonte `GenresView`** : grille de cartes riches (auto-fill, minmax 220px)
  - Collage 2x2 covers (fallback teinte famille)
  - Stats : Tracks, Artistes, BPM range, In lib badge
  - Chips famille : Tous / House / Techno / Trance / Autre (avec compteurs)
  - Search + tri + scroll infini (IntersectionObserver)
- [ ] **Refonte `GenreDetailView`** : layout shelves
  - Hero mosaique 3x2 covers + avatars top artistes
  - Shelves horizontales : Artistes, Sets, Playlists (scroll)
  - Tracks : liste complete (play, cover, titre, BPM, Key, duree, lib toggle)
  - Genres voisins : 6 chips avec metrique commune
  - Admin bloc : rename + merge (role-gated)

### Definition of Done

```bash
# Endpoint genres enrichi
curl /api/genres/?limit=10 → chaque genre a trackCount, covers[], topArtists[]

# Genres voisins
curl /api/genres/House/neighbors → [{name: "Tech House", score: 0.73}, ...]

# Frontend cartes riches
# Visual check : collage 2x2, stats, chips famille
```

---

## D3 — Hub / Search : Implementation

**Equipe : Fullstack**
**Priorite : MOYEN — Sprint 4**
**Estimation : 3-5 jours**
**Depend de : A1 (SearchService)**

### Contexte

Le designer a livre 3 directions (Spotlight, Command palette, Vitrine).
Le choix de direction doit etre tranche par willi avant implementation.
Un endpoint `/api/search` unifie multi-entites est necessaire.

### Decisions a trancher (willi)

- [ ] Direction A (Spotlight), B (Command palette), ou C (Vitrine) ?
- [ ] `GUEST_CAP` pour visiteurs non connectes (maquette = 6 resultats) ?
- [ ] Apercu artiste dans resultats (top track ou desactive) ?

### Taches Backend

- [ ] **Endpoint `/api/search`** unifie :
  - `?q=&scope=all|tracks|artists|sets|genres&limit=20&cursor=`
  - Recherche multi-entites triee par pertinence
  - Public (non-auth) avec cap visiteur configurable
  - Surlignage terme recherche dans la reponse

### Taches Frontend

- [ ] **Implementer HubView** selon la direction choisie
  - Resultats types : track, artist, set, playlist, genre (badges + icones)
  - Gating visiteur vs connecte
  - Lien genre = nom brut URL-encode

---

## D4 — Pages Detail (Vague 3)

**Equipe : Frontend**
**Priorite : MOYEN — Sprint 4-5**
**Estimation : 5-7 jours**
**Depend de : D5 (composants partages)**

### Contexte

Les pages detail (Track, Artist, Set, Playlist) existent en code mais ne suivent pas
la DA Wildflower. Le designer n'a pas encore livre de brief specifique pour Track/Playlist detail
(vague 3 de la roadmap realign). Les FIX rounds 3-4 sont partiellement appliques.

### Taches

- [ ] **Verifier FIX appliques** sur Artist Detail et Set Detail :
  - `artist.name` affiche le nom brut (pas le slug)
  - MiniTrackTable implementee (colonnes style, BPM, key, rating)
  - Bouton source en `btn-ghost` (pas accent)
  - Titre long clamp
  - LibDot fusionne (pas 2 colonnes Statut+Lib)
- [ ] **Track Detail** : implementer quand brief designer livre
  - Hero + StatStrip + 3 blocs relationnels + bloc admin
- [ ] **Playlist Detail** : implementer quand brief designer livre
  - Hero square + StatStrip + table tracks
- [ ] **Artist Detail** : verifier coherence avec maquette Artistes v2
- [ ] **Set Detail** : verifier coherence avec BRIEF-sets-fix

---

## D5 — Refactor Composants Partages

**Equipe : Frontend**
**Priorite : MOYEN — Sprint 3**
**Estimation : 3-4 jours**

### Contexte

L'audit du designer (REFACTOR-audit.md) identifie 12 clusters de composants a extraire
depuis les vues specifiques vers un kit partage. Plusieurs composants sont dupliques
ou implementes inline.

### Taches (par lot du REFACTOR-audit)

#### Lot A — Fondations (tokens + utils)

- [ ] **`utils/format.js`** : `fmtNum()`, `pl()`, formateurs communs
- [ ] **Purger `var(--x, #hex)`** : tout en tokens, zero fallback hex

#### Lot B — Composants structurels

- [ ] **`PageHeader`** : titre + sous-titre + compteur (remplace les headers dupliques)
- [ ] **`SearchBox`** : input recherche avec debounce + clear
- [ ] **`SegFilter`** : filtre segmente (onglets toggle)
- [ ] **`FamilyChips`** : chips de selection famille genre

#### Lot C — Composants metier

- [ ] **`AdminCard`** + `AdminInput` : unifies avec style D2 (surface-2 + dashed --line-2)
- [ ] **`SourceBadge`** : badge source (Deezer/TIDAL/Spotify) — extractible de WatchlistView
- [ ] **`RingPct`** : anneau pourcentage (donut SVG + pill) — extractible de SetsView
- [ ] **`SkeletonGrid`** : placeholder chargement

#### Lot D — Patterns

- [ ] **`useInfiniteScroll`** composable : sentinel + IntersectionObserver
- [ ] **`assets/table.css`** : styles table partages (header mono, hover, tri)
- [ ] **`assets/buttons.css`** : styles boutons partages (verifier existant)

---

## F1 — Multi-User Phases 5-7

**Equipe : Backend + Frontend**
**Priorite : BACKLOG — Sprint 5+**
**Estimation : 7-10 jours**

### Contexte

Les phases 0-4 multi-user sont terminees. Restent les phases 5 (trends + collections),
6 (enforcement auth complet), 7 (import multi-user).
Voir `docs/completed/ROADMAP_MULTIUSER.md` pour le detail.

### Taches

- [ ] **Phase 5** : tables `radar_trends`, `user_collections`, `collection_items`
  - Celery task `compute_trends` (decroissance half-life 14j)
  - CRUD collections API + frontend
- [ ] **Phase 6** : middleware auth obligatoire backend (tous endpoints sauf public)
  - Migrer `get_current_user_optional` → `get_current_user` la ou justifie
- [ ] **Phase 7** : endpoint `POST /api/import/rekordbox` scope au current_user
  - Gestion `scope='private'` + reconciliation ISRC
  - Promotion `private → shared`

---

## F2 — Monitoring & Observabilite

**Equipe : Platform**
**Priorite : BACKLOG — Sprint 5+**
**Estimation : 3-5 jours**

### Contexte

Sentry est integre (lazy-import) mais pas configure en prod.
Aucun monitoring de queue Celery, pas de metriques, pas d'alertes.

### Taches

- [ ] **Sentry production** : configurer `SENTRY_DSN` dans `.env` VPS
- [ ] **Celery Flower** : ajouter service Docker pour monitoring tasks
- [ ] **UptimeRobot** : check HTTP sur `/api/health` toutes les 5 min
- [ ] **pg_stat_statements** : activer pour slow queries
- [ ] **Metriques Prometheus** (optionnel) : latence API, queue Celery, DB pool
- [ ] **Alertes** : notification si API down > 5 min ou error rate > 5%
- [ ] **Backup externe** : sync backups vers S3 externe (Scaleway, AWS) pour DR

---

## F3 — Graphe Artistes

**Equipe : Frontend + Backend**
**Priorite : BACKLOG**
**Estimation : 5-7 jours**

### Contexte

Visualisation des connexions entre artistes via sets communs, feats, playlists partagees.
Necessite L2 (multi-artiste) qui est FAIT (table `catalog_artists` en place).

### Taches

- [ ] **Endpoint `/api/artists/:id/connections`** : artistes connectes + poids
- [ ] **Composant GraphView** : D3.js ou vue-flow
- [ ] **Integration** : accessible depuis la page artiste

---

## Annexe A — Tableau recapitulatif Design Handoffs

| Handoff | Livre designer | Implemente | Manque |
|---------|---------------|------------|--------|
| Player | DA + Brief | Oui | 5 correctifs round 2 |
| Catalog | DA + Brief + FIX | Oui | Bug Unicode, genres normalises |
| Radar | DA + Brief | Oui | Token `--neg`, wording confirme |
| Sets | DA + Brief | Partiel | 4 FIX graves (CSS, anneau, compteur, avis) |
| Genres | DA + Brief | Non | Cartes riches, API agregats, scroll infini |
| Artistes | DA + Brief v2 | Oui | Tri poids genres backend |
| Genre Detail | DA + Brief + 2 FIX | Partiel | Layout shelves, voisins, playlist artwork |
| Hub / Search | DA + Brief (3 dir) | Non | Direction a trancher, API unifie |
| Refactor Kit | Audit complet | Partiel | 12 composants, styles, helpers |
| Couleurs v2 | DA + Spec | Oui | OK |
| Cards v2 | DA + Brief | Partiel | Artist mosaique covers + voile |
| Track Detail | Non (vague 3) | Non | Brief a livrer |
| Playlist Detail | Non (vague 3) | Non | Brief a livrer |

---

## Annexe B — Checklist securite

| Item | Statut | Chantier |
|------|--------|----------|
| Secrets dans git history | A FAIRE | S1 |
| Rotation secrets | A FAIRE | S1 |
| Backups chiffres | A FAIRE | S1 |
| Rate limit OAuth callback | A FAIRE | S1 |
| MinIO console restreinte | A FAIRE | S1 |
| Certbot auto-renewal | A FAIRE | S1 |
| CSP headers | A FAIRE | S1 |
| Connection pool DB | A FAIRE | S1 |
| Audit logging admin | A FAIRE | S1 |
| Linting Python CI | A FAIRE | S2 |
| Coverage tracking | A FAIRE | S2 |
| PostgreSQL CI tests | A FAIRE | S2 |
| Scan vulnerabilites deps | A FAIRE | S2 |

---

## Annexe C — Decisions a trancher (willi)

Ces points necessitent une decision produit avant que les equipes puissent avancer :

1. **Sets : anneau 100%** — calme neutre ou vert ? (D1 FIX #2)
2. **Hub : direction** — Spotlight (A), Command palette (B), ou Vitrine (C) ? (D3)
3. **Hub : GUEST_CAP** — combien de resultats pour visiteurs non connectes ? (D3)
4. **Radar : wording** — "Liked / Disliked" ou "Aimes / Rejetes" ? (D1)
5. **Frontend : TypeScript** — migrer progressivement ou rester JS ? (S2, long terme)

---

## Methode de travail recommandee

Chaque chantier suit le cycle :

1. **Brief** : ce document sert de brief — chaque section est autonome
2. **Execution** : l'equipe/agent execute selon le perimetre defini
3. **Review** : relecture du code, tests CI (`pytest tests/ -v`)
4. **Deploy** : `git push origin master` → GitHub Actions → SSH → rebuild
5. **Verification** : smoke tests VPS + validation visuelle
6. **Update** : cocher les taches dans ce document

**Commit naming** : `type(scope): description` (conventional commits)
Exemples : `refactor(api): extract ArtistService from admin router`, `fix(frontend): add --neg token to diggy-tokens.css`
