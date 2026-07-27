# BRIEF — Artistes (liste) `/artists` · Refonte D6, page-liste

> Maquette pilote : `Artistes (pilote).html` — toggles thème dark/light + viewport desktop/375 px dans la toolbar ; scénarios démo (`grille`, `filtre Suivis`, `filtre Suivis vide`, `toggle sans Deezer`, `recherche sans résultat`, `chargement`) et deux arbitrages DA comparables en direct (`pastilleSuivi` : toujours visible / révélée au survol · `grilleMobile` : 2 colonnes / 1 colonne) via le panneau Tweaks. **Pastille-toggle « Suivi », play, like/dislike, SegFilter, FamilyChips, recherche et toggle « sans Deezer » sont interactifs** sur les 15 cards démo.
> Liste de **~57 700 artistes** — grille de cards visuelles à infinite scroll. **Format = GRILLE DE CARTES (verrouillé)** : entité photo-driven, aucune variante tableau (contrairement aux jumelles Sets / Playlists).
> Mouvement produit : **assainissement + un ajout ciblé**, pas une refonte de paradigme. (1) retrait du **badge rating** ★ et du **badge in-lib overlay** (doublon de la stat In Lib) ; (2) ajout de la **pastille-toggle « Suivi »** dans le coin haut-gauche libéré — elle **affiche l'état ET suit/ne suit plus depuis la card** ; (3) head : tri « Rating » → filtre **« Suivis »**, plus un **toggle « sans Deezer »**. L'anatomie de la card (mosaïque + scrim teinté pilier + avatar rond + body teinté) est **gardée**.
> Cette page **ne crée aucun composant transverse** : la pastille « Suivi » est un contrôle **interne à `ArtistCard`** (comme le play et les boutons d'avis qui y vivent déjà). Elle **consomme** `<StyleTag>`, `<LikeDislike>`, `usePaginatedList` sans les modifier.
> Tout en tokens `diggy-tokens.css`, zéro couleur hardcodée. DA Wildflower v1 inchangée. Libellés 100 % français. Pas d'état invité (page authentifiée). Responsive **container queries** uniquement (`@container`, seuils 820/720/640 + container **par card** pour le body). Aucun `position: fixed` (pas de modal sur cette page).
> Placeholders du pilote : les **covers de la mosaïque** et les **photos d'artiste** sont des dégradés dérivés de `--tag-dot-*` / `--fb-*` (en prod : images réelles `top_track_artworks[]` et `/storage/artist-artworks/{id}.jpg`) ; la silhouette de l'avatar marque « photo présente », les initiales marquent `has_artwork = false`.

## Ordre vertical

1. **Head de page** — titre « Artistes » + compteur · SearchBox · SegFilter 6 segments (Catalog · In Bib · Liked · Disliked · **Suivis** · A–Z)
2. **Rangée d'outils** — FamilyChips (7 chips pilier + compteurs) · **toggle « Sans Deezer »** fer à droite
3. **Grille de cards** — `repeat(auto-fill, minmax(208px, 1fr))`, infinite scroll (sentinelle)
4. **Empty states** — chargement (skeleton de cards) · filtre / recherche vide · **filtre « Suivis » vide** (cas fréquent)

## Décisions DA explicites

| # | Décision | Justification |
|---|---|---|
| A1 | **Pastille « Suivi » = disque de 32 px dans une cible de 44 px**, coin **haut-gauche** de l'art, **toujours présente** (jamais hover-only). Non-suivi : **cloche filaire** `--overlay-text` sur disque `--overlay-soft`, **opacité 0,5 au repos → 1 au survol de la card**. Suivi : **cloche pleine** `--on-accent` sur disque **`--accent`** pleine opacité + `--shadow-sm` | Un contrôle qui **affiche un état** ne peut pas être révélé au survol : masqué, il ne dit plus rien (et l'état non-suivi — la quasi-totalité des cards — deviendrait indécouvrable, ce qui est exactement la cause du vide actuel : 3 suivis sur 57 687). L'opacité 0,5 est le compromis : la pastille **existe** sur les 15 cards de l'écran sans peser autant qu'une donnée, et se **charge au survol** de la card qu'on vise. Le suivi, rare et précieux, est le seul mauve plein de la grille → il se compte d'un coup d'œil. *(Le Tweak `pastilleSuivi` permet de comparer avec la variante hover-only : la grille devient plus calme mais la fonction disparaît.)* |
| A2 | **Iconographie = cloche** (SVG inline `currentColor` 16 px, filaire → pleine). **Pas d'étoile** (le rating vient d'être retiré : réutiliser son glyphe pour « suivre » réinstallerait la confusion qu'on supprime), **pas de « personne + »** (lu comme « ajouter à la bibliothèque », or in-lib est déjà une stat de la card) | La cloche dit **veille / nouveautés** — la sémantique exacte du follow chez Diggy : les artistes suivis alimentent le hub « Nouveautés ». Elle est **formellement disjointe** du cœur / pouce d'avis (`<LikeDislike>`) : deux glyphes, deux emplacements (art vs body), deux couleurs (mauve accent vs vert prairie / terracotta). C'est ce qui rend lisible **suivi ≠ liké** quand les deux coexistent sur une même card (démo : Surgeon, suivi **et** liké) |
| A3 | **Distinction suivi / liké portée par 3 canaux simultanés** : emplacement (art haut-gauche vs body), couleur (`--accent` vs `--pos`), forme (cloche vs cœur). Le **liké** garde son expression actuelle : **halo positif** (`border-color: --pos` + `box-shadow 0 0 0 1px --pos-soft`) + cœur rempli. Le **suivi** ne touche **jamais** la bordure de la card | Deux états décorrélés qui empruntent le même canal (la couleur de bordure) deviennent illisibles dès qu'ils cohabitent. La bordure reste au **liké** (usage déjà installé, cohérent avec la ligne likée d'Explorer / Sets / Playlists) ; le suivi vit **dans l'art**, là où il ne concurrence rien |
| A4 | **Affordance de bouton** : cible **44 px** (disque visuel 32 px centré dans un carré transparent), `cursor: pointer`, `aria-pressed`, `title`/`aria-label` explicites (« Suivre Armin van Buuren » / « Ne plus suivre… »), hover = passage à l'opacité 1 (non-suivi) ou `--accent-hover` (suivi), `:focus-visible` = outline 2 px `--accent` (`outline-offset: -6px`, dans le disque). **Feedback au clic = bascule immédiate de l'état** (bg + glyphe, transition 0,12 s) — **aucun scale, aucun bounce** | Cible tactile ≥ 44 px imposée par le DS, mais un disque **visuel** de 44 px dans une card de 208 px écraserait l'avatar : on dissocie cible et disque. Le refus du scale/bounce est une règle DA (« hover = changement de fond/bordure, transitions 0,12 s ») : l'état est le feedback, l'optimistic update suffit (POST/DELETE `/api/artists/{id}/follow`) |
| A5 | **Coin haut-droit laissé vide** après le retrait du badge rating. Rien n'y est déplacé | Une seule pastille dans un coin **se lit comme un contrôle** ; deux éléments en vis-à-vis se relisent comme les deux badges de métadonnée qu'on vient de retirer. Le vide rend aussi son air à l'avatar (44 % de la largeur de l'art) et laisse le diagonal haut-gauche → bas-droit (suivi ↔ play) comme seule grammaire de contrôles sur l'art |
| A6 | **Play conservé, révélé au survol** (disque 32 px / cible 44 px, coin **bas-droit**, `--overlay-soft` + triangle `--overlay-text`). **En lecture** : disque **`--accent`** + glyphe pause, **toujours visible**, + bordure de card `--accent` | Le play est une **action** sans état persistant → hover-reveal légitime (asymétrie assumée avec A1 : la pastille suivi, elle, porte un état). En lecture, l'état devient persistant : il sort du survol et prend l'accent, comme la rangée `is-playing` d'Explorer |
| A7 | **Anatomie de l'art gardée** : mosaïque 2×2 des covers de top-tracks · **scrim teinté par le pilier de `genres[0]`** (radial central `--hero-scrim-*` pour détacher l'avatar + linéaire vertical du pilier, 0,10 → 0,40 → 0,78) · **avatar rond centré 44 %** (anneau 3 px `--genre-tile-ink` en light / `--genre-tile-border-dark` en dark, `--shadow-md`). `tracks_with_artwork = 0` → **fallback dégradé plein `--fb-*`** au hue du pilier. `has_artwork = false` → **initiales** 700 `--fs-lg` sur disque `--tag-bg-*`, encre `--tag-fg-*` | Structure explicitement gardée (fiche §5). Le scrim vertical a été **allégé** vs l'actuel (le haut de la mosaïque était noyé) et un **radial central** ajouté : l'avatar se détache sans assombrir les covers, qui redeviennent lisibles comme identité visuelle de l'artiste. `genres` vide → pilier **« autres »**, chroma 0 : card grise, aucune teinte inventée |
| A8 | **Body = 3 étages** : nom centré 600 `--fs-title` ellipsis · rangée de 1–2 `<StyleTag>` (`min-height: 22px`) · filet `--ct-line` puis **rangée de stats** : `Catalog` + `In Lib` (label mono nano uppercase `--ink-3` au-dessus de la valeur mono `--fs-title`) à gauche, `<LikeDislike>` à droite. Fond `oklch(var(--ct-l) var(--ct-c) H)`. **In Lib > 0 → valeur `--pos-ink`**, sinon « — » `--ink-3` | Structure actuelle conservée (2 stats + avis, `nb_liked` reporté). Le `min-height` de la rangée de tags empêche la grille de **danser** quand un artiste n'a aucun genre. La seule addition : la valeur In Lib passe en vert prairie quand elle est non nulle — c'est **la** stat qui dit « cet artiste est déjà dans ma bibliothèque », et elle porte désormais seule l'information de l'ex-badge overlay retiré |
| A9 | **Filtre « Suivis » à la place du tri « Rating »** dans la SegFilter (6 segments, actif `--accent-soft` / `--accent-ink`). Le segmented control continue de mêler tris (Catalog · In Bib · A–Z) et filtres (Liked · Disliked · **Suivis**) | Décision produit figée (fiche §5). Le contrôle reste **un seul objet** parce que l'utilisateur y exprime toujours la même chose : « quelle tranche du catalogue je regarde ». Un 7ᵉ segment n'est pas ajouté et le rating disparaît de la page (badge + tri + `avg_rating`) |
| A10 | **Toggle « Sans Deezer » = interrupteur discret en fin de rangée FamilyChips** (`margin-left: auto`), pill 32 px : piste 26×15 px + pouce 11 px, off = `--surface` / `--line-2` / `--ink-2` / piste `--surface-3`, on = `--accent-soft` / `--accent-soft-2` / `--accent-ink` / piste `--accent`. `title` = « Restreindre aux artistes non liés à Deezer (backlog d'enrichissement) ». Off par défaut | Il est de **même rang** que le filtre pilier (il restreint le corpus), donc il vit sur la **même rangée** que les FamilyChips — pas dans le head déjà chargé (titre + search + 6 segments). Un interrupteur (et non une chip) dit qu'il est **binaire et exceptionnel** : c'est un outil de curation (534 artistes), pas une facette de navigation. Il reprend la mécanique visuelle des chips pour ne pas créer un troisième vocabulaire de contrôle |
| A11 | **FamilyChips conservés** : `Tous` + 6 piliers, chacun avec **dot au hue du pilier** (`--tag-dot-*`) et compteur mono `--fs-xs`. Actif = `--accent-soft` / bordure `--accent-soft-2` / encre `--accent-ink`. Repos = `--surface` / `--line-2` | Présence figée (fiche §8). Le dot coloré porte le pilier, l'accent porte la **sélection** : les deux couleurs ne se disputent jamais le même rôle. Le compteur en mono aligne la page sur la convention « toute donnée chiffrée est en mono » |
| A12 | **Grille dense, 2 colonnes minimum** : `repeat(auto-fill, minmax(208px, 1fr))` → `minmax(168px, 1fr)` < 720 → **2 colonnes fixes** < 640. Jamais 1 colonne (variante disponible dans les Tweaks pour comparaison) | À 375 px, une colonne unique produit des cards de ~343 px : **2 cards par écran**, la grille se transforme en flux d'images et le mode de lecture « scanner beaucoup d'artistes » disparaît. À 2 colonnes (165 px de card) la densité est tenue, et c'est le **body de la card** qui s'adapte (A13) plutôt que la grille |
| A13 | **Container query par card** (`container-type: inline-size` sur la card) : sous **190 px** de card, la rangée de stats passe en **colonne** (stats centrées, puis avis centrés) et le **2ᵉ StyleTag est masqué** | La card est un composant réutilisé à plusieurs largeurs : c'est **elle** qui doit connaître son seuil, pas la page. En dessous de 190 px, `CATALOG 190 · IN LIB 32` + 2 boutons de 28 px ne tiennent pas sur une ligne : plutôt que d'écraser les stats ou de tronquer, on empile — le genre dominant reste, le secondaire tombe (même arbitrage que la chip repliée des listes Sets / Playlists) |
| A14 | **États de card cumulables** : hover = `--shadow-md` (aucun `transform`) · liked = halo `--pos` · disliked = **card entière opacity 0,45** · suivi = pastille accent · en lecture = bordure `--accent` + play accent visible. Priorité de bordure : **en lecture > liked > `--ct-line`** | Chaque état occupe un canal distinct (ombre / bordure / opacité / pastille) → ils se **superposent sans se masquer**. Seule la bordure est disputée : la lecture (transitoire, une card à la fois) prime sur le liké (persistant, relisible dans le body via le cœur rempli) |

## Head de page

| Élément | Spec | Tokens |
|---|---|---|
| Titre | h1 « Artistes », 700 `--fs-lg` | `--font-ui` |
| Compteur | sous le titre, mono 500 `--fs-sm` `--ink-3`. Non filtré : « 57 684 artistes » · filtré : « 534 / 57 684 artistes » (`toLocaleString('fr-FR')`) | `--font-mono` |
| SearchBox | pill 264 px × 40 px, `--surface` + `--line-2`, loupe 15 px `--ink-3`, input **`--fs-input` (16 px, iOS)**, placeholder « Rechercher un artiste… », focus → bordure `--accent`. → param `q` (debounce serveur) | `--r-pill` |
| SegFilter (A9) | conteneur pill `--surface-2` + `--line`, **6 boutons 32 px** : Catalog · In Bib · Liked · Disliked · **Suivis** · A–Z. Actif `--accent-soft` / `--accent-ink` ; repos transparent / `--ink-2`. Tris → `sort=catalog|lib|alpha` · filtres → `ids`/`exclude_ids` (avis) et **`followed=true`** (Suivis) | `--fs-sm` |
| FamilyChips (A11) | 7 chips 32 px : `Tous 57 684` · `House 15 008` · `Techno 8 757` · `Trance 1 392` · `Drum & Bass 2 187` · `Hard Dance 961` · `Autres 29 379`. Dot 7 px au hue du pilier ; compteur mono `--fs-xs`. → param `family`, compteurs = `pillarCounts` | `--tag-dot-*` |
| Toggle Sans Deezer (A10) | interrupteur 32 px en fin de rangée chips (`margin-left: auto`) → param `no_deezer=true` | `--accent` |
| **Absent** | aucun badge rating, aucun tri « Rating », aucun état invité, aucun bouton « Ajouter » (les artistes ne se créent pas à la main) | — |
| Repli mobile | **< 820** : head en colonne (titre + compteur, puis search + SegFilter) ; **< 640** : search **pleine largeur**, SegFilter scrollable horizontalement (`overflow-x: auto`), chips en wrap avec le toggle en fin de dernière ligne, padding `--page-px-mobile` | — |

## `ArtistCard` — anatomie

Card : `--r-md`, `overflow: hidden`, `border: 1px solid --ct-line`, `--shadow-sm`, fond = body teinté, `container-type: inline-size`. Clic n'importe où → `/artist/:id` (`<div>` + handler, **pas un `<a>`** : les StyleTags internes sont des `<a>` → pas d'imbrication invalide). Play, pastille suivi et avis font `stopPropagation`.

| Zone | Spec | Tokens |
|---|---|---|
| **Art** | `aspect-ratio: 1/1`. Fond = fallback dégradé pilier ; par-dessus **mosaïque 2×2** si `tracks_with_artwork ≥ 1` (4 tuiles = `top_track_artworks[0..3]`, `object-fit: cover`, aucun gap) ; par-dessus **scrim** (A7) | `--fb-*`, `--hero-scrim-*` |
| **Avatar** | rond centré, **44 % de la largeur**, anneau 3 px (`--genre-tile-ink` light / `--genre-tile-border-dark` dark), `--shadow-md`. Photo `/storage/artist-artworks/{id}.jpg` si `has_artwork`, sinon **initiales** 700 `--fs-lg` sur `--tag-bg-*` / `--tag-fg-*` du pilier | `--genre-tile-*` |
| **Pastille « Suivi »** (A1–A4) | haut-gauche : bouton 44×44 transparent (offset 2 px) + disque 32 px. Non-suivi `--overlay-soft` / `--overlay-text` op. 0,5 → 1 au survol de la card ; suivi `--accent` / `--on-accent` + `--shadow-sm`. Cloche filaire → pleine, 16 px | `--accent`, `--overlay-*` |
| **Play** (A6) | bas-droit, même géométrie 44/32. Repos : masqué (`opacity 0`) → 1 au survol de la card ou `:focus-visible`. En lecture : `--accent` + pause, toujours visible | `--overlay-soft` |
| **Nom** | centré 600 `--fs-title` `--ink`, `nowrap` + ellipsis (démo : « Progressive Psytrance Fullon », « Armin van Buuren ») | `--fs-title` |
| **StyleTags** | 1–2 chips 22 px `<StyleTag>` centrées, dot 6 px, `--fs-xs`, `max-width: 100%` + libellé en ellipsis (le chip garde son arrondi), clic → `/style/:name` (`stopPropagation`). `min-height: 22px` même si `genres` est vide | `--tag-*` |
| **Stats + avis** (A8) | filet `--ct-line`, puis `Catalog` / `In Lib` (label 600 `--fs-nano` mono uppercase tracking 0,07em `--ink-3` ; valeur 500 `--fs-title` mono `--ink-2`, **`--pos-ink` si In Lib > 0**, « — » `--ink-3` si 0) · `<LikeDislike>` : 2 boutons ronds 28 px, cœur (`--pos` / `--pos-soft`) + pouce bas (`--neg` / `--neg-soft`), repos `--ink-3`, hover `--surface-3` | `--font-mono` |
| **Absents** | badge rating ★, badge in-lib overlay « N en bib », 3ᵉ stat `nb_liked`, bpm, key, durée, % identifié | — |

### États de card (A14)

| État | Spec |
|---|---|
| Repos | `--shadow-sm`, bordure `--ct-line`, pastille suivi à 0,5 (si non-suivi), play masqué |
| Hover | `--shadow-md` (0,12 s), **aucun transform** ; pastille suivi à 1 ; play révélé |
| **Suivi** | pastille `--accent` + cloche pleine, pleine opacité au repos. Aucun autre changement de card |
| Liked | bordure `--pos` + `box-shadow 0 0 0 1px --pos-soft, --shadow-sm` (hover : `--shadow-md`), cœur rempli `--pos` sur `--pos-soft` |
| Disliked | card entière **opacity 0,45**, pouce `--neg` sur `--neg-soft` |
| En lecture | bordure `--accent`, play `--accent` + pause visible en permanence |
| Suivi **+** liked | les deux coexistent : halo vert **et** pastille mauve (démo : Surgeon) — le cas qui valide A2/A3 |

## Grille & scroll

| Seuil | Grille | Card |
|---|---|---|
| ≥ 820 px | `repeat(auto-fill, minmax(208px, 1fr))`, gap `--space-4`, padding `--page-px` | body sur 1 ligne de stats |
| < 820 px | idem grille ; **head empilé** | idem |
| < 720 px | `repeat(auto-fill, minmax(168px, 1fr))`, gap `--space-3` | body empilé dès que la card < 190 px (A13) |
| < 640 px | **2 colonnes fixes**, gap `--space-3`, padding `--page-px-mobile`, search pleine largeur, SegFilter scrollable | body empilé, 2ᵉ tag masqué |

**Infinite scroll** (`usePaginatedList`, pages de 24, sentinelle de fin) — conservé, non virtualisé. Note de sentinelle : mono `--fs-xs` `--ink-3` centrée. Pas de pagination, pas de tri/filtre client-side hors résolution d'avis.

## Empty states

| État | Spec |
|---|---|
| **Chargement** | 10 **cards skeleton** dans la grille exacte (art `--surface-3` + disque `--surface-2` à 44 %, puis 3 blocs de body), `ar-pulse` 1,4 s, delay +0,08 s / card |
| **Filtre / recherche vide** | centré `--space-15x` : loupe 26 px dans pastille `--surface-2` `--ink-3` · « Aucun artiste ne correspond. » 600 `--fs-md` · sous-texte `--fs-sm` `--ink-2` : « Aucun artiste ne contient « x » dans son nom. Vérifie l'orthographe ou élargis les filtres. » (recherche) / « Aucun artiste ne correspond à cette combinaison de filtres. » (filtres). **Pas de bouton** |
| **Filtre « Suivis » vide** (cas fréquent) | centré : **cloche 26 px** dans pastille **`--accent-soft` / `--accent-ink`** · « Tu ne suis aucun artiste pour l'instant. » 600 `--fs-md` · sous-texte `--ink-2` : « La pastille en haut à gauche de chaque card suit un artiste sans ouvrir sa fiche. Les artistes suivis alimentent les nouveautés du hub. » · `.btn--sm` **« Voir tout le catalogue »** (retour au segment Catalog) |

> Le seul empty state à **pastille accent + bouton** est celui de « Suivis » : c'est le seul dont la sortie est une **action à apprendre** (où est le bouton follow ?) et non un simple changement de segment. Il porte l'onboarding de la nouveauté de ce chantier — c'est aussi l'état que 100 % des utilisateurs verront au premier clic sur « Suivis » (3 suivis en prod).

## Données (`GET /api/artists/` — cible, exhaustif)

`{ items[], total, pillarCounts }`, paginé (24). Item : `id` · `name` · `has_artwork` · `nb_catalog` · `nb_lib` · **`following` (NOUVEAU)** · `genres[]` `{name, pillar, depth}` (**possiblement vide** → pilier « autres ») · `top_track_artworks[]` · `tracks_with_artwork`.
Params : `sort=catalog|lib|liked|disliked|alpha` (**`rating` RETIRÉ**) · **`followed=true` (NOUVEAU)** · `family` · `q` · `no_deezer=true`.
Actions de card : `POST` / `DELETE /api/artists/{id}/follow` (optimistic update) · avis via le store d'opinions · play = extrait aléatoire.
**Présents mais non affichés** : `avg_rating` (**retiré de la page** : badge + tri + champ) · `nb_liked` (**reporté**, pas de 3ᵉ stat). **N'existent pas au niveau card** : bpm, key, durée, % identifié, badge in-lib overlay, badge rating.

## Chantier front induit

`components/ArtistCard.vue` : retrait des 2 overlays (rating, in-lib) · ajout de la **pastille-toggle follow** (état + POST/DELETE + optimistic) · scrim allégé + radial central · `container-type: inline-size` + seuil 190 px · In Lib en `--pos-ink` si > 0.
`views/ArtistsView.vue` : SegFilter « Rating » → « Suivis » (`followed=true`) · **toggle « Sans Deezer »** (`no_deezer`) en fin de rangée FamilyChips · paliers de grille 720/640 (2 colonnes minimum) · empty state « Suivis » dédié.
Back : `following` dans `ArtistListItemOut` (LEFT JOIN `followed_artists`) · filtre `followed=true` · retrait de `avg_rating` du service/endpoint liste (chantier transverse Rating).

## Grille d'audit

Couleurs 100 % tokens · dark/light vérifiés · **accent discipliné** (pastille suivie, SegFilter/chip/toggle actifs, play en lecture — aucun autre mauve ; les hues de pilier restent la seule autre couleur sémantique, `--pos`/`--neg` réservés à l'avis et à In Lib > 0) · mono pour toute donnée chiffrée (compteur de page, Catalog, In Lib, compteurs de piliers) · `--fs-input` ≥ 16 px sur la recherche · **container queries uniquement**, aucun `position: fixed`, aucun `@media` · icônes **SVG inline `currentColor`**, zéro CDN, zéro emoji · libellés 100 % FR · **badge rating absent partout** · **badge in-lib overlay absent** (l'info vit dans la stat In Lib seule) · **pas de 3ᵉ stat** · pastille suivi **présente sur toutes les cards** et **discrète au repos** · suivi jamais exprimé par la bordure (réservée au liké / à la lecture) · cibles tactiles 44 px sur pastille et play · aucun `transform` au hover (règle DA) · `min-height` de la rangée de tags (pas de danse de grille quand `genres` est vide) · genres vide → pilier « autres » gris, aucune teinte inventée · fallback dégradé plein si `tracks_with_artwork = 0` · initiales si `has_artwork = false` · pagination absente (infinite scroll) · empty « Suivis » avec invitation + retour catalogue · jamais 1 colonne · pas d'état invité.
