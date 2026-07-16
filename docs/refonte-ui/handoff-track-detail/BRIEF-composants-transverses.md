# BRIEF — Composants transverses · vague refonte D4

> Spec de 4 composants **autonomes et réutilisables** — pas du styling de page. Première consommatrice : Track Detail ; réutilisés ensuite par Explorer, Radar, Hub, listes et autres pages détail.
> Démo vivante : nuancier en bas de `Track Detail (pilote).html` (tailles × états × thèmes).
> Tout en tokens `diggy-tokens.css`. Zéro couleur hardcodée, zéro CDN.

---

## `<Artwork>`

**Rôle** : rendu unique de toute cover — image réelle OU placeholder rayé — avec indicateur in-lib optionnel en coin. **Remplace `InLibBadge` (hero) et `LibDot` (lignes/tables) partout.**

**Props**

| Prop | Type | Défaut | Notes |
|---|---|---|---|
| `src` | `string?` | — | absent ou 404 → placeholder rayé |
| `alt` | `string` | `''` | |
| `size` | `'hero' \| 'card' \| 'row'` | `'row'` | hero 216 px · card fluide (largeur du parent) · row 36 px |
| `inLib` | `boolean?` | `undefined` | `undefined` = pas d'indicateur |

**Anatomie**

- Conteneur `aspect-ratio: 1`, `overflow: hidden`, border 1px `--ct-line`. Radius : hero/card `--r-md`, row `--r-xs`.
- **Placeholder rayé** : `repeating-linear-gradient(45deg, var(--surface-2) 0 6px, var(--surface-3) 6px 12px)` — theme-adaptif, aucun texte.
- **Indicateur in-lib** : pastille ronde en **débord coin bas-droit** (offset ≈ −20 % de son diamètre) : disque `--surface` + border 1px `--line` + `--shadow-sm`, qui garantit la lisibilité sur cover, sur placeholder et dans les deux thèmes. Contenu :
  - `inLib = true` → point plein `--pos` (dans la bibliothèque Rekordbox)
  - `inLib = false` → cercle pointillé `1.5px dashed --ink-3` (absent)
- Tailles pastille/point : hero 20/9 px · card 16/7 px · row 12/5 px.
- **Hors scope** : cards agrégées (artiste, genre…) — l'in-lib y est un *count* affiché en stat dans le body, jamais un badge overlay (décision TRANSVERSE).

---

## `<TrackCard>` — variante ligne

**Rôle** : ligne track compacte pour grilles denses (Track Detail : « Du même artiste », « Tracks similaires » ; puis Explorer, listes). **Parenté** : la variante *card verticale* (Hub/shelves, cadrée dans TRANSVERSE) partagera la même anatomie de contenu — ici on ne spécifie que la **ligne**.

**Props**

| Prop | Type | Notes |
|---|---|---|
| `track` | `{id, title, artist?, bpm, key, has_artwork, has_preview, in_lib}` | |
| `showArtist` | `boolean` | `false` = variante « même artiste » |
| `playing` | `boolean` | |
| `onPlay` | `() => void` | ignoré si `!has_preview` |
| `#end` | slot | `<ScoreRing>` pour les similaires, vide sinon |

**Anatomie** — grid `36px 1fr 42px 30px [auto]`, gap `--space-3`, padding `--space-2 --space-3`, bg `--surface`, border 1px `--line`, `--r-sm`.

| Zone | Spec |
|---|---|
| Artwork | `<Artwork size="row" :inLib>` ; **play overlay** au hover : `--overlay-soft` + triangle `--overlay-text` (invariants), rendu seulement si `has_preview` |
| Titre | `--fs-sm` 600 `--ink`, ellipsé ; artiste optionnel dessous `--fs-xs` `--ink-3` |
| BPM | mono `--fs-sm` `--ink-2`, aligné droite |
| Key | mono `--fs-sm` 500 `--accent-ink` |
| Slot fin | `<ScoreRing size="sm">` ou rien |

**États** : repos · hover (`--surface-2` + border `--line-2` + play visible) · playing (`--accent-wash`, icône pause, hover reste `--accent-wash`) · sans preview (jamais de play). Container query < 640 px : **play toujours visible**. Transitions 0.12 s.

---

## `<ScoreRing>`

**Rôle** : forme **canonique** de tout score /10 (similarité C2, scores Radar Tendance / Pour toi…). Le float 0-1 sert au tri, **jamais affiché**. **Unifie et remplace `ScorePill`** (texte %) ; `RingPct` (proportion d'un tout, ex. identified/total) migrera vers la même géométrie en mode % — même anneau, deux modes d'affichage.

**Props**

| Prop | Type | Notes |
|---|---|---|
| `score` | `number` 0-1 | affiché `Math.round(score × 10)` |
| `size` | `'sm' \| 'md'` | sm 30 px (ligne) · md 40 px (card) |

**Anatomie** : anneau SVG — piste `--line-2`, arc valeur `--accent` (remplissage = note/10, départ 12 h, `stroke-linecap: round`), stroke 2.5 px (sm) / 3 px (md). Centre : note entière mono 600, `--fs-xs` (sm) / `--fs-sm` (md), `--ink`. Pas de « /10 » affiché à ces tailles (implicite). Aucune animation.

**A11y** : `role="img"` + `aria-label="Similarité 9 /10"` (libellé selon le contexte).

---

## `<PlatformLink>`

**Rôle** : lien vers une plateforme tierce rendu en **logo**, jamais en nom texte. Ici : Beatport, Deezer ; ailleurs : SoundCloud, YouTube, TrackID, Spotify, 1001Tracklists.

**Props**

| Prop | Type | Notes |
|---|---|---|
| `platform` | enum | `beatport · deezer · tidal · soundcloud · youtube · spotify · trackid · 1001tl` |
| `href` | `string` | `target="_blank" rel="noopener"` |
| `size` | `'md' \| 'sm'` | md 38 px (aligné `.btn` du hero) · sm 30 px |
| `variant` | `'button' \| 'glyph'` | `glyph` = logo seul non cliquable (~13 px, `--ink-2`), pour marquer une **source** dans une liste dense (ex. « Détecté dans ») ; porte `title` + `aria-label` (« Détecté sur Deezer ») |

**Anatomie** : carré `.btn` (bg `--surface`, border `--line-2`, `--r-sm`), logo SVG 16 px. **Monochrome `currentColor`** : `--ink-2` → hover `--surface-2` + `--ink` (décision D6 — pas de couleurs de marque). Focus visible : outline 2px `--accent`, offset 2px.

**Contrainte CSP** : logos en **SVG inline / data-URI**, aucun CDN. Les tracés de la maquette sont des marques simplifiées — les remplacer par les SVG officiels (version mono, `fill`/`stroke: currentColor`) à l'implémentation.
**Logos temporaires (décision William 17/07/2026)** : les SVG officiels ne sont pas encore fournis → l'implémentation embarque les tracés simplifiés de la maquette comme placeholders, centralisés dans `PlatformLink.vue` (map `platform → path` unique, commentaire `TODO logos officiels`). Remplacement ultérieur = éditer ce seul fichier.

**A11y** : `aria-label="Voir sur Beatport"` — le logo est le seul contenu visible.

---

## Consommateurs (première vague)

| Composant | Track Detail | Ensuite |
|---|---|---|
| `<Artwork>` | cover hero + rows | Catalog, recherche Hub, TrackCard, Sets, toutes covers |
| `<TrackCard>` ligne | même artiste, similaires | Explorer, listes ; parent de la variante card (Hub) |
| `<ScoreRing>` | similaires | Radar (Tendance, Pour toi), `/for-you` ; absorbe RingPct à terme |
| `<PlatformLink>` | Beatport, Deezer (hero) · glyphes sources Deezer/Tidal/Spotify (« Détecté dans ») | Set detail, Artist detail, Playlist detail |
