# BRIEF — Hub / accueil `/` · Refonte D6

> Maquette pilote : `Hub (pilote).html` — toggles thème dark/light + viewport desktop/375 px dans la toolbar ; sélecteur d'écran (Connecté · Invité · Recherche · Rech. invité · Nuancier) et panneau Tweaks (`demo` : Normal / Étagères en chargement / Ça sort vide / Aucun résultat ; `densité`). Le dropdown de scope, les chips « Essaie », les `FamilyChips` de « Ça sort » (filtrage réel des 9 cartes), le bouton play (hover desktop, toujours visible < 640), la carte album dépliable et le tri des résultats sont interactifs.
>
> **Rôle de la page** : porte d'entrée de l'app **+** moteur de recherche global. C'est la **seule** page à double état (toutes les autres pages internes sont authentifiées) :
> - **État vide** (champ vide) = accueil : hero + search + Essaie + étagères de découverte.
> - **État recherche** (champ rempli) : liste de résultats unifiée typée.
>
> Et le **seul** écran qui gère **deux publics** : **invité** (pas de sidebar, confiné au Hub, funnel de conversion) et **connecté** (3 étagères + tri).
>
> **C'est une REFONTE** : la page existe, les données sont servies (une seule évolution back : `release_date` sur `TrendItem`). On réorganise l'état vide, on enrichit les cartes, on unifie les icônes, on polit l'ensemble. **Périmètre : contenu du Hub uniquement** — le shell (sidebar, BottomNav, PlayerBar) est **hors périmètre**, ne pas le designer. Le logo est **hors périmètre** (transverse) : le glyph « D » dans un carré accent reste tel quel.
>
> Tout en tokens `diggy-tokens.css`, zéro couleur hardcodée. DA Wildflower v1 inchangée. Icônes **SVG inline `currentColor`** (l'accent mauve = seul signal coloré ; les dots de pilier gardent leur teinte). Libellés 100 % français. Chiffres et données (BPM, key, âges, compteurs, ranks) en **`--font-mono`**.

## Décisions produit figées (rappel — actées Phase 0, pas à rediscuter)

1. **Genres populaires : bloc SUPPRIMÉ** du Hub (état vide maîtrisé). Entrée par genre couverte par « Essaie », le scope `genre` et la page Genres.
2. **« Essaie » déplacé juste sous la search bar** (amorces de recherche → avec l'input). Nouvelle **icône flèche** SVG (fin du `↳` CSS). Seul bloc d'amorces de l'état vide.
3. **« Ça sort en ce moment »** : aperçu **top 9** (grille 3×3) + **« Voir plus » → `/radar`** ; **invité → `/login`**. Étagère + `FamilyChips` visibles aux invités ; ouvrir une carte en invité → login.
4. **« Pour toi »** : aperçu top 9 (connecté) + **« Voir plus » → `/radar`** (colonne Pour toi).
5. **« Nouveautés de tes artistes »** : aperçu (connecté) + **« Voir plus » DÉSACTIVÉ** (état inerte, libellé « Bientôt ») — `/new-releases` n'existe pas encore.
6. **Cartes enrichies** : **BPM · KEY · âge** en **ligne mono compacte** sur les 3 étagères, dégradée proprement.
7. **Search bar — dropdown de scope** : icônes **unifiées en SVG** (fin des emoji) + **compteur par scope** en état recherche.
8. **Logo hors périmètre.** Glyph « D » inchangé.
9. **Parcours invité = funnel voulu** : montrer librement le contenu, gater le « voir plus » et les actions profondes derrière le login.
10. **Libellés 100 % FR.** Rating (étoiles Rekordbox) absent du Hub.

## Décisions DA explicites

| # | Décision | Justification |
|---|---|---|
| H1 | **Carte de découverte = horizontale** (cover 64 px carrée à gauche, corps à droite sur 3 lignes : titre, artiste, méta mono). Grille `repeat(3, 1fr)` desktop → 2 col < 720 → 1 col < 640 | L'horizontale **cohabite nativement** avec la carte album dépliable (même en-tête horizontal + chevron) ; les 3 lignes accueillent la méta `BPM · KEY · âge` sans cramper la verticale ; en 1 colonne mobile la carte reste dense et lisible. Une carte verticale aurait imposé un ratio cover fixe et un empilement plus haut, incompatible avec l'album dépliable dans la même grille |
| H2 | **Méta = ligne mono compacte** `BPM · KEY · âge`, séparateur ` · `, `white-space:nowrap` + ellipsis. Ordre de dégradation quand la place manque : **âge** tombe (ellipsis) avant KEY avant BPM. Champs absents omis (pas de tiret) : set sans BPM/KEY → méta = âge seul ; carte sans preview/cover → méta présente si BPM/KEY/âge existent | Une ligne façon `.rmeta` charge moins qu'un empilement de 3 lignes (carte compacte, surtout mobile 1-col). BPM/KEY sont l'info de mix la plus actionnable → survivent le plus longtemps ; l'âge est contextuel |
| H3 | **Âge = token brut** sur la carte : `6 j` / `2 sem` / `3 mois` (dérivé de `relativeAge`), **sans** le préfixe « Sorti il y a… ». Ce dernier (verbeux) reste réservé aux contextes moins denses (listes larges, pages détail) | Sur une ligne mono à 3 champs, « Sorti il y a 3 sem » mange toute la largeur et tronque en milieu de mot. Le token brut lit clairement comme une donnée (mono, entre séparateurs) et tient à côté de BPM/KEY |
| H4 | **Badge de carte contextuel** : « Ça sort » → pill `#rank` (`--accent-soft`/`--accent-ink` mono) ; « Nouveautés » release/lien externe → pill **« Nouveauté »** (accent, + glyph externe pour le lien) ; set → pill **« Set »** (`--surface-2`/`--ink-2` + glyph disque) ; « Pour toi » → **pas de badge** | Le badge dit la nature de la carte d'un regard. `#rank` = signal accent (viralité) ; « Nouveauté »/« Set » = typage du feed hétérogène ; la reco n'a pas besoin de badge (le contexte de l'étagère suffit) |
| H5 | **Indicateur in-lib** en coin de cover (point plein `--pos` = dans Rekordbox / cercle pointillé `--ink-3` = absent), via `<Artwork>`. Affiché sur **« Pour toi »** ; absent de « Ça sort » et « Nouveautés » (data `in_lib` non renvoyée par ces endpoints) | Décision transverse `<Artwork>` : info légère et universelle. On ne l'affiche que là où la donnée existe — pas de faux indicateur |
| H6 | **Bouton play sur la cover** : cercle 32 px centré, révélé au survol desktop (`opacity` 0→1), **toujours visible < 640 px** (tactile). Playing → cercle `--accent`/`--on-accent` + scrim `--overlay-soft` + icône pause. `has_preview=false` (set, lien externe) → **pas de bouton** | Cohérent avec le play hover-reveal du reste du repo ; le scrim au repos reste transparent (la cover respire), n'apparaît qu'au survol/lecture pour lisibilité de l'icône sur artwork |
| H7 | **« Voir plus » à 3 états** dans l'en-tête d'étagère : **actif** (lien `--accent-ink` + chevron, → `/radar` ; invité → `/login`) · **désactivé** (Nouveautés : `--ink-3` opacity 0.55, `cursor:not-allowed`, libellé **« Bientôt »**, `aria-disabled`, aucun lien mort) | Les 3 en-têtes gardent la même structure (cohérence visuelle) mais l'inerte de Nouveautés est **lisiblement** neutralisé, pas un lien cassé |
| H8 | **`FamilyChips` sous « Ça sort » uniquement** : rangée de pills (`Tous` + 6 piliers) ; sélectionnée = `--accent`/`--on-accent`, inactive = `--surface` + dot pilier (`--tag-dot-*`) + count mono `--ink-3`. Filtre l'aperçu ; famille à 0 → **état vide** de l'étagère (message + chips conservées) | `family_counts` n'est renvoyé que par `trends` ; les chips sont un affinage de tendances, pas un filtre global. La couleur de pilier reste le seul écart au monochrome (invariant DS) |
| H9 | **Search bar centrale, pill 56 px** : dropdown de scope à gauche (SVG + compteurs en recherche), loupe, champ `--fs-input` (≥ 16 px), bouton clear. **Focus ring** : `focus-within` → border `--accent` + `0 0 0 3px --accent-wash` | La search bar est l'élément central de la page. Le ring accent discret signale le focus sans casser la forme pill |
| H10 | **État résultats : POLI, pas réinventé** (cf. périmètre). Liste `rrow` typée conservée à l'identique fonctionnellement : colonne type (icône SVG + libellé), `<Artwork>`, highlight du terme, méta, badge source, zone in-lib, tri (connecté), lock-row (invité) | Le point neuf de la recherche = les **compteurs de scope** (H7 du prompt), qui vivent dans le dropdown. La liste elle-même est déjà bonne : on harmonise typo/espacements/tokens |

## Ordre vertical (état vide)

1. **Top bar** (sticky, dans le périmètre page) — voir §Top bar
2. **Hero** — glyph « D » + « Diggy » `--fs-hero` + tagline mono ; centré
3. **Search bar** — dropdown scope + champ + clear ; centrée max 760 px
4. **« Essaie »** — label mono + chips d'amorces (juste sous la search bar)
5. **Étagères** — Ça sort (+ FamilyChips) · Pour toi · Nouveautés (connecté) ; Ça sort seule (invité)

En **état recherche** : top bar (brand compact) → search bar (remplie, compteurs) → en-tête résultats (compteur + tri) → liste typée (+ lock-row invité).

## Top bar (sticky)

| Contexte | Contenu | Tokens |
|---|---|---|
| **État vide** (co & invité) | Brand **absent** de la top bar (le hero porte la marque) ; à droite seulement : **invité** → `Créer un compte` (`.btn--ghost-accent`) + `Se connecter` (`.btn--accent`, glyph login) ; **connecté** → pastille user (avatar initiale `--accent-soft`/`--accent-ink` + `williambienvenu`) | fond `--bg`, border-bottom transparente (fond dans le hero) |
| **État recherche** | Brand **compact à gauche** (glyph « D » 34 px `--accent`/`--on-accent` + wordmark « Diggy » `--fs-md` 700) — le hero disparaît, la marque remonte ici ; à droite : mêmes CTA invité / pastille connecté | border-bottom `--line` |

> Le glyph « D » est le placeholder brand figé (logo = transverse). Ne pas concevoir de nouveau logo.

## Hero (état vide)

| Élément | Spec | Tokens |
|---|---|---|
| Glyph | carré 56 px `--r-md`, « D » 700 `--fs-display` | `--accent` / `--on-accent` |
| Wordmark | « Diggy » 700 `--fs-hero`, letter-spacing −0.01em | `--ink` |
| Tagline | « Cherche un track, un set, un artiste, une playlist ou un genre — et écoute l'aperçu. » mono `--fs-md` `--ink-2`, max 34ch, `text-wrap:pretty` | `--font-mono` |

Mobile < 640 : réduire (le glyph + wordmark restent en ligne ; la tagline wrappe).

## Search bar

| Élément | Spec | Tokens |
|---|---|---|
| Conteneur | pill 56 px, `padding --space-1`, `display:flex`, `focus-within` → ring accent (H9) | `--surface`, border `--line-2`, `--r-pill`, `--shadow-sm` |
| Dropdown scope | bouton (icône SVG du scope + libellé + chevron), séparateur vertical `--line` ; ouvre un `listbox` (H7) | libellé `--fs-sm` 600 `--ink` |
| Loupe | `<use #s-search>` 18 px `--ink-3` | — |
| Champ | `--fs-input` (≥ 16 px iOS), placeholder « Rechercher dans tout Diggy… » | `--ink` |
| Clear | bouton rond 36 px (`--ink-3`, hover `--surface-2`), visible si champ rempli | `<use #s-x>` |

### Dropdown de scope (H7 — le point neuf)

- **Icônes SVG unifiées** (fin des emoji `⊕ ♫ ● ◎ ☰ ◆`), monochrome `currentColor`, lisibles à 14–16 px et réutilisées comme **badges de type** dans les résultats : `#s-track` (note), `#s-artist` (personne), `#s-set` (disque/vinyle), `#s-playlist` (lignes + play), `#s-genre` (tag). **« Tout » = texte seul** (pas d'icône).
- Item : `[icône 22px] [libellé] [compteur mono]`. Sélectionné → fond `--accent-wash`, texte `--accent-ink` 600, icône `--accent-ink`. Hover → `--surface-2`.
- **Compteur par scope** affiché **uniquement en état recherche** (alimenté par `search.totals.*` : Tout 1552, Tracks 1290, Artistes 96, Sets 84, Playlists 63, Genres 19 pour « house »). En état vide, pas de compteur.

## « Essaie »

| Élément | Spec | Tokens |
|---|---|---|
| Label | « ESSAIE » `--fs-label` 600 mono uppercase letter-spacing 0.08em | `--ink-3` |
| Chip | pill 32 px, `[flèche] terme`, hover → texte `--ink` | `--surface`, border `--line`, `--r-pill`, terme mono `--fs-sm` `--ink-2` |
| **Icône flèche** | `#s-arrow` — flèche « retour/entrée » (descend puis pointe à droite, SVG stroke `--accent-ink` 14 px). Remplace le `↳` en `::before` | `--accent-ink` |

Amorces statiques : `house`, `disclosure`, `boiler room`, `techno`, `trance`, `deep house`. Clic → remplit le champ (déclenche la recherche).

## Étagères de découverte

En-tête commun : `titre --fs-lg 700` + (badge éventuel) à gauche ; « Voir plus » (H7) à droite. Grille : `.hb-shelfgrid` (3 → 2 → 1 col). Cartes = **`<DiscoveryCard>`** (spec dédiée : `BRIEF-composants-hub.md`).

| Étagère | Public | En-tête | Aperçu | Voir plus | Source |
|---|---|---|---|---|---|
| **Ça sort en ce moment** | tous (invité inclus) | + `FamilyChips` (H8) | top 9, grille 3×3 | **→ `/radar`** (invité → `/login`) | `GET /api/radar/trends?limit=9` |
| **Pour toi** | connecté | — | top 9 | **→ `/radar`** (colonne Pour toi) | `GET /api/recommendations/?limit=9` |
| **Nouveautés de tes artistes** | connecté | badge **« N nouvelles »** (`--accent-soft`/`--accent-ink` mono, via `activity/new-count`) | aperçu | **DÉSACTIVÉ « Bientôt »** (H7) | `GET /api/following/activity?limit=12` |

### Carte album dépliable (`ActivityAlbumCard`, EXISTE)

Dans « Nouveautés », un artiste sortant un album (payload `album_id`/`album_title`) produit **1 carte album** au lieu de N cartes. **Calage visuel avec `<DiscoveryCard>`** (on ne la re-crée pas, on aligne son look) :
- Même conteneur (surface/line/`--r-md`), même cover 64 px, même en-tête horizontal (badge **« Album »** + titre + artiste + méta mono `N titres · il y a X`).
- À droite du corps : **bouton chevron rond 32 px** (au lieu du play) ; clic → déplie une liste de titres sous une `border-top --line` : `[# mono] [titre] [méta mono BPM · KEY]` par ligne (rangées `hb-rrow`, hover `--surface-2`). Chevron pivote 180° à l'ouverture.
- Vit dans la **même grille** que les cartes unitaires (hauteur repliée identique ; déploiement = hauteur auto de la cellule).

## État résultats de recherche (POLISH — cf. périmètre)

Conservé fonctionnellement, harmonisé visuellement :

| Élément | Spec | Tokens |
|---|---|---|
| En-tête | gauche : « 1 552 résultats pour « house » » mono `--fs-sm` `--ink-2` ; droite : **tri segmenté** Pertinence / BPM / A–Z (connecté uniquement) | segment actif `--surface`, inactif `--ink-3` |
| Rangée `rrow` | grille `90px 44px 1fr auto` : **colonne type** (icône SVG unifiée + libellé mono uppercase, libellé masqué < 640) · `<Artwork>` 40 px + indicateur in-lib · corps (titre **highlight** + méta mono) · zone droite | border-bottom `--line`, hover `--surface-2` |
| Highlight | occurrence du terme en `<mark>` `--accent-soft`/`--accent-ink`, radius 3px | — |
| Méta | track « artiste · BPM · KEY · m:ss » ; genre « N tracks · N artistes · lo–hi BPM » ; playlist « N tracks » ; set « jj/mm/aaaa · N tracks » ; artiste « N tracks » | mono `--fs-xs` `--ink-3` |
| Zone droite | **track in-lib** → badge `✓ EN BIB` (`--pos-soft`/`--pos-ink`) ; **track hors bib** → bouton rond `+` (hover border `--accent`) ; **playlist/set** → badge source `DEEZER`/`TIDAL` (mono uppercase `--surface-2`/`--ink-3`, masqué < 640) | — |
| **Lock-row invité** | après les 5 premiers résultats : bandeau `--accent-wash` border `--line-2` `--r-md` — icône login (`--accent-soft`), « Connecte-toi pour voir les 1 547 autres résultats » 600 + sous-texte `--ink-2`, bouton `Se connecter` (`.btn--accent`). Le tri est **masqué** pour l'invité | — |

> Les badges source `DEEZER`/`TIDAL` sont des placeholders texte ; ils migreront vers `<PlatformLink variant="glyph">` (logo monochrome `currentColor`) — chantier transverse `PlatformLink`.

## Double public

| | **Invité** | **Connecté** |
|---|---|---|
| Sidebar | **absente** (confiné au Hub — mais **hors périmètre**, ne pas la designer) ; contenu pleine largeur | présente (hors périmètre) |
| Top bar droite | `Créer un compte` + `Se connecter` | pastille user |
| Étagères (état vide) | **Ça sort seule** (+ FamilyChips) ; « Voir plus » → `/login` ; ouvrir une carte → login | **3 étagères** + tri en recherche |
| Recherche | aperçu (5 premiers) + **lock-row** « voir les N autres » → login ; **pas de tri** | liste complète + tri Pertinence/BPM/A–Z |

Le funnel invité est **voulu** : montrer librement, gater le « voir plus » / actions profondes. Aucun autre état invité à concevoir sur les pages internes (toujours authentifiées).

## États

| État | Spec |
|---|---|
| **Chargement des étagères** | cartes fantômes (skeleton) dans `.hb-shelfgrid` : cover `--surface-3` + 3 barres (`--surface-3`/`--surface-2`), `hb-pulse` 1,4 s, delay échelonné +0,09 s. (Déjà en place sur « Pour toi ».) |
| **Étagère « Ça sort » vide** | une famille sélectionnée à 0 titre → message centré (`1px dashed --line-2`) « Aucune sortie dans ce style pour le moment » + sous-texte, **chips conservées** |
| **Aucun résultat de recherche** | centré `--space-15x` : loupe 34 px `--ink-3` · « Aucun résultat pour « … » » 600 `--fs-md` · sous-texte `--ink-2` |
| **Playing** | carte : cover → cercle play `--accent`/`--on-accent` (pause) + scrim ; carte nuancier « playing » surlignée `--accent-wash` |
| **Hover** | carte → `--surface-2` + border `--line-2` (0,12 s), play révélé ; rangée résultat → `--surface-2` |
| **Troncature** | titre/artiste ellipsis 1 ligne ; méta mono ellipsis (âge tombe en premier, H2) |

## Responsive — container queries

Page dans `.hb-page` : `max-width --page-max-w`, `container-type: inline-size`, `container-name: hub`. **`@container` uniquement** (pas de `@media` ; seul `position: fixed` justifierait une media query, aucun ici). Padding `--page-px` → `--page-px-mobile` < 640.

| Seuil | Grille étagères / nuancier | Autres |
|---|---|---|
| ≥ 720 px | 3 colonnes | play hover-reveal ; colonne type + libellé + badge source visibles |
| < 720 px | 2 colonnes | — |
| < 640 px | **1 colonne** | play **toujours visible** (tactile) ; libellés de type et badges source masqués (`.hb-hidesm`) ; padding mobile |

> Convention repo 720/640 adoptée (les seuils historiques 680/640/540 du Hub actuel sont alignés sur 720/640 — un seul point de rupture intermédiaire, plus lisible). Cibles tactiles ≥ 44 px (play 32 px dans une cover 64 px + padding de carte ; CTA `.btn` ≥ 44 px).

## Données consommées (exhaustif — ne rien inventer au-delà)

- **Ça sort** — `GET /api/radar/trends?limit=9` : `catalog_id`, `title`, `artist`, `has_artwork`, `has_preview`, `bpm` (float), `key` (Camelot, nullable), `rank` (1..N), `family`, `source_count`, **`release_date`** *(seule évolution back de ce chantier : ajout à `TrendItem` + query `list_trends`)*. + `family_counts` (FamilyChips). Pas de `duration_ms`, pas de `genres`.
- **Pour toi** — `GET /api/recommendations/?limit=9` (JWT) : `id`, `title`, `artist`, `bpm`, `key`, `duration_ms`, `genres[]`, `release_date`, `has_artwork`, `has_preview`, `in_lib`. Pas de `source_count`.
- **Nouveautés** — `GET /api/following/activity?limit=12` (JWT) : `type` (`release`/`set`), `title`, `artist`/`artist_name`, `artist_id`, `catalog_id`, `set_id`, `external_url`, `bpm`, `key`, `duration_ms`, `release_date`, `has_artwork`, `has_preview`, `payload` (`album_id`/`album_title`). Badge « N nouvelles » : `GET /api/following/activity/new-count`.
- **Recherche** — `GET /api/search?q=&scope=&limit=50` : `items[]` typés (track/artist/set/playlist/genre + champs par type), `total`, **`totals`** (compteur par type → dropdown de scope, dispo en état recherche uniquement). Amorces « Essaie » = statiques.

> **Rappels** : plusieurs artistes possibles par track (`artists[]`) — ne jamais supposer un seul. Âge = `release_date` via `relativeAge()` (existe côté front) → **token brut** sur la carte (H3).

## Grille d'audit

Couleurs 100 % tokens · dark/light vérifiés (les deux dans le pilote) · accent discipliné (glyph, badge #rank/Nouveauté, FamilyChip active, in-lib du dropdown, focus ring, highlight, playing, CTA — les dots de pilier gardent leur hue) · mono pour toute donnée (BPM, key, âges, ranks, compteurs, tags mono) · `--fs-input` ≥ 16 px sur le champ · container queries uniquement · **icônes SVG inline `currentColor` unifiées** (scope + badges de type), zéro emoji, zéro CDN · libellés 100 % FR · **Genres populaires retiré** · **Essaie sous la search bar + flèche SVG** · **Ça sort top 9 3×3 + FamilyChips + Voir plus → /radar (invité → login)** · **Pour toi top 9 + Voir plus → /radar** · **Nouveautés aperçu + Voir plus désactivé « Bientôt » + badge N nouvelles** · **méta BPM · KEY · âge** ligne mono dégradée · **carte album dépliable** calée sur `<DiscoveryCard>` · **compteurs de scope** en recherche · **double public** invité (pas de sidebar, funnel, lock-row) / connecté (3 étagères + tri) · états chargement/vide/aucun résultat/playing/hover · play toujours visible < 640 · logo hors périmètre (glyph « D » inchangé) · Rating absent.
