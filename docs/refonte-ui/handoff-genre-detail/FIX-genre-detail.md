# FIX — Détail genre `/style/:genre` · Revue post-implémentation (round unique) + TRIAGE

> Revue Claude Design reçue 2026-08-05. Verdict DA : implémentation fidèle, 1 bloquant + 4 mineurs/cosmétiques + 3 suggestions hors-FIX.
> Triage William/Claude : chaque écart vérifié contre le code (et le [visuel] douteux mesuré via CDP) AVANT acceptation.
> Preuves CDP produites : `ev-playlists-mobile-dark.png`, `ev-avatars-dark.png` (dans `C:\tmp\captures-genre-detail\`).

## Verdicts

| # | Écart (DA) | Sévérité DA | Vérification | Verdict | Résolution |
|---|------------|-------------|--------------|---------|------------|
| 1 | Shelf Playlists : 2ᵉ colonne coupée en mobile (`repeat(2,1fr)` min-content + `.sc-sub` nowrap, débord masqué par `.rel-body{overflow:hidden}`) | bloquant | **Code confirmé** (`ShelfCard.sc-sub{white-space:nowrap}` l.109 + `RelBlock.rel-body{overflow:hidden}` l.46 + `.cards-grid:repeat(2,1fr)`) **+ visuel confirmé** (ev-playlists-mobile : colonne droite tronquée, « DEEZER »→« D ») | **ACCEPTÉ** | Page CSS : `.cards-grid` → `repeat(N, minmax(0,1fr))` (4/3/2) + override `:deep(.sc-sub)` : `overflow:hidden; text-overflow:ellipsis` |
| 2 | « Voir les 4968 autres » (Sets/Playlists) sans espace fine, alors que le lien Explorer de la tracklist l'a | mineur | **Code confirmé** : `\`Voir les ${setsTotal - sets.length} autres\`` (raw) vs tracklist `fmtNum(...)` | **ACCEPTÉ** | Page : envelopper les 2 compteurs de `.load-more` dans `fmtNum()` |
| 3 | Compteurs d'en-tête de shelf non formatés (« Sets 4976 » vs Tracks « 16 412 ») | cosmétique | **Code confirmé** : `RelBlock` rend `{{ count }}` brut (prop `count:{type:Number}`), rendu identique sur **Track/Artist/Set Detail** (toutes les fiches consommant RelBlock) | **REJETÉ (lot)** | Composant partagé, non modifiable pour une page → **reliquat transverse** : élargir `RelBlock.count` à `[Number,String]` (ou format interne) pour que les pages passent `fmtNum(...)`. S'appliquera à toutes les fiches détail |
| 4 | Statline « SETS n » ≠ en-tête de la section Sets | mineur | **Données confirmées** : `genre.setCount` (détail) vs `total` (endpoint sets) — Techno **5218 ≠ 5140**, Musiques de films **3 ≠ 1** ; les Playlists concordent (8/8, 1/1) | **ACCEPTÉ** | Page : la statline Sets/Playlists = compteur de navigation vers la section → binder sur `setsTotal`/`playlistsTotal` (le total de section, autoritaire) au lieu de `genre.setCount`/`genre.playlistCount`. **+ reliquat back** : `GET /api/genres/detail` sur-compte `setCount` vs `GET /api/genres/sets` (aligner les deux requêtes à la source) |
| 5 | Anneau des avatars du hero en dark = `--genre-tile-border-dark` (sombre), le brief G6 dit `--genre-tile-ink` | cosmétique | **`--genre-tile-border-dark` = convention repo** (utilisé par `ArtistCard.vue:366` + `GenreCard.vue:328` pour l'anneau avatar en dark ; token commenté « anneau avatar en dark »). **Visuel** (ev-avatars) : les 3 avatars restent distinguables, le chevauchement se lit | **REJETÉ** | Convention repo prime (triage). **Amender le BRIEF G6** : l'anneau est `--genre-tile-ink` en light, `--genre-tile-border-dark` en dark (token dédié app-wide), pas un écart d'implémentation |

## Suggestions hors-FIX (décisions du brief DA, pas des écarts) → reliquats

1. **Tuiles placeholder hero à plat noir sous le scrim** (capture 09) — la formule G2 (`--fb-*` dark × scrim 0.92 en bas) rend la rangée basse noire, lit comme un trou. Le code applique la formule à la lettre. Piste DA : relever la lightness des `--fb-*` pour les tuiles hero, ou n'appliquer que le voile (sans bas de scrim) sur les tuiles vides. **Reliquat DA** (raffinement de sa propre formule, non bloquant).
2. **Chips de voisins tronqués** (« ● Techno (Peak Time ») — cause `StyleTag.shortLabel` (`name.split('/')[0]`), pas la page, non rattrapable par `:deep()`. **Reliquat transverse** : couper sur la parenthèse fermante ou laisser l'ellipsis CSS opérer sur le nom complet (le `title` le porte déjà).
3. **« 1 tracks » / « 1 artistes en commun »** — le brief écrit littéralement « N tracks » → conforme ; règle de pluralisation `fmtCount` transverse à décider au niveau du kit. **Reliquat transverse.**

## Lot correctif (page-only, `GenreDetailView.vue`)

Écarts **1 + 2 + 4** — CSS + template, aucun composant partagé touché, aucune migration. Vérif = capture headless avant/après (CSS pur).

## Conforme (rappel DA, rien à corriger)

Hero G1–G6, statline, shelves (G7 % / G8 glyph), tracks G9/G10, genres proches, pilier « autres » G11, ordre vertical, grille d'audit — tout vérifié valeur par valeur. Détail dans le corps du FIX DA ci-dessus (section « Conforme »).
