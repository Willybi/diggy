# BRIEF — Set Detail `/set/:id` · Refonte D4, page 3

> Maquette pilote : `Set Detail (pilote).dc.html` — toggles thème dark/light + viewport desktop/375 px dans la toolbar ; états démo (hero sans artwork, 0 / 1 / B2B artistes, genres vides, date + durée null, plateforme source, similaires pleine / partielle / masquée, `is_admin`) via le panneau Tweaks ; nuancier (extension TrackCard set, ScoreRing mode %, SetCard, états page) en bas de maquette.
> Cette page **consomme** les composants transverses en prod (`BRIEF-composants-transverses.md`) et l'extension durée + artistes du `<TrackCard>` (`BRIEF-trackcard-extension.md`) — aucun n'est re-spécifié ici. Créations de ce round : **extension additive set** du `<TrackCard>` ligne (`BRIEF-trackcard-extension-set.md`) et **carte set réutilisable** (`SPEC-set-card.md`).
> Tout en tokens `diggy-tokens.css`, zéro couleur hardcodée. DA Wildflower v1 inchangée.
> **Refonte, pas création** : structure verticale proche de l'actuelle — hero repensé (immersif), tracklist enrichie, section Sets similaires nouvelle. Champs morts (event / venue / description) définitivement retirés.

## Ordre vertical

1. `dv-back` (← Sets)
2. **Hero immersif** — fond flouté depuis la cover, artwork agrandi, titre, artistes-DJ, genres déduits, stats + ring % identifiées, lien source
3. **Tracklist** — `<TrackCard>` ligne étendu set (position · timecode · états ID)
4. **Sets similaires** — grille de `<SetCard>`, cap 8, **masquée si vide**
5. **AdminCard** (gérer les artistes du set) — composant existant inchangé, déjà gaté `is_admin`. Hors périmètre design.

Pas d'état invité : les invités sont confinés au Hub, cette page est toujours authentifiée.

## Décisions DA explicites

| # | Décision | Justification |
|---|---|---|
| S1 | **Fond flouté retenu** : bande hero `--r-lg` pleine largeur, backdrop = artwork agrandi + `blur(48px) saturate(1.1)`, **opacité 0.22 en light / 0.50 en dark** au-dessus de `--surface`. Pas de scrim texte : le texte garde les inks standards | C'est l'« immersion » demandée au moindre coût : theme-adaptif sans nouveau token, lisibilité garantie par le plafond d'opacité (le blur homogénéise le fond). `has_artwork=false` → bande `--surface` nue, pas de faux décor |
| S2 | **Cover hero = `<Artwork size="hero">` 216 px carré** (crop `object-fit: cover`), sans indicateur in-lib | Même gabarit que Track/Playlist Detail (cohérence pages détail) ; les covers set sont hétérogènes (YouTube 16:9, SoundCloud 1:1) — le carré unifie, le fond flouté restitue l'image entière en ambiance. In-lib absent : objet set, pas track |
| S3 | **StatStrip supprimée** : Durée · Date · Tracks · Identifiées intègrent le hero en **data-row mono** (patron D1 / P2) | Même arbitrage que Track et Playlist Detail — carte d'identité à côté du titre, une bande de moins |
| S4 | **Ring % identifiées = variante % de `<ScoreRing>`** (`mode="pct"`, md 40 px), dans la cellule IDENTIFIÉES avec la valeur `18/26` en mono — la grosse cellule RingPct disparaît | Cible TRANSVERSE : aligner les % sur la géométrie `<ScoreRing>` — cette page est la 1ʳᵉ migration. Spec additive courte ci-dessous ; `RingPct` reste en prod ailleurs, sa migration globale est un chantier ultérieur |
| S5 | **Artistes-DJ = liens sous le titre**, séparateur « b2b » mono dès que N ≥ 2 | Vocabulaire métier (le `role` précis de l'import est incertain — jamais affiché tel quel) ; 0 artiste = cas fréquent TrackID → ligne absente, sans espace réservé |
| S6 | **Genres déduits = `StyleTag` cliquables seuls, sans %** (cap 5 API) | Le hero dit « ce que ça joue », pas les proportions — le `pct` sert au tri d'agrégation. Sobre ; les tags portent déjà la teinte pilier |
| S7 | **Lien source = `<PlatformLink size="md">` + micro-label `SOURCE` + nom plateforme** (P3 repris tel quel) | Patron déjà en prod sur Playlist Detail ; le logo mono `currentColor` (D6) remplace le bouton texte « Voir sur … » |
| S8 | **Tracklist = extension ADDITIVE du `<TrackCard>` ligne** (position + timecode + états ID), pas de rangée bespoke | La rangée set est à 90 % le composant existant (artwork, titre, artistes cliquables, BPM, KEY, durée déjà livrés) ; une rangée dédiée dupliquerait tout pour 3 ajouts. TRANSVERSE fixe le modèle additif comme voie normale d'évolution ; position/timecode resserviront (charts, cue lists). Contrainte dure zéro régression tenue — spec : `BRIEF-trackcard-extension-set.md` |
| S9 | **< 640 px : le timecode RESTE, BPM et durée tombent** (re-tranché — aujourd'hui c'est le timecode qui disparaît) | Le timecode est l'axe temporel du set ET l'accès à la source horodatée — la feature appréciée de la page. BPM/durée sont des données de préparation, consultables sur Track Detail ; KEY reste (seule donnée harmonique, déjà accentuée) |
| S10 | **Sets similaires sans score affiché** : grille de `<SetCard>` triée par `score` décroissant, le chiffre n'apparaît pas | Le tri porte l'information ; un indice de proximité par carte = bruit pour une section de rebond. `<ScoreRing>` reste disponible si le besoin émerge (un ajout, pas un retrait) |

## Hero

Bande `position: relative`, `overflow: hidden`, border 1 px `--line`, `--r-lg`, bg `--surface`, padding `--space-6`. Contenu : grid `216px 1fr`, gap `--space-8`, aligné en haut ; empilé < 640 px (cover 160 px).

| Élément | Spec | Tokens |
|---|---|---|
| Backdrop (S1) | si `has_artwork` : l'artwork en couche de fond, `object-fit: cover`, débord `inset: -48px`, `filter: blur(48px) saturate(1.1)`, `pointer-events: none`. Opacité **0.22 light / 0.50 dark** | opacité seule varie par thème ; aucun nouveau token |
| Cover (S2) | `<Artwork size="hero">` 216 px, sans in-lib. `has_artwork=false` → placeholder rayé standard | `--r-md`, `--shadow-md`, border `--ct-line` |
| Titre | h1, 700, line-height 1.12 | `--fs-xl` (→ `--fs-lg` < 640) |
| Artistes-DJ (S5) | liens → `/artist/:id`, 500 `--ink` → hover `--accent-ink` + underline. N ≥ 2 → séparateur « b2b » mono `--fs-xs` `--ink-3`. 0 artiste → ligne absente | `--fs-md` |
| Genres (S6) | rangée wrap de `StyleTag` (`name` + `pillar` + `depth` du payload) → `/style/{name}`, cap 5. `top_genres` vide (0 track identifiée) → rangée absente | gap `--space-15` |
| Stats (S3) | data-row : **DURÉE** (`duration_ms` → `h:mm:ss`, masquée si null) · **DATE** (`played_date` → `jj/mm/aaaa`, masquée si null) · **TRACKS** (`total_tracks`) · **IDENTIFIÉES** (S4) : ring % + valeur `identified/total` | label `--fs-label` mono uppercase `--ink-3` tracking 0.07em ; valeur `--fs-md` mono 600 |
| Lien source (S7) | `<PlatformLink platform=source size="md">` → `source_url`, `aria-label` « Voir sur SoundCloud ». À droite : micro-label `SOURCE` + nom plateforme. **`source_url` null → bloc entier absent** | carré 38 px `.btn`, logo 16 px `--ink-2` → hover `--surface-2` + `--ink` |

## Ring % identifiées — `<ScoreRing mode="pct">` (spec additive)

Prop ajoutée : `mode: 'score' | 'pct'`, défaut `'score'` → **rendu bit-à-bit identique** pour les consommateurs actuels.

- `mode="pct"` : `score` = proportion 0..1 (`identified_tracks / total_tracks`). Arc = proportion (départ 12 h, `stroke-linecap: round`), géométrie / strokes / couleurs **strictement inchangés** (piste `--line-2`, arc `--accent`).
- **Centre** : pourcentage entier + « % » avec espace fine insécable (« 69 % »), mono 600 `--fs-nano`, `--ink` — les 4 caractères de « 100 % » tiennent dans l'anneau md.
- **Taille** : `md` (40 px) recommandée ; `sm` déconseillé en mode % (label trop dense).
- A11y : `role="img"`, `aria-label` « 69 % de tracks identifiées ».
- 0 % → piste seule + « 0 % » ; 100 % → cercle plein.

## Tracklist

En-tête : h2 `--fs-md` 600 « Tracklist » + compteur mono `--fs-xs` `--ink-3` à droite : « 26 tracks · 18 identifiées » (les deux comptes, honnêtes).

Liste verticale 1 colonne, gap `--space-2`, de **`<TrackCard>` ligne étendus set** (spec `BRIEF-trackcard-extension-set.md`). Props par rangée : `position`, `timecode={ms, href?}`, `state` (`'id'` / `'unresolved'` / absent), `showArtist=true`, `showDuration=true`, `artists[]` (fallback chaîne), `in_lib`, `has_preview`.

**Liens** : ligne identifiée → `/catalog/:id` ; artistes → `/artist/:id` (`stopPropagation`) ; timecode → source horodatée quand constructible (**YouTube `?t=` et SoundCloud `#t=h:mm:ss` uniquement** — `trackid`, `1001tracklists` et `source_url` null → texte non cliquable). Le `href` est construit par la page, le composant ne connaît pas les plateformes.

### États de rangée

| État | Spec |
|---|---|
| Identifiée complète | rendu `<TrackCard>` standard : cover + pastille in-lib, titre 600, artistes cliquables, BPM mono `--ink-2`, KEY mono `--accent-ink`, durée mono, timecode lien |
| **ID** (`is_id`) | **en retrait** : bg `--bg` (vs `--surface`), titre « ID » **mono** 600 `--ink-3`, sous-ligne « non identifié » `--fs-xs` `--ink-3` ; placeholder rayé à opacité 0.55, **sans** pastille in-lib, **jamais** de play ; BPM / KEY / durée **vides** (rien à attendre — pas de tirets) ; position + timecode rendus normalement ; ligne non cliquable, hover neutre |
| **Non résolue** (`catalog_id` null, `is_id=false`) | `raw_title` / `raw_artist` en texte plein **sans lien** ; placeholder rayé, sans pastille, sans play ; BPM / KEY / durée « — » `--ink-3` (données inconnues) ; non cliquable, hover neutre |
| BPM / KEY / durée absents (fréquent) | « — » `--ink-3`, grille conservée |
| Timecode absent | « — » `--ink-3` |
| Timecode non cliquable | texte mono `--ink-3` (le lien est `--ink-2` → hover `--ink` + underline — la voix distingue les deux) |
| In-lib ± | pastille coin `<Artwork>` (point `--pos` / cercle pointillé) |
| Playing | tint `--accent-wash`, icône pause ; hover reste `--accent-wash` |
| Hover (identifiée) | `--surface-2` + border `--line-2`, play visible, 0.12 s |
| Sans preview | aucun bouton play (ni hover, ni mobile) |

## Sets similaires

`✦ GET /api/sets/{id}/similar` — cap 8, tri `score` desc (S10 : score non affiché). **Section entière masquée si vide** (en-tête compris).

- En-tête : h2 `--fs-md` 600 « Sets similaires » + compteur mono `--fs-xs` `--ink-3` (« 8 sets »).
- Grille de `<SetCard>` (spec `SPEC-set-card.md`) : **4 colonnes** desktop → **3** < 720 px → **2** < 640 px, gap `--space-4`. Carte entière → `/set/:id`.
- Champs affichés par carte : artwork, titre (clamp 2 lignes), artistes (noms, 1 ligne), méta mono `date · durée · N tracks` (nulls omis). `identified_tracks` et `score` non affichés.

## États page

| État | Spec |
|---|---|
| Loading | utilitaire global `.state` (inchangé) |
| Set introuvable | `.state` : « Set introuvable » `--ink-2` + `.btn` « Retour aux sets » |
| `top_genres` vide | rangée tags absente (hero se compacte, pas d'espace réservé) |
| Similaires vide | section absente |

## Responsive

La page vit dans `.detail-view` : max-width `--detail-max-w`, `container-type: inline-size`. **Container queries uniquement** (`@container`), jamais `@media`. Convention repo : breakpoints **720 / 640 px en max-width exclusif**. Pilote : 375 px.

| Seuil | Changements |
|---|---|
| < 720 px | Sets similaires → 3 colonnes |
| < 640 px | hero empilé (cover 160 px), titre → `--fs-lg`, **padding horizontal seul** → `--page-px-mobile` (`padding-left/right`, jamais le shorthand — le vertical reste), **play toujours visible**, tracklist : **BPM + durée masqués, timecode conservé** (S9), similaires → 2 colonnes |

Cibles tactiles ≥ 44 px (`--touch-min`).

## Grille d'audit

Couleurs 100 % tokens · dark/light vérifiés (backdrop S1 aux deux opacités) · accent discipliné (key / playing / arc du ring / hover artistes) · mono pour toute donnée chiffrée (BPM, key, durées, timecodes, dates, %, compteurs, positions) · espace fine insécable avant % · container queries uniquement · timecode cliquable préservé (YouTube/SoundCloud seulement) · score similaires non affiché · `<PlatformLink>` mono `currentColor` (D6) · AdminCard gatée `is_admin` en bas · genres cap 5, similaires cap 8 · zéro donnée inventée hors contrats `GET /api/sets/{id}` et `/similar`.
