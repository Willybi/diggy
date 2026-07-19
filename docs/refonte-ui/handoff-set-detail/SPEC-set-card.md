# SPEC — `<SetCard>` · carte set réutilisable

> Composant **autonome et réutilisable** — pas un fragment de page. Première consommatrice : section « Sets similaires » de Set Detail ; réutilisée telle quelle par la refonte future de la liste `/sets`. Tout en tokens `diggy-tokens.css`, zéro couleur hardcodée, zéro CDN.
> Démo vivante : nuancier en bas de `Set Detail (pilote).dc.html` (complète · sans artwork · méta partielle).

## Props

| Prop | Type | Notes |
|---|---|---|
| `set` | `{id, title, source, played_date, duration_ms, has_artwork, total_tracks, identified_tracks, artists[]}` | contrat `GET /api/sets/{id}/similar` — `artists[]` = noms simples |
| `#footer` | slot | vide par défaut — point d'extension (futur : `<ScoreRing>`, badge source…) sans re-spec |

La carte n'affiche **ni `score` ni `identified_tracks`** (décision S10 Set Detail : le tri porte la proximité, l'identification se lit sur la page). Le slot existe pour que `/sets` puisse en décider autrement sans toucher au composant.

## Anatomie

Carte verticale entièrement cliquable (`<a href="/set/:id">`, un seul lien — les artistes sont des noms, pas des liens) :

| Zone | Spec | Tokens |
|---|---|---|
| Conteneur | flex column, gap `--space-25`, padding `--space-3` | bg `--surface`, border 1 px `--line`, `--r-md`, `--shadow-sm` |
| Cover | `<Artwork size="card">` (fluide, carré, placeholder rayé si `has_artwork=false`), **sans** indicateur in-lib (l'in-lib d'un set serait un *count* → stat de body, décision TRANSVERSE — absent ici) | `--r-md`, border `--ct-line` |
| Titre | `--fs-sm` 600 `--ink`, **clamp 2 lignes** (les titres de sets sont longs), `overflow-wrap: anywhere` | line-height 1.3 |
| Artistes | noms joints « , », 1 ligne ellipsée. Vide → ligne absente | `--fs-xs` 400 `--ink-3` |
| Méta | une ligne mono : `date · durée · N tracks` (`jj/mm/aaaa` · `h:mm:ss` · `total_tracks`). **Champs null omis, séparateurs ajustés** — jamais de tiret | `--fs-xs` 500 mono `--ink-3` |

## États

| État | Spec |
|---|---|
| Repos | tokens ci-dessus |
| Hover | bg `--surface-2` + border `--line-2`, transition 0.12 s — pas de scale, pas d'ombre ajoutée |
| Focus | outline 2 px `--accent`, offset 2 px |
| Sans artwork | placeholder rayé standard `<Artwork>` |
| Méta partielle | champs omis (ex. « 2:01:15 · 30 tracks » sans date) |

## Responsive

La carte est **fluide** — la grille parente décide (cible min ≈ 150 px). Sur Set Detail : 4 colonnes → 3 (< 720 px) → 2 (< 640 px), gap `--space-4`. Cible tactile : la carte entière (≥ 44 px partout).

## Consommateurs

| Consommateur | Grille | Slot footer |
|---|---|---|
| **Set Detail — Sets similaires** (1ʳᵉ vague) | 4 / 3 / 2 colonnes | vide |
| `/sets` (refonte future) | à cadrer par sa fiche | libre (ex. count in-lib en stat) |
