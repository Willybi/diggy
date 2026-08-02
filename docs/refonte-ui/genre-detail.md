# Détail genre — `/style/:genre`

Statut : ✅ figé  |  Vue : `views/GenreDetailView.vue`

> **Pré-vol chantier (2026-08-02)** — vérifications code + données prod, arbitrages William :
> - Dette « Admin non gardé » **obsolète** : `AdminCard` gate déjà `is_admin` en interne. Reste le **déplacement en bas** de page (structure §5).
> - « Composant de rangée partagé (Explorer) » = **`<TrackCard>`** (la rangée Explorer est inline `xp-row`, non extraite) : couvre cover+in-lib, titre, `artists[]` cliquables (fallback chaîne plate intégré), BPM, Key, durée, play — **aucune modif de TrackCard**.
> - **Avis sur les rangées tracklist : OUI** (tranché 2026-08-02, cohérence Explorer) — `<LikeDislike>` via le slot `end` de TrackCard.
> - **Back lot 0 confirmé** (le §6 « rien de bloquant » était contredit par le recap C4) : `GET /api/genres/tracks/{name}` renvoie `artist` plat → ajouter `artists[]` `{id,name}` (ordre position, via `catalog_artists`). Couverture prod mesurée : **90,3 %** des entrées catalog (191 572/212 179).
> - **Badge source des cards Playlists → glyph `<PlatformLink variant="glyph">`** (tranché 2026-08-02, convention transverse /playlists du 26/07) — remplace le badge texte deezer/spotify/tidal.
> - Badge % des cards Sets = part des tracks du set dans CE genre — **variable en prod** (20–96 % mesuré) : gardé, pas de piège type /sets.
> - Edge case données : **2 genres/75 sans aucun BPM** → le hero doit dégrader « 0–0 » en « — ».
> - Tracklist : l'infinite scroll actuel est fait main (IntersectionObserver inline) → migration **`usePaginatedList`** dans le chantier.
> - **Orphelins supprimés dans ce chantier** (tranché 2026-08-02) : `GenreTrackRow`, `LibDot`, `StatStrip` (plus aucun consommateur après refonte).

## 1. Ce qu'on a (actuel)

La page la **plus complète** du site (William l'aime déjà beaucoup).

**Données** : `GET /api/genres/detail/{name}` + sous-endpoints `artists / sets / playlists / tracks / neighbors`. Admin : rename / merge.

**Structure actuelle** :
1. **Hero mosaïque** 3×2 (6 artworks **teintés par pilier**) + scrim + **avatars** (top 3 artistes) + **play** (au hover). Titre + pilier **en dessous** (hero-body).
2. **Actions** : Écouter un aperçu · **Tout filtrer dans Catalog** (→ `/catalog?genre=`) · LikeDislike.
3. **StatStrip** : Tracks · Artistes · BPM range · En bib (+ Sets · Playlists si présents).
4. **Admin** (rename / merge) — **visible par tous**.
5. **Shelves** : Artistes (round) · Sets (badge **ring % couverture**) · Playlists (source badge). Load-more.
6. **Tracks** : header (count + SearchBox + sort Récent/BPM/Key/A–Z + toggle **En bib**) + **infinite scroll** (`GenreTrackRow` bespoke).
7. **Genres proches** (neighbors) : chips « N artistes en commun ».

**Dette** : Admin non gardé (`is_admin`) · `GenreTrackRow` bespoke (≠ Explorer / `<TrackCard>`) · titre **sous** le bandeau (pas immersif) · bouton « Tout filtrer dans Catalog » potentiellement redondant.

## 2. Vision (William)

- Un des visuels les plus complets, **déjà très aimé**.
- **« Tout filtrer dans Catalog »** : à enlever (selon William).
- **Agrandir le bandeau** du haut et écrire les détails **par-dessus** (immersif, comme les autres détails).
- Sections **Artistes / Sets / Playlists** : bien.
- Section **Tracks** : à revoir les infos affichées → **comme Catalog/Explorer mais sans la colonne genre** (on est déjà dans un genre).

## 3. Revue de cohérence (Claude)

**Structure proposée** :
1. **Hero immersif** — mosaïque **agrandie**, **titre + pilier + stats clés écrits par-dessus** (Tracks · Artistes · BPM range), avatars, play.
2. **Actions** : Écouter un aperçu + LikeDislike. **« Tout filtrer dans Catalog » retiré**.
3. **Shelves** Artistes / Sets / Playlists — gardés.
4. **Tracks** : rangées alignées sur **Explorer, colonne genre en moins** (cover + **in-lib**, titre, artiste, BPM, Key, durée, play) → réutilise le composant de rangée Explorer / `<TrackCard>` + `<Artwork>`. Garde search + sort + toggle En bib + infinite scroll.
5. **Genres proches** — gardés.
6. **Admin** → `is_admin`.

**Keep / Improve / Remove**
- ✅ **Garder** : hero mosaïque, shelves artistes/sets/playlists, tracks (search/sort/lib/scroll), genres proches, like, aperçu.
- ➕ **Améliorer** : **hero immersif** (titre + stats par-dessus) ; `GenreTrackRow` → **composant partagé** (Explorer sans la colonne genre) + `<Artwork>` in-lib.
- ➖ **Retirer** : **« Tout filtrer dans Catalog »** ; Admin → `is_admin`.

**Mon avis sur le bouton** : d'accord pour le **retirer**. La page **est** déjà la vue du genre (avec sa propre section tracks complète : search + sort + lib + scroll) ; le filtrage avancé par genre est couvert par le **filtre genre d'Explorer**. Le bouton duplique un chemin et ajoute du bruit.

**Réponses (William)** : 1. ✅ retrait confirmé · 2. ✅ Explorer sans genre · 3. ✅ stats bandeau = Tracks · Artistes · BPM range.

## 4. Ré-allocation des points retirés
- **« Tout filtrer dans Catalog »** → retiré, non ré-alloué (le filtre genre d'Explorer couvre).
- **Admin** → restreint `is_admin` (reste sur la page).
- Rien à déplacer vers d'autres pages.

## 5. Décisions figées
- **Structure** : Hero immersif → Actions → Shelves (Artistes / Sets / Playlists) → Tracks → Genres proches → Admin (`is_admin`).
- **Hero immersif** : mosaïque **agrandie**, **titre + pilier + stats par-dessus** (**Tracks · Artistes · BPM range**), avatars, play ; le reste des stats (En bib / Sets / Playlists) en petit dessous.
- **Actions** : Écouter un aperçu + LikeDislike. **« Tout filtrer dans Catalog » retiré.**
- **Shelves** Artistes / Sets / Playlists : gardés.
- **Tracks** : rangées = **Explorer sans la colonne genre** (cover + in-lib, titre, artiste, BPM, Key, durée, play) via le **composant de rangée partagé** + `<Artwork>` ; garde search + sort + toggle En bib + infinite scroll.
- **(recap C4)** : la tracklist doit recevoir des **artistes structurés** — l'endpoint genre/tracks envoie une **chaîne plate** aujourd'hui → liens multi-artistes morts ; le passage au composant Explorer ne les répare que si le back renvoie `artists[]`.
- **Genres proches** : gardés.
- **Admin** → `is_admin`.

## 6. Sortie next-step
**Handoff Design**
- [ ] Hero immersif (mosaïque agrandie + overlay titre / pilier / stats).
- [ ] Rangées Tracks = variante Explorer sans genre (composant partagé).

**Chantier work_manager**
- **Front** : hero immersif ; **retrait** du bouton « Tout filtrer dans Catalog » ; `GenreTrackRow` → composant de rangée Explorer (sans genre) + `<Artwork>` ; **`is_admin`** sur l'Admin.
- **Back** : rien de bloquant (endpoints genres déjà en place).
- **Transverse** : composant de rangée Explorer / `<TrackCard>`, `<Artwork>`.

**Dépend de** : composant de rangée partagé (Explorer). Sinon autonome.

## 7. Handoff (2026-08-02)

Livré par Claude Design, versionné dans [`handoff-genre-detail/`](handoff-genre-detail/) (BRIEF + README de provenance ; conformité PASS, aucune donnée inventée, tokens 25/25 vérifiés). Décisions DA principales du round unique :
- **Hero** : bande 340 px (288 < 640), 3 couches (voile α 0.34 + teinte pilier + scrim vertical) → contraste garanti dark/light ; titre échelle fluide `cqw` **2 lignes max, jamais d'ellipsis 1 ligne** ; stats clés Tracks·Artistes·BPM dans l'overlay, calage bas.
- **Stats secondaires (En bib · Sets · Playlists) fusionnées avec la ligne d'actions** — la StatStrip disparaît sans équivalent réinventé.
- **Badge % des cards Sets** : quitte l'image (et ses seuils colorés 80/45) → **pied de carte** « `NN %` de ce genre » mono neutre (aligné footer SetCard ; libellé anti-ambiguïté avec « % identifiées »).
- **Avis par rangée** : slot `end` TrackCard, hover-reveal + **actif épinglé**, toujours visibles < 640/tactile (pattern transverse étendu aux rangées).
- **Play hero en verre** → hover accent (un seul `.btn--accent` par page) ; **0 avatar → cluster absent** ; **teinte pilier du corps bornée** à 520 px (« autres » = chroma 0 partout) ; empty recherche avec « Réinitialiser » ; cards Artistes gagnent la ligne « N en bib » (`inLibCount` existant).
