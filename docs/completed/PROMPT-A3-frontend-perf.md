# A3 -- Frontend Perf & Accessibilite

## Objectif

Optimiser le chargement initial du frontend (lazy loading routes) et ameliorer
l'accessibilite (aria-labels, skip link, keyboard navigation).

## Etat actuel

- 13 vues importees statiquement dans `src/router.js` (tout charge d'un coup)
- 13 `aria-label` existants (7 fichiers) mais 12 fichiers ont des boutons icone SVG sans aria-label
- Composables `useInfiniteScroll`, `useTheme`, `useStyleMap` deja en place (D5)
- `SearchBox.vue` integre le debounce en interne — pas besoin de `useDebounce` separe
- Production build deja correct (multi-stage Dockerfile : vite build → nginx statique)

## Taches

### 1. Lazy loading des routes (code splitting)

Modifier `src/router.js` pour remplacer les imports statiques par des imports dynamiques.
Garder UNIQUEMENT `HubView` en import statique (page d'accueil, toujours chargee).

**AVANT** (router.js actuel) :
```javascript
import HubView from './views/HubView.vue'
import GenresView from './views/GenresView.vue'
import GenreDetailView from './views/GenreDetailView.vue'
import CatalogView from './views/CatalogView.vue'
import WatchlistView from './views/WatchlistView.vue'
import TrackDetailView from './views/TrackDetailView.vue'
import ArtistDetailView from './views/ArtistDetailView.vue'
import SetDetailView from './views/SetDetailView.vue'
import PlaylistDetailView from './views/PlaylistDetailView.vue'
import ArtistsView from './views/ArtistsView.vue'
import SetsView from './views/SetsView.vue'
import AdminView from './views/AdminView.vue'
import LoginView from './views/LoginView.vue'
```

**APRES** :
```javascript
import HubView from './views/HubView.vue'

const GenresView = () => import('./views/GenresView.vue')
const GenreDetailView = () => import('./views/GenreDetailView.vue')
const CatalogView = () => import('./views/CatalogView.vue')
const WatchlistView = () => import('./views/WatchlistView.vue')
const TrackDetailView = () => import('./views/TrackDetailView.vue')
const ArtistDetailView = () => import('./views/ArtistDetailView.vue')
const SetDetailView = () => import('./views/SetDetailView.vue')
const PlaylistDetailView = () => import('./views/PlaylistDetailView.vue')
const ArtistsView = () => import('./views/ArtistsView.vue')
const SetsView = () => import('./views/SetsView.vue')
const AdminView = () => import('./views/AdminView.vue')
const LoginView = () => import('./views/LoginView.vue')
```

Le reste du fichier (`routes`, `router.beforeEach`, etc.) ne change PAS.

### 2. Analyse de bundle

Installer `rollup-plugin-visualizer` en devDependency :
```bash
cd server/frontend && npm install -D rollup-plugin-visualizer
```

Ajouter dans `vite.config.js` (conditionnel, uniquement en mode analyze) :
```javascript
import { visualizer } from 'rollup-plugin-visualizer'

export default defineConfig({
  plugins: [
    vue(),
    // Activer avec : ANALYZE=true npm run build
    process.env.ANALYZE && visualizer({ open: true, gzipSize: true }),
  ].filter(Boolean),
  // ... rest of config
})
```

Ne PAS activer par defaut — uniquement via `ANALYZE=true npm run build`.

### 3. Accessibilite — aria-label sur boutons icone

Ajouter `aria-label` sur TOUS les `<button>` qui contiennent uniquement un SVG (sans texte visible).

Fichiers a verifier et corriger (12 fichiers avec boutons SVG) :

| Fichier | Boutons a labelliser |
|---------|---------------------|
| `PlayerBar.vue` | play/pause, previous, next, mute, close (5 existants deja, verifier) |
| `SearchBox.vue` | clear button (deja fait normalement, verifier) |
| `GenreCard.vue` | play button overlay |
| `ArtistCard.vue` | play button overlay |
| `GenreTrackRow.vue` | play button |
| `HeroPlayer.vue` | play/pause button |
| `LikeDislike.vue` | like button, dislike button |
| `HubView.vue` | play buttons sur resultats |
| `SetsView.vue` | play buttons, filter toggle |
| `CatalogView.vue` | play buttons, view toggle, filter buttons |
| `LoginView.vue` | google login button |
| `GenreDetailView.vue` | play buttons |

Pattern : `<button aria-label="Lecture">` ou `<button aria-label="Fermer">` etc.

Exemples de labels FR :
- Play → `aria-label="Lecture"`
- Pause → `aria-label="Pause"`
- Close → `aria-label="Fermer"`
- Clear search → `aria-label="Effacer la recherche"`
- Mute → `aria-label="Couper le son"`
- Like → `aria-label="Aimer"`
- Dislike → `aria-label="Ne pas aimer"`
- Next → `aria-label="Suivant"`
- Previous → `aria-label="Precedent"`

### 4. Accessibilite — aria-live sur resultats dynamiques

Ajouter `aria-live="polite"` sur les conteneurs de resultats qui changent dynamiquement :
- `.genre-grid` dans GenresView
- `.results` dans HubView (resultats de recherche)
- Les listes de tracks dans CatalogView
- Le compteur de resultats dans les headers

Pattern : `<div class="genre-grid" aria-live="polite">`

### 5. Accessibilite — Skip link

Ajouter un lien "Aller au contenu" en haut de `App.vue`, avant la sidebar.
Le lien est visuellement cache sauf au focus clavier (Tab).

```html
<a href="#main-content" class="skip-link">Aller au contenu</a>
```

```css
.skip-link {
  position: absolute;
  top: -100%;
  left: 16px;
  z-index: 9999;
  padding: 8px 16px;
  background: var(--accent);
  color: var(--on-accent);
  border-radius: var(--r-sm);
  font: 500 14px var(--font-ui);
  text-decoration: none;
}
.skip-link:focus {
  top: 8px;
}
```

Ajouter `id="main-content"` sur le conteneur principal (le `<main>` ou la zone de contenu a droite de la sidebar).

### 6. Accessibilite — Keyboard navigation sur chips/filtres

Les composants `SegFilter.vue` et `FamilyChips.vue` utilisent des `<button>` — la navigation
clavier (Tab + Enter/Space) fonctionne deja nativement avec les boutons HTML.

Verifier simplement que :
- Tab navigue entre les boutons
- Enter/Space active le bouton focus
- Le focus visible est style (outline ou box-shadow)

Si le focus n'est pas visible, ajouter dans chaque composant :
```css
button:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}
```

## Fichiers a modifier

| Fichier | Modification |
|---------|-------------|
| `src/router.js` | Lazy loading 12 routes |
| `vite.config.js` | Ajouter visualizer (conditionnel) |
| `package.json` | Ajouter `rollup-plugin-visualizer` devDep |
| `App.vue` | Skip link + `id="main-content"` |
| `SearchBox.vue` | Verifier aria-label sur clear |
| `SegFilter.vue` | Ajouter focus-visible si manquant |
| `FamilyChips.vue` | Ajouter focus-visible si manquant |
| 12 fichiers .vue | Ajouter aria-label sur boutons icone |

## Verification

```bash
# Lazy loading actif — chunks separees
cd server/frontend && npm run build 2>&1 | grep "chunk"
# → doit montrer plusieurs chunks .js (un par vue lazy)

# Zero bouton icone sans aria-label
grep -rn "<button" server/frontend/src/ --include="*.vue" | grep -v "aria-label" | grep -v "visible text"
# → verifier manuellement que chaque match a du texte visible ou un aria-label

# Skip link present
grep "skip-link" server/frontend/src/App.vue
# → doit matcher

# ESLint clean
cd server/frontend && npx eslint src/

# Prettier clean
cd server/frontend && npx prettier --check src/

# Tests frontend
cd server/frontend && npx vitest run
```

## Contraintes

- Zero couleur hardcodee — tout via `var(--...)`
- Code en anglais, UI en francais (les aria-labels en francais aussi)
- Ne PAS changer la logique metier des vues
- Ne PAS changer le rendu visuel
- Les aria-labels doivent etre concis et descriptifs
- Le skip link doit etre invisible sauf au focus clavier
- Pas de handler @click multi-instructions inline
