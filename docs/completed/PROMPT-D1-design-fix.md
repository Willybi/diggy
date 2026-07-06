# D1 -- FIX Design Immediats

## Objectif

Corriger les couleurs hardcodees, ajouter le token `--sidebar-w`, et appliquer les
fix design en attente (SetsView, HubView, ArtistCard, Player).

## Ref design

- `_design/handoff-sets-fix/BRIEF-sets-fix.md` -- brief sets (4 FIX)
- `_design/design_handoff_diggy_da/realign/PROMPT-claude-code-player-round2.md` -- player round 2

## Taches

### 1. Token `--sidebar-w` dans diggy-tokens.css

Le token n'existe pas encore. L'ajouter dans la section layout :

```css
:root {
  /* ... existing tokens ... */
  --sidebar-w: 232px;
}

@media (max-width: 900px) {
  :root {
    --sidebar-w: 66px;
  }
}
```

Puis remplacer les valeurs hardcodees dans :
- `PlayerBar.vue` : `left: calc(232px + 24px)` -> `left: calc(var(--sidebar-w) + 24px)`
- `PlayerBar.vue` media query : `left: calc(66px + 24px)` -> peut etre supprime (le token change deja)
- `App.vue` : verifier si `232px` / `66px` sont hardcodes dans le grid layout -> remplacer par `var(--sidebar-w)`

### 2. Couleurs hardcodees -- HubView.vue

**Ligne 1095** : `color: #fff` sur `.rart .play`
- Remplacer par : `color: var(--on-accent)`

**Ligne 1094** : `background: oklch(0.2 0.02 70 / 0.42)` sur `.rart .play`
- Creer un token si necessaire ou utiliser un token overlay existant
- Suggestion : `background: oklch(var(--ink) / 0.42)` ou ajouter `--overlay-dark: oklch(0.2 0.02 70 / 0.42)` dans tokens

### 3. Couleurs hardcodees -- ArtistCard.vue

Plusieurs oklch hardcodes pour les overlays sombres :

| Ligne | Valeur actuelle | Remplacement |
|-------|----------------|-------------|
| 247 | `oklch(0.12 0.02 262 / 0.34)` | `--overlay-dark` token ou laisser (effet visuel specifique) |
| 256 | `oklch(0.12 0.02 262 / 0.34)` | idem |
| 275 | `oklch(0 0 0 / 0.038)` | Pattern overlay, acceptable inline |
| 332 | `oklch(0.2 0.02 262 / 0.72)` | Ajouter `--overlay-modal: oklch(0.2 0.02 262 / 0.72)` |
| 334 | `oklch(0.96 0.01 92)` | `var(--surface)` ou `var(--on-accent)` |
| 357 | `oklch(0.2 0.02 262 / 0.72)` | `var(--overlay-modal)` |
| 359 | `oklch(0.96 0.01 92)` | `var(--surface)` |

Pour les overlays visuels (247, 256, 275), ce sont des effets graphiques complexes (gradients avec
plusieurs stops et des variables CSS). Il est acceptable de les laisser si les extraire en tokens
n'a pas de sens semantique. Concentrer l'effort sur les lignes 332-359 (modal backgrounds).

### 4. Couleurs hardcodees -- SetsView.vue

**Ring low state** (anneau pourcentage faible) :
- Ligne 921 : `stroke: oklch(0.74 0.13 60)` -> `stroke: var(--warn)`
- Ligne 954 : `color: oklch(0.52 0.13 60)` -> `color: var(--warn-ink)`

Ces couleurs ambre correspondent exactement aux tokens `--warn` / `--warn-ink` (hue 70, proche de 60).
Le token `--warn` existe deja dans diggy-tokens.css (lignes 62-64).

### 5. FIX Sets (ref BRIEF-sets-fix.md)

Lire le brief complet : `_design/handoff-sets-fix/BRIEF-sets-fix.md`

**FIX #1 -- Boutons "Importer + Suivre"** :
Les classes `.btn-follow` / `.btn-follow.done` manquent dans le CSS de SetsView.vue.
Les regles CSS doivent etre ajoutees selon le brief (section 1).

**FIX #2 -- Anneau 100%** :
Actuellement quand `ringPct >= 100`, le code affiche un check SVG.
Verifier que le style `.ring.done` est bien defini avec les couleurs correctes.
Le brief propose 2 options -- implementer l'option "calme neutre" (check + texte "100%") :
- `.ring.done .chk svg` : stroke `var(--pos)`
- `.ring.done .pct` : color `var(--pos-ink)`

**FIX #3 -- Compteur en-tete** :
Lignes 6-11 : le header montre `sets.length` (filtre) au lieu du total.
Corriger pour afficher : `{totalSets} sets . {displayList.length} affiches`
Utiliser la variable `totalCount` si elle existe, sinon la totalite avant filtre.

**FIX #4 -- Vocabulaire** :
Le wording des filtres utilise "Suivre" au lieu de "Avis". Verifier la coherence
avec le brief et aligner sur le vocabulaire Radar (Aimes / Rejetes / A explorer).

### 6. Player round 2 (ref PROMPT-claude-code-player-round2.md)

Lire le brief : `_design/design_handoff_diggy_da/realign/PROMPT-claude-code-player-round2.md`

Les 5 recommandations :
1. **Icone pause sur track actif** dans les tables -- quand un track est en cours de lecture,
   afficher une icone pause a la place du bouton play dans TrackTable/MiniTrackTable
2. **Gestion erreur preview** -- si `preview_url` est absent ou invalide, afficher un message
   au lieu de crasher silencieusement
3. **Token `--sidebar-w`** -- deja traite en tache 1
4. **Position player** -- utiliser `var(--sidebar-w)` pour le positionnement
5. **Transition fluide** -- verifier que le player bar a une transition smooth a l'ouverture

## Verification

```bash
# Zero couleur hardcodee hors Google branding (LoginView)
grep -rn "#[0-9a-fA-F]\{3,8\}" server/frontend/src/ --include="*.vue" | grep -v LoginView
# -> doit etre vide

# Token sidebar-w present
grep "sidebar-w" server/frontend/src/styles/diggy-tokens.css
# -> doit matcher

# Ring utilise tokens warn
grep "warn" server/frontend/src/views/SetsView.vue
# -> doit matcher

# ESLint clean
cd server/frontend && npx eslint src/

# Prettier clean
cd server/frontend && npx prettier --check src/

# Tests frontend
cd server/frontend && npx vitest run
```

## Contraintes

- Zero couleur hardcodee (tout via `var(--...)` sauf Google branding dans LoginView)
- Pas de changement de logique JS, uniquement CSS/template
- Code en anglais, UI en francais
- Tester visuellement en light ET dark mode
- Les tokens doivent avoir une version dark mode dans `[data-theme="dark"]` si applicable
