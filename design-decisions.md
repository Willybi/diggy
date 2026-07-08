# design-decisions.md — Décisions design system Diggy — 2026-07

Ce fichier fait autorité pour la migration des échelles (commit 3).
En cas de conflit avec design-audit.md, ce fichier gagne.

## 1. Échelle de spacing

Grille hybride : pas de 2px jusqu'à 12, pas de 4px au-delà.
Justification : 6px (46 occ.) et 10px (79 occ.) sont des masses réelles
du codebase ; une grille 4px stricte forcerait des snappings visibles
sur des centaines d'occurrences pour un bénéfice théorique.

Tokens (diggy-tokens.css, en px, cohérent avec l'existant) :

    --space-05: 2px    --space-1: 4px     --space-15: 6px
    --space-2: 8px     --space-25: 10px   --space-3: 12px
    --space-4: 16px    --space-5: 20px    --space-6: 24px
    --space-8: 32px    --space-10: 40px   --space-15x: 60px

### Mapping des valeurs hors grille

| Actuel | Cible | Règle |
|---|---|---|
| 1px | 2px, ou 0 si gap décoratif | cas par cas (7 occ. seulement) |
| 3px | 2px | arrondi bas |
| 5px | 4px | arrondi bas |
| 7px | 6px | arrondi bas |
| 9px | 8px | arrondi bas |
| 11px | 10px | arrondi bas |
| 13px | 12px | arrondi bas |
| 15px | 16px | arrondi haut (14 déjà pris par règle dédiée) |
| **14px** | **16px par défaut ; 12px en contexte dense** | voir ci-dessous |
| 18px | 20px | espacement de section, respiration préservée |
| 22px | 24px | arrondi haut |
| 26px | 24px | arrondi bas |
| 28px | 24px | arrondi bas |
| 34px | 32px | arrondi bas |
| 36px | 32px | arrondi bas |
| 48px | 40px | arrondi bas |
| 56px | 60px | arrondi haut |
| 100px, 156px | inchangés, littéraux | cas uniques de layout, hors rythme |

Règle 14px : padding de conteneur, marge de section, gap entre blocs
→ --space-4 (16px). Ligne de table, chip, badge, gap interne de
composant dense → --space-3 (12px). Cas d'hésitation : lister, ne pas
trancher silencieusement.

Règle générale : tout snapping dont l'écart rendu dépasse 2px est
listé avant application (déjà dans le prompt, rappelé ici).

## 2. Échelle de font-size

| Token | Valeur | Absorbe |
|---|---|---|
| --fs-xs | 11px | 10px (fusion du cluster micro-texte) |
| --fs-sm | 13px | 12px (13 domine : 16 occ. vs 5) |
| --fs-base | 14px | — |
| --fs-md | 18px | 17px |
| --fs-lg | 24px | 23px |
| --fs-xl | 28px | — |
| --fs-display | 36px | — |
| --fs-table | 14.5px | ajustement optique tables, intentionnel |
| --fs-table-sm | 12.5px | idem |

Les demi-pixels sont conservés comme tokens explicites : les tables
sont l'écran principal de Diggy, l'ajustement optique y est traité
comme une intention documentée, pas une dérive. Normalisation
éventuelle plus tard = 2 lignes à changer.

--fs-table et --fs-table-sm sont réservés aux contextes tabulaires
(table.css et vues à table). Tout autre usage est une erreur.

## 2bis. Font-size — shorthand `font:` et valeurs off-scale (2026-07)

**Note de périmètre.** L'audit initial (design-audit.md §2) n'a compté que
les déclarations `font-size:` (64 occ., 12 valeurs). La taille de police
vit en réalité massivement dans le raccourci `font:` (324 occ., 26 valeurs
distinctes), non couvert par l'audit. Cette section étend §2 pour couvrir
l'ensemble et trancher les valeurs off-scale. À l'avenir, tout audit
typographique doit inclure le shorthand `font:`.

### Nouveaux tokens
| Token | Valeur | Rôle | Absorbe |
|---|---|---|---|
| `--fs-nano` | 9px | badges/clés nano, uppercase mono | 8.5, 9, 9.5 |
| `--fs-label` | 10.5px | en-têtes de table, micro-labels | 10.5 |
| `--fs-title` | 15px | titres de section / cartes / valeurs stat | 15, 16 |
| `--fs-input` | 16px | inputs/select/textarea (voir règle iOS) | 16.5 + tout input |
| `--fs-fallback` | 32px | initiales d'avatar / hero fallback (glyphe) | 30, 32 |
| `--fs-hero` | 46px | mot display unique (Hub big word) | 46 |

### Redéfinition
- **`--fs-lg` : 24px → 22px.** La masse (view titles, 5 occ. à 22px) fixe
  la valeur ; l'unique ex-consommateur à 23px (`.titles h1`, CatalogView)
  rejoint 22 (Δ1). Principe : la minorité rejoint la masse, pas l'inverse.

### Snaps décidés (off-scale → token existant)
- **13.5 → `--fs-sm` (13).** Promotion refusée : 13 / 13.5 institution­-
  naliserait un quasi-doublon, le pattern même que ce chantier éradique.
  Δ0.5 assumé sur 23 occ.
- 11.5 → `--fs-xs` · 19 → `--fs-md` · 16 → `--fs-title` (Δ1) · 23 → `--fs-lg`.
- **12.5 / 14.5** restent `--fs-table-sm` / `--fs-table` UNIQUEMENT en
  contexte cellule/ligne de table (`.tt-art`, `.tt-title`, `.td-*`,
  `thead th`, `.tracklist`, `.mini-table`). Tout autre usage →
  `--fs-sm` / `--fs-base`.

### Règle input (iOS)
Aucun `input` / `select` / `textarea` ne descend sous **`--fs-input`
(16px)** : iOS Safari zoome au focus sous ce seuil. Tout font-size de
contrôle de formulaire → `--fs-input`, même si le snap normal l'enverrait
plus bas.

Périmètre : `--fs-input` s'applique à tout contrôle de formulaire des vues
utilisateur. Les contrôles admin (dossier `admin/*` et sections admin des
vues de détail) sont exemptés — desktop-only, la contrainte iOS ne s'y
applique pas — et suivent le snap normal.

### Exception clamp() — "responsive display"
Trois sélecteurs gardent un `clamp()` littéral (taille fluide
intentionnelle, hors échelle) :
- `.hb-name` : `clamp(22px, 2.4vw, 34px)` (ArtistDetailView)
- `.hero-title` : `clamp(20px, 2.2vw, 34px)` (PageHero)
- `.hero-title` : `clamp(24px, 2.2vw, 34px)` (GenreDetailView)

Toute nouvelle taille fluide passe par une décision explicite, jamais par
imitation.

## 3. Densité ([data-density])

**Conservée et généralisée, avec scope.**

Scope de --pad : surfaces de contenu répétitif uniquement — lignes et
cellules de table, listes de résultats, cards de catalogue (Catalog,
Sets, Watchlist, Collections, Artists, Genres, résultats de recherche).

Hors scope (spacing fixe --space-*) : navigation (BottomNav, SidebarNav),
modals, PlayerBar, pages admin, pages de détail hors leurs tables,
Login.

Migration : les 16px en dur des contextes in-scope → var(--pad) ;
tous les autres 16px → --space-4. Avant exécution : produire la liste
des fichiers classés in-scope / hors-scope pour validation.

Les valeurs de densité existantes (--pad : 16px, compact 12px,
comfy 22px) restent inchangées dans ce commit.

## 4. Reporté (hors scope commit 3)

- Migration de --accent-wash vers la mécanique alpha de --pos-wash
  (change des valeurs rendues, à faire isolément avec vérif visuelle).
- Vérification/application de --touch-min: 44px sur les cibles
  tactiles mobiles (BottomNav, boutons) — audit reco 9.
- Éventuelle migration px → rem : non, pas dans cette refonte.

## 5. Liste blanche — littéraux `px` résiduels légitimes (fin commit 3)

Après migration complète, **8 littéraux `px`** subsistent volontairement en
spacing. Le prochain audit doit les ignorer (ne pas les re-signaler) :

| Fichier | Déclaration | Justification |
|---|---|---|
| App.vue | `.app-main.has-player` `padding-bottom: 100px` | dégagement PlayerBar — cote de layout unique, hors rythme |
| ArtistDetailView.vue | `.hero-body-below` `padding: … 156px` | décalage avatar du hero — cote de layout unique |
| GenreCard.vue | `.av` `margin-left: -9px` | chevauchement d'avatars empilés (géométrie) |
| GenreDetailView.vue | `.av` `margin-left: -10px` | chevauchement d'avatars (géométrie) |
| ArtistDetailView.vue | `margin-bottom: -20px` | chevauchement de section (géométrie) |
| AdminView.vue | `margin-bottom: -1px` | collapse de bordure d'onglet (géométrie) |
| SetsView.vue | `margin-bottom: -1px` | collapse de bordure d'onglet (géométrie) |
| HubView.vue | `.rart .play svg` `margin-left: 1px` | centrage optique du triangle play (commenté `/* optical centering */`) |

Complètent la liste blanche typographique : les **3 `clamp()`** de §2bis
(responsive display) et les demi-pixels `--fs-table` / `--fs-table-sm`
(ajustement optique tables, intentionnel).

**Fausse équivalence (ne pas re-signaler)** : les fallbacks d'ArtistCard
(gradient 2 stops, `--fb-l1/c1/l2/c2`) et de GenreCard (mosaïque 4 tuiles,
`--ml/--mc`) sont des mécaniques **volontairement distinctes**, examinées
lors de la factorisation et non unifiées — l'item §1.3-B de l'audit était
une fausse équivalence.