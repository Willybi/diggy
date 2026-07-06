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
> **Derniere mise a jour** : 2026-07-06 (H0 + P1 termines, F5/C6 prochains)

---

## Vision cible

Avant l'ouverture aux amis (5-10 DJs), Diggy doit offrir :
1. Une experience mobile utilisable (ils seront sur telephone)
2. Une recommandation de tendance solide, decorrellee des likes (offre par defaut des nouveaux arrivants sans historique)
3. Un moteur de similarite fonctionnel (socle de toute recommandation, avec ou sans user)
4. Une application fermee et etanche entre utilisateurs (auth obligatoire, scopes respectes)

Apres l'ouverture : la recommandation personnalisee (croisement similarite x likes), utile des un seul user et enrichie par chaque nouvel utilisateur.

Sequence : **~~C0 -> R1 -> C1 -> C2~~ (TERMINE) -> ~~H0 + P1~~ (TERMINE) -> F5 + C6 (paralleles) -> C3 (ouverture) -> C4 -> C5**

---

## Vue d'ensemble

```
 #    Chantier                              Priorite    Estimation   Statut
----  ------------------------------------  ----------  ----------   ------
 C0   Correctifs critiques + fondations     CRITIQUE    1-2 jours    TERMINE
 R1   Responsive / Support Mobile           HAUT        3-4 jours    TERMINE
 C1   Trend v2 + Decouvrir + Collections    HAUT        5-7 jours    TERMINE
 C2   Moteur de Similarite (absorbe F3)     MOYEN       7-10 jours   TERMINE (graphe D3 reporte)
 H0   Hygiene & Solidification              MOYEN       2 jours      TERMINE
 P1   Polish & Correctifs UI               MOYEN       1-2 jours    TERMINE
 C6   Veille elargie & Suivi artistes       HAUT        7-10 jours   A FAIRE
 F5   Import manuel (recherche externe)    MOYEN       2-3 jours    A FAIRE
 C3   Ouverture aux amis                    MOYEN       5-7 jours    DECLENCHEMENT MANUEL (apres H0)
 C4   Reco personnalisee                    BAS         3-5 jours    APRES OUVERTURE
 C5   Collections v2 (polymorphe + dossiers) BAS       3-5 jours    APRES OUVERTURE
 D4   Pages Detail (Vague 3)               BAS         5-7 jours    BLOQUE (briefs)
```

### Chantiers termines (reference)

```
 #    Chantier                           Statut
----  ---------------------------------  ------
 S1   Securite & Hardening              TERMINE
 S2   Qualite & CI Pipeline             TERMINE
 A1   Service Layer Backend             TERMINE
 A2   Refactor Workers                  TERMINE
 A3   Frontend Perf & Accessibilite     TERMINE
 D1   FIX Design immediats             TERMINE
 D2   Genres — Refonte complete         TERMINE
 D3   Hub / Search                      TERMINE
 D5   Refactor Composants partages      TERMINE
 F4   Import Rekordbox Web              TERMINE
 C0   Correctifs critiques + fondations TERMINE
 R1   Responsive / Support Mobile     TERMINE
 C1   Trend v2 + Decouvrir + Collections TERMINE
 C2   Moteur de Similarite + Artistes    TERMINE (graphe D3 reporte)
 H0   Hygiene & Solidification          TERMINE
 P1   Polish & Correctifs UI            TERMINE
```

### Dependances

```
C0 ─────────> Tout (prerequis securite + fondations data)              ✅ TERMINE
R1 ─────────> C1 (mobile requis pour l'UX decouvrir)                  ✅ TERMINE
C1 (trend) ─> C3 (reco par defaut prete avant ouverture)              ✅ TERMINE
C2 (simil) ─> C4 (socle de la reco personnalisee)                     ✅ TERMINE

H0 ─────────> C3 (hygiene secu/infra avant ouverture)              ✅ TERMINE
P1 ─────────> Rien (parallelisable avec tout)                      ✅ TERMINE

--- actif ---
C6 (veille) ┬ C6.0 dedup prerequis avant C6.a crawl massif
             ├ parallele avec F5
             └ avant C3 idealement (plus de donnees = meilleure XP nouveaux users)
F5 ─────────> Rien (parallelisable avec tout)
C3 (ouvert) = declenchement manuel, apres H0 (FAIT) + C1 + idealement C6
C4 ─────────> C2 + C3 (similarite + likes + users)
C5 ─────────> C3 (apres ouverture)
```

### Decisions produit actees

| Decision | Contenu |
|---|---|
| Politique de scope a l'import | Track absente du catalog -> tentative d'enrichissement. Match plateforme -> `shared`. Pas de match ou match ambigu -> `private`, visible uniquement par l'importeur. Re-tentative periodique avec promotion automatique si un match apparait. Doublons entre scopes prives : non traites, par design. |
| Collections perso | v1 (tracks only) integree dans C1. v2 prevue dans C5 : items polymorphes (tracks/sets/artistes/genres/playlists) + dossiers. Strictement privees : une collection n'est visible que par son proprietaire. |
| F3 Graphe artistes | Absorbe dans le moteur de similarite (C2). Le graphe devient une vue du moteur, pas un chantier separe. |
| Trend | Classement (pas score absolu), calcule par famille de genre, recalcule chaque nuit. Formule composite : detections ponderees (type de source, taille de playlist) x decay temporel x velocite x convergence multi-sources. Distinction fraicheur / revival portee par la ponderation temporelle. |
| Reco de trend | Decorrellee des likes. Offre par defaut, notamment pour les nouveaux users sans historique. |
| Reco personnalisee | Apres ouverture. Necessite le moteur de similarite + les likes. |
| Dedup sets | Un set logique = un seul signal trend, peu importe le nombre de sources (YouTube + Soundcloud) ou de parties. Les doublons sont rattaches (parent/enfant ou multi-source) et exclus du scoring. |
| Follow vs Like | Like = signal passif de gout pour la reco. Follow = surveillance active d'un artiste (releases, sets, activite). Les deux systemes coexistent, decorrelees. |

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
**Statut : A FAIRE — parallélisable avec C2**

### P1.1 — PlayerBar : navigation titre et artiste

Le titre et l'artiste dans la PlayerBar sont des `<span>` inertes. Les rendre cliquables.

- [ ] Titre cliquable → `/catalog/:catalog_id`
- [ ] Artiste cliquable → `/artist/:artist_id`
- [ ] Stocker `artist_id` dans le player store lors du `play()` (champ absent actuellement)

### P1.2 — Boutons Play dans TrackDetailView

Les sections "Du même artiste" et "Tracks similaires" sont des `RouterLink` sans bouton play,
contrairement aux mini-rows de ArtistDetailView qui en ont un.

- [ ] Ajouter bouton play (conditionnel sur `has_preview`) dans la grille "Du même artiste"
- [ ] Ajouter bouton play dans la grille "Tracks similaires"
- [ ] Vérifier que `has_preview` est bien exposé par les endpoints `/api/catalog/{id}/similar` et `same_artist_tracks`

### P1.3 — ScorePill : refonte pour les floats

Le score radar (`trend_score_10`) peut désormais être un float. Le composant actuel
affiche `7.3/10` avec 10 barres binaires (on/off) — lisible mais pas optimal pour un continu.

- [ ] Remplacer les 10 barres discrètes par une barre de progression continue (`width: score * 10%`)
- [ ] Arrondir l'affichage texte à 1 décimale si float, entier sinon

### P1.4 — GenreDetailView : pagination shelves artistes/playlists

Les shelves "Artistes" et "Playlists" chargent 12 items max sans possibilité d'en voir plus.
Si `artistsTotal > 12` ou `playlistsTotal > 12`, les items supplémentaires sont inaccessibles.
Audit aussi le scroll horizontal (possible conflit de container query sur mobile).

- [ ] Ajouter un bouton "Voir les N autres" sous chaque shelf si total > items affichés
- [ ] Fetch paginé au clic (limit +12 ou page suivante)
- [ ] Auditer le CSS scroll horizontal des shelves sur mobile

### P1.5 — Admin : split artiste manuel sur espace

`detectSeparator()` ne reconnait que les séparateurs explicites (`/`, ` & `, `,`, `feat.`…).
Les concaténations sans séparateur type "Bad Boombox mischluft" ne sont pas détectables
automatiquement — l'espace seul est trop ambigu.

- [ ] Ajouter un mode de split manuel : afficher les tokens potentiels du nom en cliquant sur les espaces
- [ ] UI : nom de l'artiste affiché avec espaces cliquables, clic = choisir le point de coupure
- [ ] Générer les tokens côté frontend, envoyer vers le flow `flags/manual` existant
- [ ] Bouton "Splitter manuellement" visible pour tous les artistes (pas uniquement ceux avec séparateur reconnu)

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

- [ ] Migration Alembic : index compound `radar_tracks(source, detected_at DESC)`
- [ ] Migration Alembic : index compound `user_opinions(user_id, opinion)`

**`selectinload` explicite sur les relations accedees** (30 min)
En async SQLAlchemy, acceder a une relation non-chargee leve `MissingGreenlet` au lieu de
faire un N+1 silencieux. Donc pas de risque de perf cachee, mais risque de crash inattendu
si un dev accede a une relation sans y penser. Ajouter des `selectinload` explicites la ou
des relations sont accedees dans les routers/services.

- [ ] Auditer les acces relation dans les routers et ajouter `selectinload` si manquant

**Deplacer `deezer_enrich.py` dans workers/** (15 min)
Ce fichier utilise des sessions synchrones (contexte Celery) mais vit dans `server/api/`
qui est entierement async. Source de confusion pour les devs. 2-3 imports a mettre a jour.

- [ ] Deplacer `server/api/deezer_enrich.py` -> `server/workers/deezer_enrich.py`
- [ ] Mettre a jour les imports dans les tasks qui l'utilisent

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

- [ ] Extraire chaque section en composant dans `components/admin/`
- [ ] AdminView.vue : layout avec tabs, charge le composant actif
- [ ] Verification manuelle de chaque onglet apres le split

**Toast global pour les erreurs** (1h)
Aucun feedback utilisateur sur les erreurs API (30+ blocs `catch {}` silencieux). Le seul
intercepteur Axios gere le 401 (auto-logout). Les 500, timeouts, erreurs reseau sont avales.
Fix : un store Pinia `toast.js` (~10 lignes) + un composant `ToastNotification.vue` (~40 lignes)
+ branchement dans l'intercepteur Axios pour les 5xx et network errors.

- [ ] Creer `stores/toast.js` (message, type, show/hide)
- [ ] Creer `components/ToastNotification.vue` (affichage temporaire, auto-dismiss)
- [ ] Brancher dans l'intercepteur Axios (`api.js`) pour 5xx et network errors
- [ ] Remplacer les `catch {}` silencieux par `catch (e) { toast.show(...) }` dans les vues critiques

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

- [ ] Sprint Pydantic : creer les response models pour tous les endpoints
- [ ] Verifier la doc OpenAPI generee (`/api/docs`)

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

- [ ] Test integration : pipeline radar (crawl → trends)
- [ ] Test integration : import Rekordbox (upload → enrichissement)
- [ ] Test integration : similarite (tracks → scoring)

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

---

## C6 — Veille elargie & Suivi artistes

**Priorite : HAUT**
**Estimation : 7-10 jours**
**Depend de : C1 (TERMINE). Parallelisable avec C2.**
**Statut : A FAIRE**

### Objectif

Le bottleneck de Diggy n'est ni l'algo ni l'UI : c'est le volume et la diversite des donnees entrantes. Aujourd'hui 29 playlists suivies + 27 sets manuels = bassin trop etroit et biaise vers les choix de curation du createur. Ce chantier elargit les sources de donnees automatiques pour alimenter le trend, la similarite (C2), et la reco (C4).

Trois axes :
1. Crawler global TrackID.net (pas juste les sets user)
2. Suivi actif d'artistes (releases, sets, activite multi-source)
3. Re-crawl intelligent des sets incomplets

### Constats

- Les 29 playlists produisent ~5000 radar_tracks : seul flux entrant automatique
- Les sets sont ajoutes manuellement, jamais re-crawles apres import
- Un track qui passe dans un set DJ = signal de trending fort et objectif (pondere 3x dans C1), mais on ne capture quasi rien de ce signal aujourd'hui
- TrackID.net publie des dizaines de sets quotidiennement avec tracklists identifiees : mine d'or inexploitee
- Probleme de doublons TrackID.net : meme set sur YouTube + Soundcloud = 2 lignes, sets en parties (PART1, PART2...) = pollution du scoring

### C6.0 — Dedup sets TrackID (prerequis)

**Doit passer AVANT le crawl massif, sinon on cree de la dette immediatement.**

Deux cas de doublons a traiter :

**Cas 1 : Meme set, sources differentes (YouTube + Soundcloud)**

Signaux de dedup par ordre de confiance :
- Artiste + titre normalise (apres strip des tags source, lowercase, trim) : couvre ~90% des cas
- Premiere track identique + meme artiste : quasi certain
- Tracklist overlap > 80% dans le meme ordre : meme set

Modele : ne pas supprimer le doublon, mais le **rattacher** via une table `set_sources` :
```
set_sources (nouvelle table)
  set_id      → sets.id (le set "master")
  source      → enum (youtube, soundcloud, mixcloud, etc.)
  external_url
  trackid_id  → identifiant TrackID.net de cette version
```
Avantages : un seul set dans le scoring, on garde les deux sources, on peut **merger les tracklists** (YouTube a identifie tracks 1-5, Soundcloud 3-8 → on recupere 1-8).

**Cas 2 : Set complet + parties (PART 1, PART 2...)**

- Detection : regex sur le titre → `(part\s*\d+|pt\.?\s*\d+|p\d+)` en fin de titre
- Groupement : meme artiste + meme titre de base (sans suffixe part) → candidats au regroupement
- Si un set "complet" existe : les parties sont rattachees comme enfants (`parent_set_id` sur `sets`)
- Si pas de set complet : les parties partagent un `group_id`, scorees comme un seul set logique

**Regle scoring : un set logique = un seul signal trend, peu importe le nombre de sources ou de parties.**

Taches :
- [ ] Normalisation titre : fonction `normalize_set_title()` (strip tags source, lowercase, trim, retirer "Official", "Full Set", etc.)
- [ ] Migration : table `set_sources` (set_id, source, external_url, trackid_id, created_at)
- [ ] Migration : colonne `parent_set_id` (nullable FK vers `sets.id`) + `group_id` (nullable) sur `sets`
- [ ] Logique de detection de doublons a l'import (avant insertion)
- [ ] Merge tracklists entre sources d'un meme set (union ordonnee)
- [ ] Adapter `compute_trends` : exclure les sets avec `parent_set_id IS NOT NULL` du scoring
- [ ] Audit des 27 sets existants pour valider la logique de dedup

### C6.a — Crawler global TrackID.net

Crawler le flux global de TrackID.net (pas juste les sets importes par un user). Impact immediat sur trend + co-occurrence (C2.c).

- [ ] Crawl quotidien du flux "latest sets" de TrackID.net (toutes categories, pages 1 a N)
- [ ] Import automatique dans `sets` + `set_tracks` + enrichissement `catalog`
- [ ] Dedup a l'import via C6.0 (verifier doublon avant insertion)
- [ ] Filtrage optionnel par pertinence genre (a evaluer apres quelques jours de crawl test — risque de bruit hors-scope : pop, rock, etc.)
- [ ] Rate limiting poli : headers respectueux, throttling entre requetes, pas de crawl agressif
- [ ] Task Celery Beat : `crawl_trackid_latest`, schedule quotidien

Volume attendu : 10-50 sets/jour → des centaines de paires track x set par semaine. Multiplie le bassin de co-occurrence pour C2.c.

### C6.b — Re-crawl decroissant des sets incomplets

Les sets TrackID.net ne sont pas toujours complets a la premiere visite (identification en cours). Re-crawler intelligemment sans gaspiller de bande passante.

Cadence de re-crawl (backoff exponentiel) :

```
Age du set           Frequence
───────────────────  ─────────────────────
0 - 7 jours          tous les jours
7 - 30 jours         1x / semaine
30 - 90 jours        1x / mois
90+ jours             STOP (marque "final")
```

Sortie anticipee : si le % d'identification n'a pas bouge sur 3 re-crawls consecutifs → marque "final" immediatement, peu importe l'age.

- [ ] Colonnes sur `sets` : `completion_pct` (float), `last_recrawl_at`, `recrawl_count`, `recrawl_status` (enum: active/final)
- [ ] Task Celery : `recrawl_incomplete_sets`, schedule quotidien, selectionne les sets eligibles selon la cadence
- [ ] Logique de sortie anticipee (3 crawls sans changement → final)
- [ ] Mise a jour des tracklists au re-crawl (ajout des tracks nouvellement identifiees)

### C6.c — Suivi d'artistes v1 (Deezer + TrackID)

Feature user-facing : "suivre" un artiste = surveillance active de son activite. Decouple du like (qui reste un signal de gout passif pour la reco).

| Source | Signal surveille | Faisabilite |
|--------|-----------------|-------------|
| **Deezer** | Nouvelles releases (`/artist/{id}/albums?order=date`) | Trivial — `deezer_id` sur 99% des artistes |
| **TrackID.net** | Nouveaux sets contenant l'artiste | Faisable — on scrape deja le site |

- [ ] Migration : table `followed_artists` (user_id, artist_id, followed_at)
- [ ] Migration : table `artist_activity` (id, artist_id, activity_type enum, source, title, external_url, catalog_id nullable, set_id nullable, detected_at, payload_json)
- [ ] Bouton "Suivre" sur ArtistDetailView (distinct du like)
- [ ] Task Celery Beat : `check_followed_artists`, quotidien, batch sur tous les artistes suivis par au moins 1 user
- [ ] Check Deezer releases : comparer derniere release connue vs API, creer `artist_activity` si nouveau
- [ ] Check TrackID.net : rechercher sets recents contenant l'artiste, croiser avec sets deja importes
- [ ] Surface frontend : section "Nouveautes de tes artistes" (vue dediee ou shelf sur le Hub)
- [ ] Badge/notification : indicateur de nouvelles activites non vues

### C6.d — Suivi d'artistes v2 (Soundcloud) — futur

Extension du suivi artiste a Soundcloud. **Reporte apres validation de C6.c** car le scraping Soundcloud est fragile (pas d'API officielle, anti-bot).

| Source | Signal surveille | Faisabilite |
|--------|-----------------|-------------|
| **Soundcloud** | Nouveaux tracks + reposts + mixes | Moyen — scraping ou `soundcloud-lib`, fragile |

- [ ] Colonne `soundcloud_url` sur `artists`
- [ ] Scraping profil Soundcloud (tracks + reposts)
- [ ] Import des tracks trouvees → enrichissement Deezer/Beatport
- [ ] Integration dans `artist_activity`

Extensions futures possibles (non planifiees) :
- YouTube : Data API v3, quota limite mais suffisant pour des checks quotidiens
- Bandcamp : RSS/feed scraping
- Beatport : extension naturelle de l'enrichissement existant

### C6.e — Playlists auto-follow

Toute playlist en base devrait etre surveillee a intervalle regulier, pas seulement les 29 "watched".

- [ ] Supprimer la distinction rigide watched/non-watched : toute playlist connue = crawl periodique
- [ ] Cadence adaptative (meme principe que C6.b : frequente au debut, decroissante si stable)
- [ ] Ou a minima : elargir les criteres d'ajout automatique de playlists a surveiller

### Risques identifies

| Risque | Mitigation |
|--------|-----------|
| Rate limiting / ban TrackID.net | Headers polis, throttling, potentiellement proxy rotatif |
| Bruit hors-genre (pop, rock) | Filtrage post-crawl par pertinence genre — a evaluer empiriquement |
| Volume DB (5k → 50k+ radar_tracks) | Pas un probleme pour Postgres, mais surveiller index et temps de `compute_trends` |
| Fragilite scraping Soundcloud | Ne pas en faire un pilier critique en v1, d'ou le report en C6.d |

### Definition of Done

```bash
# Dedup
# Doublons sets existants identifies et rattaches
# Nouveau set importe → dedup automatique avant insertion
# compute_trends exclut les doublons/parties

# Crawler global
# crawl_trackid_latest tourne quotidiennement
# Nouveaux sets apparaissent dans la table sets sans intervention manuelle
# Impact visible sur le trend (plus de signaux set)

# Re-crawl
# Sets incomplets re-crawles avec backoff exponentiel
# Sets "final" ne consomment plus de bande passante

# Suivi artistes
# Bouton "Suivre" sur Artist Detail, distinct du like
# check_followed_artists detecte les nouvelles releases Deezer
# Section "Nouveautes" accessible dans l'app
```

---

## F5 — Import manuel (recherche externe)

**Priorite : MOYEN**
**Estimation : 2-3 jours**
**Depend de : rien (APIs Deezer/TIDAL deja accessibles)**
**Statut : A FAIRE — parallelisable avec C6/P1**

### Objectif

Permettre a tout utilisateur connecte d'ajouter un track au catalog via une recherche sur les sources externes (Deezer, TIDAL). Aujourd'hui les tracks n'entrent que par import en masse (Rekordbox XML, crawl playlists, import sets TrackID) — aucun moyen d'ajouter un son a la main.

### Faisabilite technique

| Source | Recherche | Auth | ISRC | Statut |
|--------|-----------|------|------|--------|
| **Deezer** | `search_deezer()` dans `deezer_enrich.py` | Aucune (API publique) | Oui | Pret a l'emploi |
| **TIDAL** | `tidalapi.session.search()` | OAuth device flow (tokens deja en Redis) | Oui | Trivial a ajouter |
| **Spotify** | Pas de search dans `spotifyscraper` | — | Non | Pas faisable |

### F5.a — Backend : endpoint recherche externe

- [ ] `GET /api/search/external?q=...` : recherche parallele Deezer + TIDAL
- [ ] Resultats fusionnes, dedupliques par ISRC (priorite Deezer si doublon)
- [ ] Rate limiting Deezer (0.12s entre requetes, deja en place dans `deezer_enrich.py`)
- [ ] Indiquer dans la reponse si le track existe deja dans le catalog (`catalog_id` si match ISRC/normalized_key)

### F5.b — Backend : endpoint import

- [ ] `POST /api/catalog/import` : prend un `deezer_id` ou `tidal_id`
- [ ] Enrichissement via `deezer_enrich.py` (flow existant : artwork, ISRC, duration, etc.)
- [ ] Scope `shared` (source officielle = match confirme)
- [ ] Dedup : verifier ISRC / `normalized_key` avant insertion, retourner l'entree existante si doublon
- [ ] Creation artiste(s) via le flow existant (`get_or_create_artist`)

### F5.c — Frontend : barre de recherche + import

- [ ] UI de recherche (vue dediee ou modale depuis le header)
- [ ] Affichage resultats : artwork, titre, artiste, source (badge Deezer/TIDAL)
- [ ] Badge "Deja dans le catalog" si le track existe
- [ ] Bouton "Importer" par resultat, feedback immediat (track ajoutee, lien vers la fiche catalog)

### Definition of Done

```bash
# GET /api/search/external?q=artist+title -> resultats Deezer + TIDAL
# POST /api/catalog/import avec deezer_id -> entree catalog creee
# Dedup : meme ISRC -> pas de doublon, retourne l'existant
# Frontend : recherche + affichage + bouton import fonctionnels
# Accessible a tout utilisateur connecte
```

---

## C3 — Ouverture aux amis

**Priorite : MOYEN**
**Estimation : 5-7 jours**
**Depend de : C1 (TERMINE) + H0 (hygiene secu/infra) + idealement C6 (donnees)**
**Declenchement : ta decision d'inviter, pas la roadmap**
**Statut : A FAIRE**

### Objectif

Fermer l'application et garantir l'etancheite entre users. Regroupe le reliquat Phase 6, la verification Phase 7, et les prerequis d'accueil.

### C3.a — Fermeture (reliquat Phase 6, dimensionne par l'audit)

L'audit invalide le "normalement deja traite" : le middleware laisse public tout GET sur catalog/artists/sets/genres/search/taxonomy.

- [ ] Basculer les GET publics en auth obligatoire (`get_current_user_optional` -> `get_current_user`), exemptions restantes : `/api/auth/*`, `/api/health`, `/api/watchlist/active` (a securiser autrement : token interne ou appel direct DB par le worker)
- [ ] **Filtrer `scope=private` d'autrui sur tous les endpoints catalog** (browse, detail, search, stats genres) : bloquant, sans ca la politique de scope est violee des le browse
- [ ] `GET /api/sets/{id}` : filtre `user_id` sur le check in_lib (`sets.py:281`)
- [ ] `/storage/*` : proteger les artworks (auth au niveau Nginx via `auth_request` vers l'API, ou URLs signees MinIO) : IDs sequentiels enumerables aujourd'hui
- [ ] Supprimer le guest cap (plus de visiteurs = plus besoin de cap)

### C3.b — Import multi-user (verification Phase 7, audit largement OK)

L'audit confirme : chaine user_id propre de bout en bout, lock Redis per-user, champ scope actif, et la promotion private -> shared via enrichissement Deezer **deja implementee** (`deezer_enrich.py`). La politique decidee est a ~80% en place.

Reste :
- [ ] **Corriger le perimetre d'enrichissement** : le check SQL montre 0/259 tracks private enrichies, preuve que les tasks d'enrichissement excluent `scope=private`. La mecanique de promotion existe (`deezer_enrich.py`) mais ne s'execute jamais sur les private. Inclure explicitement le scope private dans les passes d'enrichissement (tache Celery Beat dediee ou extension de `enrich_catalog`), sinon une track mal taguee ou un unreleased qui sort officiellement reste private a vie
- [ ] Etendre le test d'admission a Beatport (pas seulement Deezer) si pertinent
- [ ] Test reel de bout en bout : import d'une deuxieme bibliotheque Rekordbox (compte de test), verification dedup ISRC/normalized_key, scopes, non-regression sur ta lib
- [ ] Verifier le comportement funnel en cas de match ambigu : rester private (acte : en cas de doute, on ne matche pas)

### C3.c — Accueil

- [ ] Onboarding minimal : que voit un nouvel utilisateur sans bibliotheque ? (reponse : le catalogue shared + le trend par famille = la reco par defaut, d'ou C1 avant C3)
- [x] ~~Frontend build statique de prod~~ — FAIT (Nginx static build, voir reliquats)
- [ ] Sentry DSN configure (monitoring minimal avant d'avoir des users reels)

### Definition of Done

```bash
# Tout GET sans token -> 401 (sauf /api/auth/*, /api/health)
# scope=private d'un autre user invisible dans catalog/search/genres
# /storage/* protege (pas d'acces anonyme)
# Import d'une 2e lib Rekordbox : dedup OK, scopes OK
# Build frontend statique (pas Vite dev server)
```

---

## C4 — Recommandation personnalisee (apres ouverture)

**Priorite : BAS**
**Estimation : 3-5 jours**
**Depend de : C2 + C3**
**Statut : APRES OUVERTURE**

### Objectif

Croiser le moteur de similarite (C2) avec les likes (`user_opinions`). Utile des un seul user (toi), mais volontairement place apres l'ouverture : chaque nouvel utilisateur enrichit le signal.

- [ ] Profil de gout par user : agregation des scores de similarite (C2) des tracks likees (penalisation des dislikees)
- [ ] Reco = scoring C2 (metadonnees + co-occurrence) pondere par le profil, filtre par famille/BPM, excluant la lib existante
- [ ] Surface : section "Pour toi" distincte de la section trend (les deux recos coexistent, decorrelees)
- [ ] Long terme (parque, inchange) : track2vec sur tracklists de sets, pgvector si embeddings necessaires, audio features, LLM normalisation

### Definition of Done

```bash
# Endpoint /api/recommendations -> tracks personnalisees
# Section "Pour toi" dans le Hub, distincte du trend
```

---

## C5 — Collections v2 (polymorphe + dossiers)

**Priorite : BAS**
**Estimation : 3-5 jours**
**Depend de : C1 (TERMINE)**
**Statut : A FAIRE — après ouverture**

### Objectif

Transformer les collections (actuellement tracks-only) en un système de curation général :
n'importe quelle entité de l'app peut être ajoutée à une collection, et les collections
peuvent être organisées en dossiers. Concept : "boards" de curation DJ (inspiration Pinterest/Rekordbox folders).

### C5.a — Items polymorphes

Actuellement `collection_items` a une FK stricte vers `catalog.id`. Migration vers un pattern
polymorphe : `item_type` (enum) + `item_id` (integer) + `item_name` optionnel (pour les entités
adressées par slug comme les genres).

- [ ] Migration Alembic : alter `collection_items` — supprimer FK `catalog_id`, ajouter `item_type VARCHAR(20)` + `item_id INTEGER` + `item_name VARCHAR(255)` nullable
- [ ] Types supportés : `track` / `set` / `artist` / `genre` / `playlist`
- [ ] Mettre à jour le router `/api/collections` : sérialisation et désérialisation par type
- [ ] Bouton "Ajouter à une collection" sur les pages : ArtistDetailView, SetDetailView, GenreDetailView, CollectionDetailView (pour les playlists/watched)
- [ ] `CollectionDetailView` : render hétérogène selon le type de chaque item (card artiste ≠ card track ≠ card set)

### C5.b — Dossiers

Ajouter un niveau hiérarchique au-dessus des collections, dans l'esprit des dossiers Rekordbox.

- [ ] Migration Alembic : nouvelle table `collection_folders` (id, user_id, name, position, created_at)
- [ ] Ajouter `folder_id INTEGER NULL` FK vers `collection_folders` sur `user_collections`
- [ ] CRUD dossiers : POST/PATCH/DELETE `/api/collections/folders`
- [ ] `CollectionsView` : affichage arborescent — dossiers dépliables avec leurs collections, collections "orphelines" (sans dossier) en bas
- [ ] UX déplacement : assigner/retirer une collection d'un dossier (simple select ou drag & drop)

### Decision produit actee

| Decision | Contenu |
|---|---|
| Intégrité référentielle | Pattern polymorphe sans FK native PostgreSQL — intégrité gérée au niveau applicatif. Acceptable à l'échelle de Diggy. |
| Dossiers | Un seul niveau (dossier > collection > items). Pas de dossiers imbriqués. |
| Visibilité | Collections et dossiers strictement privés par user (inchangé). |

### Definition of Done

```bash
# collection_items supporte track/set/artist/genre/playlist
# Bouton "Ajouter à une collection" présent sur Artist/Set/Genre/Playlist detail
# CollectionDetailView render correct pour chaque type d'item
# collection_folders CRUD fonctionnel
# CollectionsView affiche l'arborescence dossiers > collections
```

---

## D4 — Pages Detail (Vague 3 Design)

**Priorite : BAS**
**Estimation : 5-7 jours**
**Depend de : D5 (composants partages)**
**Statut : BLOQUE — en attente briefs designer pour Track/Playlist detail**

### Taches

- [ ] **Verifier FIX appliques** sur Artist Detail et Set Detail
- [ ] **Track Detail** `/catalog/:id` (quand brief livre) : Hero + StatStrip + blocs relationnels
- [ ] **Playlist Detail** `/playlists/:id` (quand brief livre) : Hero square + StatStrip + table tracks
- [ ] **Vague 5 — Admin panel** `/admin` (quand brief livre) : Refonte visuelle selon DA Wildflower

---

## Reliquats hors chantiers (opportunistes)

| Point | Quand |
|---|---|
| ~~Refonte AdminView (1725 LOC)~~ | Absorbe dans H0.d |
| Monitoring complet (Flower, UptimeRobot, pg_stat_statements) | Apres ouverture, si le besoin apparait |
| Websocket progression import | Jamais peut-etre : le polling 2s suffit |
| Tests composants frontend | Au fil de l'eau (tests integration backend dans H0.f) |
| ~~Auto-migration au deploy~~ | FAIT — `alembic upgrade head` dans deploy.yml |
| ~~`/api/radar/full` crash genres sort~~ | FAIT — `literal_column` au lieu de `StringArray[1]` |
| ~~CSP bloque requetes API~~ | FAIT — `upgrade-insecure-requests` + location priority `^~` sur `/api/` et `/storage/` |
| ~~Frontend build statique~~ | FAIT — Vite dev server → Nginx static build. Container 5 MB au lieu de 512 MB. CSP propre. |
| ~~Nginx location priority~~ | FAIT — regex `\.(jpg)$` captait `/storage/` → fix avec `^~` prefix priority |

---

## Recapitulatif de sequence

| # | Chantier | Declencheur | Depend de |
|---|---|---|---|
| C0 | Correctifs critiques + cycle de vie detections | Immediat | - |
| R1 | Responsive mobile | Immediat apres C0 | - |
| C1 | Trend v2 + velocite + Decouvrir + Collections | Apres R1 | - (velocite calculable sur l'existant) |
| C2 | Moteur de similarite + graphe artistes | Apres C1 (ou en parallele partiel) | pgvector (metadonnees verifiees OK) |
| H0 | Hygiene & Solidification | Parallelisable avec tout | Rien (audit 06/07) |
| C6 | Veille elargie & Suivi artistes | Parallelisable avec C2 | C1 (trend). C6.0 dedup prerequis a C6.a crawl |
| F5 | Import manuel (recherche externe Deezer/TIDAL) | Parallelisable avec C6/P1 | Rien (APIs deja accessibles) |
| P1 | Polish & Correctifs UI (player nav, play btns, score, genres, admin split) | Parallelisable avec C2/C6 | C1 |
| C3 | Ouverture (fermeture app + import multi-user + accueil) | Ta decision d'inviter | C1 + idealement C6 (plus de donnees) |
| C4 | Reco personnalisee | Apres ouverture | C2 + likes |
| C5 | Collections v2 (items polymorphes + dossiers) | Apres ouverture | C1 |

Notes :
- La velocite sur les ajouts (C1.b) est calculable des maintenant depuis `radar_tracks`. Seul le signal de retrait (`removed_at`) necessite d'accumuler de l'historique a partir de C0.1.
- C6 alimente directement C2 (plus de co-occurrences en set) et le trend C1 (plus de signaux). Lancer C6.0 + C6.a tot maximise les benefices pour les autres chantiers.

---

## Methode de travail

Chaque chantier suit le cycle :

1. **Brief** : ce document sert de brief — chaque section est autonome et assignable
2. **Execution** : le dev/agent execute selon le perimetre defini
3. **Review** : relecture du code + tests CI (`pytest tests/ -v`)
4. **Deploy** : `git push origin master` -> GitHub Actions -> SSH -> rebuild Docker
5. **Verification** : smoke tests VPS + validation visuelle
6. **Update** : cocher les taches dans ce document

**Commit naming** : `type(scope): description` (conventional commits)

```
fix(api): remove legacy unauthenticated radar endpoint
feat(frontend): add bottom nav for mobile responsive
feat(api): compute_trends v2 with source weighting
```

**Regles** :
- Un chantier = un delivrable deployable. On ne passe pas au suivant tant que le precedent n'est pas deploye et verifie.
- Les tests CI doivent passer a chaque commit.
- Zero couleur hardcodee dans le frontend — tout via `var(--...)`.
- Code en anglais, UI en francais.
