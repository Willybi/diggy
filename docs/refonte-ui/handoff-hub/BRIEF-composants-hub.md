# BRIEF — `<DiscoveryCard>` · carte de découverte réutilisable

> **Le morceau design de ce handoff.** Composant **autonome et réutilisable** — pas du styling de page. Aujourd'hui les 3 étagères du Hub dupliquent chacune leur markup de carte inline ; on spécifie **un composant unique** consommé par les aperçus Hub (Ça sort / Pour toi / Nouveautés) **et** les futures pages destinations (`/new-releases`, colonnes cards de Radar).
>
> **Nom : `<DiscoveryCard>`.** NE PAS l'appeler `TrackCard` — c'est déjà le composant **ligne dense** existant (Track/Playlist/Set Detail), distinct. `<DiscoveryCard>` = variante **card horizontale**, la déclinaison « card » restée à cadrer dans `TRANSVERSE.md` § Composants de découverte mutualisés.
>
> Démo vivante : nuancier en bas de `Hub (pilote).html` (écran « Nuancier ») — tendance #rank, reco in-lib, nouveauté release, set, lien externe, sans cover, playing, méta dégradée, skeleton.
>
> Tout en tokens `diggy-tokens.css`, zéro couleur hardcodée, zéro CDN, icônes SVG inline `currentColor`.

## Anatomie (une seule, props optionnelles)

Carte **horizontale** entièrement cliquable, `--r-md`, `--surface` + `1px --line` + hover `--surface-2`/`--line-2` :

```
┌──────────────────────────────────────────┐
│ ┌──────┐  [badge] Titre du morceau…       │   ← cover 64px + corps 3 lignes
│ │cover │  Artiste, Artiste…               │
│ │ ▶ ●  │  128 · 4A · 6 j                   │   ← play (hover) + in-lib · méta mono
│ └──────┘                                   │
└──────────────────────────────────────────┘
```

| Zone | Spec | Tokens |
|---|---|---|
| Conteneur | `display:flex`, `gap --space-25`, `padding --space-2`, `min-width:0`, `cursor:pointer`, transition 0.12s. Hover → bg `--surface-2` + border `--line-2` (pas de scale, pas d'ombre ajoutée) | bg `--surface`, border 1px `--line`, `--r-md` |
| Cover | `<Artwork>` 64 px carré `--r-sm`, `flex-shrink:0`, `overflow:hidden`. Cover réelle (`/storage/catalog-artworks/{id}.jpg`) OU placeholder rayé (`repeating-linear-gradient` `--surface-2`/`--surface-3`). Porte le play (H-play) et l'indicateur in-lib | `--r-sm` |
| Titre | 1 ligne, 600 `--fs-title` `--ink`, ellipsis | `--font-ui` |
| Artiste(s) | 1 ligne, 400 `--fs-sm` `--ink-3`, ellipsis. `artists[]` joints « , » (jamais supposer un seul) | — |
| Méta | ligne mono compacte `BPM · KEY · âge`, 500 `--fs-xs` `--ink-3`, `nowrap` + ellipsis. Champs nuls **omis** (pas de tiret), séparateur ` · ` ajusté | `--font-mono` |

## Props

| Prop | Type | Notes |
|---|---|---|
| `title` | `string` | ellipsis 1 ligne |
| `artists` | `{id, name}[]` | joints « , », cliquables en prod (fallback chaîne plate `artist`) |
| `coverId` + `hasArtwork` | `number`, `boolean` | passés à `<Artwork>` ; `false` → placeholder rayé |
| `hasPreview` | `boolean` | `true` → bouton play sur cover ; `false` → pas de play |
| `rank` | `number?` | présent → badge `#rank` accent (variante tendance) |
| `badge` | `'Nouveauté' \| 'Set'?` | pill de typage (avec glyph : `#s-ext` pour lien externe, `#s-set` pour set) |
| `meta` | `{bpm?, key?, age?}?` | `age` = **token brut** issu de `relativeAge` (`6 j`/`2 sem`/`3 mois`), pas « Sorti il y a… » (compacité, cf. BRIEF-hub H3) |
| `inLib` | `boolean?` | `true` → point plein `--pos` ; `false` → cercle pointillé `--ink-3` ; `undefined` → aucun indicateur (donnée absente de l'endpoint) |
| `to` | `route \| {href, external}` | cible du clic : `/catalog/:id`, `/set/:id`, ou lien Deezer `target="_blank"`. **Invité** → intercepté vers `/login` |
| `playing` | `boolean` | piloté par le player global ; surligne la carte + bascule play→pause |
| `onPlay` | `() => void` | callback preview |

## Matrice de variantes (une anatomie, props qui varient)

| Variante | Badge | Méta | Cover / Play | Cible clic |
|---|---|---|---|---|
| **Ça sort** (tendance) | `#rank` (accent) | `BPM · KEY · âge` | cover + play si `has_preview` | `/catalog/:id` (invité → login) |
| **Pour toi** (reco) | — | `BPM · KEY · âge` | cover + play si preview + **indicateur in-lib** | `/catalog/:id` |
| **Nouveautés — release** (crawlée) | « Nouveauté » | `BPM · KEY · âge` | cover + play si preview | `/catalog/:id` |
| **Nouveautés — lien externe** | « Nouveauté » (+ glyph externe) | `il y a X` (+ « Sur Deezer ») | **pas de cover/play** (placeholder rayé) | lien Deezer `target="_blank"` |
| **Nouveautés — set** | « Set » (+ glyph disque) | `il y a X` | **pas de cover/play** | `/set/:id` |

Badge tokens : `#rank` & « Nouveauté » = `--accent-soft`/`--accent-ink` ; « Set » = `--surface-2`/`--ink-2`. Tous : pill `--r-pill`, `--fs-nano` mono uppercase, glyph optionnel 10 px.

## Bouton play (H-play)

- Cercle **32 px** centré sur la cover, révélé au **survol desktop** (`opacity` 0→1, 0.12 s) ; **toujours visible < 640 px** (tactile). Scrim `--overlay-soft` derrière l'icône au survol/lecture (transparent au repos).
- Repos : `--surface` + border `--line-2`, icône `--ink` (triangle play). **Playing** : `--accent`/`--on-accent` + icône pause, carte surlignée.
- `has_preview=false` → **pas de bouton** (set, lien externe).
- Cible tactile : la carte entière reste cliquable ; le play `stopPropagation`.

## `<Artwork>` (EXISTE — consommé, pas re-designé)

Gère la cover réelle **ou** le placeholder rayé + **indicateur in-lib** optionnel en coin (point plein `--pos` = dans Rekordbox / cercle pointillé `--ink-3` = absent), lisible même sur placeholder. `<DiscoveryCard>` le **consomme** en taille card 64 px ; il ne re-spécifie ni la cover ni l'indicateur.

## États

| État | Spec |
|---|---|
| Repos | tokens ci-dessus |
| Hover | bg `--surface-2` + border `--line-2` ; play révélé (desktop) — 0.12 s, pas de scale |
| Focus | outline 2 px `--accent`, offset 2 px (clavier) |
| `playing` | carte surlignée `--accent-wash` + bouton pause accent |
| Sans preview | pas de bouton play |
| Sans cover (`has_artwork=false`) | placeholder rayé standard `<Artwork>` |
| Méta dégradée | champs nuls omis (set → âge seul ; track sans key → `BPM · âge`) ; jamais de tiret |
| Troncature | titre/artiste ellipsis 1 ligne ; méta mono ellipsis (**âge tombe en premier**) |
| Skeleton | cover `--surface-3` + 3 barres (`--surface-3`/`--surface-2`), `hb-pulse` 1,4 s |

## Cohabitation avec `ActivityAlbumCard` (EXISTE)

Contrainte : la carte album dépliable vit dans la **même grille** que `<DiscoveryCard>` (Nouveautés) → **même langage visuel**, aligné (on cale le look de l'album, on ne le re-crée pas) :
- Même conteneur (`--surface`/`--line`/`--r-md`), **même cover 64 px**, même en-tête horizontal (badge « Album » + titre + artiste + méta mono `N titres · il y a X`).
- **Différence** : à la place du play, un **chevron rond 32 px** ; déplié → liste de titres sous `border-top --line` (`[# mono] [titre] [BPM · KEY]` par rangée `hb-rrow`).
- **Hauteur repliée identique** à `<DiscoveryCard>` ; déploiement = hauteur auto de la cellule de grille (aucun décalage des cartes voisines de la même rangée au-delà de l'expansion).

## Responsive

Fluide — la **grille parente décide** (cible 3 col ≥ 720 px → 2 col < 720 → 1 col < 640, gap `--space-3`). La carte remplit sa cellule ; en 1 colonne mobile elle reste dense (cover 64 + corps 3 lignes) et le play est **toujours visible**. Container queries (`@container`), jamais `@media`.

## Consommateurs

| Consommateur | Grille | Variantes | in-lib |
|---|---|---|---|
| **Hub — Ça sort** | 3 / 2 / 1 col | tendance (#rank) | — |
| **Hub — Pour toi** | 3 / 2 / 1 col | reco | oui |
| **Hub — Nouveautés** | 3 / 2 / 1 col | release · lien externe · set (+ `ActivityAlbumCard`) | — |
| **`/new-releases`** (à venir) | à cadrer par sa fiche | release · lien externe · set (+ album) | — |
| **Radar** (cards, si migration) | selon la page | tendance · reco | oui |

## Audit composant

Une anatomie unique, 5 variantes par props · méta mono `BPM · KEY · âge` dégradée sans tiret · âge token brut · badge contextuel (#rank / Nouveauté / Set) monochrome accent · in-lib affiché seulement si la donnée existe · play hover-reveal desktop + toujours visible < 640 + absent sans preview · `<Artwork>` consommé (non re-designé) · cohabitation `ActivityAlbumCard` (même grille, même hauteur, même look) · `artists[]` jamais réduit à un seul nom · fluide en grille, container queries · tokens 100 %, SVG `currentColor`, FR.
