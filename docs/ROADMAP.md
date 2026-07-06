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
> **Derniere mise a jour** : 2026-07-03

---

## Vision cible

Avant l'ouverture aux amis (5-10 DJs), Diggy doit offrir :
1. Une experience mobile utilisable (ils seront sur telephone)
2. Une recommandation de tendance solide, decorrellee des likes (offre par defaut des nouveaux arrivants sans historique)
3. Un moteur de similarite fonctionnel (socle de toute recommandation, avec ou sans user)
4. Une application fermee et etanche entre utilisateurs (auth obligatoire, scopes respectes)

Apres l'ouverture : la recommandation personnalisee (croisement similarite x likes), utile des un seul user et enrichie par chaque nouvel utilisateur.

Sequence : **C0 -> R1 -> C1 -> C2 + P1 -> C3 (ouverture) -> C4 -> C5**

---

## Vue d'ensemble

```
 #    Chantier                              Priorite    Estimation   Statut
----  ------------------------------------  ----------  ----------   ------
 C0   Correctifs critiques + fondations     CRITIQUE    1-2 jours    TERMINE
 R1   Responsive / Support Mobile           HAUT        3-4 jours    TERMINE
 C1   Trend v2 + Decouvrir + Collections    HAUT        5-7 jours    TERMINE
 C2   Moteur de Similarite (absorbe F3)     MOYEN       7-10 jours   A FAIRE
 P1   Polish & Correctifs UI               MOYEN       1-2 jours    A FAIRE
 C3   Ouverture aux amis                    MOYEN       5-7 jours    DECLENCHEMENT MANUEL
 C4   Reco personnalisee                    BAS         3-5 jours    APRES OUVERTURE
 C5   Collections v2 (polymorphe + dossiers) BAS       3-5 jours    A FAIRE
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
```

### Dependances

```
C0 ─────────> Tout (prerequis securite + fondations data)
R1 ─────────> C1 (mobile requis pour l'UX decouvrir)
C1 (trend) ─> C3 (reco par defaut prete avant ouverture)
C2 (simil) ─> C4 (socle de la reco personnalisee)
C3 (ouvert) = declenchement manuel (ta decision d'inviter)
C4 ─────────> C2 + C3 (similarite + likes + users)
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
- [ ] Le signal de retrait (fading) s'ajoutera quand `removed_at` aura de la profondeur
- [ ] Signal revival : badge distinct "revient" — reporte (donnees insuffisantes)

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
**Statut : A FAIRE — prochain chantier**

### Objectif

Relations de proximite entre tracks et entre artistes. C'est le socle de toute recommandation, il fonctionne avec ou sans user.

### Constats verifies (check SQL 02/07/2026, 7 335 entrees catalog)

- **pgvector absent** : passer l'image Docker a `pgvector/pgvector:pg16` + migration extension
- **Metadonnees saines** : BPM 91.6%, key 91.6% (100% source Beatport, mapping `beatport/enrich.py` intact), genres 95.2%, release_date 95.5%, label 95.5%. Couverture Beatport : 95% des tracks shared (6 723 / 7 076)
- **Trou identifie** : les 259 tracks `scope=private` (origin rekordbox) ont 0% d'enrichissement. Les tasks d'enrichissement excluent le scope private. Pour la similarite : negligeable en MVP (3.5% du catalog), fallback possible sur `user_tracks.rb_bpm` / `rb_key`

### C2.a — Preparation

- [ ] Installation pgvector (image Docker `pgvector/pgvector:pg16`) + migration `CREATE EXTENSION vector`
- [ ] Optionnel : campagne d'enrichissement ciblee sur les ~350 shared non trouvees sur Beatport

### C2.b — V1 metadonnees

- [ ] Embedding sur les champs disponibles (genre, BPM, key, label, release era)
- [ ] Fallback `rb_bpm` / `rb_key` pour les tracks private non enrichies
- [ ] Stockage pgvector, endpoint de voisinage track -> tracks similaires
- [ ] Prototype notebook d'abord (methodologie standard)

### C2.c — V2 co-occurrence

- [ ] Paires par playlist (`radar_tracks` x 29 playlists) et par set (`set_tracks`, 428 lignes) : volume modeste mais exploitable en MVP, et croissant (crawls quotidiens + futurs imports YouTube)
- [ ] Ponderation : co-occurrence en set > co-occurrence en playlist (meme logique que le trend)
- [ ] Multi-view : poids controlables metadonnees / co-occurrence

### C2.d — Graphe artistes (ex-F3, devient une vue du moteur)

- [ ] Endpoint `/api/artists/:id/connections` : sets communs (`set_artists`), collabs (`catalog_artists`), playlists partagees, similarite C2
- [ ] Composant GraphView (D3 force-directed ou vue-flow) depuis Artist Detail
- [ ] Shelves "artistes proches" sur les pages artistes

### Definition of Done

```bash
# pgvector installe et fonctionnel
# Endpoint /api/catalog/{id}/similar -> top 10 tracks similaires
# Graphe artistes accessible depuis Artist Detail
```

---

## C3 — Ouverture aux amis

**Priorite : MOYEN**
**Estimation : 5-7 jours**
**Depend de : C1 (reco par defaut prete)**
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
- [ ] Frontend build statique de prod (sortir du Vite dev server) : a faire avant d'exposer l'app a d'autres
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

- [ ] Profil de gout par user : agregation des embeddings des tracks likees (et penalisation des dislikees)
- [ ] Reco = voisinage pgvector du profil, filtre par famille/BPM, excluant la lib existante
- [ ] Surface : section "Pour toi" distincte de la section trend (les deux recos coexistent, decorrelees)
- [ ] Long terme (parque, inchange) : track2vec sur tracklists de sets, imports YouTube timestamps, V3 audio features, LLM local en normalisation

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
| Refonte AdminView (1725 LOC) | Opportuniste, pas bloquant |
| Monitoring complet (Flower, UptimeRobot, pg_stat_statements) | Apres ouverture, si le besoin apparait |
| Websocket progression import | Jamais peut-etre : le polling 2s suffit |
| Tests composants frontend | Au fil de l'eau |
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
| P1 | Polish & Correctifs UI (player nav, play btns, score, genres, admin split) | Parallélisable avec C2 | C1 |
| C3 | Ouverture (fermeture app + import multi-user + accueil) | Ta decision d'inviter | C1 (reco par defaut prete) |
| C4 | Reco personnalisee | Apres ouverture | C2 + likes |
| C5 | Collections v2 (items polymorphes + dossiers) | Apres ouverture | C1 |

Note : la velocite sur les ajouts (C1.b) est calculable des maintenant depuis `radar_tracks`. Seul le signal de retrait (`removed_at`) necessite d'accumuler de l'historique a partir de C0.1, et il s'ajoutera a la formule quand il aura de la profondeur.

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
