# D5 -- Refactor Composants Partages

## Objectif

Extraire les patterns UI dupliques dans les vues en composants reutilisables.
Reduire la duplication de ~1500 LOC dans les vues.

## Etat actuel

- 17 composants existent deja dans `src/components/`
- 2 composables existent : `useTheme.js`, `useStyleMap.js`
- `utils/format.js` est complet (fmtNum, pl, fmtMs, fmtBpm, fmtDate, fmtSec, fmtCue)
- `assets/buttons.css` (56 LOC) et `assets/table.css` (121 LOC) existent
- Aucun fallback `var(--x, #hex)` a purger (deja clean)

## Composants a creer

### 1. SearchBox.vue

**Duplication** : 7 vues (CatalogView, SetsView, GenresView, ArtistsView, WatchlistView, AdminView, GenreDetailView)

**Pattern actuel** (copie dans chaque vue) :
```html
<label class="search">
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9">
    <circle cx="11" cy="11" r="7" />
    <path d="m20 20-3.2-3.2" stroke-linecap="round" />
  </svg>
  <input v-model="search" placeholder="Rechercher..." @input="onSearch" />
</label>
```

**Composant cible** :
```vue
<SearchBox v-model="search" placeholder="Rechercher..." :debounce="300" />
```

Props : `modelValue` (string), `placeholder` (string, default "Rechercher..."), `debounce` (number, default 300)
Emits : `update:modelValue` (debounced)
Inclut : SVG icone loupe, bouton clear (X) si non vide, `aria-label="Rechercher"`
Le debounce est integre dans le composant (setTimeout interne).

Apres creation : remplacer les 7 instances dans les vues + supprimer le CSS `.search` duplique.

### 2. SegFilter.vue

**Duplication** : 6 vues (CatalogView, SetsView, GenresView, ArtistsView, GenreDetailView, HubView)

**Pattern actuel** :
```html
<div class="filterseg">
  <button :class="{ on: mode === 'all' }" @click="mode = 'all'">Tous</button>
  <button :class="{ on: mode === 'liked' }" @click="mode = 'liked'">Aimes</button>
  ...
</div>
```

**Composant cible** :
```vue
<SegFilter v-model="mode" :options="[
  { value: 'all', label: 'Tous' },
  { value: 'liked', label: 'Aimes' },
  { value: 'disliked', label: 'Rejetes' },
]" />
```

Props : `modelValue` (string), `options` (array of `{ value, label, count? }`)
Emits : `update:modelValue`
Si `count` est fourni dans une option, afficher `label (count)`.
CSS : reprendre le pattern `.filterseg` existant (boutons inline, `.on` = active state).

Apres creation : remplacer les 6 instances + supprimer les CSS `.filterseg` dupliques.

### 3. FamilyChips.vue

**Duplication** : 2 vues (GenresView, ArtistsView) — ~180 LOC de CSS chacune

**Pattern actuel** :
```html
<div class="fam-chips">
  <button v-for="f in families" :data-fam="f.key"
    :class="{ on: family === f.key }" @click="family = f.key">
    {{ f.label }} <span class="fam-count">{{ f.count }}</span>
  </button>
</div>
```

**Composant cible** :
```vue
<FamilyChips v-model="family" :counts="familyCounts" />
```

Props : `modelValue` (string), `counts` (object `{ house: 12, techno: 8, ... }`)
Emits : `update:modelValue`
Utilise `PILLAR_ORDER` et `PILLAR_LABELS` depuis `useStyleMap.js`.
Inclut le bouton "Tous" avec le total.
CSS : les couleurs par famille via `[data-fam]` (reprendre le pattern existant).

### 4. AdminCard.vue

**Duplication** : 5 vues (GenreDetailView, ArtistDetailView, SetDetailView, TrackDetailView, GenresView)

**Pattern actuel** :
```html
<div v-if="auth.user?.is_admin" class="admin-card">
  <span class="admin-label">Admin</span>
  <!-- contenu admin -->
</div>
```

**Composant cible** :
```vue
<AdminCard v-if="auth.user?.is_admin">
  <!-- contenu admin via slot -->
</AdminCard>
```

Props : aucune (ou `label` optionnel, default "Admin")
Slot : default (contenu admin)
Le composant importe `useAuthStore` et gere le `v-if` en interne (role-gated).
CSS : `border: 2px dashed var(--line-2)`, `background: var(--surface-2)`, label en accent.

### 5. SourceBadge.vue

**Duplication** : inline dans WatchlistView (~25 LOC)

**Pattern actuel** (WatchlistView lignes 125-127 + CSS 690-711) :
```html
<span class="src-badge" :class="srcClass(pl.source)">{{ pl.source }}</span>
```

**Composant cible** :
```vue
<SourceBadge source="deezer" />
```

Props : `source` (string: 'deezer' | 'tidal' | 'spotify')
CSS : 3 variantes couleur (accent-soft/surface-3/pos-soft).

### 6. RingPct.vue

**Duplication** : inline dans SetsView (~60 LOC template + 30 LOC JS + 60 LOC CSS)

**Pattern actuel** (SetsView lignes 220-230 + 283-297 + 895-955) :
SVG anneau avec fond/progression, etats done/mid/low, check icon a 100%.

**Composant cible** :
```vue
<RingPct :value="identified" :total="total" />
```

Props : `value` (number), `total` (number)
Computed internes : `pct`, `offset`, `stateClass` (done/mid/low)
CSS : `.ring` avec etats couleur via `--pos`/`--accent`/`--warn` tokens.

### 7. SkeletonGrid.vue

**Duplication** : 3 vues (GenresView, ArtistsView, GenreDetailView) — ~40 LOC chacune

**Pattern actuel** :
```html
<div class="grid">
  <div v-for="i in 12" :key="i" class="skeleton-card">
    <div class="sk-art"></div>
    <div class="sk-body"><div class="sk-line w60"></div><div class="sk-line w40"></div></div>
  </div>
</div>
```

**Composant cible** :
```vue
<SkeletonGrid :count="12" />
```

Props : `count` (number, default 12)
CSS : animation shimmer integree, structure carte (art + body + lines).

### 8. useInfiniteScroll.js (composable)

**Duplication** : IntersectionObserver + sentinel pattern dans ArtistsView, GenresView, et potentiellement d'autres.

**Composable cible** :
```javascript
import { useInfiniteScroll } from '@/composables/useInfiniteScroll'

const { sentinel } = useInfiniteScroll(loadMore)
```

```html
<div ref="sentinel"></div>
```

Export : `sentinel` (template ref), `loading` (ref bool)
Parametres : `fetchMore` (async function), `options` (IntersectionObserver options)
Gere automatiquement l'observer lifecycle (onMounted/onUnmounted).

## Procedure

L'ordre d'implementation est important car certains composants sont utilises par d'autres :

1. **SearchBox** — le plus duplique (7 vues), aucune dependance
2. **SegFilter** — 2e plus duplique (6 vues), aucune dependance
3. **FamilyChips** — depend de useStyleMap (existe deja)
4. **AdminCard** — depend de auth store (existe deja)
5. **SourceBadge** — simple, aucune dependance
6. **RingPct** — simple, aucune dependance
7. **SkeletonGrid** — simple, aucune dependance
8. **useInfiniteScroll** — composable, aucune dependance

Pour chaque composant :
1. Creer le fichier dans `src/components/` (ou `src/composables/`)
2. Remplacer TOUTES les instances dans les vues
3. Supprimer le CSS duplique des vues (garder uniquement dans le composant)
4. Verifier ESLint + Prettier + vitest

## Fichiers a creer

| Fichier | Type |
|---------|------|
| `src/components/SearchBox.vue` | Composant |
| `src/components/SegFilter.vue` | Composant |
| `src/components/FamilyChips.vue` | Composant |
| `src/components/AdminCard.vue` | Composant |
| `src/components/SourceBadge.vue` | Composant |
| `src/components/RingPct.vue` | Composant |
| `src/components/SkeletonGrid.vue` | Composant |
| `src/composables/useInfiniteScroll.js` | Composable |

## Fichiers a modifier (suppression CSS duplique + remplacement par composants)

| Fichier | Modifications |
|---------|--------------|
| `CatalogView.vue` | SearchBox, SegFilter |
| `SetsView.vue` | SearchBox, SegFilter, RingPct |
| `GenresView.vue` | SearchBox, SegFilter, FamilyChips, SkeletonGrid, AdminCard |
| `ArtistsView.vue` | SearchBox, SegFilter, FamilyChips, SkeletonGrid |
| `WatchlistView.vue` | SearchBox, SourceBadge |
| `AdminView.vue` | SearchBox |
| `GenreDetailView.vue` | SearchBox, SegFilter, AdminCard, SkeletonGrid |
| `ArtistDetailView.vue` | AdminCard |
| `SetDetailView.vue` | AdminCard |
| `TrackDetailView.vue` | AdminCard |
| `HubView.vue` | SegFilter |

## Verification

```bash
# Composants crees
ls server/frontend/src/components/ | grep -E "SearchBox|SegFilter|FamilyChips|AdminCard|SourceBadge|RingPct|SkeletonGrid"

# Composable cree
ls server/frontend/src/composables/useInfiniteScroll.js

# Plus de duplication CSS filterseg dans les vues
grep -rn "\.filterseg" server/frontend/src/views/ --include="*.vue" | wc -l
# -> devrait etre 0 (tout dans SegFilter.vue)

# Plus de duplication CSS .search dans les vues
grep -rn "\.search {" server/frontend/src/views/ --include="*.vue" | wc -l
# -> devrait etre 0

# ESLint clean
cd server/frontend && npx eslint src/

# Prettier clean
cd server/frontend && npx prettier --check src/

# Tests frontend
cd server/frontend && npx vitest run
```

## Contraintes

- Zero couleur hardcodee — tout via `var(--...)`
- Code en anglais, UI en francais
- Les composants utilisent `<script setup>` (Composition API)
- Les props suivent le pattern v-model (`modelValue` + `update:modelValue`) pour les composants avec etat
- Ne PAS changer la logique metier des vues, uniquement extraire les patterns UI
- Ne PAS changer le rendu visuel — le resultat doit etre pixel-identical
- Les CSS existants dans `assets/buttons.css` et `assets/table.css` ne sont PAS a toucher
- Ne PAS toucher aux composants existants (LibDot, StyleTag, LikeDislike, etc.)
- Chaque composant doit etre autonome (pas de dependance entre les nouveaux composants)
- Pas de handler @click multi-instructions inline (extraire en methode si > 1 instruction)
