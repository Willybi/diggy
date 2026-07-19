# BRIEF — Artist Detail `/artist/:id` · Refonte D4, page 4

> Maquette pilote : `Artist Detail (pilote).dc.html` — toggles thème dark/light + viewport desktop/375 px dans la toolbar ; états démo (avatar avec/sans artwork, montage riche / pauvre / vide, 0 genre, plateformes deezer/trackid/aucune, Suivi, sets 6 / 3 / vide masquée, `is_admin`) via le panneau Tweaks ; l'expand des tracks et des artistes proches est interactif dans la page ; nuancier (SetCard + footer % identifiées, ShelfCard round, consommation TrackCard, états page) en bas de maquette.
> Cette page **consomme** les composants transverses en prod : `<Artwork>` / `<TrackCard>` ligne / `<ScoreRing>` / `<PlatformLink>` (`BRIEF-composants-transverses.md`), l'extension durée + artistes (`BRIEF-trackcard-extension.md`, livrée), `<SetCard>` (`SPEC-set-card.md`), `<ShelfCard>` + `<ExpandableShelf>` (existants). **Aucun composant créé, aucune extension** — zéro re-spec ici.
> Tout en tokens `diggy-tokens.css`, zéro couleur hardcodée. DA Wildflower v1 inchangée.
> **Refonte, pas création** : le hero-bannière (aimé) est conservé ; on retire le code mort (sous-titre real_name · country, lien SoundCloud — `ArtistDetailOut` ne les renvoie plus), on migre les rangées bespoke vers les composants partagés, et la section Sets passe en grille de cartes.

## Ordre vertical

1. `dv-back` (← Artistes)
2. **Hero-bannière** — montage des covers du catalog + scrim + nom, avatar rond débordant ; dessous : genres `StyleTag`, actions (Écouter un aperçu · Suivre/Suivi · logos `<PlatformLink>` Deezer/TrackID), **stats repliées** (Catalog · In lib · Sets)
3. **Aliases** (si présents) — ligne texte simple
4. *[Slot réservé — **Bio artiste**, feature future (source à définir). Repère de layout seulement.]*
5. **Tracks** — `<TrackCard>` ligne (`showArtist` + `showDuration`), expand progressif 10 + N
6. *[Slot réservé — **Albums / Sorties**, futur (objet album, roadmap). Repère de layout seulement.]*
7. **Sets** — grille de `<SetCard>`, **masquée si vide**
8. **Artistes proches** — `<ShelfCard variant="round">` dans `<ExpandableShelf>`
9. **AdminCard** (lien Deezer) — composant existant inchangé, déjà gaté `is_admin`. Hors périmètre design.

Pas d'état invité : les invités sont confinés au Hub, cette page est toujours authentifiée.

## Décisions DA explicites

| # | Décision | Justification |
|---|---|---|
| A1 | **Banner conservé tel quel dans l'esprit** : montage 6×2 des covers du catalog plein-bleed dans une bande `--r-lg` (216 px), scrim composé des tokens `--hero-scrim-*` (alpha au point d'usage : 0.72 → 0 à 62 %), **nom en `--overlay-text`** (invariant, lisible sur montage clair comme sombre dans les deux thèmes) + `text-shadow` `--genre-tile-shadow` | Le hero est la partie réussie de la page — on ne le redessine pas, on le nettoie. Les invariants overlay/scrim garantissent le light mode sans nouveau token |
| A2 | **StatStrip repliée dans le hero** : data-row mono Catalog · In lib · Sets en bas du bloc sous-banner — pas de bande séparée | Même arbitrage que Track (D1), Playlist (P2) et Set (S3) Detail : la carte d'identité vit dans le hero, une bande de moins. Rating moy. retiré (décision transverse) |
| A3 | **Montage pauvre → tuiles cyclées ; catalog vide → bande placeholder rayé** (motif `<Artwork>`) sous le même scrim, hauteur inchangée | 1–11 covers : on répète les covers disponibles plutôt que des trous. 0 cover : pas de faux décor (règle S1), le scrim reste pour la lisibilité du nom |
| A4 | **Avatar rond 120 px débordant** (−60 px sous le banner), ring 3 px `--surface` + `--shadow-md` ; `has_artwork=false` → **initiale** `--fs-fallback` 600 `--ink-2` sur `--surface-3`. **< 640 px : repasse en flux** sous le banner (72 px) — comportement actuel conservé | Le débord est la signature du hero. Le ring `--surface` isole l'avatar du montage et du fond dans les deux thèmes |
| A5 | **Footer `<SetCard>` = badge sobre**, pas de `<ScoreRing mode="pct">` : ligne mono « 69 % » 600 `--ink-2` + « identifiées » `--ink-3`, séparée par un hairline `--line`, calée en bas de carte | Jusqu'à 8 arcs accent en grille = bruit (discipline accent, même logique que S10) ; l'anneau 40 px pèse trop dans une carte ~200 px. Usage du slot `#footer` prévu par la spec — **zéro changement au composant** ; le ring reste disponible si le besoin émerge |
| A6 | **Actions** : « Écouter un aperçu » = `.btn--accent` + triangle play (seul accent plein de la page) ; Suivre = `.btn`, état Suivi = `.btn--ghost-accent` ; liens externes = `<PlatformLink size="md">` Deezer + TrackID (38 px, mono `currentColor`, D6) | Hiérarchie : une action primaire, un toggle d'état, des logos secondaires. Plus de bouton texte, plus de SoundCloud (mort) |
| A7 | **Artistes des `<SetCard>` joints par « , »** (spec canonique, consommée telle quelle) — le séparateur « b2b » reste un traitement du hero de Set Detail | Contrainte zéro extension : la carte est en prod, on ne la fork pas pour un séparateur. Le rôle b2b se lit sur la page du set |
| A8 | **Tracks = `<TrackCard>` ligne** `showArtist` + `showDuration`, grille `36px 1fr 42px 30px 44px`, slot de fin vide, **pas de StyleTag par ligne** | Cohérent Playlist/Set Detail ; la colonne genre par ligne disparaît (le hero porte déjà les genres). Extension durée + artistes cliquables déjà livrée — consommation pure |
| A9 | **Artistes proches** : `<ShelfCard variant="round">` (avatar 72 px + nom, rien d'autre) en grille `minmax(96px, 1fr)`, `<ExpandableShelf>` aperçu 12 + expand paginé — **polish visuel seulement** | Structure partagée déjà en place ; avatar + nom UNIQUEMENT (figé — pas de score, pas de « pourquoi ») |

## Hero

Bande `position: relative`, `overflow: hidden`, border 1 px `--line`, `--r-lg`, bg `--surface`. Deux zones : **banner** (montage + scrim + nom) et **bloc sous-banner** (avatar débordant, genres, actions, stats).

| Élément | Spec | Tokens |
|---|---|---|
| Banner | 216 px de haut (150 px < 640), border-bottom 1 px `--line`. Montage : grid 6×2 plein-bleed des covers du catalog (`/storage/catalog-artworks/{id}.jpg`, `object-fit: cover`), sans gap | — |
| Montage pauvre (A3) | 1–11 covers → tuiles **cyclées** (répétition des covers disponibles) | — |
| Catalog vide (A3) | bande = placeholder rayé standard `repeating-linear-gradient(45deg, var(--surface-2) 0 6px, var(--surface-3) 6px 12px)`, scrim conservé | — |
| Scrim (A1) | `linear-gradient(to top, oklch(var(--hero-scrim-l) var(--hero-scrim-c) var(--hero-scrim-h) / 0.72), transparent 62%)` — invariant sombre, valide light et dark | `--hero-scrim-*` |
| Nom | h1 sur le banner, bas-gauche, décalé à droite de l'avatar (desktop), 700 `--fs-xl` (→ `--fs-lg` < 640), `--overlay-text`, text-shadow `--genre-tile-shadow`, `overflow-wrap: anywhere` | invariants |
| Avatar (A4) | 120 px rond, débordant −60 px, à gauche (`--space-6`) ; `/storage/artist-artworks/{id}.jpg` si `has_artwork`, sinon **initiale** du nom. < 640 : en flux, 72 px | ring `--surface`, `--shadow-md` |
| Genres | rangée wrap de `StyleTag` (`name` + `family=pillar` + `depth`) → `/style/{name}`. **0 genre → rangée absente** (pas d'espace réservé) | gap `--space-15` |
| Écouter un aperçu | `.btn--accent` + triangle play 15 px — lance un preview aléatoire du catalog (tracks `has_preview` seulement) | `--accent`, `--on-accent` |
| Suivre / Suivi | `.btn` (repos) ↔ `.btn--ghost-accent` label « Suivi » (état `following`). Toggle `POST/DELETE /api/artists/{id}/follow` | — |
| Liens externes (A6) | `<PlatformLink platform="deezer">` si `deezer_id`, `<PlatformLink platform="trackid">` si `trackid_id` — carré 38 px, logo 16 px `--ink-2` → hover `--surface-2` + `--ink`, `aria-label` « Voir sur Deezer / TrackID ». **Champ null → logo absent** ; les deux null → rangée d'actions sans logos | mono `currentColor` (D6) |
| Stats (A2) | data-row : **CATALOG** (`nb_catalog`) · **IN LIB** (`nb_lib`) · **SETS** (`nb_sets`) — labels `--fs-label` mono uppercase `--ink-3` tracking 0.07em, valeurs `--fs-md` mono 600. **Pas de Rating moy.** | — |
| RETIRÉ (code mort) | sous-titre `real_name · country`, lien SoundCloud — ne pas faire revivre | — |

## Aliases

Si `aliases[]` non vide : ligne discrète sous le hero — micro-label `ALIAS` (`--fs-label` mono uppercase `--ink-3`) + noms joints « · » (`--fs-sm` 500 `--ink-2`). Vide → ligne absente.

## Slots futurs (repères, non livrables)

- **Bio artiste** : s'insère **après Aliases**. Feature future — la colonne `bio` est vide, aucune source branchée (Wikipedia / MusicBrainz / Discogs / Last.fm à choisir).
- **Albums / Sorties** : s'insère **après Tracks**. Dépend de l'objet album (roadmap) ; album/EP uniquement, les singles restent dans Tracks.

Dans la maquette : marqueurs dashed `--line-2` / `--ink-3`, à ne **pas** implémenter (aucun rendu en prod tant que les features n'existent pas).

## Tracks

En-tête : h2 `--fs-md` 600 « Tracks » + compteur mono `--fs-xs` `--ink-3` (« 87 tracks » = `nb_catalog`).

Liste verticale 1 colonne, gap `--space-2`, de **`<TrackCard>` ligne** (spec canonique + extension durée/artistes livrée). Props par rangée : `showArtist=true`, `showDuration=true`, `artists[]` (fallback chaîne `artist`), `in_lib` (→ `<Artwork size="row" :inLib>`), `has_preview`. Slot de fin vide. Grille `36px 1fr 42px 30px 44px`.

**Liens** : titre / ligne → `/catalog/:id` ; artistes → `/artist/:id` (`stopPropagation`). **Aucune colonne genre** (figé).

**Expand progressif** : 10 rangées visibles + `.btn--sm` « Afficher les N autres tracks » (N = chargées − 10) ; le bouton disparaît après expand (la maquette garde un toggle pour la démo). Si `nb_catalog` > tracks chargées : note mono `--fs-xs` `--ink-3` centrée « … et N autres tracks au catalog » en fin de liste.

### États de rangée

| État | Spec |
|---|---|
| Normale | cover + pastille in-lib, titre 600, artistes cliquables `--ink-3` → hover `--ink` + underline, BPM mono `--ink-2`, KEY mono `--accent-ink`, durée mono `--ink-2` |
| BPM / KEY / durée absents | « — » `--ink-3`, grille conservée |
| In-lib ± | pastille coin `<Artwork>` : point plein `--pos` / cercle pointillé `--ink-3` |
| Playing | tint `--accent-wash`, icône pause ; hover reste `--accent-wash` |
| Hover | `--surface-2` + border `--line-2`, play visible, 0.12 s |
| Sans preview | aucun bouton play (ni hover, ni mobile) |
| `has_artwork=false` | placeholder rayé standard |

## Sets

`sets[]` (`ArtistSetOut`, ✦ `artists[]` + `duration_ms` livrés par le lot back arbitré 2026-07-20). **Section entière masquée si vide** (en-tête compris).

- En-tête : h2 `--fs-md` 600 « Sets » + compteur mono `--fs-xs` `--ink-3` (« 6 sets » = `nb_sets`).
- Grille de `<SetCard>` (spec `SPEC-set-card.md`, consommée telle quelle) : **4 colonnes** desktop → **3** < 720 px → **2** < 640 px, gap `--space-4`. Carte entière → `/set/:id`.
- Par carte : artwork `/storage/set-artworks/{set_id}.jpg` (`has_artwork=false` → placeholder rayé), titre clamp 2 lignes, artistes = noms joints « , » (A7 ; **0 artiste → ligne absente**), méta mono `date · durée · N tracks` — **nulls omis, séparateurs ajustés** (jamais de tiret).
- **Slot `#footer` (A5)** : badge % identifiées — « `NN %` » mono 600 `--ink-2` (espace fine insécable avant %) + « identifiées » `--fs-xs` `--ink-3`, `border-top` 1 px `--line`, `padding-top --space-2`, `margin-top auto` (calé en bas, aligné entre cartes). Valeur = `identified_tracks / total_tracks` arrondie entière.
- `role` (`dj`/`b2b`/`live`) **jamais affiché tel quel** (vocabulaire d'import incertain — même règle que S5).

## Artistes proches

`GET /api/artists/{id}/connections` — on n'utilise **que** `artist_id`, `name`, `has_artwork`. `score`, `components`, `shared_*` **ne sont pas affichés** (figé).

- En-tête : h2 `--fs-md` 600 « Artistes proches » + compteur mono `--fs-xs` `--ink-3` (« 24 artistes »).
- `<ExpandableShelf>` : **aperçu 12** + expand paginé (`.btn--sm` « Afficher les N autres artistes ») — comportement du composant existant, inchangé.
- `<ShelfCard variant="round">` : avatar rond 72 px (`/storage/artist-artworks/{id}.jpg` ; `has_artwork=false` → **initiale** `--fs-md` 600 `--ink-2` sur `--surface-3`, border `--ct-line`) + nom `--fs-xs` 500 centré, clamp 2 lignes. Carte → `/artist/:id`, padding `--space-2`, `--r-md`, hover bg `--surface-2`, transition 0.12 s. Grille `repeat(auto-fill, minmax(96px, 1fr))`, gap `--space-2`.
- Cible tactile : la carte entière (≥ 44 px).

## États page

| État | Spec |
|---|---|
| Loading | utilitaire global `.state` : « Chargement… » |
| Artiste introuvable | `.state` : « Artiste introuvable. » `--ink-2` + `.btn` « Retour aux artistes » |
| Catalog vide | banner sans montage (A3) ; section Tracks : compteur « 0 track », liste vide |
| 0 genre | rangée de tags absente |
| Sets vide | section entière masquée |
| Aliases vide | ligne absente |
| `deezer_id` / `trackid_id` null | logo correspondant absent |

## Responsive

La page vit dans `.detail-view` : max-width `--detail-max-w`, `container-type: inline-size`. **Container queries uniquement** (`@container`), jamais `@media`. Convention repo : breakpoints **720 / 640 px en max-width exclusif**. Pilote : 375 px.

| Seuil | Changements |
|---|---|
| < 720 px | Sets → 3 colonnes |
| < 640 px | banner 150 px, nom → `--fs-lg` calé à gauche (l'avatar ne décale plus), **avatar en flux** sous le banner (72 px — comportement actuel conservé), **padding horizontal seul** → `--page-px-mobile` (`padding-left/right`, jamais le shorthand), **play toujours visible**, tracks : **durée masquée** (défaut du composant — BPM et KEY restent), Sets → 2 colonnes |

Cibles tactiles ≥ 44 px (`--touch-min`).

## Grille d'audit

Couleurs 100 % tokens · dark/light vérifiés (scrim invariant A1, ring avatar `--surface`) · accent discipliné (btn aperçu / key / playing / hover artistes / ghost-accent Suivi) · mono pour toute donnée chiffrée (BPM, key, durées, dates, %, compteurs, stats) · espace fine insécable avant % · container queries uniquement · Rating moy. absent · code mort non ressuscité (real_name · country, SoundCloud) · `<PlatformLink>` mono `currentColor` (D6) · SetCard consommée telle quelle (« , », nulls omis, footer via slot) · artistes proches = avatar + nom seulement · aperçu proches 12, tracks 10 + N · AdminCard gatée `is_admin` en bas · zéro donnée inventée hors `ArtistDetailOut` / `connections`.
