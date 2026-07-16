# BRIEF — Track Detail `/catalog/:id` · Refonte D4, page 1

> Maquette pilote : `Track Detail (pilote).html` — toggles thème dark/light + viewport desktop/375 px dans la toolbar de revue ; états démo (blocs présents, loading similaires, `is_admin`) via le panneau Tweaks ; nuancier des composants transverses en bas de maquette.
> Consomme les 4 composants partagés — spec autonome dans `BRIEF-composants-transverses.md`.
> Tout en tokens `diggy-tokens.css`, zéro couleur hardcodée. DA Wildflower v1 inchangée.
> **Refonte, pas création** : structure actuelle conservée et polie. **Rating supprimé partout** (chantier transverse), aucune demande backend.

## Ordre vertical

1. `dv-back` (← Catalog)
2. **Hero** — cover `<Artwork>` + identité + stats musicales + actions + liens externes
3. **Découverte** — « Du même artiste » · « Tracks similaires » (grilles `<TrackCard>` ligne)
4. **« Où on l'entend »** — `.rel-cols` : « Apparaît dans » (sets) · « Détecté dans » (playlists radar)
5. **AdminCard** — inchangée, gatée `is_admin`, tout en bas. Hors périmètre design.

Pas d'état invité : les invités sont confinés au Hub, cette page est toujours authentifiée.

## Décisions DA explicites

| # | Décision | Justification |
|---|---|---|
| D1 | **StatStrip supprimée.** Les 4 stats musicales **BPM · Key · Durée · Année** intègrent le hero : data-row mono sous les chips | Carte d'identité du track = à côté du titre. Une bande horizontale de moins, hero plus riche, scroll réduit |
| D2 | **Compteurs Radar** (`nb_radar_playlists`, `nb_radar_sets`) portés par les en-têtes de bloc « Où on l'entend » (« 3 sets », « 4 playlists ») | La donnée contextuelle vit à côté de son contexte ; supprime le doublon strip/bloc |
| D3 | Un seul bloc présent → **la grille `.rel-cols` reste 2 colonnes**, le bloc occupe sa colonne | Des lignes denses étirées sur 1080 px seraient illisibles ; la densité prime |
| D4 | **Key rendue `--accent-ink` mono** partout (hero, TrackCard) | Accent discipliné : action / key / score |
| D5 | In-lib : plus aucun `InLibBadge` ni `LibDot` — **uniquement** la pastille coin de `<Artwork>` | Décision transverse ; info légère et universelle |
| D6 | Logos plateformes **monochromes `currentColor`** (`--ink-2` → `--ink` au hover), jamais les couleurs de marque | Le mauve accent reste le seul signal coloré de l'UI |

## Hero

Grid `216px 1fr`, gap `--space-8`, aligné en haut ; empilé < 640 px (cover 160 px).

| Élément | Spec | Tokens |
|---|---|---|
| Cover | `<Artwork>` taille hero 216 px, indicateur in-lib coin bas-droit (`in_lib`) | `--r-md`, `--shadow-md` ; pastille : cf. spec transverse |
| Titre | h1, 700, line-height 1.12 | `--fs-xl` (→ `--fs-lg` < 640) |
| Artist-chips | pill : avatar rond 22 px + nom, **une chip par artiste** (`artists[]` — jamais supposer un seul) → `/artist/:id` | bg `--surface`, border `--line`, hover `--surface-2`, `--r-pill`, `--fs-sm` 500 |
| Genres | `StyleTag` cliquables → `/style/:genre` (`pillar` + `depth` du payload) | tokens `--tag-*`, hues piliers |
| Tags Rekordbox | chips `.rb-tag` secondaires (`tags[]`), non cliquables | bg `--surface-2`, `--ink-2`, `--fs-xs`, `--r-pill` |
| Stats musicales (D1) | 4 cellules label + valeur : BPM · KEY · DURÉE · ANNÉE (`release_date` → année) | label `--fs-label` mono uppercase `--ink-3`, tracking 0.07em ; valeur `--fs-md` mono 600 ; Key en `--accent-ink` (D4) |
| Actions | « Aperçu » `btn--accent` ▶/pause (masqué si `!has_preview`) · like/dislike (`avis`) · « Collection » dropdown | `.btn` 38 px ; like actif : `--pos-soft` + `--pos-ink` ; dislike actif : `--neg-soft` + `--neg-ink` |
| Liens externes | `<PlatformLink>` Beatport (si `beatport_id`) · Deezer (si `deezer_id`) + label en texte (micro-label LABEL + nom) | carrés 38 px alignés sur les actions ; label `--fs-label` / `--fs-sm` |

Dropdown collection : `--surface`, border `--line-2`, `--r-md`, `--shadow-md` ; items `--fs-sm`, hover `--surface-2` ; « + Nouvelle collection » séparé par un filet `--line`.

## « Où on l'entend »

`.rel-cols` : grid 2 colonnes, gap `--space-4`, 1 colonne < 720 px. Chaque bloc = carte `--surface` + border 1px `--line` + `--r-md` + `--shadow-sm`.

En-tête de bloc : titre `--fs-title` 600 + compteur mono `--fs-xs` `--ink-3` à droite (D2). Lignes sur **2 niveaux** — les titres de sets réels sont très longs (« Defected Radio Show Ibiza Special Hosted by Sam Divine… »), un seul niveau les tronquerait illisiblement : titre `--fs-sm` 500 ellipsé, puis ligne méta mono ; chevron `--ink-3` à droite. Border-top `--line`, min-height 52 px (≥ `--touch-min`), hover `--surface-2`, **ligne entière cliquable**.

- **« Apparaît dans »** (sets, `set_appearances[]`) : méta = **chip timecode** (▶ + `h:mm:ss` mono `--fs-xs`, fond `--accent-soft`, texte `--accent-ink`, `--r-xs`) = deep-link vers le set horodaté · date. Ligne → `/set/:id`.
- **« Détecté dans »** (playlists, `radar_appearances[]`) : méta = **logo de la source** (`playlist_source` → glyphe `<PlatformLink>` variante `glyph`, ~13 px, `--ink-2`, non cliquable, `title` + `aria-label` « Détecté sur Deezer ») · date — remplace le badge texte DEEZER/TIDAL/SPOTIFY. Ligne → `/playlists/:id`.

Dates : `jj/mm/aaaa` mono `--fs-xs` `--ink-3` (format existant conservé).

**Troncature** : 5 lignes affichées par bloc, puis pied de bloc « Afficher plus (n) » / « Afficher moins » — `--fs-sm` 500 `--accent-ink`, min-height 40 px, border-top `--line`, hover `--surface-2`. Pied absent si ≤ 5 lignes.

**Sobre** : pas de nom de DJ, pas de « 1re/dernière détection », pas de ligne de résumé. Bloc vide → masqué ; un seul présent → D3 ; les deux vides → section entière masquée.

## Découverte

Deux sous-blocs : en-tête `--fs-title` 600 + compteur mono, puis `.mini-grid` (2 colonnes desktop, gap `--space-2`/`--space-4`, 1 colonne < 720 px) de `<TrackCard>` ligne :

- **« Du même artiste »** (`same_artist_tracks[]`) : variante **sans nom d'artiste**, slot de fin vide. **Tronqué à 6 tracks** (3 lignes de grille desktop) + bouton `btn--sm` « Afficher plus (n) » / « Afficher moins » centré sous la grille.
- **« Tracks similaires »** (`GET /similar?limit=8`) : variante **avec artiste** + `<ScoreRing>` 30 px en slot de fin — `Math.round(similarity.score × 10)`, jamais le float, fini le « 87 % » texte. Non tronqué (déjà limité à 8 par l'API).

## États

| État | Spec |
|---|---|
| Loading page | utilitaire global `.state` (inchangé) |
| Track introuvable | `.state` : « Track introuvable » `--ink-2` + `.btn` « Retour au catalog » |
| Bloc vide | masqué — jamais d'état vide affiché sur cette page |
| Loading similaires | 4 rangées squelette : carré 36 px + 2 barres `--surface-2`, pulse opacity 1.2 s |
| Playing (hero ou ligne) | tint `--accent-wash`, icône pause ; le hover d'une ligne playing reste `--accent-wash` |
| Hover ligne / card | `--surface-2` (+ border `--line-2` sur TrackCard), transition 0.12 s background/color/border-color |
| Sans preview | aucun bouton play (ni hover, ni mobile) |

## Responsive

La page vit dans `.detail-view` : max-width `--detail-max-w`, `container-type: inline-size`. **Container queries uniquement** (`@container`), jamais `@media`. Pilote : 375 px.

| Seuil | Changements |
|---|---|
| < 720 px | `.rel-cols` et `.mini-grid` → 1 colonne |
| < 640 px | hero empilé (cover 160 px), titre → `--fs-lg`, padding horizontal → `--page-px-mobile`, **boutons play toujours visibles** (pas de hover mobile), chevrons des lignes masqués |

Cibles tactiles ≥ 44 px (`--touch-min`).

## Grille d'audit

Couleurs 100 % tokens · dark/light vérifiés · accent discipliné (action / key / score) · in-lib = `--pos` partout via `<Artwork>` · mono pour toute donnée chiffrée (BPM, key, durées, timecodes, dates, compteurs) · container queries · AdminCard gatée `is_admin` en bas · rating absent de toute la page.

## MàJ round 2 (retours William — 17/07/2026)

- **Découverte remonte au-dessus de « Où on l'entend »** : le rebond (même artiste, similaires) d'abord, le contexte radar ensuite. Ordre vertical mis à jour ci-dessus.
- **« Détecté dans » : logo de la source** (glyphe PlatformLink mono) au lieu du badge texte.
- **Listes tronquées** : sets et playlists 5 lignes + « Afficher plus (n) » en pied de bloc ; « Du même artiste » 6 tracks + bouton centré. Similaires inchangés (8 max côté API).
