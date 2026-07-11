# REFACTOR-audit.md — Factorisation du front Diggy

> Audit de dette + plan de factorisation du front Vue 3.
> Cible : extraire les duplications « molécule » en composants partagés, supprimer
> le code mort, centraliser les helpers. **0 régression visuelle** — on déplace, on ne redessine pas.
> Réf. DA : `Component Kit (pilote).html` (ce dossier) fige le rendu de chaque composant cible.

---

## TL;DR

- **Les atomes sont sains.** `LikeDislike`, `LibDot`, `InLibBadge`, `ScorePill`, `StyleTag`,
  `StatStrip`, `RelBlock`, `PageHero`, `ShelfCard`, `AppearRow`, `GenreCard`, `ArtistCard`
  sont déjà des SFC réimportés correctement. **Ne pas y toucher.**
- **La dette est au niveau des « molécules »** recomposées inline dans chaque view :
  en-tête de page, recherche, segment de filtre, table, family-chips, carte admin,
  skeleton, sentinel. → 12 clusters ci-dessous.
- **Code mort** : `components/TrackTable.vue` (8,6 Ko) n'est importé par **aucune** view.
- **Helpers dupliqués** : `fmtNum` (×3), `authHeaders` (×5), maths d'anneau (×2).
- **Tokens manquants** : `--warn-ink / --warn-soft / --orange` → utilisés en hex de secours
  partout (viole « zéro hex en dur »).

Gain estimé : **~1 100 lignes** de CSS/markup/JS dédupliquées sur les 11 views.

---

## Inventaire des views (état actuel)

| View | Lignes | Recompose inline |
|---|---|---|
| CatalogView | 733 | page-head, search, chips, viewseg, **table tt**, src-badge, rating, pagination |
| SetsView | 830 | page-head, search, filterseg, **table tt**, addform, ring donut, btn-like |
| GenresView | 508 | page-head, search, filterseg, **fam-chips**, admin-strip, skeleton, sentinel |
| ArtistsView | 469 | page-head, search, filterseg, **fam-chips**, skeleton, sentinel |
| GenreDetailView | 906 | hero mosaïque, **admin-card**, shelves, ring pill, source-badge, sentinel |
| ArtistDetailView | 440 | **admin-card** (deezer), **mini-table**, btn-ghost |
| SetDetailView | 427 | **admin-card (orange)**, tracklist table, btn-ghost |
| PlaylistDetailView | 378 | **admin-card (orange)**, **mini-table**, crawl-banner, btn-ghost |
| TrackDetailView | 255 | **admin-card (orange)**, track-meta, btn-sync |
| GenresView/AdminView | 38 Ko | admin tables, status-badges, reason-badges (hors scope listes) |

---

## Les 12 clusters

### 1 — En-tête de page  → `<PageHeader>` + `<SearchBox>`
**Fichiers** : Catalog, Sets, Artists, Genres.
**Constat** : `.page-head / .titles h1 / .sub / .head-tools` + `.search` (avec le **même SVG loupe**
copié 4×) sont identiques au pixel. ~60 lignes CSS × 4.
**Cible**
```
<PageHeader title="Sets" :sub="…">
  <template #tools> … </template>
</PageHeader>
<SearchBox v-model="search" placeholder="Rechercher…" @input="onSearch" />
```
- `PageHeader` : slot `#tools` aligné à droite, responsive (`.head-tools` passe full-width < 820px container).
- `SearchBox` : input + icône, `v-model`, `placeholder`, hauteur 38px fixe.

### 2 — Segment de filtre  → `<SegFilter>`
**Fichiers** : Sets, Artists, Genres (+ `viewseg` Catalog = variante pill).
**Constat** : `.filterseg` + variantes `.liked.on` / `.disliked.on` recopiées à l'identique.
**Cible**
```
<SegFilter v-model="sortBy" :options="[
  { value:'catalog', label:'Catalog' },
  { value:'liked', label:'Liked', tone:'pos' },
  { value:'disliked', label:'Disliked', tone:'neg' },
]" />
```
- `tone` ∈ `accent` (défaut) | `pos` | `neg` pilote la couleur de l'état actif.
- Variante `pill` (prop `shape="pill"`) pour le toggle Catalog/Radar avec icônes (slot par option).

### 3 — Family chips  → `<FamilyChips>` + `FAMILY_HUES` dans `useStyleMap`
**Fichiers** : Artists, Genres.
**Constat** : `.fam-chips/.fam-chip/.fc-dot/.fc-n`, la constante `FAMILY_HUES = { house:260, techno:320, trance:352, other:42 }`,
**et** le computed `familyChips` sont dupliqués mot pour mot.
**Cible**
```
<FamilyChips v-model="familyFilter" :counts="familyCounts" />
```
- `FAMILY_HUES` exporté depuis `composables/useStyleMap.js` (source unique avec `FAMILY_LABELS`).
- Le composant construit lui-même la liste `[all, house, techno, trance, other]` à partir de `counts`.

### 4 — Table principale  → styles partagés `table.dt` + `<TrackCell>`  (+ statuer sur `TrackTable.vue`)
**Fichiers** : Catalog, Sets. **Mort** : `TrackTable.vue`.
**Constat** : ~200 lignes quasi identiques — `table.tt`, `.td-track/.aw/.tx/.tt-title/.tt-art/.fallback-letter`,
`th.sortable` + flèche, hover, états ligne `liked/disliked`, hover-reveal avis, `.detect`, `.td-dur`.
`TrackTable.vue` était la table partagée mais a été **abandonnée** (0 import) et a **divergé**
(gouttière play 8px vs 14px, btn 26px vs 30px — cf. PROMPT-claude-code-like-dislike.md).
**Cible**
- **Décision** : promouvoir une table canonique. Soit on récupère `TrackTable.vue` et on l'aligne sur Catalog
  (la référence gouttières), soit on l'efface et on extrait depuis Catalog. **Recommandé : extraire depuis
  Catalog → `assets/table.css` (classe `.dt`) importée, + supprimer `TrackTable.vue`.**
- `<TrackCell :artwork :title :artist :to-track :to-artist />` = la cellule artwork+titre+artiste
  (identique Catalog/Sets ; ré-utilisable dans mini-tables).
- États ligne `liked/disliked` + hover-reveal avis = classes dans `table.css`, pas par-view.

### 5 — Mini-table de tracks  → `<MiniTrackTable>`
**Fichiers** : ArtistDetail, PlaylistDetail (+ SetDetail tracklist = variante cue/is_id).
**Constat** : `.mini-table` (thead mono uppercase, `.mt-link/.mt-title/.mt-artist/.mt-num`) recopiée.
La maquette de référence l'appelle déjà `MiniTrackTable` (cf. pages-components.jsx).
**Cible**
```
<MiniTrackTable :rows="tracks" :columns="['style','bpm','key','rating']" />
```
- Colonnes pilotées par prop (`style|bpm|key|dur|rating|preview`).
- Variante set : `<SetTrackTable>` (cue cliquable + états `row--id` / `row--unknown`) — composant frère,
  même thead/`.tl-*`, pour SetDetail.

### 6 — Carte admin  → `<AdminCard>` + `<AdminInput>`  ⚠️ unification D2
**Fichiers** : GenreDetail, ArtistDetail, Genres (**dashed-gris OK**) · SetDetail, TrackDetail, PlaylistDetail (**orange, à corriger**).
**Constat** : 6 implémentations, **2 styles divergents**. 3 utilisent `border:1px solid var(--warn-ink,#e67e22)`
(orange, hex en dur) au lieu du style D2 (`dashed var(--line-2)` + `surface-2`).
**Décision figée (validée)** : on unifie **tout vers D2**.
**Cible**
```
<AdminCard label="Admin">
  <AdminInput v-model="q" placeholder="…" />
  …
</AdminCard>
```
- `AdminCard` : `surface-2` + `dashed var(--line-2)` + `.admin-label` mono uppercase. Role-gating
  (`v-if="auth.user?.is_admin"`) reste **dans la view** (le composant ne gère pas l'auth).
- `AdminInput`, `.admin-msg.ok/.err` (→ `--pos` / `--neg`), boutons via cluster 12.

### 7 — Infinite scroll  → `useInfiniteScroll()` + `<Sentinel>`
**Fichiers** : Artists, Genres, GenreDetail.
**Constat** : même `IntersectionObserver({ rootMargin:'0px 0px 360px 0px' })` + `.sentinel/.spin/@keyframes spin`,
+ `onMounted/onUnmounted/nextTick` recopiés.
**Cible**
```
const sentinel = ref(null)
useInfiniteScroll(sentinel, loadMore, () => hasMore.value)   // gère observer + cleanup
```
```
<Sentinel ref="sentinel" :loading="loading" />
```

### 8 — Skeleton  → `<SkeletonCard>`
**Fichiers** : Artists, Genres.
**Constat** : `.skeleton-card/.sk-art/.sk-line/.sk-stats/@keyframes shimmer` dupliqués (seule la hauteur
de `.sk-art` change : 132 vs 130).
**Cible** : `<SkeletonGrid :count="12" variant="artist|genre" />` (shimmer + `prefers-reduced-motion` inclus).

### 9 — Source badge  → `<SourceBadge>`
**Fichiers** : Catalog (`.src-badge`), GenreDetail (`.source-badge`).
**Constat** : le mapping `deezer → accent-soft` / `spotify → pos-soft` / `tidal → surface-3+line` codé 2×
sous deux noms de classe.
**Cible** : `<SourceBadge :source="e.source_kind" />` (mappe la plateforme → couleur, conforme bloc « Badge source » de CLAUDE.md).

### 10 — Anneau %  → `<RingPct>`
**Fichiers** : Sets (donut SVG `stroke-dashoffset`), GenreDetail (pastille `.ring` texte).
**Constat** : deux représentations du « % identifié / pertinence ». Maths recopiées (`ringPct/ringOffset/ringClass`).
**Cible** : `<RingPct :value="pct" variant="donut|pill" />`. Maths (`R`, `C`, classes seuils) dans le composant.

### 11 — Helpers & axios  → `utils/format.js` + instance axios
**Constat**
- `fmtNum` défini inline dans Artists, Genres, GenreDetail (×3) — **pas** dans utils.
- `authHeaders()` recopié dans Sets, Artists, Genres, ArtistDetail, SetDetail, TrackDetail (×5-6).
- `pl()` (pluralize) inline dans Genres.
**Cible**
- `fmtNum`, `pl` → `utils/format.js`.
- **Instance axios partagée** `utils/api.js` avec **intercepteur** qui injecte `Authorization` depuis le store
  → supprime tous les `authHeaders()` et les `{ headers: authHeaders() }`. Gain net + sécurité.

### 12 — Boutons & tokens  → `assets/buttons.css` + tokens warn
**Constat** : `.btn-ghost / .btn-ghost-sm / .btn-accent-sm / .btn-go / .btn-add / .btn-sync / .btn-admin`
redéfinis par view, avec micro-variations. `--warn-ink/--warn-soft/--orange` **absents** des tokens.
**Cible**
- Classes boutons partagées : `.btn` + modificateurs `.btn--ghost / --accent / --sm / --danger`.
  (Classes plutôt qu'un `<Btn>` pour garder `<a>` / `<button>` / `<RouterLink>` libres.)
- **Ajouter aux tokens** : `--warn / --warn-soft / --warn-ink` (hue ambre ~70, aligné famille misc) en light + dark.
  Puis remplacer tous les `var(--x, #hex)` par `var(--x)`.

---

## Cibles — récap composants/fichiers à créer

| Nouveau | Type | Remplace |
|---|---|---|
| `components/PageHeader.vue` | SFC | `.page-head` ×4 |
| `components/SearchBox.vue` | SFC | `.search` ×4 |
| `components/SegFilter.vue` | SFC | `.filterseg` ×3 + `.viewseg` |
| `components/FamilyChips.vue` | SFC | `.fam-chips` ×2 |
| `components/TrackCell.vue` | SFC | `.td-track` ×2 |
| `components/MiniTrackTable.vue` | SFC | `.mini-table` ×2 |
| `components/SetTrackTable.vue` | SFC | tracklist SetDetail |
| `components/AdminCard.vue` + `AdminInput.vue` | SFC | `.admin-card` ×6 |
| `components/Sentinel.vue` | SFC | `.sentinel` ×3 |
| `components/SkeletonGrid.vue` | SFC | `.skeleton-card` ×2 |
| `components/SourceBadge.vue` | SFC | `.src-badge` / `.source-badge` |
| `components/RingPct.vue` | SFC | ring ×2 |
| `composables/useInfiniteScroll.js` | composable | observer ×3 |
| `utils/api.js` | axios instance | `authHeaders` ×5 |
| `assets/table.css` | CSS | `table.tt` ×2 |
| `assets/buttons.css` | CSS | `.btn-*` ×N |
| `utils/format.js` (+`fmtNum`,`pl`) | edit | helpers ×3 |
| `styles/diggy-tokens.css` (+warn) | edit | hex de secours |
| ❌ `components/TrackTable.vue` | **supprimer** | code mort |

---

## Lots d'implémentation (ordre conseillé)

**Lot A — fondations, non-bloquant, 0 risque visuel**
1. Tokens `--warn-*` + purge des `var(--x,#hex)`.
2. `utils/format.js` : `fmtNum`, `pl`. `utils/api.js` : axios + intercepteur ; retirer `authHeaders`.
3. `assets/buttons.css` + `assets/table.css` importés au root ; supprimer `TrackTable.vue`.

**Lot B — atomes molécules réutilisables**
4. `SearchBox`, `SegFilter`, `PageHeader` → câbler Catalog, Sets, Artists, Genres.
5. `FamilyChips` (+ `FAMILY_HUES` dans useStyleMap) → Artists, Genres.
6. `Sentinel` + `useInfiniteScroll` + `SkeletonGrid` → Artists, Genres, GenreDetail.

**Lot C — tables & badges**
7. `TrackCell` + `table.css` → Catalog, Sets.
8. `MiniTrackTable` / `SetTrackTable` → ArtistDetail, PlaylistDetail, SetDetail.
9. `SourceBadge`, `RingPct`.

**Lot D — admin**
10. `AdminCard` + `AdminInput` → les 6 vues (unification orange → D2).

Chaque lot = 1 passe Claude Code, vérifiable écran par écran contre le `Component Kit (pilote).html`.

---

## Grille de vérif post-refacto (par view)
- [ ] Rendu **identique** avant/après (light + dark + densité).
- [ ] 0 `#hex` ; tout en `var(--…)`.
- [ ] 0 `authHeaders` résiduel ; appels via `utils/api.js`.
- [ ] Carte admin = style D2 partout, role-gated, 2 états (admin ON/OFF).
- [ ] `TrackTable.vue` supprimé, aucun import cassé.
- [ ] Responsive container queries conservées par composant.
