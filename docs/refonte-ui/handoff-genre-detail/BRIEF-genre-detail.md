# BRIEF — Détail genre `/style/:genre` · Refonte D6, dernière page

> Maquette pilote : `Genre Detail (pilote).dc.html` — toggles **Genre riche / Genre pauvre**, **thème dark/light** et **viewport desktop / 375 px** dans la toolbar ; cas hero (pilier forcé, mosaïque 6/4/2/0 covers, 3/2/0 avatars, BPM absent) et `is_admin` via le panneau Tweaks ; recherche, tri, toggle « En bib », play et avis (genre + rangées) sont interactifs dans la page ; nuancier (cas de mosaïque, états de rangée TrackCard, badge % Sets avant/après, glyphs de source, états page) en bas de maquette.
> Cette page **ne crée et ne modifie AUCUN composant transverse**. Elle consomme en prod : `<TrackCard>` ligne (+ extensions durée / `artists[]` livrées), `<Artwork>` (in-lib), `<LikeDislike>`, `<PlatformLink variant="glyph">`, `<StyleTag>`, `<ExpandableShelf>` / `<ShelfCard>`, `<SearchBox>`, `<AdminCard>`, `BackButton`. Tout besoin local est un **override scopé** (`:deep()`), jamais une modification de composant.
> Tout en tokens `diggy-tokens.css`, zéro couleur hardcodée. DA Wildflower v1 inchangée. UI 100 % française. Pas d'état invité (page toujours authentifiée).
> **Mise au niveau, pas refonte de paradigme** : la page est aimée telle quelle. On agrandit le bandeau et on écrit par-dessus, on aligne la tracklist sur le reste de l'app, on assainit (bouton retiré, Admin en bas, badge source en glyph). Le reste ne bouge pas.

## Ordre vertical

1. `dv-back` (← Genres)
2. **Hero immersif** — mosaïque agrandie teintée pilier + scrim + **overlay** : label pilier, titre, stats clés (Tracks · Artistes · BPM), avatars top-3 « +N », play
3. **Ligne stats secondaires + actions** — En bib · Sets · Playlists à gauche ; « Écouter un aperçu » + `<LikeDislike>` (avis sur le GENRE) à droite
4. **Artistes** — `<ShelfCard variant="round">` dans `<ExpandableShelf>`
5. **Sets** — cards + **% de ce genre** en pied de carte · **masquée si 0**
6. **Playlists** — cards + **glyph de source** · **masquée si 0**
7. **Tracks** — en-tête (compteur + SearchBox + tri segmenté + toggle En bib) puis rangées `<TrackCard>` + avis en slot `end`, infinite scroll
8. **Genres proches** — chips `<StyleTag>` + « N artistes en commun »
9. **AdminCard** (rename / merge) — **en dernier**, déjà gatée `is_admin` en interne

**Supprimé par ce chantier** : bouton « Tout filtrer dans Catalog » (non ré-alloué), **StatStrip** (absorbée par le hero), `GenreTrackRow` bespoke, `LibDot`.

## Décisions DA explicites

| # | Décision | Justification |
|---|---|---|
| G1 | **Hero = bande 340 px** (288 px < 640) `--r-lg`, mosaïque **3×2** plein-bleed (2×3 < 640) ; overlay en **colonne calée en bas** : label pilier → titre → (stats clés · play) | 180 → 340 px : assez haut pour que la mosaïque redevienne une image et pas une frise, assez court pour que les shelves restent au-dessus de la ligne de flottaison en 1440. Le calage bas met tout le texte dans la zone la plus sombre du scrim (lisibilité garantie), la mosaïque respire au-dessus |
| G2 | **Trois couches fixes sur la mosaïque, dans cet ordre** : (1) voile sombre `--hero-scrim-*` α 0.34 — unifie des covers hétérogènes ; (2) **teinte pilier** `oklch(var(--tag-dot-l) calc(var(--tag-dot-c) × 0.9) <hue>/0.30)` ; (3) **scrim vertical** 0.92 → 0.62 (38 %) → 0.18 (74 %) → 0.28 (bas de course remonté pour le haut de bande) | Le voile (1) est ce qui rend le contraste **prévisible** : sans lui, une cover blanche sous le titre casse la lisibilité. La teinte (2) reste lisible comme signal de pilier parce qu'elle est posée sur une base déjà unifiée. Tout est composé de tokens, **invariant dark/light** (le scrim est sombre dans les deux thèmes, comme le hero Artist A1) |
| G3 | **Titre `clamp(var(--fs-lg), 4.3cqw, var(--fs-display))`, 2 lignes max** (`-webkit-line-clamp: 2`, `overflow-wrap: anywhere`), `--overlay-text` + `text-shadow --genre-tile-shadow`. **Jamais d'ellipsis sur une ligne** | « Techno (Raw / Deep / Hypnotic) » tronquait à 375 px (capture 03). L'échelle fluide en `cqw` (le conteneur, pas le viewport) donne 36 px en 1080 et 22 px en 375 sans media query, et la 2ᵉ ligne absorbe les noms taxonomiques longs |
| G4 | **Stats clés dans le hero, stats secondaires dehors** : Tracks · Artistes · BPM en mono `--fs-md` 600 `--overlay-text` (labels `--fs-nano` mono uppercase `--genre-tile-ink` α 0.78) ; **En bib · Sets · Playlists** en ligne mono `--fs-sm` **sous** le hero, sur fond de page | Les trois stats du hero sont celles qu'on lit en arrivant (volume, densité d'artistes, tempo — info DJ). Les trois autres sont des compteurs de navigation : les sortir du hero évite un pavé de 6 chiffres sur image et **remplace la StatStrip** sans la réinventer |
| G5 | **Play du hero = bouton rond 56 px en verre** (`--overlay-soft` + backdrop-blur, anneau `--genre-tile-ink`), **hover → accent plein**. Il ne double PAS « Écouter un aperçu » : le bouton d'actions reste le seul `.btn--accent` de la page | Même action, deux affordances de nature différente : l'une est sur l'image (geste direct), l'autre dans la barre d'actions (libellée). En laissant le rond neutre au repos, on garde **un seul accent plein** (discipline D6) |
| G6 | **Avatars top-3 40 px, chevauchement −12 px, anneau 2 px `--genre-tile-ink`**, alignés à droite du titre (sous le titre < 640) + « +N » mono `--genre-tile-ink`. **0 avatar → cluster absent**, rien ne le remplace | Le cluster est une preuve sociale, pas une donnée : quand l'API ne renvoie que des artistes sans photo (cas réel), l'absence est préférable à un placeholder d'initiales qui ferait doublon avec la shelf Artistes juste en dessous |
| G7 | **Badge % des cards Sets descendu de l'artwork vers le pied de carte** : hairline `--line` + « `78 %` » mono 600 `--ink-2` + « de ce genre » `--ink-3`. **Plus de pastille sur l'image, plus de seuils colorés 80/45** | Aligné sur le footer `<SetCard>` d'Artist Detail (A5) : jusqu'à 8 pastilles colorées en grille = bruit, et les seuils inventaient une lecture qualitative sur une valeur qui varie structurellement (20–96 % en prod). Le libellé « de ce genre » lève l'ambiguïté avec le « % identifiées » des autres pages |
| G8 | **Source des playlists = `<PlatformLink variant="glyph">`** 13 px `--ink-3` monochrome, en pied de carte devant le compteur de tracks — remplace le badge texte coloré DEEZER/TIDAL/SPOTIFY | Convention transverse actée (26/07, liste `/playlists`). Non cliquable **par contrainte** : la carte entière est un lien, on n'imbrique pas deux ancres |
| G9 | **Avis par rangée dans le slot `end` de TrackCard** (2 boutons 28 px), **révélés au survol** ; le bouton **actif reste épinglé** hors survol. Tactile / < 640 px : **toujours visibles** | Arbitrage 2026-08-02 (cohérence Explorer) + règle transverse « un contrôle qui porte un état ne peut pas être hover-only ». Le survol garde la rangée calme dans une liste de 15 664 entrées ; l'épinglage garantit qu'un avis posé reste lisible |
| G10 | **Contrôles simples restylés, PAS la FilterBar d'Explorer** : SearchBox + segmented `Récent / BPM / Key / A–Z` (actif = `--accent` plein) + toggle `En bib` (actif = `--pos-soft` / `--pos-ink`, point plein) | Figé par la fiche. Le toggle En bib porte une sémantique de bibliothèque, pas de filtre générique → il prend le duo positif, pas l'accent ; le tri, lui, est un état d'UI → accent |
| G11 | **Teinte pilier prolongée sur le corps de page** : dégradé `oklch(var(--ct-l) calc(var(--ct-c) × C) <hue>)` → `--bg` sur 520 px derrière le contenu. Pilier **« autres » → C = 0** (aucune teinte, ni mosaïque ni corps) | Le comportement actuel est conservé mais borné : au-delà du hero la couleur s'éteint, la tracklist reste sur `--bg` neutre. « Autres » (chroma 0) traverse toute la page sans exception à écrire |

## Hero immersif

Bande `position: relative`, `overflow: hidden`, `border: 1px solid var(--line)`, `--r-lg`.

| Élément | Spec | Tokens |
|---|---|---|
| Hauteur | 340 px desktop · **288 px < 640 px** | — |
| Mosaïque | grid **3×2** plein-bleed sans gap des `artworks[]` (≤ 6) ; **2×3 < 640 px** | — |
| Tuile manquante (< 6 covers) | `linear-gradient(145deg, oklch(var(--fb-l1) calc(var(--fb-c1) × C) H), oklch(var(--fb-l2) calc(var(--fb-c2) × C) H))` + `inset 0 0 0 1px var(--ct-line)` — **teintée pilier**, jamais de trou ni de motif rayé | `--fb-*`, `--ct-line` |
| 0 cover | les 6 tuiles sont des placeholders teintés (le hero garde sa hauteur et son scrim) | idem |
| Voile + teinte + scrim | trois couches G2, ordre fixe | `--hero-scrim-*`, `--tag-dot-*` |
| Label pilier | pill `--overlay-soft` : point `--tag-dot-*` (hue pilier, chroma dégradé par `depth`) + libellé `--fs-nano` mono uppercase `--genre-tile-ink`. « Autres » → point gris (chroma 0) | invariants overlay |
| Titre | h1, échelle fluide G3, 2 lignes max | `--overlay-text`, `--genre-tile-shadow` |
| Stats clés | **TRACKS · ARTISTES · BPM**, gap `--space-8` (`--space-5` < 640) ; valeurs mono `--fs-md` 600 ; milliers séparés par une **espace fine insécable** | `--overlay-text`, `--genre-tile-ink` |
| BPM absent | **« — »** (2 genres / 75 en prod) — **jamais « 0–0 »** ; la colonne reste en place | `--overlay-text` |
| Avatars | 3 max, 40 px, `−12 px`, anneau 2 px, `+N` = `artistCount − avatars affichés`. Lien → `/artist/:id` | `--genre-tile-ink` |
| Play | rond 56 px G5, `aria-label` « Écouter un extrait aléatoire de <genre> » ; en lecture → icône pause | `--overlay-soft` → hover `--accent` / `--on-accent` |

## Stats secondaires + actions (une seule ligne)

| Élément | Spec |
|---|---|
| En bib | label `--fs-label` mono uppercase `--ink-3` + valeur mono 600 **`--pos-ink` si > 0**, « — » `--ink-3` sinon (traitement de référence des cards agrégées) |
| Sets · Playlists | même gabarit, valeur `--ink-2`. **0 → « 0 »** dans la ligne (la stat reste), mais la **section correspondante est masquée** |
| Écouter un aperçu | `.btn--accent` + triangle 15 px — **seul accent plein de la page** |
| Avis genre | `<LikeDislike>` : 2 boutons 38 px `--r-sm`, repos `--surface` / `--ink-2` / border `--line` ; liké `--pos-soft` / `--pos-ink` ; disliké `--neg-soft` / `--neg-ink`. **Toujours visibles** (portent un état) |
| RETIRÉ | « Tout filtrer dans Catalog » — non ré-alloué, le filtre genre d'Explorer couvre |

La ligne wrappe : sous 640 px, stats puis actions sur deux lignes, cibles ≥ 44 px.

## Shelves

Panneau commun : `--surface`, `1px solid var(--line)`, `--r-md`, `--shadow-sm`, padding `--space-4` ; en-tête h2 `--fs-md` 600 + compteur mono `--fs-xs` `--ink-3` ; `<ExpandableShelf>` = aperçu + `.btn--sm` « Voir les N autres » centré (comportement du composant, inchangé).

| Shelf | Contenu de carte |
|---|---|
| **Artistes** | `<ShelfCard variant="round">` : avatar 72 px (`hasArtwork=false` → initiale `--fs-md` 600 `--ink-2` sur `--surface-3`), nom `--fs-xs` 500 clamp 2 lignes, `N tracks` mono `--fs-nano` `--ink-3`, puis **`N en bib` `--pos-ink` si > 0** (ligne absente sinon). Grille `minmax(104px, 1fr)` |
| **Sets** | artwork carré (`--r-sm`, placeholder rayé si absent), titre `--fs-xs` 600 clamp 2, `playedDate` mono `--fs-nano`, pied G7 « `NN %` de ce genre ». Grille **4 → 3 (< 720) → 2 (< 640)** |
| **Playlists** | même gabarit ; titre, `owner` mono `--fs-nano` `--ink-3`, pied : **glyph source** + `N tracks` mono `--ink-2`. « Voir les N autres » **seulement si `total > 8`** (0–15 playlists en prod) |

## Tracks

En-tête sur une ligne : h2 « Tracks » + compteur mono (`trackCount` complet, pas le nombre chargé) à gauche ; outils à droite — SearchBox 210 px (`--fs-input` **16 px**, loupe 14 px `--ink-3`), segmented de tri, toggle En bib. **< 720 px : les outils passent pleine largeur** et la SearchBox devient `flex: 1`.

Rangées `<TrackCard>` ligne, gap `--space-2`, grille **`36px 1fr 44px 34px 46px 64px`** (cover · titre+artistes · BPM · Key · durée · slot end). Props : `showArtist`, `showDuration`, `artists[]` (fallback `artist` plat non cliquable ~10 %), `inLib` → `<Artwork :inLib>`, `hasPreview`. **Aucune colonne genre** (on est dans le genre).

| État | Spec |
|---|---|
| Normale | fond `--surface`, border `--line` ; titre 600 `--fs-sm`, artistes cliquables `--ink-3` → hover `--ink` + underline ; BPM mono `--ink-2`, Key mono `--accent-ink`, durée mono `--ink-2` |
| Hover | `--surface-2` + border `--line-2`, **play sur la cover** et **avis** révélés, 0.12 s |
| En lecture | tint `--accent-wash`, icône pause, hover reste `--accent-wash` |
| Likée | tint `--pos-wash` (hover `--pos-wash-2`), cœur épinglé `--pos-soft` / `--pos-ink` |
| Dislikée | rangée à `opacity: 0.5`, pouce épinglé `--neg-soft` / `--neg-ink` |
| BPM / Key / durée absents | « — » `--ink-3`, grille conservée |
| In-lib ± | pastille `<Artwork>` : point plein `--pos` / cercle pointillé `--ink-3` |
| Sans preview | aucun bouton play (ni hover, ni tactile) — les avis restent |
| `hasArtwork=false` | placeholder rayé standard |

**Pagination** : `usePaginatedList` (remplace l'IntersectionObserver inline). Sentinelle de fin = ligne mono `--fs-xs` `--ink-3` « Chargement des tracks suivantes… » en pulse 1.2 s ; elle disparaît quand tout est chargé.

**Empty state recherche** : bloc `--surface` centré, « Aucune track ne correspond. » `--fs-base` `--ink-2` + `.btn--sm` « Réinitialiser » (vide `q` et le toggle En bib). L'en-tête et ses outils **restent affichés**.

## Genres proches

En-tête h2 + compteur mono. Grille `minmax(196px, 1fr)`, gap `--space-2`. Chaque voisin = bloc `--surface` / `--line` / `--r-sm` (hover `--surface-2` + `--line-2`) contenant un chip `<StyleTag>` (hue du pilier, chroma dégradé par `depth`, « autres » gris) + « **N artistes en commun** » mono `--fs-nano` `--ink-3`. Lien → `/style/{name}`. Section masquée si aucun voisin.

## Admin

`<AdminCard>` existante, **en dernier**, gate `is_admin` interne (déjà en place — la dette « admin non gardé » est obsolète). Panneau `--surface` / `--line` / `--r-md`, micro-label `ADMIN` mono uppercase `--ink-3`, deux lignes `1fr auto` : champ nom + « Renommer », champ « Fusionner dans… » + « Fusionner ». Aucun re-design.

## États page

| État | Spec |
|---|---|
| Loading | utilitaire global `.state` : « Chargement… » |
| Genre introuvable | `.state` : « Genre introuvable. » `--ink-2` + `.btn` « Retour aux genres » |
| BPM absent | « — » dans le hero (jamais « 0–0 ») |
| < 6 covers / 0 cover | tuiles placeholder teintées pilier, hauteur et scrim inchangés |
| 0 avatar | cluster + « +N » absents |
| 0 set / 0 playlist | section entière masquée (en-tête compris) |
| Recherche sans résultat | « Aucune track ne correspond. » + Réinitialiser |
| Pilier « autres » | chroma 0 : mosaïque, point, corps de page et chips neutres |
| Invité | **n'existe pas** (page authentifiée, l'invité est confiné au Hub) |

## Responsive

`container-type: inline-size` sur `.detail-view` (max `--detail-max-w`), **container queries uniquement**, seuils **720 / 640** en `max-width`.

| Seuil | Changements |
|---|---|
| < 720 px | Sets / Playlists → 3 colonnes · outils de la section Tracks pleine largeur, SearchBox `flex: 1` |
| < 640 px | padding **horizontal seul** → `--page-px-mobile` · hero 288 px, mosaïque **2×3**, overlay `padding --space-4`, avatars **sous le titre**, stats clés gap `--space-5` · tracklist : **durée masquée** (défaut du composant), grille `36px 1fr 44px 34px 64px`, **play + avis toujours visibles** · shelves → 2 colonnes (artistes `minmax(88px, 1fr)`) · Genres proches 1 colonne |

Cibles tactiles ≥ 44 px (`--touch-min`) : rangée entière, cards, boutons d'actions.

## Grille d'audit

Zéro couleur hardcodée · dark **et** light vérifiés (overlay hero invariant : voile + scrim sombres dans les deux thèmes) · un seul `.btn--accent` sur la page · accent réservé aux états actifs (tri, lecture, Key) · `--pos` réservé à l'in-lib et au liké · mono sur toute donnée chiffrée (stats, BPM, Key, durées, %, compteurs, dates) · espace fine insécable dans les milliers et avant `%` · titre jamais tronqué par ellipsis · « — » et jamais « 0–0 » · container queries uniquement · StatStrip absente · « Tout filtrer dans Catalog » absent · Admin en dernier · badge source en glyph monochrome · aucun composant transverse créé ou modifié · zéro donnée inventée hors `GenreDetailOut` et sous-endpoints.
