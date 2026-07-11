# Handoff — Diggy Design System v1 « Wildflower »

Pour : un dev (toi + Claude Code) qui implémente la DA de **Diggy** dans un frontend **Vue 3**.

---

## 1. Ce qu'il y a dans ce paquet

| Fichier | Rôle |
|---|---|
| `diggy-tokens.css` | **La base à installer en premier.** Toutes les couleurs, type, ombres, rayons, densité, et le système de familles de style — en variables CSS. |
| `diggy-components.css` | Styles **de référence** des composants (track card, table, badges, tags, filtres, sidebar…). À recréer en `<style scoped>` Vue, pas à copier tel quel. |
| `diggy-style-map.js` | Source de vérité **style → famille de couleur** + helpers (classe d'un tag, ajout de nouveaux styles sans refaire les maths). |
| `reference/Diggy DA.html` | **Le prototype vivant.** Ouvre-le dans un navigateur : c'est le contrat visuel. Panneau « Tweaks » pour basculer light/dark, densité, et comparer les autres palettes. |

> ⚠️ Les fichiers HTML/JSX du dossier `reference/` sont une **maquette de référence faite en HTML** — pas du code de prod à copier. Le but est de **recréer ces écrans dans Vue 3** avec les patterns du repo. Les seuls fichiers destinés à entrer dans le code sont `diggy-tokens.css`, `diggy-style-map.js`, et l'esprit de `diggy-components.css`.

**Fidélité : haute.** Couleurs, type, espacements et états sont définitifs. Reproduis au pixel en t'appuyant sur les tokens.

---

## 2. Phase 1 — installer la base (à faire une fois)

**a. Fonts** — dans `index.html` :
```html
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
```

**b. Tokens** — copie `diggy-tokens.css` dans `src/styles/` et importe-le **une seule fois** au root :
```js
// main.js
import './styles/diggy-tokens.css'
```

**c. Dark mode & densité** — attributs sur `<html>` :
```js
document.documentElement.dataset.theme = 'dark'      // ou supprime pour light
document.documentElement.dataset.density = 'compact' // 'regular' (défaut) | 'comfy'
```

**d. Consommer les tokens** dans n'importe quel composant Vue :
```vue
<style scoped>
.card { background: var(--surface); border: 1px solid var(--line); border-radius: var(--r-md); }
.cta  { background: var(--accent); color: var(--on-accent); }
.bpm  { font-family: var(--font-mono); color: var(--ink-2); }
</style>
```

**e. (Optionnel) Tailwind** — pont vers les tokens dans `tailwind.config.js` :
```js
theme: { extend: { colors: {
  bg: 'var(--bg)', surface: 'var(--surface)', ink: 'var(--ink)',
  accent: 'var(--accent)', 'accent-ink': 'var(--accent-ink)', pos: 'var(--pos)',
}, fontFamily: { ui: 'var(--font-ui)', mono: 'var(--font-mono)' } } }
```

---

## 3. Le système de couleur (à comprendre une fois)

- **Base neutre = invariante.** Ivoire chaud + gris tièdes (`--bg`, `--surface`, `--ink…`, `--line…`). Ne change jamais d'une palette à l'autre. C'est le socle calme.
- **Duo Accent × In-lib.** `--accent` (mauve 328°) porte l'action, le rating, la key, le score. `--pos` (prairie 138°) signale « déjà dans ma lib live ». Choisis comme une fleur et sa feuille : proches mais jamais confondus.
- **4 familles de style.** Les styles sont regroupés par parenté sonore ; **une famille = une teinte**, ses membres en sont des variations (teinte + clarté). Voir `diggy-style-map.js`.

| Famille | Hue base | Membres actuels |
|---|---|---|
| House | 268° | Tech House, Deep House |
| Melodic | 312° | Melodic Techno, Progressive |
| Disco | 352° | Nu Disco, Breaks |
| Roots | 42° | Afro House, Organic |

**Ajouter un style** = l'ajouter à la fin du tableau de sa famille dans `diggy-style-map.js`, puis générer ses vars avec `styleVarsCss()` (ou via la classe `.style-tag--<slug>` dans `diggy-components.css`). Pas de maths à la main.

**Rendre un tag** (deux options) :
```vue
<!-- via classe -->
<span :class="styleTagClass(track.style)">{{ track.style }}</span>
<!-- via style inline -->
<span class="style-tag" :style="{ '--th': tone.hue, '--ts': tone.shade }">{{ track.style }}</span>
```

---

## 4. Composants à produire (priorité)

Specs exactes : `diggy-components.css` + le prototype. Ordre conseillé :

1. **`StyleTag`** — pill famille (la brique la plus réutilisée).
2. **`TrackCard`** — artwork carré gauche, titre/artiste + meta (BPM mono, key en `--accent-ink`, durée, rating), tag de style.
3. **`TrackTable`** — colonnes triables (header mono uppercase), hover `--surface-2`, hauteur de ligne = `--row-h`.
4. **`InLibBadge`** — `in` (rempli `--pos-soft`) vs `out` (contour pointillé neutre).
5. **`ScorePill`** — score radar 0–10, 10 ticks, en `--accent-soft`.
6. **`Filters`** — BPM range, select key, select style, toggle « in lib only ».
7. **`SidebarNav`** — items, item actif en `--accent-soft` / `--accent-ink`, compteur mono.

---

## 5. La boucle de travail — comment on se transmet l'intention

C'est un **ping-pong en 2 temps**, par module/écran :

**① Côté design (moi, dans cette app)** — pour chaque écran (Live lib, Radar, détail track, Catalog…) je produis :
- une **maquette HTML hi-fi** utilisant exactement ces tokens,
- un **mini-brief** : layout (grid/flex, largeurs, paddings), liste des composants, états (hover/empty/loading), copy exacte, comportements.

Je te donne ça en lien + (au besoin) un export téléchargeable.

**② Côté code (toi + Claude Code)** — tu ouvres la maquette, tu colles le brief à Claude Code, et il **recrée l'écran en Vue 3** avec les composants déjà construits + les tokens. Tu itères dans le repo.

**↔ Allers-retours** : si en codant une question de design surgit (« et le empty state du Radar ? », « le tri par défaut ? »), tu me la renvoies, je tranche visuellement, je mets à jour la maquette, tu réappliques.

> Règle d'or : **les tokens sont la frontière.** Le design ne livre jamais de couleur/typo « en dur » hors tokens ; le code ne réinvente jamais une valeur — il lit les vars. Tant que les deux côtés parlent en tokens, ça reste cohérent même quand on change la palette.

### Message prêt à coller à Claude Code (kickoff Phase 1)
```
Voici le design system d'un projet Vue 3 (Diggy, web app de gestion de
bibliothèque musicale pour DJ). Le dossier design_handoff_diggy_da/ contient :
- diggy-tokens.css : variables CSS (couleurs, type, ombres, densité, familles
  de style). Importe-le une fois dans main.js. Ne mets aucune couleur en dur.
- diggy-components.css : styles de référence des composants.
- diggy-style-map.js : map style→famille de couleur + helpers.
- reference/Diggy DA.html : la maquette de référence (ouvre-la pour voir le rendu).

Tâche Phase 1 : installe les fonts (Space Grotesk + JetBrains Mono), importe les
tokens, ajoute le toggle dark via data-theme sur <html>, puis crée les composants
de base en SFC Vue scoped en lisant les tokens : StyleTag, TrackCard, TrackTable,
InLibBadge, ScorePill, Filters, SidebarNav. Reproduis fidèlement diggy-components.css.
Ne touche pas aux valeurs : lis les variables. Montre-moi d'abord StyleTag + TrackCard.
```
Ensuite, écran par écran, tu répètes avec la maquette + le brief de chacun.

---

## 6. Tokens de référence rapide

- **Type** : Space Grotesk (UI/titres), JetBrains Mono (données : BPM, key, durée, score).
- **Rayons** : `--r-xs/sm/md/lg/xl` = 6/9/13/18/24px.
- **Ombres** : `--shadow-sm/md/lg`.
- **Densité** : `--row-h` 46/56/68px selon compact/regular/comfy.
- **Accent** mauve `--accent-h: 328`, **in-lib** prairie `--pos-h: 138`.
- Tout est en `oklch()` — pour changer de palette, il suffit de changer les hues (`--accent-h`, `--pos-h`, `--family-*` + `--h-*`/`--s-*`). Les 4 palettes explorées (Peony, Camellia, Wildflower, Cosmos) sont dans le prototype.
