# BRIEF — Filtres partagés · spec autonome (D6)

> Spec **indépendante de la page** : la mécanique de filtres conçue pour Explorer sera réutilisée **telle quelle** par la future page Radar (« filtres façon Explorer », décision figée) et par toute liste filtrable à venir. Rien ici ne référence les colonnes ou le contenu d'Explorer — uniquement le conteneur et les contrôles.
> Tout en tokens `diggy-tokens.css`, zéro couleur hardcodée. Icônes SVG inline `currentColor` (l'accent mauve = seul signal coloré). Libellés FR. Container queries (`@container`) ; seule exception `@media`/fixed : le drawer.
> Démo interactive de tous les contrôles : `Explorer (pilote).html`.

## Principes du système

1. **L'état des filtres est un objet plat** `{ critère: valeur }`, synchronisé 1:1 avec les query params de l'URL. Valeur par défaut = param absent. Le composant ne connaît que la **sémantique** des critères (les noms exacts des params sont fixés à l'implémentation).
2. **Trois surfaces, un seul état** : la **barre** (résumé + entrée), le **panneau** desktop (éditeur), le **drawer** mobile (éditeur plein écran). Les **chips** sont la représentation canonique de l'état actif — toujours visibles, panneau fermé ou non → une URL filtrée restaurée est lisible immédiatement.
3. **Feedback live** : chaque mutation ré-exécute la requête (debounce 250 ms pour texte/sliders) et met à jour le **compteur de résultats** partout où il apparaît (barre, footer de panneau, CTA drawer).
4. **Sélection = accent** : contrôles à valeurs neutres → fond `--accent` + `--on-accent` ; chips porteuses d'une couleur sémantique (piliers de genre) → ring accent, couleur préservée.
5. **Chaque contrôle est un composant Vue autonome** (props `modelValue` + `options`/bornes, événement `update:modelValue`) — le conteneur les compose, il ne les implémente pas.

## `<FilterBar>` — le conteneur

| Zone | Spec | Tokens |
|---|---|---|
| Rangée | flex wrap, gap `--space-2` | — |
| Slot recherche | `<SearchInput>` (voir Contrôles), flex `1 1 220px`, max-width 400 px | — |
| Bouton Filtres | `.btn` + icône sliders 15 px + **badge compteur** : pill min 18 px, `--accent`/`--on-accent`, mono 600 `--fs-xs`, = nombre de critères actifs (une valeur multiple compte ses valeurs pour styles/artistes, 1 pour ranges/segments). ≥ 720 : toggle panneau, `aria-expanded` ; < 640 : ouvre le drawer | — |
| Slot tri | `<SortSelect>` (optionnel — la page fournit ses options) | — |
| Compteur | droite, mono 500 `--fs-sm` `--ink-2` « N résultats » (`fr-FR`), « … » en chargement | `--font-mono` |
| Chips | rangée dessous si ≥ 1 actif, gap `--space-15`, wrap ; `<FilterChip>` × N + « Tout effacer » | — |
| Panneau | `<FilterPanel>` sous les chips, **inline** (pousse le contenu, pas d'overlay) | — |

### `<FilterChip>`

Pill 26 px : padding `0 4px 0 10px`, border 1 px `--line-2`, bg `--surface`, `--r-pill`. Contenu : **label** uppercase mono `--fs-nano` `--ink-3` tracking 0.06em + **valeur** mono 600 `--fs-xs` `--ink` + **×** 18 px rond (`--ink-3`, hover bg `--surface-3` + `--ink`). Clic × = retire **ce** critère (pour un multi : cette valeur).
Mapping : range → « BPM 120–133 » ; multi keys → 1 chip, valeurs triées harmonique « 5A 6A 7A 6B » ; styles / artistes → **1 chip par valeur** ; segments → le libellé de l'option ; booléen → le libellé du toggle ; texte → la saisie.
Variante **empty-state** (consommée par la page) : le chip devient bouton entier, hover border + texte `--neg` (retirer = réparer).

### `<FilterPanel>` (desktop ≥ 720)

Carte pleine largeur : bg `--surface`, border 1 px `--line`, `--r-md`, `--shadow-sm`, padding `--space-5`. Grille interne **6 colonnes**, gap `--space-4` / `--space-5` ; chaque contrôle occupe 2 ou 4 colonnes (span déclaré par le consommateur). < 860 (container) : 2 colonnes ; < 700 : 1 colonne.
Chaque bloc : **micro-label** uppercase mono `--fs-label` `--ink-3` tracking 0.07em, margin-bottom `--space-25`, puis le contrôle.
Footer : hairline `--line`, compteur live (mono `--fs-sm` `--ink-2`) + `.btn--sm` « Réinitialiser » + `.btn--sm .btn--accent` « Fermer ».
Ouverture/fermeture : apparition simple (pas d'animation de hauteur — la table se repositionne en 1 frame ; transitions réservées aux états hover/selected 0.12 s).

### `<FilterDrawer>` (mobile < 640)

`position: fixed` (exception assumée), z-index au-dessus de tout sauf toasts.
- **Overlay** : `--overlay-modal` (invariant sombre), tap = fermer.
- **Feuille** : bottom-sheet pleine largeur (max 430 px centrée), max-height 84 vh, bg `--bg`, `--r-xl` coins hauts seulement, border 1 px `--line` (sauf bas), `--shadow-lg`. Poignée 36 × 4 px `--line-2` centrée.
- **Header** : « Filtres » 600 `--fs-md` + « Réinitialiser » (texte `--fs-sm` `--ink-3`), padding `--space-3 --space-4`.
- **Corps** : scroll interne, contrôles empilés **1 colonne**, gap `--space-5`, cibles élargies (segments 32 px, inputs 44 px, Camelot 6 × 4 cellules 32 px).
- **Footer sticky** : bg `--surface`, hairline `--line`, CTA `.btn--accent` **44 px pleine largeur** « Afficher N résultats » (= fermer ; le filtrage est déjà appliqué en live).
- Fermeture : CTA, tap overlay, swipe-down (nice-to-have), Échap.

## Contrôles

Communs : **focus clavier** = `outline: none` + `border-color: --accent` sur les champs, `outline 2px --accent offset 2px` sur boutons/segments (`:focus-visible`) ; **désactivé** = opacity 0.45 + `pointer-events: none` ; transitions 0.12 s background/color/border-color ; tout contrôle textuel en `--fs-input` (≥ 16 px, règle iOS).

### `<SearchInput>` — texte libre

Input 38 px, `--r-sm`, border `--line-2`, bg `--surface`, loupe 15 px `--ink-3` à gauche (padding-left 34 px), placeholder `--ink-3`. Debounce 250 ms. Vide = critère absent (pas de chip — le champ EST son propre affichage d'état). Consommé aussi pour **Label** (sans loupe, placeholder d'exemples « Defected, Drumcode… »).

### `<RangeSlider>` — plage numérique (BPM, année, durée si besoin)

Piste 3 px `--r-pill` : fond `--surface-3`, **segment sélectionné `--accent`** (left/right en %). Deux thumbs 16 px ronds `--accent`, border 2 px `--surface`, `--shadow-sm` (implémentation : 2 `input[type=range]` superposés, pointer-events sur thumbs seuls — accessibilité native flèches clavier). Valeurs bornes en mono 600 `--fs-xs` `--ink-2` de part et d'autre. Min ne dépasse jamais max (clamp). Plage complète = critère inactif. Props : `min`, `max`, `step`, `modelValue [lo, hi]`.

### `<CamelotSelect>` — multi-select Key

Grille **12 colonnes × 2 rangées** (A = mineures en haut, B = majeures en bas — légende `--fs-nano` mono uppercase `--ink-3` « A mineures · B majeures »), gap `--space-05`. Cellule : 28 px min (32 px en drawer, grille 6 × 4), `--r-xs`, mono 600 `--fs-xs`, border `--line-2`, bg `--surface`, texte `--ink-2` ; hover `--surface-2` ; **sélectionnée** : bg `--accent`, texte `--on-accent`, border transparent ; `aria-pressed`. Adjacence = compatibilité harmonique (±1 colonne, A↔B même colonne) : une sélection harmonique se peint d'un geste. Valeurs : les 24 Camelot statiques `1A`…`12B` (= valeurs en base).

### `<StyleMultiSelect>` — piliers + sous-genres

Données : liste plate `{ name, count, pillar, depth }` (`GET /api/catalog/genres`) — **le composant groupe par pilier**, ordre fixe House · Techno · Trance · Drum & Bass · Hardcore · Hard Dance · Autres, pilier vide omis. Rangée par pilier : étiquette uppercase mono `--fs-nano` `--ink-3` (78 px) + chips wrap gap `--space-1`.
Chip genre : pill 24 px (30 px drawer), **couleurs de pilier** (mêmes formules que `StyleTag` : fond `oklch(--tag-bg-l, --tag-bg-c × (1−0.17d), hue)`, texte `--tag-fg-*`, dot 6 px `--tag-dot-*` ; Autres chroma 0) + **count** mono `--fs-nano`. Repos : border transparent ; hover : léger ring `--line-2` ; **sélectionné** : border + ring 1 px `--accent` (la couleur pilier reste — principe 4) ; `aria-pressed`.

### `<ArtistTypeAhead>` — recherche serveur

Champ-conteneur 38 px min (border/bg/focus = SearchInput) contenant : **chips sélection** (pill 24 px `--accent-soft`/`--accent-ink` 600 `--fs-xs` + × 18 px) + input nu flex (`--fs-input`, placeholder « Rechercher un artiste… » masqué dès 1 sélection).
Dropdown : card `--surface`/`--line-2`/`--r-md`/`--shadow-lg`, max-height 220 px scroll, dès 1 caractère (debounce 250 ms, `GET /api/artists/?q=&limit=6`). Item 36 px : avatar 24 px rond (`/storage/artist-artworks/{id}.jpg` si `has_artwork`, sinon initiale `--fs-nano` 600 `--ink-2` sur `--surface-3`) + nom `--fs-sm` 500, hover `--surface-2`, navigation ↑↓ + Entrée, Échap ferme. Sélection = ajout chip + vidage input. Aucun résultat : ligne « Aucun artiste » `--fs-sm` `--ink-3`.

### `<SegmentedFilter>` — tri-state & enums (In lib, Avis, Durée presets)

Rangée wrap de pills 28 px (32 px drawer), gap `--space-1` : border `--line-2`, bg `--surface`, texte 500 `--fs-xs` `--ink-2` ; hover `--surface-2` ; **actif** : `--accent`/`--on-accent`/border transparent. Exactement un actif pour les tri-states avec option « Tous » (= critère inactif, pas de chip) ; pour les presets sans « Tous » (Durée), re-clic = désélection. Valeurs numériques (durées) en mono.
Instances : **In lib** Tous / Dans ma bib / Pas dans RB · **Avis** Tous / Aimés / Rejetés / Sans avis · **Durée** < 3 min / 3–5 min / 5–8 min / > 8 min.

### `<ToggleChip>` — booléen (Écoutable)

Pill unique 28 px, icône 12 px + libellé (« Écoutable uniquement »), mêmes états repos/hover/actif que SegmentedFilter, `aria-pressed`. Off = critère absent.

### `<SortSelect>` — sélecteur de tri

Select natif stylé : 38 px, `appearance: none`, `--r-sm`, border `--line-2`, bg `--surface`, texte 500 `--fs-sm` `--ink-2`, icône tri 14 px à gauche + chevron 12 px à droite (`--ink-3`, `pointer-events: none`). Options fournies par la page ; le tri fait partie de l'état URL. Le tri n'est **pas** un filtre : jamais de chip, pas compté dans le badge.

## États récapitulatifs (audit par contrôle)

| Contrôle | Vide / repos | Actif | Focus clavier | Désactivé |
|---|---|---|---|---|
| SearchInput | placeholder `--ink-3` | texte `--ink` | border `--accent` | opacity 0.45 |
| RangeSlider | segment plein = piste entière accent ? non : plage complète → piste `--surface-3` seule | segment `--accent` entre thumbs | thumb : anneau `:focus-visible` | thumbs `--ink-3` |
| CamelotSelect | cellules `--surface` | cellules `--accent` | outline 2 px `--accent` | — |
| StyleMultiSelect | chips couleur pilier | + ring `--accent` | outline 2 px `--accent` | — |
| ArtistTypeAhead | placeholder | chips `--accent-soft` | border `--accent`, dropdown | — |
| SegmentedFilter | « Tous » actif | option `--accent` | outline 2 px `--accent` | opacity 0.45 |
| ToggleChip | pill `--surface` | pill `--accent` | outline 2 px `--accent` | opacity 0.45 |

Dark/light : aucun style propre au thème — tout dérive des tokens (vérifié dans le pilote sur les deux thèmes). Les invariants (`--overlay-modal`) restent sombres dans les deux.

## Contrat consommateur (Radar & suivantes)

- La page fournit : la liste de critères + leurs options/bornes, les options de tri, l'endpoint de comptage, le mapping query params.
- Le système fournit : barre + badge, chips + « Tout effacer », panneau, drawer, tous les contrôles, la sync URL et le debounce.
- Ajouter un critère = ajouter un bloc dans le panneau/drawer + son mapping chip — **zéro changement** aux composants.
