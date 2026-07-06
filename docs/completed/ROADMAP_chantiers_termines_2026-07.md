# Diggy — Chantiers termines (juillet 2026)

> Archive extraite de `docs/ROADMAP.md` le 2026-07-06.
> Ce fichier est FIGE : lecture seule, ne jamais modifier.

---

## C0 — Correctifs critiques & fondations data (IMMEDIAT)

**Priorite : CRITIQUE — avant tout le reste**
**Estimation : 1-2 jours**
**Depend de : rien**
**Statut : TERMINE (2026-07-02)**

### Pourquoi maintenant

Les correctifs critiques de l'audit securite, et le signal de retrait des playlists qui ne s'accumule qu'a partir de sa mise en place.

### C0.1 — Cycle de vie des detections radar

Precision importante : la velocite sur les ajouts est deja calculable retroactivement depuis `radar_tracks` (chaque paire track x playlist est datee par `detected_at`). Ce qui manque et ne se reconstitue pas : les retraits (track sorti d'une playlist) et les re-apparitions (INSERT or IGNORE, `detected_at` fige).

- [x] Ajouter `removed_at` sur `radar_tracks` + logique de diff dans le crawl : track present en base mais absent du crawl courant = retire. Re-apparitions = `removed_at` remis a NULL. Migration 0026.
- [x] Neutraliser le biais de premiere surveillance : `is_initial_detection` sur `RadarTrack`, flag base sur `last_crawled_at IS NULL` de la playlist.

Urgence moderee : seul le signal de retrait (fading) s'accumule a partir de sa mise en place, et c'est un signal secondaire pour la v1 du trend.

### C0.2 — Correctifs securite critiques (audit)

- [x] `GET /api/radar/` et `POST /api/radar/` legacy : supprimes (aucun consommateur)
- [x] `DELETE /api/radar/{id}` : protege par `require_admin`
- [x] `uid()` fallback `user_id=1` : supprime, retourne `None` pour les guests. Type `int | None` propage dans 5 services + search helpers.

### Definition of Done

```bash
# Securite
# GET /api/radar/ sans token -> 401
# DELETE /api/radar/{id} d'un autre user -> 404
# uid() sans user -> leve une exception (plus de fallback)

# Cycle de vie
# radar_tracks a un champ removed_at (migration)
# crawl_single_playlist marque les tracks absentes
```

---

## R1 — Responsive / Support Mobile

**Priorite : HAUT**
**Estimation : 3-4 jours**
**Depend de : C0 (TERMINE)**
**Statut : TERMINE (2026-07-02)**

### Contexte

Diggy est actuellement concu pour desktop (sidebar fixe, tables denses, modales larges).
Sur telephone vertical, la sidebar deborde, les tables sont illisibles, et les
interactions tactiles ne sont pas pensees. L'objectif : rendre l'app utilisable
confortablement sur mobile sans refonte de l'architecture — responsive progressif,
pas de version separee.

Breakpoints cibles :
- `< 640px` : telephone vertical (priorite principale)
- `640px-1024px` : tablette / telephone paysage (amelioration secondaire)
- `> 1024px` : desktop (comportement actuel preserve)

### Taches

#### Navigation (critique)

- [x] **Sidebar -> bottom nav sur mobile** : BottomNav sous 640px, sidebar masquee
- [x] **`BottomNav.vue`** : 5 items + Admin conditionnel, badge radar new-count, highlight accent + barre
- [x] **Token `--bottom-nav-h`** dans `diggy-tokens.css` (56px) + `--page-px-mobile` (16px) + `--touch-min` (44px)

#### Layout global

- [x] **Meta viewport** : deja present dans `index.html`
- [x] **Padding lateral mobile** : `var(--page-px-mobile)` applique dans 12 vues
- [x] **min-width fixes** : `min-width: 0` sous 640px sur tables Catalog et Sets

#### Tables (TrackTable, MiniTrackTable)

- [x] **Colonnes masquees progressivement** : 6 breakpoints (1160→560px). Sur 375px survivent : Play · Track · Key · InLib
- [x] **Scroll horizontal** : `.dt-wrap` overflow-x deja en place, min-width 0 sous 640px

#### Composants

- [x] **Modales** : plein ecran sous 640px (`@media`)
- [x] **Filtres / chips** : scroll horizontal (CatalogView head-tools wrap + SegFilter overflow-x)
- [x] **Player** : repositionne au-dessus de la BottomNav (`@media`, bottom calc)
- [x] **Cibles tactiles** : hover-only (.pbtn, .act, .ld-btn) → toujours visibles sous 640px

#### Vues prioritaires a verifier

| Vue | Probleme attendu | Fix |
|-----|-----------------|-----|
| `CatalogView` | Table trop large, filtres debordent | Colonnes masquees + filtres scroll |
| `ArtistDetailView` | Hero image + grille tracks | Grille 1 col, hero full-width |
| `SetDetailView` | Anneau + table tracks | Anneau centre, table allegee |
| `GenresView` | Grille cartes | `minmax(150px, 1fr)` |
| `HubView` | Search bar + resultats | A verifier |
| `SetsView` | Grille anneaux | Verifier wrapping |

### Definition of Done

```bash
# Visual check sur Chrome DevTools -> iPhone SE (375px)
# - Navigation bas visible et fonctionnelle
# - Aucune scrollbar horizontale sur le body
# - CatalogView lisible (titre + artiste visible)
# - Modales full-screen
# - Boutons >= 44px de hauteur
```

---

## C1 — Moteur de Trend v2 + Surface Decouverte

**Priorite : HAUT**
**Estimation : 5-7 jours**
**Depend de : R1 (TERMINE)**
**Statut : TERMINE (2026-07-02)**

### Objectif

Transformer `compute_trends` (formule actuelle : `SUM(0.5^(age/14)) x COUNT(DISTINCT playlists)`, signaux ignores : type de source, taille de playlist, release date, velocite) en un vrai classement de tendance par famille de genre, et lui donner une surface produit.

### C1.a — Formule v2 (sans velocite, sur signaux disponibles)

Calculable des maintenant sur `radar_tracks` :

- [x] Ponderation par **type de source** : set DJ = 3x, playlist = 1x
- [x] Ponderation par **taille de playlist** : `1/sqrt(track_count)`
- [x] Bonus de **convergence multi-sources** : +30% par plateforme supplementaire
- [x] **Decay temporel** : half-life 14 jours conserve
- [x] Calcul et exposition **par famille de genre** : mapping via genre_nodes/edges/mappings, rang par famille
- [x] Sortie en **rang** : `rank_global` + `rank_in_family` stockes dans `radar_trends`

Methode : prototype notebook sur les donnees reelles (~5000 radar_tracks), calibration subjective : le top 20 par famille doit correspondre a l'intuition DJ. Puis portage dans `compute_trends`.

### C1.b — Velocite (calculable des maintenant sur les ajouts)

- [x] Ratio fenetre recente / fenetre precedente : 7j vs 7j precedents, clampe 0-5
- [x] Bonus multiplicateur sur le score C1.a : `* (1 + 0.5 * velocity)`
- [x] Exclure les detections `is_initial_detection` du calcul de velocite
- ~~Le signal de retrait (fading) s'ajoutera quand `removed_at` aura de la profondeur~~ → futur (donnees insuffisantes)
- ~~Signal revival : badge distinct "revient"~~ → futur (donnees insuffisantes)

### C1.c — Surface produit "Decouvrir"

- [x] Section "Ca sort en ce moment" sur le Hub, filtrable par famille (FamilyChips)
- [x] Shelves trend en grille responsive sur le Hub
- [x] Badge trend `#N` sur les tracks top 50 dans CatalogView

### C1.d — Vue Collections (reliquat Phase 5)

- [x] `CollectionsView.vue` + `CollectionDetailView.vue` : CRUD complet, routes `/collections` et `/collections/:id`
- [x] Ajout depuis TrackDetailView (dropdown), retrait depuis CollectionDetailView
- [x] Lien "Collections" dans la sidebar, strictement prive par user

### Definition of Done

```bash
# Formule v2 operationnelle
# compute_trends integre les ponderations source/taille/convergence/famille
# Le rang par famille est expose dans l'API radar

# Surface produit
# Vue "Decouvrir" accessible depuis la nav
# Hub affiche des shelves trend par famille

# Collections
# CollectionsView CRUD fonctionnel
```

---

## P1 — Polish & Correctifs UI

**Priorite : MOYEN**
**Estimation : 1-2 jours**
**Depend de : C1 (TERMINE)**
**Statut : TERMINE (2026-07-06)**

### P1.1 — PlayerBar : navigation titre et artiste

Le titre et l'artiste dans la PlayerBar sont des `<span>` inertes. Les rendre cliquables.

- [x] Titre cliquable → `/catalog/:catalog_id`
- [x] Artiste cliquable → `/artist/:artist_id` (conditionnel, span fallback si null)
- [x] Stocker `artist_id` dans le player store lors du `play()` + mise a jour de 10 appelants

### P1.2 — Boutons Play dans TrackDetailView

Les sections "Du même artiste" et "Tracks similaires" sont des `RouterLink` sans bouton play,
contrairement aux mini-rows de ArtistDetailView qui en ont un.

- [x] Ajouter bouton play (conditionnel sur `has_preview`) dans la grille "Du même artiste"
- [x] Ajouter bouton play dans la grille "Tracks similaires"
- [x] `has_preview` ajoute a `SameArtistTrackOut` + query SQL corrigee

### P1.3 — ScorePill : refonte pour les floats

Le score radar (`trend_score_10`) peut désormais être un float. Le composant actuel
affiche `7.3/10` avec 10 barres binaires (on/off) — lisible mais pas optimal pour un continu.

- [x] Remplacer les 10 barres discretes par une barre de progression continue (`width: score * 10%`, `color-mix` pour le fond)
- [x] Arrondir l'affichage texte a 1 decimale si float, entier sinon

### P1.4 — GenreDetailView : pagination shelves artistes/playlists

Les shelves "Artistes" et "Playlists" chargent 12 items max sans possibilité d'en voir plus.
Si `artistsTotal > 12` ou `playlistsTotal > 12`, les items supplémentaires sont inaccessibles.
Audit aussi le scroll horizontal (possible conflit de container query sur mobile).

- [x] Composant `ExpandableShelf.vue` : shelf collapsed (grille auto-fill, 1 rangee) → expanded (grille wrappee + pagination interne par pages de 48)
- [x] Integre dans GenreDetailView (artistes, fetch backend pagine) et ArtistDetailView (artistes proches, pagination client)
- [x] Pagination intelligente (first/last + ±2 + ellipses), hauteur de cards uniforme (`min-height: 2.6em` sur titre)
- [x] Audit mobile : pas de probleme, grille wrap naturellement

### P1.5 — Admin : split artiste manuel sur espace

`detectSeparator()` ne reconnait que les séparateurs explicites (`/`, ` & `, `,`, `feat.`…).
Les concaténations sans séparateur type "Bad Boombox mischluft" ne sont pas détectables
automatiquement — l'espace seul est trop ambigu.

- [x] Bouton "Splitter" visible pour tous les artistes avec espaces dans AdminArtists.vue
- [x] UI : mots separes par des separateurs `·` cliquables, preview pills gauche/droite
- [x] Flow : `POST flags/manual` + auto-resolve `split` en un seul clic "Confirmer"
- [x] Edge case : nom sans espace → bouton masque

### Definition of Done

```bash
# PlayerBar : clic titre -> navigation /catalog/:id, clic artiste -> /artist/:id
# TrackDetailView : play button visible au hover sur "Du même artiste" et "Tracks similaires"
# ScorePill : barre continue, texte arrondi à 1 décimale
# GenreDetailView : "Voir plus" fonctionnel sur artistes et playlists
# Admin : split manuel disponible sur n'importe quel artiste
```

---

## C2 — Moteur de Similarite (absorbe F3)

**Priorite : MOYEN**
**Estimation : 7-10 jours**
**Depend de : C1 (TERMINE)**
**Statut : TERMINE (2026-07-06) — graphe visuel D3 reporte**

### Objectif

Relations de proximite entre tracks et entre artistes. C'est le socle de toute recommandation, il fonctionne avec ou sans user.

### Constats verifies (check SQL 02/07/2026, 7 335 entrees catalog)

- **pgvector absent** : passer l'image Docker a `pgvector/pgvector:pg16` + migration extension
- **Metadonnees saines** : BPM 91.6%, key 91.6% (100% source Beatport, mapping `beatport/enrich.py` intact), genres 95.2%, release_date 95.5%, label 95.5%. Couverture Beatport : 95% des tracks shared (6 723 / 7 076)
- **Trou identifie** : les 259 tracks `scope=private` (origin rekordbox) ont 0% d'enrichissement. Les tasks d'enrichissement excluent le scope private. Pour la similarite : negligeable en MVP (3.5% du catalog), fallback possible sur `user_tracks.rb_bpm` / `rb_key`

### C2.a — Preparation

- [x] ~~Installation pgvector~~ — non necessaire : le scoring fonctionne sans embeddings vectoriels (metadonnees + co-occurrence suffisent pour le MVP)

### C2.b — V1 metadonnees

- [x] Scoring sur les champs disponibles (genre, BPM, key, label, release era) — sans pgvector, calcul direct
- [x] Endpoint `/api/catalog/{id}/similar` -> top tracks similaires

### C2.c — V2 co-occurrence

- [x] Paires par playlist (`radar_tracks`) et par set (`set_tracks`) : co-occurrence integree au scoring
- [x] Ponderation : co-occurrence en set > co-occurrence en playlist (asymptotique calibree)

### C2.d — Bareme v2 + Graphe artistes

- [x] Refonte du scoring : bareme a 4 segments additifs sur 8 pts (sets 3, playlists 2, style 2, contexte 1), calibre par notebook sur donnees reelles (17.2M paires)
- [x] Endpoint `/api/artists/:id/connections` : collabs (`catalog_artists`), sets communs (`set_artists`), playlists partagees, genre Jaccard
- [x] Shelf "Artistes proches" sur les pages artistes (ShelfCard round, navigation inter-artistes)
- [ ] **REPORTE** : Composant GraphView (D3 force-directed) depuis Artist Detail — les donnees et l'endpoint sont prets, il manque le composant visuel interactif. Graphe egocentrique (1 artiste + ses connexions directes). A faire quand le besoin se fera sentir.

### Definition of Done

```bash
# Endpoint /api/catalog/{id}/similar -> top 10 tracks similaires (scoring metadonnees + co-occurrence)
# Endpoint /api/artists/{id}/connections -> artistes proches
# Shelf "Artistes proches" sur ArtistDetailView
# REPORTE : graphe visuel D3 (endpoint pret, composant visuel manquant)
```

---

## H0 — Hygiene & Solidification

**Priorite : MOYEN**
**Estimation : 2 jours (1 jour backend/infra + 1 jour frontend)**
**Depend de : rien (parallelisable avec tout)**
**Statut : TERMINE (2026-07-06)**

### Contexte

Audit technique du 06/07/2026 : revue globale securite, architecture, performance et friction de dev.
Aucun point critique bloquant identifie, mais 16 points d'hygiene a traiter pour solidifier le projet
avant de continuer a empiler des features. Chaque point est independant et peut etre fait isolement.

### H0.a — Securite & Resilience (3-4h)

**CORS : restreindre methods et headers** (5 min)
`main.py:75-76` — `allow_methods=["*"]` et `allow_headers=["*"]` sont plus larges que necessaire.
Pas de risque reel (pas de `allow_credentials`), mais c'est de l'hygiene.
Fix : remplacer par `allow_methods=["GET", "POST", "PATCH", "DELETE"]` et
`allow_headers=["Authorization", "Content-Type"]`.

- [x] Restreindre CORS methods et headers dans `main.py`

**Rate limiting : etendre au-dela de l'auth** (15 min)
Seules 3 routes auth sont rate-limitees (`rate_limit.py:15-19`). Les endpoints publics (search,
catalog) et admin (triggers de crawl, import) n'ont aucune protection contre le spam.
Fix : ajouter des entrees dans le dict `RATE_LIMITS` existant. Pas de nouveau code, juste
de la config.

- [x] Ajouter rate limits : `/api/search` (30/min), `/api/import/rekordbox` (3/5min), `/api/admin` (10/min)

**Timeouts Celery explicites** (10 min)
3 taches longues n'ont pas de `soft_time_limit`/`time_limit` explicites et dependent du global
(1h). Sur des playlists volumineuses ou un catalogue large, elles peuvent timeout sans grace.
Les autres taches (beatport, backfill, genres) ont deja des timeouts explicites.
Fix : ajouter 2 lignes par tache.

- [x] `crawl_single_playlist` (`workers/tasks/radar.py:21`) : `soft_time_limit=3600, time_limit=4500`
- [x] `enrich_catalog` (`workers/tasks/catalog.py:16`) : `soft_time_limit=7200, time_limit=9000`
- [x] `sync_artists` (`workers/tasks/artists.py:16`) : `soft_time_limit=3600, time_limit=4500`

**Retirer `Base.metadata.create_all` en production** (5 min)
`main.py:54-55` — `create_all` au demarrage peut creer des tables hors Alembic. Alembic gere
deja tout via `alembic upgrade head` dans deploy.yml. Conditionner a un flag env ou supprimer.

- [x] Conditionner `create_all` a `ENV != production` ou supprimer

### H0.b — Infra Docker (30 min)

**Healthchecks manquants** (20 min)
`api`, `frontend`, `nginx` n'ont pas de healthcheck dans `docker-compose.yml`. Docker ne detecte
pas si ces services plantent et ne peut pas les redemarrer proprement. Les autres services
(postgres, redis, minio) en ont deja.
Fix : ajouter un bloc `healthcheck` avec `curl -f` sur chaque service.

- [x] Healthcheck `api` : python urllib sur 127.0.0.1:8000
- [x] Healthcheck `frontend` : wget sur 127.0.0.1:80
- [x] Healthcheck `nginx` : wget HTTPS sur 127.0.0.1:443

**Volume mount en production** (10 min)
`docker-compose.yml:69` — `./server/api:/app` monte le code source en live. En prod le code
devrait venir du `COPY` dans le Dockerfile, pas d'un mount. Risque : divergence entre image
buildee et code sur le disque VPS.
Fix : utiliser un `docker-compose.override.yml` pour le dev avec le volume mount, et retirer
le mount du compose principal.

- [x] Retirer `./server/api:/app` du compose principal, deplacer en override dev

### H0.c — Architecture backend (2-3h)

**Split `models.py` en multi-fichiers** (1-2h)
582 lignes, 22 modeles dans un seul fichier. Genable aujourd'hui mais va continuer a grossir.
Pattern : creer un package `models/` avec un fichier par domaine et un `__init__.py` qui
reexporte tout (`from .catalog import *`, etc.). Tous les imports existants (`from models import
Artist`) continuent de fonctionner sans modification. Les 564 tests servent de filet.

```
models/
  __init__.py     → reexporte tout
  user.py         → User
  catalog.py      → CatalogEntry, CatalogArtist
  artist.py       → Artist, ArtistAlias, ArtistFlag
  radar.py        → RadarTrack, RadarTrend, WatchedEntity, UserFollow, UserRadarState
  sets.py         → DJSet, SetTrack, SetArtist
  genre.py        → GenreNode, GenreEdge, GenreMapping
  collection.py   → UserCollection, CollectionItem
  opinion.py      → UserOpinion
  admin.py        → AdminAuditLog, CrawlLog
```

- [x] Creer le package `models/` avec split par domaine
- [x] Verifier que `from models import X` fonctionne toujours (tests)
- [x] Supprimer l'ancien `models.py`

**Index compound supplementaires** (15 min)
La migration `0020` couvre les index critiques. Deux index compound supplementaires utiles
quand les tables grossiront (20K+ rows) :
- `radar_tracks(source, detected_at DESC)` — tri radar par date et source
- `user_opinions(user_id, opinion)` — requete "tous mes likes" rapide

- [x] Migration Alembic : index compound `radar_tracks(source, detected_at DESC)`
- [x] Migration Alembic : index compound `user_opinions(user_id, opinion)`

**`selectinload` explicite sur les relations accedees** (30 min)
En async SQLAlchemy, acceder a une relation non-chargee leve `MissingGreenlet` au lieu de
faire un N+1 silencieux. Donc pas de risque de perf cachee, mais risque de crash inattendu
si un dev accede a une relation sans y penser. Ajouter des `selectinload` explicites la ou
des relations sont accedees dans les routers/services.

- [x] Auditer les acces relation dans les routers et ajouter `selectinload` si manquant (audit : aucun cas risque trouve)

**Deplacer `deezer_enrich.py` dans workers/** (15 min)
Ce fichier utilise des sessions synchrones (contexte Celery) mais vit dans `server/api/`
qui est entierement async. Source de confusion pour les devs. 2-3 imports a mettre a jour.

- [x] Deplacer `server/api/deezer_enrich.py` -> `server/workers/deezer_enrich.py`
- [x] Mettre a jour les imports dans les tasks qui l'utilisent

### H0.d — Frontend (4-5h)

**Decouper AdminView.vue** (3-4h)
1725 lignes, plus grosse vue du projet. C'est une page a sections/onglets : chaque section
peut devenir un composant autonome avec son propre state et ses appels API.
AdminView.vue devient un layout leger qui charge le bon composant.

```
components/admin/
  AdminArtists.vue    → sync artistes, recherche Deezer, linking
  AdminFlags.vue      → gestion des flags artistes
  AdminSets.vue       → linking artistes-sets
  AdminGenres.vue     → taxonomie, enrichissement genres
  AdminCrawl.vue      → logs de crawl, triggers
  AdminBeatport.vue   → enrichissement Beatport
```

- [x] Extraire chaque section en composant dans `components/admin/`
- [x] AdminView.vue : layout avec tabs, charge le composant actif
- [x] Verification manuelle de chaque onglet apres le split

**Toast global pour les erreurs** (1h)
Aucun feedback utilisateur sur les erreurs API (30+ blocs `catch {}` silencieux). Le seul
intercepteur Axios gere le 401 (auto-logout). Les 500, timeouts, erreurs reseau sont avales.
Fix : un store Pinia `toast.js` (~10 lignes) + un composant `ToastNotification.vue` (~40 lignes)
+ branchement dans l'intercepteur Axios pour les 5xx et network errors.

- [x] Creer `stores/toast.js` (message, type, action optionnelle show/hide)
- [x] Creer `components/ToastNotification.vue` (affichage temporaire, auto-dismiss, bouton action)
- [x] Brancher dans l'intercepteur Axios (`api.js`) pour 5xx et network errors
- [x] Remplacer les `catch {}` silencieux dans les vues critiques + migrer le toast local HubView

### H0.e — Qualite API : response models Pydantic (sprint dedie ~1 jour)

**Pourquoi** : la plupart des routers retournent des `dict` construits a la main. Risques :
doc OpenAPI incomplete, breaking changes silencieuses (renommer un champ backend = crash
frontend sans warning), pas de validation de sortie.

**Comment** : sprint d'une journee dedie. Pour chaque router, creer les schemas Pydantic de
reponse et les brancher en `response_model`. ~40-50 endpoints, ~10-15 min chacun.

**Ordre suggere** (par frequence d'utilisation frontend) :
1. `catalog.py` (128 lignes, 5 endpoints) — le plus utilise
2. `artists.py` (66 lignes, ~3 endpoints) — pages artistes
3. `search.py` (408 lignes, ~5 endpoints) — hub
4. `sets.py` (358 lignes, ~6 endpoints) — sets
5. `radar.py` (148 lignes, ~3 endpoints) — radar/trend
6. `tracks.py` (350 lignes, ~5 endpoints) — user library
7. `collections.py` (215 lignes, ~5 endpoints)
8. `watchlist.py` (432 lignes, ~6 endpoints)
9. `genres.py` (194 lignes, ~4 endpoints)
10. `opinions.py` (92 lignes, ~3 endpoints)
11. `admin.py` (468 lignes, ~15 endpoints)
12. Reste : `taxonomy.py`, `import_rb.py`, `auth.py`

- [x] Sprint Pydantic : creer les response models pour tous les endpoints (89/89 endpoints, 16 fichiers schemas/)
- [x] Verifier la doc OpenAPI generee (`/api/docs`)

### H0.f — Tests d'integration backend (2-3h)

**Pourquoi** : 564 tests unitaires API mais aucun test de flux complet. Les bugs de pipeline
(crawl → enrichissement → trend → surface) ne sont detectes qu'en prod.

**Quoi** : 2-3 tests pytest qui chainent des etapes. Pas d'infra supplementaire,
pas de browser, juste des tests pytest plus longs. Pas d'E2E frontend (trop lourd
a mettre en place et a maintenir pour la taille du projet).

Flux critiques a couvrir :
1. **Pipeline radar** : creer watched_entity → simuler crawl → verifier radar_tracks → trigger compute_trends → verifier radar_trends
2. **Import Rekordbox** : upload XML → verifier user_tracks crees → verifier enrichissement catalog
3. **Similarite** : creer tracks avec metadonnees variees → appeler `/catalog/{id}/similar` → verifier que le scoring est coherent

- [x] Test integration : pipeline radar (crawl → trends) — 4 tests
- [x] Test integration : import Rekordbox (upload → enrichissement) — 3 tests
- [x] Test integration : similarite (tracks → scoring) — 5 tests

### Definition of Done

```bash
# Securite
# CORS restreint, rate limiting etendu, timeouts Celery explicites
# create_all conditionne a l'env

# Infra
# Healthchecks sur api/frontend/nginx
# Volume mount retire du compose principal

# Architecture
# models/ split en multi-fichiers, imports preserves
# Index compound ajoutes, selectinload audite
# deezer_enrich.py dans workers/

# Frontend
# AdminView decoupe en 6 composants
# Toast global operationnel, catch silencieux remplaces

# API
# Response models Pydantic sur tous les endpoints
# Doc OpenAPI complete

# Tests
# 3 tests d'integration sur les flux critiques
# pytest passe toujours (564+ tests)
```
