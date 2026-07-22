# BRIEF — Radar `/radar` · Refonte D6, nouvelle page

> Maquette pilote : `Radar (pilote).html` — toggles thème dark/light + viewport desktop/375 px dans la toolbar ; scénarios démo via le panneau Tweaks (`tri tendance` par défaut, `tri pour toi`, `filtres actifs`, `cold-start`, `aucun résultat`, `chargement`) + densité. La barre de filtres, le panneau, les chips, le tri (select + en-têtes de score/BPM), le play, le like/dislike et le drawer mobile sont interactifs — le tri et le filtrage s'appliquent réellement aux 20 sons démo.
>
> **Rôle de la page** : surface de recommandation **bi-score** de Diggy. Une **seule liste** de sons, où chaque ligne porte **deux scores de recommandation côte à côte** — **Tendance** (ce qui monte, classement global nocturne) et **Pour toi** (reco perso). On trie par l'un ou l'autre ; beaucoup de lignes n'ont qu'un seul score, l'autre affiche « — ».
>
> **Radar réutilise le squelette d'Explorer** (`BRIEF-explorer.md`) : même table dense virtualisée, même barre de filtres, mêmes composants transverses. La nouveauté design = **les deux colonnes de score**. Cette page **ne crée AUCUN composant transverse** : elle consomme `<ScoreRing>`, `<Artwork>`, la famille de filtres (`FilterBar`/`FilterPanel`/`FilterDrawer` + contrôles, `BRIEF-filtres-partages.md`), `<StyleTag>`, like/dislike — tels qu'ils sont.
>
> Tout en tokens `diggy-tokens.css`, zéro couleur hardcodée. DA Wildflower v1 inchangée. Icônes SVG inline `currentColor` (l'accent mauve = seul signal coloré, y compris l'arc des rings). Libellés 100 % français. **Pas d'état invité** (page authentifiée, JWT). **Périmètre : contenu de la page uniquement** — le shell (sidebar/BottomNav, entrée de nav « Radar ») est hors périmètre.

## Ordre vertical

1. **Head de page** — titre « Radar » + compteur bi-score factuel
2. **Barre de filtres** — recherche texte · bouton « Filtres » (badge compteur) · **sélecteur de tri** (Tendance / Pour toi / BPM / Récent) · compteur de résultats live
3. **Rangée de chips actives** (si ≥ 1 filtre) — un chip par critère + « Tout effacer »
4. **Panneau de filtres** (déplié à la demande) — carte inline, identique à Explorer
5. **Invite cold-start** (si `reco` vide) — bandeau discret « Débloque Pour toi »
6. **Table bi-score** — en-tête sticky + rangées à hauteur constante, infinite scroll virtualisé
7. **Drawer de filtres** (mobile) — feuille bottom-sheet plein écran

## Décisions DA explicites

| # | Décision | Justification |
|---|---|---|
| R1 | **Deux colonnes de score côte à côte** : `Tendance` puis `Pour toi`, chacune un `<ScoreRing size="sm">` (30 px) centré, colonne 64 px (desktop). Ordre : Tendance à gauche (défaut de tri, classement global), Pour toi à droite (perso) | Les 2 scores sont la raison d'être de la page ; côte à côte on compare d'un regard « ce qui monte » vs « ce qui me correspond ». `sm` (30 px) tient dans la rangée dense 56 px sans l'étirer (contrainte virtualisation) ; `md` réservé aux cards |
| R2 | **Pas de colonne Durée** (contrairement à Explorer) — elle saute pour laisser la place aux 2 scores. Durée reste **disponible en filtre** (preset dans le panneau) | Radar a 2 colonnes de plus qu'Explorer ; la durée d'un son n'aide pas à juger une reco. `duration_ms` existe côté data mais n'est jamais affiché |
| R3 | **Colonne de score active surlignée** : la colonne triée (Tendance ou Pour toi) reçoit une **bande verticale continue** `--accent-wash` (en-tête + toutes les cellules) + en-tête `--accent-ink` 600 + flèche ↑/↓. L'autre colonne reste neutre | Sur deux anneaux identiques côte à côte, il faut dire lequel gouverne l'ordre. La bande de colonne (pas seulement l'en-tête) rend le tri actif lisible sur toute la hauteur scrollée. Tri BPM/Récent → aucune colonne de score surlignée |
| R4 | **Score absent = « — » muet** : tiret cadratin mono `--fs-table` `--ink-3` centré dans la cellule, **pas d'anneau, pas de piste vide**. `aria-label` « Pas de score Tendance / Pour toi » | Un anneau à 0 % se lirait comme un « vrai » score bas ; le tiret dit clairement « non concerné ». Fréquent : l'union bornée fait que la plupart des lignes n'ont qu'un score. Une ligne mono-score reste lisible, pas « cassée » |
| R5 | **Accent velocity (optionnel, implémenté)** : un son qui monte vite (`velocity` élevée) porte un petit **▲ `--accent-ink` 9 px** en coin haut-droit de l'anneau **Tendance** (jamais Pour toi), `title="Monte vite"` | Signal léger, non intrusif, qui différencie « déjà haut » de « accélère » sans ajouter de colonne ni de couleur. Monochrome accent, cohérent DA. Non bloquant : peut être retiré sans impact |
| R6 | **Tri = select explicite** (Tendance défaut · Pour toi · BPM · Récent) **+** clic d'en-tête sur Tendance / Pour toi / BPM (toggle asc/desc). Les deux pilotent le même état, synchronisé URL | Tendance est le défaut TOUJOURS (fonctionne même sans likes) ; le select couvre Récent (sans colonne) ; le clic d'en-tête reste le geste naturel là où la colonne existe |
| R7 | **Cold-start = un état, pas une page** : `reco` vide → colonne Pour toi entièrement « — » + **bandeau invite** discret (`--accent-wash`, cœur `--accent-soft`, « Débloque Pour toi », fermable) ; la page s'ouvre sur le tri Tendance (le défaut de toute façon) | L'utilisateur sans likes voit quand même la valeur (Tendance) et comprend comment activer Pour toi (liker). Pas de mur, pas de page vide dédiée |
| R8 | **Badge #rank conservé** (comme Explorer) : si `trend_rank` ≤ 50, pill `--accent-soft`/`--accent-ink` mono `--fs-nano` « #14 » collé au titre | Cohérence avec Explorer ; c'est le rang de tendance, information de la surface reco |
| R9 | **Reste hérité d'Explorer sans changement** : indicateur in-lib sur cover (`<Artwork>`), 1 `StyleTag` + « +N », hauteur de rangée constante, en-tête sticky opaque, skeleton 8 rangées, empty state actionnable, like/dislike (wash liked / opacity disliked) sans pondération Radar, play inline, ligne playing surlignée | Radar EST Explorer orienté reco : on ne re-conçoit ni la table ni les filtres. Seuls les scores sont neufs |

## Head de page

| Élément | Spec | Tokens |
|---|---|---|
| Titre | h1 « Radar », 700 `--fs-lg` | — |
| Compteur | sous le titre, mono 500 `--fs-sm` `--ink-3` : « 1 240 tendances · 100 pour toi » (bornes de l'union) ; cold-start → « 1 240 tendances · Pour toi en attente de tes likes ». Chiffres `toLocaleString('fr-FR')` | `--font-mono` |
| RETIRÉ | menu « + » imports (spécifique Explorer, pas de sens sur une surface reco) | — |

## Barre de filtres

**Réutilisée telle quelle** — assemblage identique à Explorer, spec des composants dans `BRIEF-filtres-partages.md`. Seule différence : les **options de tri** du `<SortSelect>`.

| Élément | Spec |
|---|---|
| Recherche | input 38 px, flex `1 1 220px` max 400 px, loupe 15 px, `--fs-input` (≥ 16 px iOS) |
| Bouton Filtres | `.btn` + icône sliders + badge compteur `--accent`/`--on-accent` si ≥ 1 critère. Desktop : toggle panneau ; < 640 : ouvre le drawer |
| Tri (R6) | select natif stylé, **4 options** : **Tendance (défaut)** · Pour toi · BPM · Récent. Masqué < 640 px (le tri vivra dans le drawer ; v1 : ordre par défaut) |
| Compteur live | droite, mono 500 `--fs-sm` `--ink-2` « N sons » ; « … » en chargement |
| Chips actives | rangée sous la barre, 1 chip/critère + « Tout effacer » (mapping canonique de `BRIEF-filtres-partages.md`) |
| Panneau | carte inline 6 colonnes, jeu de filtres **identique à Explorer** : BPM (2) · Année (2) · Durée-preset (2) / Key Camelot (4) · Bibliothèque (2) / Styles (4) · Artiste (2) / Label (2) · Avis (2) · Extrait (2) |

**Priorité au trio Style · BPM · Key** (cas cible : « ce qui monte en techno 130–135 qui me correspond »). Tous les autres contrôles Explorer restent disponibles dans le même panneau/drawer. Filtres synchronisés dans l'URL (bookmarkable). Le tri fait partie de l'état URL, jamais un chip, jamais compté dans le badge.

## Table — anatomie de la ligne bi-score

`table-layout` en CSS grid, **une grille partagée** en-tête/rangées.

**Grille desktop (≥ 1000 px)** : `44px minmax(0,1fr) 176px 56px 48px 64px 64px 84px`
→ Play · Track · Style · BPM · Key · **Tendance** · **Pour toi** · Avis. Gap `--space-2`, padding horizontal `--page-px`.

| Colonne | Spec | Tokens |
|---|---|---|
| Play | bouton rond 30 px, hover-reveal desktop, toujours visible ≤ 640. Playing → pause accent. `has_preview=false` → aucun bouton | — |
| Track | `<Artwork size="row">` 38 px + **indicateur in-lib** (point plein `--pos` / cercle pointillé `--ink-3`). Titre 600 `--fs-table` ellipsis + **badge #rank** (R8) ; artistes `--fs-table-sm` `--ink-3` cliquables (`artists[]`, `stopPropagation`, séparateur « , ») | — |
| Style | 1 `<StyleTag>` (name+pillar+depth, clic → `/style/:genre`) + « +N » mono `--fs-nano` si `genres.length>1`. `genres` vide → repli `style` | hue pilier |
| BPM | mono 500 `--fs-table` `--ink-2`, arrondi entier, aligné droite ; null → « — » `--ink-3` | `--font-mono` |
| Key | mono 600 `--fs-table` `--accent-ink` ; null → « — » `--ink-3` | — |
| **Tendance** (R1/R3/R4/R5) | cellule 64 px, `align-self: stretch` + flex centré → **bande de colonne** possible. Contenu : `<ScoreRing size="sm">` (`score = trend_score_10 / 10`, note `round(trend_score_10)` au centre, arc `note/10 × circonférence`) **OU** « — » si `trend_score_10 == null`. Colonne triée → fond cellule `--accent-wash`. Velocity haute → ▲ accent en coin | arc `--accent`, note `--ink` mono |
| **Pour toi** (R1/R3/R4) | idem, `score = reco_score_10 / 10` ; « — » si `reco_score_10 == null` (systématique en cold-start). Colonne triée → fond `--accent-wash`. Jamais de ▲ velocity | idem |
| Avis (R9) | 2 boutons ronds 28 px : cœur (liked `--pos`/`--pos-soft`) + pouce bas (disliked `--neg`/`--neg-soft`), repos `--ink-3`. `stopPropagation`, `PATCH /api/catalog/{id}/avis` | — |

### `<ScoreRing>` — rappel du contrat consommé (FIGÉ, `BRIEF-composants-transverses.md`)

Anneau SVG : piste `--line-2`, arc valeur `--accent` (remplissage = note/10, départ 12 h, `stroke-linecap: round`), stroke 2.5 px (sm) / 3 px (md). Centre : note entière mono 600 `--fs-xs` (sm) / `--fs-sm` (md), `--ink`, **pas de « /10 » affiché**. Entrée = score 0-1 (ici `*_score_10 / 10`), affichage = `round(score×10)`. Le float sert au tri, jamais affiché. Tailles : **sm 30 px (ligne, utilisée ici)** · md 40 px (card). A11y : `role="img"` + `aria-label` contextuel (« Tendance 9 sur 10 », « Pour toi 7 sur 10 »). **Géométrie non redéfinie** — Radar décide seulement placement (2 colonnes), taille (sm), et comportement en colonne (bande active, état « — »).

### En-têtes de score (R3)

- En-tête sticky 36 px, `align-self: stretch`, contenu centré.
- Tendance / Pour toi / BPM = **boutons triables** (clic → tri, flèche ↑/↓). Colonne active : texte `--accent-ink` 600 + fond en-tête `--accent-wash` (prolonge la bande). Inactive : `--ink-2`.
- La bande `--accent-wash` couvre en-tête + cellules de la colonne active sur toute la hauteur — un repère vertical continu même en scroll virtualisé.

### États de rangée (hérités Explorer, R9)

| État | Spec |
|---|---|
| Repos | fond transparent |
| Hover | `--surface-2`, play révélé, 0.12 s |
| Playing | tint `--accent-wash` (hover inclus), bouton play → pause accent |
| Liked | wash `--pos-wash` (repos) → `--pos-wash-2` (hover), cœur rempli `--pos` — **aucune pondération Radar** des likes |
| Disliked | rangée entière opacity 0.45, pouce `--neg`/`--neg-soft` |
| Sans preview | pas de bouton play |
| BPM / Key null | « — » `--ink-3` |
| Mono-score | l'autre colonne = « — » muet (R4), rangée par ailleurs normale |

*Note interaction bande × wash : la bande de colonne `--accent-wash` est portée par la **cellule** (enfant), elle prime visuellement sur le wash de rangée dans cette seule cellule — accepté (léger renforcement de teinte sur la colonne active d'une ligne playing/liked).*

### Scroll & virtualisation

**Infinite scroll virtualisé (windowing)** : hauteur de rangée **constante** `--row-h` (les 2 rings sm + « — » n'étirent jamais la rangée), en-tête **sticky**, **pas de pagination**. Sentinelle de fin = note mono `--fs-xs` `--ink-3` centrée. Scroll = celui de la page.

### États page

| État | Spec |
|---|---|
| Chargement | 8 rangées skeleton dans la grille exacte (incl. 2 disques `--surface-2` 30 px pour les colonnes de score), `rd-pulse` 1,4 s, delay +0,12 s ; compteur « … » |
| Aucun résultat | centré `--space-15x` : loupe barrée 34 px · « Aucun résultat avec ces filtres » 600 `--fs-md` · sous-texte `--fs-sm` `--ink-2` · chips retirables (hover `--neg`) · `.btn` « Réinitialiser tous les filtres » |
| Cold-start (R7) | colonne Pour toi entièrement « — » + bandeau invite ; tri Tendance |
| Vierge | aucun filtre → compteur = bornes de l'union, table pleine |

## Cold-start — l'invite (R7)

Bandeau entre la barre de filtres et la table, affiché seulement si `reco` vide (aucun like) et non fermé :
- Conteneur : flex, `--accent-wash`, border `--line-2`, `--r-md`, padding `--space-25 --space-3`.
- Icône : disque 32 px `--accent-soft` + cœur `--accent-ink` 16 px.
- Texte : « **Débloque Pour toi** » 600 `--fs-sm` + « Like quelques sons pour activer tes recommandations personnalisées. En attendant, tu vois le classement Tendance. » `--fs-xs` `--ink-2`.
- Bouton fermer 26 px rond `--ink-3` (hover `--surface-2`).
- La colonne Pour toi reste visible (en-tête + « — » partout) — on montre la promesse, pas un trou.

## Responsive — échelle de column-drop préservant les 2 scores

Page dans `.rd-page` : max-width `--page-max-w`, `container-type: inline-size`. **Container queries uniquement** (`@container`), seuils repo 720/640 ; seule exception `position: fixed` : le drawer. Padding `--page-px` → `--page-px-mobile` < 640.

**Ordre de disparition** : les 2 scores sont la raison d'être de la page → ils **survivent le plus longtemps**. Tombent avant, dans l'ordre : **Style, puis Key, puis BPM**.

| Seuil | Colonnes | Grille |
|---|---|---|
| ≥ 1000 px | Play · Track · Style · BPM · Key · Tendance · Pour toi · Avis | `44px 1fr 176px 56px 48px 64px 64px 84px` |
| < 1000 px | − **Style** | `44px 1fr 56px 48px 64px 64px 84px` |
| < 860 px | − **Key** (panneau → 2 colonnes) | `44px 1fr 56px 64px 64px 84px` |
| < 700 px | − **BPM** (panneau → 1 colonne) | `44px 1fr 64px 64px 84px` |
| < 640 px | **Play · Track · Tendance · Pour toi · Avis** — play toujours visible (tactile), avis conservé, gap `--space-1`, tri select masqué, « Filtres » → **drawer** | `40px 1fr 52px 52px 76px` |

Les 2 anneaux sm (30 px) tiennent dans les colonnes 52 px du pilote 375 px. Jamais de scroll horizontal ; cibles tactiles ≥ 44 px via le padding de rangée. **Drawer mobile** : identique à Explorer (`BRIEF-filtres-partages.md`), sans surprise Radar.

## Données consommées (exhaustif — endpoint bi-score, ne rien inventer au-delà)

Forme par item : `id`, `title`, `artist` (repli), `artists[]` `{id,name}` (jamais supposer un seul), `bpm` (float, arrondi affichage), `key` (Camelot, nullable), `genres[]` `{name,pillar,depth}`, `style` (repli), `has_artwork`, `has_preview`, `in_lib`, `avis` (`liked`/`disliked`/null), `artist_id`, `trend_rank` (nullable, badge si ≤ 50), **`trend_score_10`** (float /10, nullable → « — »), **`reco_score_10`** (float /10, nullable → « — »), `velocity` (float nullable → ▲). `duration_ms` existe mais **jamais affiché**.

- Liste = **union bornée** : top tendances par famille de genre ∪ ≤ 100 recos perso → la plupart des lignes n'ont qu'un score.
- **Auth obligatoire** (JWT). Cold-start (aucun like) → `reco_score_10 = null` partout.
- Options de filtres identiques à Explorer : Styles `GET /api/catalog/genres` (plat, groupé par pilier) · Artiste `GET /api/artists/?q=` · Keys = 24 Camelot statiques.

## Grille d'audit

Couleurs 100 % tokens · dark/light vérifiés (deux thèmes dans le pilote) · accent discipliné (badge compteur, sélections filtres, key, colonne de score active, arc des rings, ▲ velocity, badge #rank, playing — pas d'autre mauve) · mono pour toute donnée chiffrée (BPM, key, notes de score, compteurs, chips) · `--fs-input` ≥ 16 px sur tous les contrôles · container queries uniquement (fixed = drawer) · icônes SVG inline `currentColor` monochrome, zéro CDN · libellés 100 % FR · **Rating absent partout** · **pas de colonne Durée** · **2 colonnes de score** avec en-têtes triables + colonne active surlignée · **état « — »** muet pour score absent · **cold-start** géré comme état (Pour toi vide + invite) · `<ScoreRing>` géométrie non redéfinie (consommé) · rangée hauteur constante `--row-h` · en-tête sticky opaque · pagination absente · `artists[]` jamais réduit à un seul nom · responsive préservant les 2 scores jusqu'au 375 px (play + avis conservés) · zéro donnée inventée hors surface endpoint bi-score.
