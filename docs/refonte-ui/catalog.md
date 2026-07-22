# Explorer — `/explorer` (ex-Catalog ; redirects `/catalog`, `/tracks`)

Statut : ✅ LIVRÉ (D6 p.1, 2026-07-21 — commits e2b90ac + FIX b8e7875/056183f)  |  Vue : `views/ExplorerView.vue` (ex-CatalogView, supprimée ; Radar extrait → page dédiée à venir, redirect temporaire `/radar` → `/explorer`)

## 1. Ce qu'on a (actuel)

**Rôle** : le tableau dense du catalog. **Deux modes dans une seule vue**, basculés par un segment Catalog / Radar (query `?view=radar`) :
- **Catalog** : la bibliothèque / tout le catalog.
- **Radar** : les tracks détectées récemment sur les playlists surveillées.

**Données** : `GET /api/catalog/` (paginé `skip`/`limit`, **PAGE_SIZE = 50**) avec params `view, in_lib, min_radar_playlists, search, sort, order, detected_after`. `PATCH /api/catalog/{id}/avis` (like/dislike). `nLib` chargé par un fetch séparé (`in_lib=true&limit=1`). 2 modals d'import.

**Colonnes** (table-layout fixed, « zone d'échange » qui swap entre modes, largeur constante) :
- Communes : Play · **Track** (artwork + titre + `ArtistLinks` + badge `#trend_rank` si ≤50) · **Style** (`StyleTag` → `/style/`) · BPM · Key · **Radar** (`ScorePill`) · **Avis** (`LikeDislike`).
- Catalog-only : **Durée** · **Rating** (étoiles) · **In lib** (`LibDot`).
- Radar-only : **Source** (badge Deezer/Spotify/Tidal + nom) · **Détecté** (relatif).

**Filtres / actions** (dans le head) :
- `SearchBox` (artiste/titre), chips **Pas dans RB** · **Radar ≥ 2** · **In lib** (persistant `sessionStorage`).
- Mode Catalog seulement : boutons **Ajouter un track** (`ExternalImportModal`, Deezer/TIDAL) + **Importer XML** (`ImportRekordboxModal`).
- Mode Radar seulement : sub-bar **Période** (24h / 7j / 30j / Tout).

**Interactions** : tri par clic sur en-tête (toggle asc/desc, défaut `nb_radar_playlists` en catalog / `detected_at` en radar) ; **pagination classique** `← page/N →` ; play preview inline ; like/dislike colore la ligne (liked = wash vert, disliked = row estompée).

**Composants** : SearchBox, ImportRekordboxModal, ExternalImportModal, ScorePill, LibDot, LikeDislike, StyleTag, ArtistLinks.

**Responsive** : masquage **progressif** des colonnes sur ~8 breakpoints (1160→dur, 1010→rating, 900→avis, 760→radar, 620→style, 560→bpm). Table `min-width: 1060px` + scroll horizontal ; `min-width: 0` sous 640. Play/avis toujours visibles au touch.

**Dette / limites (factuel)** :
- **Pagination `← →`** alors que le projet a `usePaginatedList` / `useInfiniteScroll` (utilisés par Artists/Genres) → incohérence de pattern.
- **Handler inline multi-statements** sur le bouton play (`@click="e.has_preview && player.play({...})"`) → exactement le pitfall CLAUDE.md (Prettier casse le compilo Vue). À extraire en méthode.
- **Mélange FR/EN** dans les libellés : « Catalog », « tracks in lib », « In lib » (EN) vs « Pas dans RB », « détectées », « Période » (FR) → règle « UI en français » non tenue.
- Head très chargé (search + 3 chips + 2 imports + segment) → densité.
- Modes Catalog/Radar cohabitent dans une vue via swap de colonnes → **directement lié au chantier nav** (vraie page Radar + onglet Catalog) → [TRANSVERSE.md](TRANSVERSE.md) § Navigation.

## 2. Vision (William)

- Catalog = **récap de toutes les tracks de la base** (tout ce qu'on a récupéré).
- **Outil de recherche** avec critères précis. On **éclate catalog/radar** (Radar → sa page), renommage possible.
- **Ne plus afficher les infos de trend** : juste les **données brutes** du son.
- **Filtres riches** : key (multi-select), BPM (range), durée, style, artiste, etc.
- **Garder** : like, écoute, click → page détail. Garder le **badge #rank** (léger, cool).
- **Design** : supprimer la colonne **In lib** (lourde) → indicateur sur la **cover** (point vert / cercle pointillé vide dans un coin, pas trop grand). Léger, réutilisable partout.

## 3. Revue de cohérence (Claude)

### ✅ Cohérent / à garder
- La **liste tabulaire + tri par colonne** = cœur de l'outil. On garde et on enrichit.
- **Play inline · like/dislike · click → détail** · **StyleTag → /style** · recherche titre/artiste.
- **Badge #rank** : OK — c'est le seul reliquat « trend » mais il est décoratif et léger (nécessite juste de continuer à joindre `trend_rank`, cheap).

### ➕ À ajouter
- **Barre de filtres avancés** (le gros du chantier). Proposition (à trancher) :
  - **Essentiels DJ** : BPM (range slider) · Key (multi-select, pensé harmonique/Camelot) · Style/genre (multi-select piliers + sous-genres) · Artiste (type-ahead) · In lib (tri-state tous / dans ma bib / pas dans RB — le **filtre** reste, c'est la colonne qui saute).
  - **Secondaires** : Durée (range ou presets <3 / 3–5 / 5–8 / >8 min) · Écoutable (a un preview) · Avis (liked / disliked / neutre).
  - **Avancés / plus tard** : Année (release_date range) · A une cover · Label (si dispo en base, à vérifier).
- **Sélecteur de tri explicite** (pour les dimensions sans colonne) : Récemment ajoutés (défaut) · Titre A–Z · Artiste A–Z · BPM · Key (ordre harmonique) · Durée · Release date.
- **Indicateur in-lib sur la cover** : point vert plein (in lib) / cercle pointillé vide (pas in lib), petit, en coin, lisible aussi sur le placeholder sans artwork. → **composant partagé** (voir reco).

### ➖ À retirer / déplacer
- **Tout le mode Radar** : segment Catalog/Radar, swap de colonnes, sub-bar Période, colonnes **Source** + **Détecté**, colonne **Radar (ScorePill)**, chip **Radar ≥ 2**. → page Radar dédiée.
- **Colonne In lib** → remplacée par l'indicateur cover.
- **Colonne Rating** → supprimée : le rating Rekordbox est retiré de **tout** le projet → [TRANSVERSE.md](TRANSVERSE.md) § Rating.

### ⚙️ Faisabilité & invariants
- **Impact back (assumé, feature-first)** : `/api/catalog/` gagne un query-builder — params `bpm` range, `key[]`, `genre[]`, `artist`, `duration`, `has_preview`, `avis`, `release` range + index (bpm, key, duration_ms, release_date). Genre via `TEXT[]`/graphe, artiste via join `catalog_artists`, avis via join `user_opinions`. Non bloquant.
- **Invariant C3** : la query doit garder `catalog_visible(user_id)`.
- 💡 **Filtres synchronisés dans l'URL** (query params) → recherche bookmarkable, survit au refresh, partageable. Aujourd'hui seuls `view`/`inlib` y sont.
- 💡 Profiter du chantier : pagination → **infinite scroll** (`usePaginatedList`) ; corriger le **handler inline** du play (pitfall Prettier/Vue) ; nettoyer les **libellés en FR**.
- ⚠️ **Mobile** : multi-select + range sliders → prévoir un **drawer/feuille de filtres** (Design).

## 4. Ré-allocation des points retirés (proposition)
- **Mode Radar** (segment, swap, Période, Source, Détecté, ScorePill, chip Radar ≥ 2) → **nouvelle page Radar dédiée** (= aussi la cible « voir plus » du Hub). → ajoutée au registre, spec détaillée avec le chantier nav ([TRANSVERSE.md](TRANSVERSE.md) § Navigation).
- **Colonne In lib** → transformée en indicateur cover (pas ré-alloué : supprimé/transformé).
- **Boutons Import** (Ajouter un track / Importer XML) → **restent sur Catalog** (ils alimentent la base) mais rangés dans un menu « + » pour désencombrer le head qui accueille désormais les filtres.

## 5. Décisions figées
- **Nom** : « Catalog » → **Explorer** (FR). Route `/explorer` (redirects `/catalog`, `/tracks`). Route de la fiche détail track réglée sur sa propre page.
- **Rôle** : moteur de recherche sur la **base brute** ; plus d'infos trend affichées, **sauf le badge #rank** (léger, conservé).
- **Radar éclaté** → **page dédiée `/radar`** (spec avec le chantier nav).
- **Filtres retenus** : BPM (range) · Key (multi-select) · Style (multi-select) · Artiste (type-ahead) · In lib (tri-state tous / ma bib / pas dans RB) · Durée · Écoutable · Avis · Année (release_date) · Label (dispo en base — vérifié au pré-vol 2026-07-20). **Écarté (arbitrage 2026-07-20)** : « a une cover ». **Rating supprimé.**
- **Tri par défaut** : **Récemment ajoutés** (`created_at`). Autres : Titre · Artiste · BPM · Key · Durée · Release date.
- **In lib** : colonne supprimée → **indicateur sur la cover** (composant `<Artwork>` partagé → TRANSVERSE).
- **Filtres synchronisés dans l'URL** (query params) → recherche bookmarkable/partageable.
- **Conserve** : play, like/dislike, click → détail, StyleTag → /style, badge #rank.
- **Imports** (Ajouter un track / Importer XML) : conservés, rangés dans un menu « + ».
- **Scroll** : **infinite scroll virtualisé — windowing dès le départ** (`usePaginatedList` pour le fetch + rendu virtualisé, seules les lignes visibles rendues → encaisse les listes non filtrées).
- **Filtres dans l'URL** : ✅ confirmé (partage / favori / refresh-safe / back-forward).
- **Nettoyage** : fix du **handler inline** play ; **libellés en FR**.
- **Transition (arbitrage 2026-07-20)** : Explorer est livrée AVANT la page Radar — **gap assumé** : `/radar` et `?view=radar` redirigent temporairement vers `/explorer` jusqu'à la livraison de la page Radar (livrable suivant). Le badge new-count (porté par l'entrée Hub du BottomNav) est inchangé.
- **Décisions handoff (round unique 2026-07-21 — référence : `handoff-explorer/`, décisions DA E1-E13)** : Durée = **presets single-select** (pas de range) · recherche texte = 1er contrôle de la **barre de filtres** (plus dans le head) et **étendue au label** (impact back : `search` titre+artiste+label) · Avis filtrable en 4 options dont **« Sans avis »** (impact back : `avis` accepte l'absence d'avis) · **Artiste multi-sélection** (impact back : plusieurs ids) · panneau de filtres **inline** (pousse la table) + **chips actives permanentes** = représentation canonique de l'état URL · Key = **grille Camelot 12×2** · colonne Style = 1 `StyleTag` + « +N » (garantit la hauteur de rangée constante) · column-drop **4 paliers** (1000/860/700/640) · **tri mobile absent en v1** (< 640 px, ordre par défaut — reliquat ROADMAP, le tri rejoindra le drawer).

## 6. Sortie next-step
**Handoff Design**
- [ ] Barre de filtres (multi-select, range slider BPM, type-ahead artiste) + **drawer mobile**.
- [ ] Indicateur in-lib sur la cover → composant `<Artwork>` (TRANSVERSE).
- [ ] Menu import « + ». Libellés FR.

**Chantier work_manager**
- **Back** : query-builder `/api/catalog/` (params filtres + index), tri `created_at`, **garder `catalog_visible`**.
- **Front** : renommage Explorer + route ; barre de filtres **URL-syncée** ; **infinite scroll virtualisé (windowing)** ; `<Artwork>` + indicateur lib ; retrait colonnes In lib / Rating / Radar / Source / Détecté ; fix handler play ; libellés FR.
- **Transverse** : `<Artwork>` · suppression Rating projet · page Radar (nav).

**Dépend de** : rien de bloquant. Pré-vol 2026-07-20 : `<Artwork>` + indicateur in-lib DÉJÀ livré (D4 Track Detail — le « à créer » de TRANSVERSE est obsolète) ; `in_lib` tri-state et filtre `avis` déjà supportés par l'API ; key stockée en Camelot (`1A`…`12B`) ; `label` dispo en base ; aucun index sur bpm/key/duration_ms/release_date/created_at (à poser au lot back) ; tri `created_at` absent de l'API (à ajouter — c'est le futur défaut). Nav : renommage figé ici ; la place de Radar se cadre à la page suivante (gap assumé, voir §5). Suppression Rating : la part catalog (colonne UI + champ/tri API) part dans CE chantier, le reste (artistes, import XML, drop colonne DB) suit page par page.
