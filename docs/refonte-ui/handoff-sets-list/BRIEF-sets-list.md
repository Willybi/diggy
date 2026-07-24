# BRIEF — Sets (liste) `/sets` · Refonte D6, page-liste

> Maquette pilote : `Sets (pilote).html` — toggles thème dark/light + viewport desktop/375 px dans la toolbar ; scénarios démo (`liste`, `filtre liked`, `panneau ajouter`, `aucun résultat`, `filtre avis vide`, `chargement`) et densité via le panneau Tweaks. SegFilter d'avis, recherche texte, tri par en-tête, like/dislike et panneau Ajouter (2 onglets) sont interactifs — le filtrage s'applique réellement aux 15 rangées démo.
> Liste des DJ sets importés (~11 800). Aujourd'hui : **tableau dense** jumeau de la liste Playlists, « un des visuels les moins aimés » (William). Mouvement produit : **garder le format tableau** mais l'**assainir et l'enrichir** — exclure le bruit (sets 0 % identifiés), ajouter le **genre déduit**, passer en **infinite scroll**. Refonte de **densité / hiérarchie / enrichissement de rangée**, pas un changement de paradigme.
> **Format = TABLEAU (décision William, verrouillée).** Pas de grille de cartes `<SetCard>` ici (TRANSVERSE corrigé — `<SetCard>` reste le composant des « Sets similaires » de Set detail).
> Cette page **consomme** les composants transverses en prod : `<Artwork>` (sans indicateur in-lib — un set n'est pas « dans la bibliothèque »), `<StyleTag>`, `<RingPct>`, `<LikeDislike>`, `usePaginatedList`. **Elle ne crée aucun composant transverse.**
> Tout en tokens `diggy-tokens.css`, zéro couleur hardcodée. DA Wildflower v1 inchangée. Libellés 100 % français. Pas d'état invité (page authentifiée). Responsive en container queries (`@container`, seuils 720/640 + paliers intermédiaires), `position: fixed` seule exception (overlay du panneau Ajouter en bottom-sheet mobile).

## Ordre vertical

1. **Head de page** — titre « Sets » + compteur factuel · recherche texte · SegFilter d'avis (Tous / Liked / Disliked / À explorer) · bouton **Ajouter**
2. **Panneau Ajouter** (modal, à la demande) — 2 onglets : « Rechercher » (recherche TrackID → résultats + import par résultat) · « URL » (coller une URL TrackID)
3. **Tableau** — en-tête sticky triable + rangées enrichies, infinite scroll (sentinelle)
4. **Empty states** — chargement (skeleton) · aucun résultat (recherche) · filtre avis vide

## Décisions DA explicites

| # | Décision | Justification |
|---|---|---|
| S1 | **Genre = colonne dédiée en desktop** (`Genre` entre Set et Date, 1–2 `<StyleTag>`), qui **se replie sous le titre** (chips dans la cellule Set) sous 860 px au lieu de disparaître | Le genre est l'enrichissement clé de la refonte : il ne doit jamais être sacrifié au responsive. En colonne il est alignable/scannable ; replié il reste attaché à son set. Genre vide → **on omet**, jamais de tiret |
| S2 | **Ordre de rangée** : Set (cover + titre + artistes) · Genre · Date · Tracks (`RingPct` %) · Durée · Avis. **Aucune colonne Source, Play, BPM/Key, rating, nb de tracks brut** | Contenu figé (fiche §2–4). La colonne Source est retirée (100 % `trackid` en base → logo identique partout). Le % de `RingPct` suffit, le nombre brut est redondant |
| S3 | **`RingPct` = anneau accent + « N % » au centre** (mono, espace fine insécable), 40 px. Sous 640 px l'anneau **perd son libellé** (anneau seul) | Migration cible « RingPct → géométrie ScoreRing » (TRANSVERSE). L'arc porte la proportion en un coup d'œil ; le libellé central est le détail, sacrifiable en premier sur écran étroit. `identified_tracks` toujours ≥ 1 → l'anneau ne tombe jamais à 0 |
| S4 | **Cover `<Artwork>` sans indicateur in-lib** (44 px, `--r-sm`), placeholder rayé standard si `has_artwork=false` | Un set n'est pas « dans la bibliothèque » (décision fiche) — l'indicateur coin de `<Artwork>` n'est pas monté ici |
| S5 | **SegFilter d'avis = segmented control dans le head** (4 segments, sélection `--accent-soft` / `--accent-ink`), **c'est un filtre, pas un tri** | L'opinion se résout côté app (store `opinions` → `ids`), pas par colonne triable. La sélection reste **douce** (accent-soft, pas accent plein) : c'est un filtre de navigation persistant, pas une action ponctuelle |
| S6 | **Tri par clic d'en-tête**, server-side, sur **Set (titre) · Date · Tracks (%) · Durée** uniquement. Défaut = **Date décroissante**. Genre et Avis **non triables** | Le tri « Avis » n'existe plus (opinion = filtre). En-tête actif = `--accent-ink` + flèche ↑/↓ ; les autres restent `--ink-3` |
| S7 | **Bouton Ajouter = `.btn--accent` dans le head**, ouvre un **modal 2 onglets** (recentré desktop, **bottom-sheet** `position: fixed` mobile) | Le flux Ajouter est conservé (fiche §8) ; un modal (vs panneau inline) convient à une **action ponctuelle** de saisie sans repousser le tableau. Onglets soulignés (underline accent) plutôt que segments, pour distinguer du SegFilter du head |
| S8 | **Rangée à `min-height: var(--row-h)`** (pas hauteur fixe), padding vertical `--space-2` | L'infinite scroll ici n'est **pas virtualisé** (sentinelle server-side, pas de windowing) → pas de contrainte de hauteur constante. La rangée peut grandir quand le genre se replie sous le titre en mobile |
| S9 | **Coloration de rangée par avis conservée** : liked = wash positif (`--pos-wash` repos / `--pos-wash-2` hover, cœur rempli `--pos`) ; disliked = rangée **estompée** (opacity 0.45, pouce `--neg`) | Continuité avec la table actuelle et avec Explorer ; l'avis se lit sans regarder la colonne Avis |
| S10 | **Empty states distincts** : chargement (8 rangées skeleton dans la grille exacte, `st-pulse`) ≠ aucun résultat de recherche (loupe + « Effacer la recherche ») ≠ filtre avis vide (« Aucun set liké/disliké/à explorer ») | Chaque vide a une cause et une réparation différentes ; le message et l'action s'y adaptent |
| S11 | **Compteur factuel post-exclusion** (mono, ex. « 9 412 sets ») | Les sets à 0 % identifié sont exclus **par défaut, sans toggle** (fiche §5.1) → le compteur reflète les sets réellement listables, pas le total base (~11 800) |

## Head de page

| Élément | Spec | Tokens |
|---|---|---|
| Titre | h1 « Sets », 700 `--fs-lg` | `--font-ui` |
| Compteur | sous le titre, mono 500 `--fs-sm` `--ink-3` : « 9 412 sets » (`total` post-exclusion 0 %, `toLocaleString('fr-FR')`) | `--font-mono` |
| Recherche | input 38 px, `flex 1 1 200px` max 320 px, loupe 15 px `--ink-3` à gauche, `--fs-input` (≥ 16 px — iOS), border `--line-2` → focus `--accent`, bg `--surface`. Param `q` server-side | — |
| SegFilter avis (S5) | conteneur pill `--surface-2` + `--line`, 4 boutons 32 px : Tous · Liked · Disliked · À explorer. Actif `--accent-soft` / `--accent-ink` ; repos transparent / `--ink-2` (hover `--ink`). Résolution app via `opinions` → `ids` | — |
| Bouton Ajouter (S7) | `.btn--accent` + icône « + » 15 px. Ouvre le modal Ajouter | `--accent` |
| Repli mobile (< 640) | head en colonne : titre + compteur, puis recherche pleine largeur, puis rangée SegFilter (wrap), puis bouton Ajouter | — |

## Panneau Ajouter (modal 2 onglets)

Overlay `--overlay-modal` (tap = fermer). Carte `--surface`, border `--line-2`, `--shadow-lg` ; desktop **recentrée** (`--r-lg`, `min(460px, 100vw − 32px)`), mobile **bottom-sheet** `position: fixed` bas (`--r-xl` haut seulement, 375 px).

| Zone | Spec |
|---|---|
| Header | « Ajouter un set » 700 `--fs-md` + bouton fermer 30 px (X 16 px, hover `--surface-2`) |
| Onglets | « Rechercher » / « URL », `--fs-sm` 600, underline 2 px `--accent` sur l'actif (`--ink` actif / `--ink-3` repos), hairline `--line` dessous |
| Onglet Rechercher | input recherche 44 px (loupe, placeholder « Titre, artiste ou show TrackID… ») + libellé « N résultats TrackID » (`--fs-label` mono uppercase) + liste de résultats : cover 40 px `--r-xs` + titre `--fs-sm` 600 ellipsis + méta mono `--fs-xs` `--ink-3` (« TrackID · durée · N % identifié ») + bouton `.btn--sm` **Importer** par résultat → à l'import, remplacé par « ✓ Importé » (`--pos-ink`) |
| Onglet URL | label « URL TrackID » + input 44 px mono (placeholder `https://trackid.net/show/…`) + aide `--fs-xs` `--ink-3` + `.btn--accent` « Importer depuis l'URL ». **Erreur** : bordure `--neg`, message `--neg-ink` + icône (« URL non reconnue — colle un lien de show TrackID. ») |

## Tableau

CSS grid partagée en-tête/rangées.

| Zone | Spec | Tokens |
|---|---|---|
| Grille desktop (≥ 1000 px) | `minmax(0,1fr) 190px 104px 72px 92px 80px` (Set · Genre · Date · Tracks · Durée · Avis), gap `--space-3`, padding horizontal `--page-px` | — |
| Rangée | **`min-height: var(--row-h)`** (56 px ; compact 46 / comfy 68), padding-block `--space-2`, border-bottom 1 px `--line`, cursor pointer, clic → `/set/:id`, transition background 0.12 s | — |
| En-tête sticky | 36 px, `position: sticky; top: 53px` (sous la toolbar app), bg **`--bg`** opaque, border-bottom `--line-2`, labels uppercase mono `--fs-label` `--ink-3` tracking 0.07em. Triables (S6) : bouton + flèche ↑/↓, actif `--accent-ink` | `--fs-label` |
| **Set** | `<Artwork>` 44 px `--r-sm` (cover `/storage/set-artworks/{id}.jpg` ; sinon placeholder rayé) **sans** indicateur in-lib (S4). Titre 600 `--fs-table` ellipsis (titres souvent longs) ; dessous artistes `--fs-table-sm` `--ink-3` ellipsis, **chaque artiste cliquable** → `/artist/:id` (`stopPropagation`, hover `--ink` + underline), séparateur « , ». `artists` **peut être vide** → ligne artistes omise (jamais supposer un seul). Sous 860 px : chips genre repliés ici (S1) | — |
| **Genre** (S1) | 1–2 `<StyleTag>` (name + pillar + depth → hue pilier, chroma décroissant avec la profondeur), clic → `/style/:name` (`stopPropagation`). **Vide → cellule vide** (jamais de tiret). Overflow masqué | hue pilier |
| **Date** | `played_date` mono 500 `--fs-table` `--ink-2`, `DD/MM/YYYY`. Nullable → « — » `--ink-3` | `--font-mono` |
| **Tracks** (S3) | `<RingPct>` 40 px : arc `--accent` = `identified_tracks / total_tracks`, piste `--surface-3`, « N % » mono `--fs-nano` `--ink-2` au centre (espace fine insécable). Titre natif = « N / M tracks identifiés ». Justify center | `--accent` |
| **Durée** | `duration_ms` mono 500 `--fs-table` `--ink-2`, `m:ss` / `h:mm:ss`, aligné droite. Nullable → « — » | `--font-mono` |
| **Avis** | `<LikeDislike>` — 2 boutons ronds 28 px centrés : cœur (liked : fill `--pos`, bg `--pos-soft`) + pouce bas (disliked : `--neg`, bg `--neg-soft`) ; repos `--ink-3`, hover `--surface-3`. `stopPropagation` | — |

### États de rangée (S9)

| État | Spec |
|---|---|
| Repos | fond transparent |
| Hover | `--surface-2`, 0.12 s |
| Liked | wash `--pos-wash` (repos) → `--pos-wash-2` (hover), cœur rempli `--pos` + bg `--pos-soft` |
| Disliked | **rangée entière opacity 0.45**, pouce `--neg` + `--neg-soft` (hover restaure le fond, pas l'opacité) |

### Scroll

**Infinite scroll** (`usePaginatedList`, sentinelle de fin) — chargement par pages server-side au défilement. **Plus de pagination `← page/N →`**, plus de tri/filtre client-side. Non virtualisé (d'où `min-height` en S8, vs windowing d'Explorer). Sentinelle : note mono `--fs-xs` `--ink-3` centrée en fin de fenêtre.

### États page

| État | Spec |
|---|---|
| Chargement (S10) | 8 rangées skeleton dans la grille exacte (cover + 2 lignes + chip + date + anneau + durée + avis en blocs `--surface-2/3`), `st-pulse` 1,4 s, delay +0,12 s/rangée |
| Aucun résultat (recherche) | centré `--space-15x` : loupe 26 px dans pastille `--surface-2` `--ink-3` · « Aucun set trouvé » 600 `--fs-md` · « Aucun set ne correspond à *q*. Vérifie l'orthographe ou élargis ta recherche. » `--fs-sm` `--ink-2` · `.btn` « Effacer la recherche » |
| Filtre avis vide (S10) | même gabarit, icône disque/note · « Aucun set liké » (resp. disliké / à explorer) · sous-texte adapté (« Tu n'as encore liké aucun set. » ; À explorer → « Tous tes sets ont déjà un avis. »). Pas de bouton |

## Responsive — échelle de column-drop

Page `container-type: inline-size`. **Container queries uniquement** ; padding `--page-px` → `--page-px-mobile` < 640. Pilote : 375 px.

| Seuil | Colonnes | Grille |
|---|---|---|
| ≥ 1000 px | Set · Genre · Date · Tracks · Durée · Avis | `minmax(0,1fr) 190px 104px 72px 92px 80px` |
| < 1000 px | − Durée | `minmax(0,1fr) 190px 104px 72px 80px` |
| < 860 px | − Genre (colonne) → **chips repliés sous le titre** (S1) | `minmax(0,1fr) 104px 72px 80px` |
| < 700 px | − Date | `minmax(0,1fr) 72px 80px` |
| < 640 px | Set (+ genre replié) · Tracks · Avis — **avis toujours visible** (tactile), anneau **sans libellé %** (S3), gap `--space-2`, head empilé | `minmax(0,1fr) 46px 84px` |

Minimum garanti < 640 : **Set + Tracks(%) + Avis**. Jamais de scroll horizontal ; cibles tactiles ≥ 44 px (les boutons 28 px gagnent leur cible via le padding de rangée).

## Données (`GET /api/sets/` — cible, exhaustif)

`{ total, items[] }`, pagination `limit`/`offset` + param `sort` (titre/date/tracks/durée) + `q` + `ids` (résolution filtre avis). Item : `id` · `title` · `artists[]` (0..n) · `top_genres[]` `{name, pillar, depth, pct}` (**possiblement vide** → 1–2 StyleTags) · `played_date` (nullable) · `duration_ms` (nullable) · `has_artwork` · `total_tracks` · `identified_tracks` (**toujours ≥ 1**). **Non affichés** : `source` (toujours `trackid`), `source_url`. **N'existent pas au niveau set** : bpm, key, rating, extrait/play, indicateur in-lib.

## Grille d'audit

Couleurs 100 % tokens · dark/light vérifiés · accent discipliné (SegFilter actif, en-tête trié, arc `RingPct`, onglet actif, bouton Ajouter — pas d'autre mauve ; les hues de pilier des StyleTags sont la seule autre couleur sémantique) · mono pour toute donnée chiffrée (compteur, dates, durées, %) · `--fs-input` ≥ 16 px sur tous les contrôles de saisie · container queries uniquement (fixed = overlay Ajouter seul) · icônes SVG inline `currentColor` monochrome, zéro CDN · libellés 100 % FR · **aucune colonne Source / Play / BPM / Key / rating** · genre vide → omis (pas de tiret) · `artists[]` jamais réduit à un seul nom, vide → ligne omise · `identified_tracks` ≥ 1 (anneau jamais à 0) · pagination absente (infinite scroll) · tri « Avis » absent (opinion = filtre) · pas d'indicateur in-lib sur la cover · pas d'état invité.
