# Prompt — Claude Design · Revue post-implémentation Détail genre (round UNIQUE)

> Envoyer au projet Claude Design avec les 11 captures listées en bas.
> Round unique et timeboxé : un seul aller-retour, livrable unique. C'est la DERNIÈRE page de la refonte D6 — cette revue clôt le chantier.

---

## Contexte

La refonte **Détail genre** (`/style/:genre`) que tu as spécifiée est **implémentée et déployée en prod** (commits `80285ef` refonte + `5c945ed` fix shelf Artistes + `3574e1d` tracklist bornée). Ton rôle : vérifier la conformité de l'implémentation à **TON brief** — et uniquement à lui :

- `BRIEF-genre-detail.md` (décisions DA G1–G11, hero immersif, stats secondaires + actions, shelves Artistes/Sets/Playlists, tracks, genres proches, admin, états, responsive)

La page **ne crée et ne modifie AUCUN composant transverse**. Elle consomme, sans les modifier : `<TrackCard>` ligne, `<Artwork>`, `<LikeDislike>`, `<PlatformLink variant="glyph">`, `<StyleTag>`, `<ExpandableShelf>`, `<ShelfCard>`, `<RelBlock>`, `<SearchBox>`, `<AdminCard>`, `BackButton`. Tout besoin local passe par un **override scopé `:deep()`** dans la vue — c'est le mécanisme prévu, pas un écart.

## Périmètre — ce que tu juges

**Canal visuel (11 captures jointes)** : fidélité de la mise en forme au brief et à la maquette pilote —
- **Hero immersif** (G1–G6) : bande 340 px (288 < 640), mosaïque 3×2 (2×3 < 640), les **trois couches fixes** (voile α 0.34 + teinte pilier + scrim vertical), **invariance dark/light** du scrim, label pilier (point teinté / gris pour « autres »), titre fluide `cqw` **2 lignes max jamais tronqué par ellipsis**, stats clés TRACKS · ARTISTES · BPM (mono, « — » si BPM absent), cluster avatars 40 px `−12 px` ring 2 px + « +N », play rond 56 px « verre » → hover accent.
- **Stats secondaires + actions** (G4) : En bib (`--pos-ink` si > 0, « — » sinon) · Sets · Playlists à gauche ; « Écouter un aperçu » (**seul `.btn--accent`**) + `<LikeDislike>` genre à droite.
- **Shelves** : Artistes ronds 72 px + « N tracks » + « N en bib » ; Sets pied **« NN % de ce genre »** hairline neutre (G7) ; Playlists pied **glyph source monochrome + N tracks** (G8) ; grilles 4 → 3 → 2.
- **Tracks** : en-tête (compteur + SearchBox + tri segmenté actif accent + toggle En bib) (G10) ; rangées `<TrackCard>` (cover · titre · artistes cliquables · BPM · Key accent-ink · durée) ; avis en slot `end` **hover-reveal, actif épinglé** (G9) ; « — » sur données absentes.
- **Genres proches** : chips `<StyleTag>` + « N artistes en commun ».
- Les deux thèmes, le mobile 375, le cas pilier « autres » (chroma 0), le cas genre pauvre (BPM absent, peu de covers).

**Canal code (fichier exact, sur GitHub)** :
- https://github.com/Willybi/diggy/blob/master/server/frontend/src/views/GenreDetailView.vue

Compare aux valeurs de TON brief : hero 340/288 px `--r-lg` ; mosaïque `repeat(3,1fr)/repeat(2,1fr)` (2×3 < 640) ; voile `oklch(--hero-scrim-* / 0.34)`, teinte `oklch(--tag-dot-l calc(--tag-dot-c×0.9) <hue> / 0.30)`, scrim `0.92 → 0.62 (38%) → 0.18 (74%) → 0.28` ; titre `clamp(--fs-lg, 4.3cqw, --fs-display)` `-webkit-line-clamp: 2` ; avatars 40 px `margin-left:-12px` ring `2px --genre-tile-ink` ; play 56 px `--overlay-soft` + `backdrop-blur` → hover `--accent`/`--on-accent` ; stats clés mono `--fs-md` 600 ; stats secondaires mono `--fs-sm` ; grille tracklist **`36px 1fr 44px 34px 46px 64px`** (mobile `36px 1fr 44px 34px 64px`, durée retirée) ; avis end 28 px ; shelves `cards-grid` 4/3/2 ; neighbors `minmax(196px,1fr)` ; libellés français ; **espace fine insécable avant `%` et dans les milliers** ; « — » jamais « 0–0 ».

## Périmètre — ce que tu NE juges PAS

- **Interdiction de commenter l'architecture JS, les patterns Vue, les composables, les tests, le state management, le backend** — hors de ton mandat.
- **Les composants transverses préexistants** (`TrackCard`, `Artwork`, `LikeDislike`, `PlatformLink`, `StyleTag`, `ExpandableShelf`, `ShelfCard`, `RelBlock`, `SearchBox`, `AdminCard`, `BackButton`) : design acté par les handoffs précédents — seul leur **USAGE** sur cette page est jugeable. La page les consomme SANS les modifier (contrainte dure) ; un polish local passe par override scopé `:deep()`.
- **Convention repo vs pilote** : les breakpoints s'écrivent `@container (max-width: 720px/640px)` **sans nom de conteneur** (exclusif) — convention du repo, elle PRIME sur toute variante du pilote. Pas un écart.
- Le bloc **AdminCard** (rename / merge) : hors périmètre design, gate `is_admin` interne déjà en place.
- **La donnée elle-même** (genre sans BPM, peu de covers, artistes sans photo, sets/playlists absents) : tu juges le TRAITEMENT du cas, pas la donnée. En prod, **aucun artiste des `artists[]` du hero n'a de photo sur certains genres** → le cluster peut être absent (G6) ; sur d'autres il est présent (les captures montrent le cas présent).

### Arbitrages d'implémentation ACTÉS (documentés au chantier — PAS des écarts)

1. **Tracklist bornée (D8.b, acté 2026-08-04, commit `3574e1d`)** : ton brief §Tracks spécifie « infinite scroll + sentinelle pulse `usePaginatedList` ». **Cette décision est SUPERSÉDÉE** : la tracklist est désormais un **aperçu borné (1 page de 50)** suivi d'un lien **« Voir les N autres dans Explorer »** (`/explorer?genre=`) — le scroll infini a été retiré (retour d'usage : il rendait « Genres proches » inatteignable sur les gros genres). Ne le tague PAS en écart. Le reste de §Tracks (grille, états de rangée, avis slot end, empty state) reste la référence.
2. **Shelves Sets/Playlists** rendues via `<RelBlock>` + un lien **`.load-more` accent centré** pour « Voir les N autres » (au lieu du `.btn--sm` mentionné pour `<ExpandableShelf>`) — cohérent avec le lien Explorer de la tracklist. La shelf **Artistes**, elle, utilise bien `<ExpandableShelf>`. Aperçu = 8 cards ; « Voir les N autres » n'apparaît que si `total > 8`. Choix d'implémentation acté.
3. **Play du hero** en « verre » (`--overlay-soft` + blur) → hover accent, pour préserver « un seul `.btn--accent` par page » (G5).
4. **`goToTrack` → `/catalog/:id`**, voisins → `/style/:name` : routage, pas du design.

## Livrable — `FIX-genre-detail.md` (unique)

Un tableau d'écarts, chacun tagué :
- **[visuel]** — constaté sur capture (préciser LAQUELLE, ex. « 04 »)
- **[spec]** — constaté dans le code (préciser fichier + valeur)

Colonnes : `#` · Tag · Où (capture / fichier) · **Constaté** (valeur exacte) · **Attendu** (valeur du brief, avec référence G1–G11 ou section) · Sévérité (bloquant / mineur / cosmétique).

Pas de refonte de tes propres décisions : si tu changerais un choix de TON brief aujourd'hui, note-le en « suggestion hors FIX » séparée — ce n'est pas un écart d'implémentation. Les placeholders/reliquats assumés ne sont pas des écarts.

## Captures jointes (référence pour ta lecture)

Entités de démo (choisies via SQL read-only prod) : **riche + titre long** = `Techno (Raw / Deep / Hypnotic)` (16 412 tracks, pilier techno, titre 30 c pour tester le clamp 2 lignes) ; **pilier « autres » chroma 0** = `Electronica` ; **genre pauvre / BPM absent** = `Musiques de films` (3 tracks, BPM « — », < 6 covers). Toutes authentifiées (session admin).

| # | Fichier | Contenu |
|---|---------|---------|
| 1 | `01-desktop-dark-full.png` | Page complète, genre riche, **dark** : hero → stats+actions → Artistes → Sets → Playlists → Tracks → Genres proches → Admin |
| 2 | `02-desktop-dark-hero.png` | Zoom hero dark : mosaïque 3×2, voile+teinte+scrim, pill TECHNO, titre (1 ligne à 1280), stats TRACKS·ARTISTES·BPM, cluster avatars « +N », play verre |
| 3 | `03-desktop-dark-tracks.png` | Zoom Tracks dark : en-tête (compteur + Rechercher + tri Récent·BPM·Key·A–Z + En bib), 50 rangées TrackCard (BPM · Key accent-ink · durée avec « — »), pied **« Voir les N autres dans Explorer »** (tracklist bornée D8.b) |
| 4 | `04-desktop-dark-shelves.png` | Zoom Sets + Playlists dark : Sets 8 cards + pied **« NN % de ce genre »** (G7) + « Voir les N autres » ; Playlists 8 cards + pied **glyph source + N tracks** (G8) |
| 5 | `05-desktop-dark-neighbors.png` | Zoom Genres proches dark : chips `<StyleTag>` + « N artistes en commun » |
| 6 | `06-desktop-light-full.png` | Page complète, genre riche, **light** (invariance du scrim hero, lisibilité) |
| 7 | `07-desktop-light-hero.png` | Zoom hero **light** (scrim reste sombre — invariant thème G2) |
| 8 | `08-desktop-dark-autres-full.png` | Genre pilier **« autres »** (`Electronica`) : point pill gris, **chroma 0** sur mosaïque + corps de page + chips (G11) |
| 9 | `09-desktop-dark-poor-full.png` | Genre **pauvre** (`Musiques de films`) : **BPM « — »**, EN BIB « — », < 6 covers (tuiles placeholder teintées), tracklist courte, shelves réduites |
| 10 | `10-mobile-375-dark-full.png` | Page complète **375 px** dark : hero 288 px mosaïque 2×3, **titre sur 2 lignes** (sans ellipsis), avatars sous le titre, stats gap réduit, tracklist durée masquée + play/avis toujours visibles, shelves 2 colonnes |
| 11 | `11-mobile-375-light-full.png` | La même, **light** |
