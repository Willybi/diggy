# BRIEF — Playlist Detail `/playlists/:id` · Refonte D4, page 2

> Maquette pilote : `Playlist Detail (pilote).html` — toggles thème dark/light + viewport desktop/375 px dans la toolbar ; états démo (bannière crawl, hero sans artwork / titre / owner, description, bloc vivant, jamais crawlée, `is_admin`) via le panneau Tweaks ; nuancier (extension TrackCard, bannière crawl, états page, teintes genres) en bas de maquette.
> Cette page **consomme** les 4 composants transverses en prod (`BRIEF-composants-transverses.md`) — aucun n'est re-spécifié ici. Seule création transverse : l'**extension additive du `<TrackCard>` ligne**, spec séparée `BRIEF-trackcard-extension.md`.
> Tout en tokens `diggy-tokens.css`, zéro couleur hardcodée. DA Wildflower v1 inchangée.
> **Refonte, pas création** : structure actuelle conservée — hero repensé, « Dans cette playlist » enfin câblé (lot 0 back), rangées alignées sur le composant partagé.

## Ordre vertical

1. `dv-back` (← Playlists)
2. **Hero** — cover carrée `<Artwork size="hero">` + infos latérales (titre, owner, stats, lien source)
3. **Bannière crawl** — conditionnelle (`queued` / `running`), poll live, disparaît à la fin
4. **Description** — si présente, paragraphe sobre
5. **« Dans cette playlist »** — top artistes · genres dominants (le bloc vivant de la page)
6. **Tracks détectées** — liste de `<TrackCard>` ligne étendus
7. **AdminCard** (fetch artwork Deezer) — composant existant inchangé, déjà gaté `is_admin`, déplacé tout en bas. Hors périmètre design.

Pas d'état invité : les invités sont confinés au Hub, cette page est toujours authentifiée.
**Pas de bouton « Suivre / Ne plus suivre »** : le concept follow-playlist est masqué de l'UI — il n'apparaît nulle part sur la page.

## Décisions DA explicites

| # | Décision | Justification |
|---|---|---|
| P1 | **Cover hero = `<Artwork size="hero">` (216 px)**, même gabarit que Track Detail — pas de nouvelle taille | Cohérence entre pages détail ; c'est déjà l'« agrandissement » demandé vs l'actuel (~158 px). Pas d'indicateur in-lib (objet playlist, pas track) |
| P2 | **StatStrip supprimée** : **Tracks · Dernier crawl** intègrent le hero en data-row mono (même patron que D1 Track Detail). « Tracks radar » et « Ajoutée le » retirés | Carte d'identité de la playlist à côté du titre ; une bande de moins, scroll réduit. « Tracks » = total côté source — l'honnêteté du détecté est portée par le compteur de la liste |
| P3 | **Lien source = `<PlatformLink>` 38 px** (variante `button`) + micro-label `SOURCE` + nom de la plateforme en texte `--ink-2` — unique action du hero | Plus de bouton texte « Voir sur … ↗ » ; le logo mono `currentColor` (D6), le micro-label lève l'ambiguïté d'un carré seul |
| P4 | **Bannière crawl = bande discrète** pleine largeur sous le hero : `queued` neutre, `running` accent + dot pulsant. Pas de spinner, pas de barre de progression | Info d'arrière-plan, pas une alerte ; l'accent signale « ça travaille », la pulsation suffit |
| P5 | **Description = paragraphe sobre** `--ink-2`, max-width 640 px, sans carte ni en-tête « Description » | Sous-texte éditorial du hero, pas une section ; l'encadré actuel lui donnait un poids qu'elle n'a pas |
| P6 | **« Dans cette playlist » = une seule carte, 2 colonnes** (top artistes | genres dominants) | Un bloc vivant unique et dense plutôt que deux cartes maigres ; c'est le cœur enrichi de la page, il mérite une vraie surface |
| P7 | **Genres = `StyleTag` cliquable + barre % teintée par famille** via les tokens `--tag-dot-*` et la formule depth existante (L +0.04·d, chroma ×(1−0.19·d)) ; « autres » chroma 0 | Réutilise la mécanique piliers v2 telle quelle — aucun nouveau code couleur ; % en mono |
| P8 | **Durée = 5ᵉ colonne du TrackCard étendu, masquée < 640 px** | Donnée secondaire ; en étroit la place va au titre et aux artistes (spec : `BRIEF-trackcard-extension.md`) |
| P9 | **Titre absent → fallback `external_id` rendu mono** (`--font-mono`, même corps) | Cas réel fréquent ; le mono dit honnêtement « identifiant technique », pas de faux titre |

## Hero

Grid `216px 1fr`, gap `--space-8`, aligné en haut ; empilé < 640 px (cover 160 px).

| Élément | Spec | Tokens |
|---|---|---|
| Cover | `<Artwork size="hero">` 216 px, **sans** indicateur in-lib. `has_artwork=false` (fréquent) → placeholder rayé standard du composant | `--r-md`, `--shadow-md`, border `--ct-line` |
| Titre | h1, 700, line-height 1.12. **`title` null → `external_id` en `--font-mono`** (P9) | `--fs-xl` (→ `--fs-lg` < 640) |
| Owner | sous le titre, une ligne. **Masqué si absent ou redondant avec la source** (owner ≡ nom de la plateforme, ex. « Tidal ») | `--fs-sm` 400 `--ink-2` |
| Stats (P2) | 2 cellules label + valeur : **TRACKS** (`track_count`, masquée si null) · **DERNIER CRAWL** (`last_crawled_at` → `jj/mm/aaaa`, null → « jamais » en `--ink-3`) | label `--fs-label` mono uppercase `--ink-3` tracking 0.07em ; valeur `--fs-md` mono 600 |
| Lien source (P3) | `<PlatformLink platform=source size="md">` → URL construite `source` + `external_id`, `aria-label` « Voir sur Deezer ». À droite : micro-label `SOURCE` + nom plateforme | carré 38 px `.btn`, logo 16 px `--ink-2` → hover `--surface-2` + `--ink` ; label `--fs-label` / `--fs-sm` `--ink-2` |

## Bannière crawl

Poll `GET /api/watchlist/{id}/crawl-status` (mécanique `useTaskPoll` existante, inchangée). Bande sous le hero, margin-top `--space-6`, padding `--space-25 --space-4`, `--r-md`. Apparition/disparition simple (rendu conditionnel — pas d'animation d'entrée) ; `done`/null → absente.

| État | Spec |
|---|---|
| `queued` | bg `--surface`, border 1px `--line` ; dot 8 px `--ink-3` statique ; texte `--fs-sm` `--ink-2` « Crawl en file d'attente — la playlist sera analysée sous peu. » ; label `QUEUED` mono `--fs-nano` uppercase `--ink-3` à droite |
| `running` | bg `--accent-soft`, border 1px `--accent-soft-2` ; dot 8 px `--accent` **pulsant** (opacity 1→0.3, 1.2 s ease-in-out infinite) ; texte `--fs-sm` 500 `--accent-ink` « Crawl en cours — les tracks détectées se mettront à jour à la fin. » ; label `RUNNING` mono `--accent-ink` |

## « Dans cette playlist »

En-tête de section h2 `--fs-md` 600. Une carte `--surface` + border 1px `--line` + `--r-md` + `--shadow-sm`, padding `--space-5`, grid 2 colonnes gap `--space-8` (P6) ; 1 colonne < 720 px.

- **Top artistes** (`top_artists[]`) : micro-label `TOP ARTISTES` (`--fs-label` mono uppercase `--ink-3`), puis rangée wrap de **6 max** : avatar rond 48 px (`/storage/artist-artworks` si `has_artwork`, sinon initiales sur `--accent-soft` / `--accent-ink`) + nom `--fs-xs` 500 ellipsé + count mono `--fs-nano` `--ink-3` (« 6 tracks »). Item entier → `/artist/:id`, hover : nom souligné.
- **Genres dominants** (`top_genres[]`) : micro-label `GENRES DOMINANTS`, puis **5 max** rangées grid `120px 1fr 40px` gap `--space-3` : `StyleTag` (`pillar` + `depth` du payload) → `/style/:genre` · barre 6 px `--r-pill` piste `--surface-2`, remplissage `pct` % teinté famille (P7 — hues `--hue-house/techno/trance/dnb/hardcore/harddance`, fallback « autres » gris) · `pct` mono `--fs-xs` `--ink-2` aligné droite.
- **Un seul des deux présents** : la colonne restante occupe sa colonne, la grille reste 2 colonnes (même logique que D3 Track Detail). **Les deux vides → bloc entier masqué** (en-tête compris). Playlist jamais crawlée → masqué (pas de données).

## Tracks détectées

En-tête : h2 `--fs-md` 600 « Tracks détectées » + compteur mono `--fs-xs` `--ink-3` à droite (« 87 tracks » — le compte des **détectées**, pas `track_count`). Libellé honnête : jamais « Tracks » seul.

Liste verticale 1 colonne, gap `--space-2`, de **`<TrackCard>` ligne étendus** (spec `BRIEF-trackcard-extension.md`) :

- Props : `showArtist=true`, `showDuration=true`, `artists[]` structurés (✦ lot 0) avec fallback chaîne `artist`, `in_lib` (✦) → pastille coin `<Artwork>`, play preview si `has_preview`. Slot de fin vide.
- **Tri : détection la plus récente d'abord** (`detected_at` desc). `detected_at` n'est pas affiché.
- Ligne entière → `/catalog/:id` ; les liens artistes → `/artist/:id` sans déclencher la ligne.
- Plus de table bespoke, plus de colonne LibDot, plus d'en-têtes de colonnes.

## États

| État | Spec |
|---|---|
| Loading page | utilitaire global `.state` (inchangé) |
| Playlist introuvable | `.state` : « Playlist introuvable » `--ink-2` + `.btn` « Retour aux playlists » |
| Jamais crawlée | stat DERNIER CRAWL « jamais » (`--ink-3`) ; « Dans cette playlist » masqué ; liste remplacée par un état vide engageant : carte `--surface` centrée, mini placeholder rayé 56 px, « Aucune track détectée pour l'instant » `--fs-base` 500 `--ink-2` + « La playlist est surveillée — les tracks apparaîtront après le premier crawl. » `--fs-sm` `--ink-3`. La bannière crawl peut être active au-dessus (c'est le cas nominal juste après l'ajout) |
| Description absente | paragraphe non rendu, aucun espace réservé |
| Playing (ligne) | tint `--accent-wash`, icône pause ; hover reste `--accent-wash` |
| Hover ligne | `--surface-2` + border `--line-2`, play visible, transition 0.12 s |
| Sans preview | aucun bouton play (ni hover, ni mobile) |

## Responsive

La page vit dans `.detail-view` : max-width `--detail-max-w`, `container-type: inline-size`. **Container queries uniquement** (`@container`), jamais `@media`. Convention repo : breakpoints **720 / 640 px en max-width exclusif**. Pilote : 375 px.

| Seuil | Changements |
|---|---|
| < 720 px | « Dans cette playlist » → 1 colonne |
| < 640 px | hero empilé (cover 160 px), titre → `--fs-lg`, padding horizontal → `--page-px-mobile`, **play toujours visible** (pas de hover mobile), **colonne durée masquée** (P8) |

Cibles tactiles ≥ 44 px (`--touch-min`).

## Grille d'audit

Couleurs 100 % tokens · dark/light vérifiés · accent discipliné (key / playing / crawl running / genres via mécanique piliers) · mono pour toute donnée chiffrée (BPM, key, durées, dates, %, compteurs) · container queries · aucun bouton Suivre · libellé « détectées » sur la liste · `<PlatformLink>` mono currentColor (D6) · AdminCard gatée `is_admin` en bas · zéro donnée inventée hors contrat `GET /api/watchlist/{id}`.
