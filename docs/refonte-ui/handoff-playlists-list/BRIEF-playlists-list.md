# BRIEF — Playlists (liste) `/playlists` · Refonte D6, page-liste

> Maquette pilote : `Playlists (pilote).html` — toggles thème dark/light + viewport desktop/375 px dans la toolbar ; scénarios démo (`liste`, `filtre liked`, `panneau ajouter`, `panneau ajouter — erreur`, `filtre avis vide`, `chargement`), densité et visibilité du bouton Crawl (`survol` / `toujours`) via le panneau Tweaks. SegFilter d'avis, tri par en-tête, like/dislike, **bouton Crawl (déclenche la séquence live En attente → En cours → Crawlé → cooldown)** et modal Ajouter sont interactifs sur les 14 rangées démo.
> Liste des **playlists surveillées** (watchlist, ~56) — les sources externes que Diggy crawle pour alimenter le radar. Aujourd'hui : tableau dense, jumeau de la liste Sets. Mouvement produit : **garder le tableau**, l'**assainir** (retrait de l'`external_id`) et l'**enrichir** (source en logo, genre déduit, signal de cadence), passer en **infinite scroll**. Refonte de **densité / hiérarchie / enrichissement de rangée**, pas un changement de paradigme.
> **Format = TABLEAU (verrouillé, comme la jumelle Sets).** Pas de grille de cartes.
> Cette page **ne crée aucun composant transverse** : elle **consomme** `<Artwork>` (sans indicateur in-lib — une playlist n'est pas « dans la bibliothèque »), `<PlatformLink variant="glyph">`, `<StyleTag>`, `<LikeDislike>`, `usePaginatedList`. **Pas de `<ScoreRing>` / `<RingPct>`** : la colonne Tracks est un **nombre brut**, pas un ratio.
> Tout en tokens `diggy-tokens.css`, zéro couleur hardcodée. DA Wildflower v1 inchangée. Libellés 100 % français. Pas d'état invité (page authentifiée). Responsive en container queries (`@container`, seuils 720/640 + paliers intermédiaires) ; `position: fixed` seule exception (overlay du modal Ajouter).

## Ordre vertical

1. **Head de page** — titre « Playlists » + compteur factuel · SegFilter d'avis (Toutes / Liked / Disliked / À explorer) · bouton **Ajouter**. *(Pas de champ de recherche sur cette page.)*
2. **Modal Ajouter** (à la demande) — un champ URL + bouton « Ajouter » + messages d'erreur
3. **Tableau** — en-tête sticky triable + rangées enrichies, infinite scroll (sentinelle)
4. **Empty states** — chargement (skeleton) · filtre avis vide

## Décisions DA explicites

| # | Décision | Justification |
|---|---|---|
| P1 | **Genre = colonne dédiée en desktop** (entre Playlist et Créateur, 1–2 `<StyleTag>`) qui **se replie sous le titre** (chips `--fs-nano`) sous 880 px au lieu de disparaître. Genre vide → **cellule vide**, jamais de tiret | Le genre est l'enrichissement clé de la refonte : il ne doit pas être sacrifié au responsive. En colonne il est scannable ; replié il reste attaché à sa playlist. Identique à la jumelle Sets (S1) → cohérence de la paire |
| P2 | **Logo de source = glyph inline immédiatement après le titre** (`<PlatformLink variant="glyph">`, ~13 px, `--ink-3`, `currentColor`, `flex-shrink: 0`, `title`/`aria-label` « Source : Deezer »), **non cliquable**, **pas de colonne Source** | La rangée entière est un `RouterLink` → un `<a>` imbriqué serait invalide (fiche pré-vol). Le logo est un **attribut du titre** (« cette playlist vient de… »), pas une donnée à aligner : accolé au titre il se lit sans traverser la rangée, et ne coûte pas 40 px de grille. Le titre garde l'ellipsis, le logo reste visible après troncature. Remplace le badge texte `DEEZER`/`TIDAL` |
| P3 | **Ordre de rangée** : Playlist (cover + titre + logo source) · Genre · Créateur · Tracks · **Dernier crawl** · Avis. **`external_id` retiré**, aucun toggle « suivi », pas de Play/BPM/Key/rating/% identifié/in-lib | Contenu figé (fiche §5 + pré-vol). L'`external_id` (UUID) était du bruit technique pur, très visible en mobile ; sa suppression libère la 2ᵉ ligne de la cellule Playlist pour le genre replié |
| P4 | **Bloc « Dernier crawl » à géométrie variable dans une cellule de 196 px** (padding-left `--space-2`) : **rangée sans cadence → une seule ligne** `date … [Crawl à droite]`, centrée sur la ligne de base de la rangée ; **rangée avec cadence → 2 lignes.** L1 = **date relative** (mono `--fs-table` `--ink-2`) **ou** statut live qui la remplace. L2 = **pastille cadence** (gauche) + **bouton Crawl** (droite, `margin-left: auto`). En mode 1 ligne, le bouton occupe l'espace horizontal libre à droite de la date | La cellule porte 4 informations d'importance inégale : on hiérarchise par ligne **quand il y a matière à hiérarchiser**. Réserver systématiquement 2 lignes centrait un bloc de 43 px et faisait flotter la date ~13 px au-dessus de la ligne de base sur les ~3/4 de rangées sans cadence — seul élément décroché de la rangée. La ligne L2 n'est donc réservée **que si la cadence existe** ; le bouton Crawl apparaît horizontalement (jamais de reflow vertical au survol) et la **rangée à 2 lignes redevient un signal distinctif** : c'est celle qui porte une cadence |
| P5 | **Bouton Crawl révélé au survol de la rangée** (`.btn--sm`, opacité 0 → 1, 0,12 s ; visible aussi au `:focus-visible`, et **toujours visible** sous 640 px / en tactile). Pendant le **cooldown 12 h** : bouton absent, remplacé au survol par le libellé mono `cooldown 12 h` (`--fs-nano`, `--ink-3`, `title` explicatif) | 56 boutons gris permanents = le bruit exact que la refonte doit retirer ; le crawl manuel est une action **occasionnelle**. Au repos la colonne ne montre que de la donnée. Le libellé de cooldown n'apparaît qu'au survol : il **répond à l'absence du bouton** sans polluer le repos (règle : pas d'état de repli inventé, mais pas de bouton fantôme non expliqué) |
| P6 | **Statut live prioritaire** : il remplace **date ET bouton** (jamais les deux ensemble). `En attente` = point **creux** 7 px (cercle 1 px `--ink-3`) · `En cours` = point plein `--accent` **animé** (`pl-live` 1,1 s, opacité 0,35→1 + scale 0,8→1) + libellé `--accent-ink` 600 · `Crawlé` = point plein `--pos` + libellé `--pos-ink` ; puis retour à la date (+ cooldown) | Un crawl en cours est l'information la plus fraîche de la rangée : elle prend la place de la donnée qu'elle est en train de périmer. Le seul mouvement animé de la page est réservé à l'état réellement transitoire ; l'accent mauve marque l'activité, le vert prairie la réussite (duo déjà posé par like/in-lib) |
| P7 | **Pastille cadence = libellé mono nano uppercase** (`Quotidien` / `Hebdo` / `Mensuel`) dans une pill `--surface-2` / `--ink-3`, `title` = « Dernière nouveauté il y a X ». **Aucun code couleur** (pas de 3 teintes), **aucune pastille si `last_changed_at` est nul** — ~3 rangées sur 14 dans le pilote | Rappel DA : monochrome sauf l'accent. Un feu tricolore Quotidien/Hebdo/Mensuel serait la seule couleur non sémantique de la page et hiérarchiserait à tort une info secondaire. La pastille est **souvent absente** (8/56 en prod) : un libellé discret supporte l'absence sans laisser de trou, là où un point coloré aurait créé un « manque » visuel |
| P8 | **Tracks = nombre brut** mono 500 `--fs-table` `--ink-2`, **aligné à droite** (colonne 64 px, en-tête aligné droite aussi). Pas d'anneau, pas de % | Le `track_count` est le compte **source** (45 → 472), pas une proportion : un anneau mentirait sur la nature de la donnée (≠ liste Sets, S3). Alignement droit = comparaison de grandeurs en un coup d'œil (45 vs 472) |
| P9 | **SegFilter d'avis = 4 segments dans le head** (actif `--accent-soft` / `--accent-ink`) — **c'est un filtre, pas un tri**. **Tri par clic d'en-tête**, server-side, sur **Playlist (titre) · Créateur · Tracks · Dernier crawl**. Défaut = **Titre A→Z**. Genre, Cadence et Avis **non triables** | Aligné sur la jumelle Sets (S5/S6) et sur Artistes (résolution `ids`/`exclude_ids`). Défaut alphabétique (et non « dernier crawl ») parce que la watchlist est une **liste de référence** qu'on parcourt pour retrouver une source nommée, pas un flux d'actualité. En-tête actif `--accent-ink` + flèche ↑/↓ |
| P10 | **Bouton Ajouter `.btn--accent` dans le head** → **modal** (recentré desktop `--r-lg` `min(460px, 100vw − 32px)` · **bottom-sheet** `position: fixed` mobile `--r-xl` haut) : label mono uppercase, **un champ URL** 44 px mono, aide, `.btn--accent` **« Ajouter »**, 2 erreurs | Le flux est conservé (fiche §9), seul le style change ; le modal aligne la page sur sa jumelle Sets (S7) plutôt que sur un panneau inline qui repousse le tableau. Libellé « Ajouter » et non « Suivre » : le concept follow est masqué (fiche §5) |
| P11 | **Rangée `min-height: var(--row-h)`** (56 px ; compact 46 / comfy 68), padding-block `--space-2`, clic → `/playlists/:id`. **Coloration par avis conservée** : liked = `--pos-wash` (repos) / `--pos-wash-2` (hover) ; disliked = rangée **estompée** (opacity 0,45) | Infinite scroll non virtualisé → pas de hauteur fixe nécessaire ; la rangée doit pouvoir grandir quand genre + méta crawl se replient sous le titre en mobile. L'avis se lit sans regarder la colonne Avis (continuité Explorer / Sets) |
| P12 | **Column-drop** : Créateur (< 1040) → Genre replié sous le titre (< 880) → **Dernier crawl replié en méta mono sous le titre** (< 720) → 640 : pad mobile, gap `--space-2`, head empilé. Minimum garanti : **Playlist (+ genre + méta crawl) · Tracks · Avis** | Le brief suggérait de faire tomber « Dernier crawl » **en premier** : refusé. C'est le cœur de veille de la page — le laisser tomber avant le `owner` (souvent un nom de plateforme générique, « TIDAL ») ferait perdre l'information la plus utile pour garder la moins utile. À la place, la colonne tombe **en dernier avant le seuil mobile** et sa donnée **survit repliée** (`crawl il y a 14 j` / `crawl en cours` + cadence) ; le **bouton Crawl**, lui, n'est pas repris en mobile (action ponctuelle, disponible sur `/playlists/:id`) |

## Head de page

| Élément | Spec | Tokens |
|---|---|---|
| Titre | h1 « Playlists », 700 `--fs-lg` | `--font-ui` |
| Compteur | sous le titre, mono 500 `--fs-sm` `--ink-3` : « 56 playlists » (`total`, `toLocaleString('fr-FR')`) | `--font-mono` |
| SegFilter avis (P9) | conteneur pill `--surface-2` + `--line`, 4 boutons 32 px : Toutes · Liked · Disliked · À explorer. Actif `--accent-soft` / `--accent-ink` ; repos transparent / `--ink-2` (hover `--ink`). Résolution server-side `ids` / `exclude_ids` façon Artistes | — |
| Bouton Ajouter (P10) | `.btn--accent` + icône « + » 15 px | `--accent` |
| Repli mobile (< 640) | head en colonne : titre + compteur, puis rangée SegFilter (wrap), puis bouton Ajouter | — |
| **Absent** | pas de champ de recherche texte (aucune recherche sur cette page aujourd'hui) | — |

## Modal Ajouter

Overlay `--overlay-modal` (tap = fermer). Carte `--surface`, border `--line-2`, `--shadow-lg`.

| Zone | Spec |
|---|---|
| Header | « Ajouter une playlist » 700 `--fs-md` + bouton fermer 30 px (X 16 px, hover `--surface-2`) |
| Champ | label « URL DE LA PLAYLIST » (`--fs-label` mono uppercase `--ink-3`) + input **44 px mono** `--fs-input` (≥ 16 px, iOS), bg `--bg`, border `--line-2` → focus `--accent`, placeholder `https://www.deezer.com/playlist/…` |
| Aide | `--fs-xs` `--ink-3` : « Colle l'URL d'une playlist Deezer, Tidal ou Spotify. Elle est crawlée dès l'ajout et alimente le radar. » |
| Validation | `.btn--accent` **« Ajouter »** (jamais « Suivre ») |
| Erreurs | bordure `--neg` + message `--neg-ink` `--fs-xs` + icône 13 px : **URL invalide** « URL non reconnue — colle un lien de playlist Deezer, Tidal ou Spotify. » · **Doublon** « Cette playlist est déjà dans ta watchlist. » |
| Mobile | bottom-sheet `position: fixed` bas, 375 px, `--r-xl` en haut seulement |

## Tableau

CSS grid partagée en-tête / rangées.

| Zone | Spec | Tokens |
|---|---|---|
| Grille desktop (≥ 1040 px) | `minmax(0,1fr) 190px 128px 64px 196px 80px` (Playlist · Genre · Créateur · Tracks · Dernier crawl · Avis), gap `--space-3`, padding horizontal `--page-px`. **Compensation optique de la gouttière Tracks↔Dernier crawl** : Tracks est fer à droite et Dernier crawl fer à gauche, donc les deux valeurs mono se collent à la gouttière et se lisent comme un seul bloc (« 45 aujourd'hui »). Correction : `padding-right: var(--space-2)` sur Tracks + `padding-left: var(--space-2)` sur Dernier crawl → **28 px de blanc perçu** ; les 20 px rendus à Créateur (148 → 128) suppriment au passage son excès de vide (`TIDAL`, valeur la plus fréquente, fait 7 caractères) | — |
| Rangée | `min-height: var(--row-h)`, padding-block `--space-2`, border-bottom 1 px `--line`, cursor pointer, clic → `/playlists/:id`, hover `--surface-2` (0,12 s) | — |
| En-tête sticky | 36 px, `position: sticky; top: 53px` (sous la toolbar app ; **`top: 0` en prod** — pas de toolbar), bg `--bg` opaque, border-bottom `--line-2`, labels uppercase mono `--fs-label` `--ink-3` tracking 0,07em. Triables (P9) : bouton `gap: var(--space-1)` + flèche dans **son propre `<span>` en `letter-spacing: normal`** (sinon le tracking de 0,07em rejette l'espace *après* la flèche et `PLAYLIST↑` se lit collé), actif `--accent-ink` | `--fs-label` |
| **Playlist** | `<Artwork>` 44 px `--r-sm` (cover `/storage/playlist-artworks/{id}.jpg` si `has_artwork`, sinon placeholder rayé) **sans** indicateur in-lib. Titre 600 `--fs-table` `--ink` ellipsis + **logo source 13 px** `--ink-3` accolé (P2). Sous 880 px : chips genre repliés ici ; sous 720 px : méta crawl repliée ici | — |
| **Genre** (P1) | 1–2 `<StyleTag>` (`name` + `pillar` + `depth` → hue pilier, chroma décroissant avec la profondeur), clic → `/style/:name` (`stopPropagation`). Chaque chip garde son bord arrondi : `max-width: 100%` + libellé en `text-overflow: ellipsis` (jamais coupé net par la cellule). **La 1ʳᵉ chip (genre dominant) ne se comprime jamais** (`flex-shrink: 0`) — seule la 2ᵉ absorbe le manque de place. Vide → cellule vide | hue pilier |
| **Créateur** | `owner` 400 `--fs-table` `--ink-2`, ellipsis, non cliquable (ce n'est pas une entité Diggy). Valeurs réelles mêlées : nom de plateforme générique (« TIDAL », « Spotify ») ou vrai label (« Defected Records », « Armada Music », « Laeti — Deezer Dance & EDM Editor ») | `--font-ui` |
| **Tracks** (P8) | `track_count` mono 500 `--fs-table` `--ink-2`, **aligné droite**. Nullable → « — » `--ink-3` | `--font-mono` |
| **Dernier crawl** (P4–P7) | voir le détail ci-dessous | — |
| **Avis** | `<LikeDislike>` — 2 boutons ronds 28 px centrés : cœur (liked : `--pos` + bg `--pos-soft`) + pouce bas (disliked : `--neg` + `--neg-soft`) ; repos `--ink-3`, hover `--surface-3`. `stopPropagation` | — |

### Bloc « Dernier crawl » — anatomie et états

Cellule 196 px (padding-left `--space-2`). **Sans cadence** : flex **row**, `align-items: center` — L1 (date/statut, 19 px) puis L2 (bouton, `flex: 1`, contenu fer à droite) sur la même ligne, centrée dans la rangée. **Avec cadence** : flex **column** (`gap: 2px`), L1 19 px / L2 24 px réservées. Dans les deux cas les hauteurs de ligne sont réservées → **aucun décalage vertical** à l'apparition du statut live, du bouton ou du libellé de cooldown.

| État | L1 | L2 |
|---|---|---|
| **Repos, crawlable, sans cadence** (~3/4 des rangées) | date relative mono `--fs-table` `--ink-2` : « aujourd'hui » / « il y a 14 j » | **même ligne** : `.btn--sm` **Crawl** fer à droite, **révélé au survol** |
| **Repos, crawlable, avec cadence** | idem | ligne 2 : pastille cadence (gauche) · `.btn--sm` **Crawl** (droite), révélé au survol |
| **Jamais crawlée** | « jamais » mono `--ink-3` (atténué, pas de tiret) | idem (le crawl manuel est justement l'action attendue) |
| **Cooldown 12 h** | date relative (typiquement « aujourd'hui ») | cadence si présente · au survol seulement : `cooldown 12 h` mono `--fs-nano` `--ink-3` (opacité 0 au repos → 0,7 au survol de la rangée) — **pas de bouton** |
| **`En attente`** (`current_task_id` présent, tâche queued) | point **creux** 7 px (`border 1px --ink-3`) + « En attente » `--fs-table-sm` `--ink-3` | cadence seule (pas de bouton) |
| **`En cours`** (running) | point plein `--accent` **animé** `pl-live` 1,1 s + « En cours » 600 `--accent-ink` | cadence seule |
| **`Crawlé`** (done) | point plein `--pos` + « Crawlé » `--pos-ink` | cadence seule ; puis retour à la date + cooldown |
| **Cadence** (P7) | — | pill `--surface-2` / `--ink-3`, mono `--fs-nano` uppercase tracking 0,06em, 18 px de haut : `Quotidien` (< 14 j) · `Hebdo` (14–60 j) · `Mensuel` (> 60 j) ; `title` = « Dernière nouveauté il y a X ». **Absente si `last_changed_at` est nul** |

Séquence après clic sur **Crawl** (pilote fidèle au polling `useTaskPoll`) : `En attente` → `En cours` → `Crawlé` → date « aujourd'hui » + cooldown 12 h.

### États de rangée (P11)

| État | Spec |
|---|---|
| Repos | fond transparent |
| Hover | `--surface-2` 0,12 s + révélation du bouton Crawl / du libellé cooldown |
| Liked | wash `--pos-wash` (repos) → `--pos-wash-2` (hover), cœur rempli `--pos` + bg `--pos-soft` |
| Disliked | rangée entière **opacity 0,45**, pouce `--neg` + `--neg-soft` (hover restaure le fond, pas l'opacité) |

### Scroll

**Infinite scroll** (`usePaginatedList`, sentinelle de fin) — pages server-side au défilement. **Plus de pagination `‹ page/N ›`**, plus de tri/filtre client-side (corrige au passage le `limit=50` qui n'affichait que 50/56). Non virtualisé (d'où le `min-height` de P11). Sentinelle : note mono `--fs-xs` `--ink-3` centrée en fin de fenêtre.

### États page

| État | Spec |
|---|---|
| Chargement | 8 rangées skeleton **dans la grille exacte** (cover 44 + 2 lignes de titre + chip genre + créateur + nombre + bloc crawl 1 ligne + avis, blocs `--surface-2/3`), `pl-pulse` 1,4 s, delay +0,12 s / rangée |
| Filtre avis vide | centré `--space-15x` : icône liste-veille 26 px dans pastille `--surface-2` `--ink-3` · « Aucune playlist likée » (resp. dislikée / à explorer) 600 `--fs-md` · sous-texte `--fs-sm` `--ink-2` (« Tu n'as encore liké aucune playlist surveillée. » ; À explorer → « Toutes tes playlists surveillées ont déjà un avis. »). **Pas de bouton** (rien à réparer : il suffit de changer de segment) |
| *(Pas d'empty state recherche)* | aucune recherche texte sur cette page |

## Responsive — échelle de column-drop

Page `container-type: inline-size` (`container-name: pl`). **Container queries uniquement** ; padding `--page-px` → `--page-px-mobile` < 640. Pilote : 375 px.

| Seuil | Colonnes | Grille |
|---|---|---|
| ≥ 1040 px | Playlist · Genre · Créateur · Tracks · Dernier crawl · Avis | `minmax(0,1fr) 190px 128px 64px 196px 80px` |
| < 1040 px | − **Créateur** | `minmax(0,1fr) 190px 64px 196px 80px` |
| < 880 px | − Genre (colonne) → **chips repliés sous le titre** (P1), variante **nano** (`--fs-nano`, 20 px, dot 5 px — la variante `--fs-xs` / 22 px / dot 6 px reste réservée à la colonne, sinon la chip pèse autant que le titre) | `minmax(0,1fr) 64px 196px 80px` |
| < 720 px | − Dernier crawl (colonne) → **méta mono repliée sous le titre**, date **abrégée** (« crawl 14 j » / « crawl auj. » / « jamais crawlée » / « crawl en cours ») + cadence ; bouton Crawl non repris (P12) | `minmax(0,1fr) 64px 80px` |
| < 640 px | Playlist (+ genre + méta crawl) · Tracks · Avis — **avis toujours visible** (tactile), gap `--space-2`, head empilé, pad mobile | `minmax(0,1fr) 44px 72px` |

Sous 720 px le genre replié est limité à **une seule chip** (la dominante) et la méta crawl est en `nowrap` + ellipsis : rangée mobile = **3 lignes max** dans la cellule Playlist (titre + logo · chip genre · méta crawl + cadence) — l'`external_id` retiré paie exactement ce budget. Jamais de scroll horizontal ; cibles tactiles ≥ 44 px (les boutons d'avis 28 px gagnent leur cible via le padding de rangée).

## Données (`GET /api/watchlist/browse` — cible, exhaustif)

`{ total, items[] }`, pagination `limit`/`offset` + `sort` (titre / créateur / tracks / crawl) + sens + `ids` / `exclude_ids` (résolution du filtre avis). Item : `id` · `title` (nullable → fallback `external_id`) · `source` (`deezer` \| `tidal` \| `spotify`) · `top_genres[]` `{name, pillar, depth, pct}` (**possiblement vide**) · `owner` (nullable) · `track_count` (nullable) · `has_artwork` · `last_crawled_at` (nullable → « jamais ») · `last_changed_at` (nullable → **pas de pastille**) · `current_task_id` (nullable → statut live). Statut live par polling : `En attente` / `En cours` / `Crawlé`.
**Présents mais non affichés** : `external_id` (retiré), `followed` (concept « suivre » masqué), `description`, `created_at`. **N'existent pas au niveau playlist** : bpm, key, rating, % de tracks identifiées, extrait/play, indicateur in-lib.

## Revue post-implémentation

`FIX-playlists-list.md` relève 6 écarts du rendu déployé. **E1** (bloc crawl décroché) et **E2** (déséquilibre Tracks↔Dernier crawl) sont des défauts de spec de ma part : corrigés ci-dessus (P4, grille) et dans le pilote. **E6** (flèche de tri collée) est précisé dans « En-tête sticky ». **E3** (segment actif en vert), **E4** (cœur barré au lieu du pouce bas) et **E5** (chip repliée à la taille desktop) sont des écarts de l'implémentation par rapport au brief : le pilote a toujours été conforme (4 segments en `--accent-soft`/`--accent-ink`, pouce bas, chip nano sous 880 px) — cf. `FIX-playlists-list.md` pour l'arbitrage E3/E4.

## Grille d'audit

Couleurs 100 % tokens · dark/light vérifiés · accent discipliné (SegFilter actif, en-tête trié, bouton Ajouter, point `En cours` — pas d'autre mauve ; hues de pilier des StyleTags = seule autre couleur sémantique, `--pos`/`--neg` réservés à l'avis et au statut `Crawlé`) · mono pour toute donnée chiffrée (compteur, `track_count`, dates relatives, cadence, cooldown) · `--fs-input` ≥ 16 px sur le champ URL · container queries uniquement (fixed = overlay du modal seul) · logos plateforme **SVG inline monochrome `currentColor`**, zéro CDN · libellés 100 % FR · **`external_id` absent partout** · **aucun toggle « suivi »** · **aucun anneau / % sur Tracks** · genre vide → omis (pas de tiret) · **cadence absente si `last_changed_at` nul** (pas d'état de repli fabriqué) · statut live remplaçant date **et** bouton · bouton Crawl masqué pendant le cooldown 12 h · pagination absente (infinite scroll) · **aucune donnée de rangée hors de la ligne de base** (bloc crawl 1 ligne sans cadence) · ≥ 24 px de blanc entre `track_count` et la date · flèche de tri détachée du libellé · tri « Avis » et « Genre » absents · pas d'indicateur in-lib sur la cover · pas d'état invité.
