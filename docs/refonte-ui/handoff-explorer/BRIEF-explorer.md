# BRIEF — Explorer `/explorer` · Refonte D6, page 1

> Maquette pilote : `Explorer (pilote).html` — toggles thème dark/light + viewport desktop/375 px dans la toolbar ; scénarios démo (« filtres actifs » par défaut, vierge, aucun résultat, chargement) et densité via le panneau Tweaks. La barre de filtres, le panneau, les chips, le tri (select + en-têtes), le play, le like/dislike et le drawer mobile sont interactifs — le filtrage s'applique réellement aux 20 rangées démo.
> Ex-Catalog, renommée **Explorer**, route `/explorer` (redirects `/catalog`, `/tracks`). Moteur de recherche de la base brute (117 683 tracks). **Le mode Radar quitte intégralement la page** (segment, colonnes Source/Détecté/Radar, chip « Radar ≥ 2 », sub-bar Période — rien de tout ça ici) ; il devient une page dédiée conçue au livrable suivant.
> Cette page **consomme** les composants transverses en prod : `<Artwork>` (+ indicateur in-lib), `<StyleTag>`, like/dislike. **Elle ne crée aucun composant transverse** — mais la mécanique de filtres est spécifiée comme un jeu de composants autonomes dans `BRIEF-filtres-partages.md` (réutilisée telle quelle par la future page Radar).
> Tout en tokens `diggy-tokens.css`, zéro couleur hardcodée. DA Wildflower v1 inchangée. Libellés 100 % français. Pas d'état invité (page authentifiée).

## Ordre vertical

1. **Head de page** — titre « Explorer » + compteur factuel, menu « + » (imports)
2. **Barre de filtres** — recherche texte · bouton « Filtres » (badge compteur) · sélecteur de tri · compteur de résultats live
3. **Rangée de chips actives** (si ≥ 1 filtre) — un chip par critère + « Tout effacer »
4. **Panneau de filtres** (déplié à la demande) — carte inline qui pousse la table
5. **Table** — en-tête sticky + rangées à hauteur constante, infinite scroll virtualisé
6. **Drawer de filtres** (mobile) — feuille bottom-sheet plein écran

## Décisions DA explicites

| # | Décision | Justification |
|---|---|---|
| E1 | **Panneau de filtres inline** (carte `--surface` + `--line` + `--shadow-sm` sous la barre, qui **pousse** la table) — pas un overlay/popover | Les filtres sont le cœur de la page, pas un à-côté : on les traite comme du contenu. Un overlay masquerait les résultats qu'on est en train d'affiner ; le compteur live + la table visible dessous donnent un feedback immédiat |
| E2 | **Chips d'état toujours visibles** sous la barre, panneau fermé ou non : un chip par critère (`LABEL valeur ×`), + « Tout effacer » | Filtres URL-syncés → au retour sur une URL partagée, l'état complet doit se lire **sans ouvrir le panneau**. Les chips sont la représentation canonique de l'état ; le panneau n'est que l'éditeur |
| E3 | **Compteur de résultats live** à droite de la barre (mono), répété en footer de panneau et en CTA du drawer (« Afficher N résultats ») | Chaque manipulation de filtre répond immédiatement — c'est ce qui rend l'affinage confortable sur 117 k rangées |
| E4 | **Key = grille Camelot 12 × 2** (rangée A = mineures, rangée B = majeures, colonnes 1→12), cellules mono, multi-select | Les voisins harmoniques (±1 numéro, même colonne A↔B) sont **adjacents dans la grille** — la sélection « 5A 6A 7A 6B » se fait d'un geste. Une roue circulaire serait plus littérale mais moins dense et inutilisable en drawer mobile |
| E5 | **Durée = presets single-select** `< 3` / `3–5` / `5–8` / `> 8 min` (re-clic = désélection), pas de range | Les classes de durée DJ sont discrètes (edit / club / extended / long mix) ; un 2ᵉ slider serait de la sur-précision et un preset se lit mieux en chip et en URL |
| E6 | **La recherche texte est le premier contrôle de la barre de filtres** (plus dans le head) — placeholder « Artiste, titre ou label… » | La recherche est un filtre parmi les autres (même pipeline, même URL) ; le head reste identité + compteur + imports |
| E7 | **Imports = menu « + » icon-only 38 px** dans le head (items : « Ajouter un track », « Importer XML Rekordbox ») | Décision produit figée : le head est désencombré au profit des filtres ; les imports sont des actions rares |
| E8 | **Tri = select explicite dans la barre** (7 options, défaut Récemment ajoutés) **+** clic d'en-tête sur les colonnes existantes (Track, BPM, Key, Durée — toggle asc/desc, en-tête actif en `--accent-ink` + flèche) | Le select couvre les dimensions sans colonne (Artiste, Date de sortie, Récemment ajoutés) ; le clic d'en-tête reste le geste naturel là où la colonne existe. Les deux pilotent le même état |
| E9 | **Sélection = accent plein** pour les contrôles à valeurs neutres (segments, cellules Camelot : fond `--accent`, texte `--on-accent`) ; **ring accent** (`box-shadow 0 0 0 1px --accent` + border) pour les chips de style, qui **gardent leur couleur de pilier** | L'accent mauve = seul signal de sélection ; on ne détruit pas l'information de hue des piliers en la remplaçant par du mauve |
| E10 | **Empty state actionnable** : « Aucun résultat avec ces filtres » + les chips actives **retirables inline** (hover `--neg`) + bouton « Réinitialiser tous les filtres » | L'utilisateur voit *quoi* assouplir sans remonter au panneau — l'empty state répare au lieu de constater |
| E11 | **Indicateur in-lib sur la cover** (`<Artwork>` : point plein `--pos` / cercle pointillé `--ink-3`, coin bas-droit, ring 2 px `--surface`) — la colonne In lib disparaît | Décision produit figée ; l'info devient légère et universelle |
| E12 | **Colonne Style : 1 `StyleTag` + « +N »** si plusieurs genres (jamais d'empilement vertical) | Hauteur de rangée **constante** exigée par la virtualisation — l'empilement actuel (capture 01, rangée « Fara ») créait des rangées à hauteur variable |
| E13 | **Skeleton de chargement** : 8 rangées fantômes (blocs `--surface-2`/`--surface-3`, pulse 1,4 s décalé) dans la grille exacte de la table | Le chargement préserve la géométrie (pas de saut de layout) ; distinct de l'empty state |

## Head de page

| Élément | Spec | Tokens |
|---|---|---|
| Titre | h1 « Explorer », 700 `--fs-lg` | — |
| Compteur | sous le titre, mono 500 `--fs-sm` `--ink-3` : « 117 683 tracks · 631 dans ma bibliothèque » (total base + `nLib`) — chiffres `toLocaleString('fr-FR')` | `--font-mono` |
| Menu « + » (E7) | `.btn` carré 38 px icon-only (plus 15 px), `aria-label` « Imports ». Ouvre un menu card : `--surface`, border `--line-2`, `--r-md`, `--shadow-lg`, items 38 px (icône 15 px + libellé `--fs-sm` 500, hover `--surface-2`) : « Ajouter un track » (ExternalImportModal) · « Importer XML Rekordbox » (ImportRekordboxModal) | — |
| RETIRÉ | boutons Ajouter/Importer inline, segment Catalog/Radar, chips Pas dans RB / Radar ≥ 2 / In lib (remplacées par le panneau), libellés EN (« tracks in lib », « Catalog ») | — |

## Barre de filtres (desktop)

Rangée flex wrap, gap `--space-2`. Composants détaillés dans `BRIEF-filtres-partages.md` — ici leur assemblage :

| Élément | Spec |
|---|---|
| Recherche (E6) | input 38 px, flex `1 1 220px` max 400 px, loupe 15 px `--ink-3` à gauche, `--fs-input` (16 px mini — iOS), border `--line-2` → focus `--accent`, bg `--surface` |
| Bouton Filtres | `.btn` + icône sliders 15 px + badge compteur (pill `--accent`/`--on-accent`, mono `--fs-xs`) si ≥ 1 filtre actif. Desktop : toggle le panneau ; < 640 : ouvre le drawer |
| Tri (E8) | select natif stylé (38 px, appearance none, icône tri à gauche + chevron à droite, `--fs-sm` 500 `--ink-2`) : Récemment ajoutés (défaut) · Titre A–Z · Artiste A–Z · BPM · Key (harmonique) · Durée · Date de sortie |
| Compteur live (E3) | à droite (flex spacer), mono 500 `--fs-sm` `--ink-2` : « N résultats » ; « … » pendant le chargement |
| Chips actives (E2) | rangée sous la barre, gap `--space-15` : pill 26 px `--surface`/`--line-2`, label uppercase `--fs-nano` mono `--ink-3` + valeur `--fs-xs` mono 600 `--ink` + × 18 px (hover `--surface-3`). Ranges = 1 chip (« BPM 120–133 »), keys = 1 chip (liste triée harmonique), styles/artistes = 1 chip **par valeur**. + « Tout effacer » (texte `--fs-xs` `--ink-3` → hover `--ink`) |
| Panneau (E1) | carte pleine largeur : grille 6 colonnes, gap `--space-4/--space-5` — BPM (2) · Année (2) · Durée (2) / Key Camelot (4) · Bibliothèque (2) / Styles (4) · Artiste (2) / Label (2) · Avis (2) · Extrait audio (2). Footer : compteur + `.btn--sm` Réinitialiser + `.btn--sm .btn--accent` Fermer, hairline `--line` au-dessus |

**Filtres retenus** (sémantique figée) : BPM range 60–200 · Key multi Camelot `1A`…`12B` · Style multi (piliers + sous-genres, groupés par pilier — données `GET /api/catalog/genres`) · Artiste type-ahead (`GET /api/artists/?q=`) · In lib tri-state (Tous / Dans ma bib / Pas dans RB) · Durée presets (E5) · Écoutable booléen · Avis (Tous / Aimés / Rejetés / Sans avis) · Année range 1985–2026 · Label texte libre. Écarté : « a une cover ».

**URL** : chaque critère ↔ un query param (noms fixés à l'implémentation) ; état par défaut = param absent ; retour sur URL filtrée → chips + compteur + panneau pré-remplis. La recherche texte et le tri font partie de l'état.

## Table

`table-layout` en CSS grid, **une grille partagée** en-tête/rangées :

| Zone | Spec | Tokens |
|---|---|---|
| Grille desktop | `44px minmax(0,1fr) 176px 56px 48px 60px 84px` (Play · Track · Style · BPM · Key · Durée · Avis), gap `--space-2`, padding horizontal `--page-px` | — |
| Rangée | hauteur **fixe `--row-h`** (56 px ; densité compact 46 / comfy 68), border-bottom 1 px `--line`, cursor pointer, clic → `/catalog/:id`, transition background 0.12 s | — |
| En-tête sticky | 36 px, `position: sticky; top: 0` (sous le head applicatif), z-index au-dessus des rangées, **bg `--bg`** (opaque, pas de transparence), border-bottom `--line-2`, labels uppercase mono `--fs-label` `--ink-3` tracking 0.07em. Colonnes triables (E8) : bouton, flèche ↑/↓, actif `--accent-ink` | `--fs-label` |
| Play | bouton rond 30 px, border `--line-2`, bg `--surface`, triangle 11 px `--ink-2` ; **hover-reveal desktop** (opacity 0 → 1 au hover de rangée), toujours visible ≤ 640. En lecture : bg `--accent`, icône pause `--on-accent`, opacity 1. **`has_preview=false` → aucun bouton** (ni hover ni mobile) | — |
| Track | `<Artwork size="row">` 38 px `--r-xs` (cover `/storage/catalog-artworks/{id}.jpg` ; `has_artwork=false` → placeholder rayé standard) + **indicateur in-lib** (E11). Titre 600 `--fs-table` ellipsis + **badge #rank** ; dessous artistes `--fs-table-sm` `--ink-3` ellipsis, **chaque artiste cliquable** → `/artist/:id` (`stopPropagation`, hover `--ink` + underline), séparateur « , » — jamais supposer un seul artiste (`artists[]`, repli chaîne `artist`) | — |
| Badge #rank | si `trend_rank` ≤ 50 : pill `--accent-soft` / `--accent-ink`, mono 600 `--fs-nano`, « #14 », collé au titre. **Seule info trend de la page** | — |
| Style (E12) | 1 `StyleTag` (name + pillar + depth, clic → `/style/:genre`, `stopPropagation`) + « +N » mono `--fs-nano` `--ink-3` si `genres.length > 1`. `genres` vide → repli `style` ; les deux vides → « — » | hue pilier |
| BPM | mono 500 `--fs-table` `--ink-2`, **arrondi entier**, aligné droite ; null → « — » `--ink-3` | `--font-mono` |
| Key | mono 600 `--fs-table` `--accent-ink` ; null → « — » `--ink-3` | — |
| Durée | mono 500 `--fs-table` `--ink-2` m:ss, aligné droite | — |
| Avis | 2 boutons ronds 28 px centrés : cœur (liked : fill `--pos`, bg `--pos-soft`) + pouce bas (disliked : `--neg`, bg `--neg-soft`) ; repos `--ink-3`, hover `--surface-3`. `stopPropagation`. `PATCH /api/catalog/{id}/avis` | — |

**Colonnes supprimées** : In lib (→ indicateur cover) · **Rating (purge projet — ne réapparaît nulle part)** · Radar · Source · Détecté. **Aucune nouvelle colonne.**

### États de rangée

| État | Spec |
|---|---|
| Repos | fond transparent |
| Hover | `--surface-2`, play révélé, 0.12 s |
| Playing | tint `--accent-wash` (hover inclus), bouton play → pause accent |
| Liked | wash `--pos-wash` (repos) → `--pos-wash-2` (hover), cœur rempli `--pos` |
| Disliked | **rangée entière opacity 0.45**, pouce `--neg` + `--neg-soft` (hover restaure l'affordance, pas l'opacité) |
| Sans preview | pas de bouton play, le reste inchangé |
| BPM / Key null | « — » `--ink-3` (rangée « Fara » de la démo) |

### Scroll & virtualisation

**Infinite scroll virtualisé (windowing)** — contraintes design honorées : hauteur de rangée **constante** `--row-h` (E12 garantit qu'aucun contenu ne l'étire), en-tête **sticky**, **pas de pagination** `← page/N →`. Sentinelle de fin de fenêtre : note mono `--fs-xs` `--ink-3` centrée (dans la maquette : rappel du windowing). Le scroll est celui de la page (pas de conteneur scrollable imbriqué).

### États page

| État | Spec |
|---|---|
| Chargement (E13) | 8 rangées skeleton dans la grille exacte, `xp-pulse` 1,4 s, delay +0,12 s/rangée ; compteur « … » |
| Aucun résultat (E10) | centré `--space-15x` : loupe barrée 34 px `--ink-3` · « Aucun résultat avec ces filtres » 600 `--fs-md` · « Retire un critère ci-dessous ou réinitialise la recherche. » `--fs-sm` `--ink-2` · chips retirables (hover border/texte `--neg`) · `.btn` « Réinitialiser tous les filtres » |
| Vierge | aucun filtre → compteur = total base, table pleine |

## Responsive

Page dans `.xp-page` : max-width `--page-max-w`, `container-type: inline-size`. **Container queries uniquement** (`@container`), seule exception `position: fixed` : le drawer. Padding horizontal `--page-px` → `--page-px-mobile` < 640. Pilote : 375 px.

**Échelle de column-drop** (redéfinie pour le nouveau jeu de colonnes — 4 paliers au lieu de ~8) :

| Seuil | Colonnes | Grille |
|---|---|---|
| ≥ 1000 px | Play · Track · Style · BPM · Key · Durée · Avis | `44px 1fr 176px 56px 48px 60px 84px` |
| < 1000 px | − Durée | `44px 1fr 176px 56px 48px 84px` |
| < 860 px | − Style (le panneau passe à 2 colonnes) | `44px 1fr 56px 48px 84px` |
| < 700 px | − BPM (panneau 1 colonne) | `44px 1fr 48px 84px` |
| < 640 px | Play · Track · Key · Avis — **play toujours visible** (tactile), avis conservé, gap `--space-1`, tri select masqué de la barre (le tri vit dans le drawer à terme — v1 : ordre par défaut), « Filtres » → **drawer** | `40px 1fr 46px 76px` |

Jamais de scroll horizontal ; cibles tactiles ≥ 44 px (`--touch-min`) — les boutons 28/30 px gagnent leur cible via le padding de rangée 56 px.

**Drawer mobile** (spec complète dans `BRIEF-filtres-partages.md`) : bottom-sheet `position: fixed`, overlay `--overlay-modal` (tap = fermer), feuille `--bg` `--r-xl` haut seulement, poignée 36×4 `--line-2`, header « Filtres » + « Réinitialiser », contrôles empilés 1 colonne (Camelot 6×4, cibles 32–44 px), footer sticky `--surface` + CTA `.btn--accent` 44 px pleine largeur « Afficher N résultats » (E3).

## Grille d'audit

Couleurs 100 % tokens · dark/light vérifiés · accent discipliné (badge compteur, sélections, key, en-tête trié, playing, badge #rank — pas d'autre mauve) · mono pour toute donnée chiffrée (BPM, key, durées, années, compteurs, chips) · `--fs-input` ≥ 16 px sur tous les contrôles de saisie · container queries uniquement (fixed = drawer seul) · icônes SVG inline `currentColor` monochrome, zéro CDN · libellés 100 % FR · **Rating absent partout** · **aucune trace Radar** (colonnes, chip, segment, période) sauf badge #rank · rangée hauteur constante `--row-h` · en-tête sticky opaque · pagination absente · `artists[]` jamais réduit à un seul nom · nulls (« — ») pour bpm/key manquants · filtres = état entièrement visible en chips (URL restaurable) · zéro donnée inventée hors surface `GET /api/catalog/` cible.
