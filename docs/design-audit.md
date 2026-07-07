# Audit de dette visuelle — Diggy Frontend

> Généré le 2026-07-08. Scope : `server/frontend/src/**/*.{vue,css}` (55 fichiers : 51 `.vue`, 2 `.css` d'assets, 1 `.css` de tokens). Extraction par script (regex + parsing paren-balancé sur les blocs `<style>` et fichiers CSS), comptage brut, pas de dédup manuelle des styles générés dynamiquement (`v-bind`, classes conditionnelles).

## Résumé exécutif

Le système de tokens (`diggy-tokens.css`, 204 lignes) est **globalement bien respecté pour les couleurs** : seulement 59 occurrences de couleur brute hors fichier de tokens, contre des centaines d'usages de `var(--...)`. La vraie dette est ailleurs :

1. **Aucune échelle de spacing ni de font-size n'existe.** `diggy-tokens.css` ne définit que 2 tokens de spacing (`--pad`, `--page-px-mobile`). Résultat : 30 valeurs de px différentes (0 à 156px) utilisées en dur pour margin/padding/gap, et 12 valeurs de font-size différentes, sans grille cohérente (8px et 9px coexistent, 12px/12.5px/13px coexistent, 14px/14.5px coexistent).
2. **2 variables CSS utilisées mais jamais définies** : `var(--border)` et `var(--ink-muted)` — bug silencieux (le navigateur ignore la déclaration, la valeur retombe sur l'héritage). 5 fichiers concernés.
3. **`--page-px` (30px) est défini mais jamais utilisé** — 7 vues hardcodent `30px` en dur (39 occurrences) au lieu du token, alors que son pendant mobile `--page-px-mobile` est correctement utilisé 37 fois. `--r-xl` et `--touch-min` sont aussi définis et jamais consommés.
4. **Un bloc CSS de 3 lignes identique dupliqué verbatim dans 7 vues** (`padding: 26px 30px 18px; gap: 20px;` — header de page), candidat évident à une classe/composant partagé.
5. **`ArtistCard.vue`/`ArtistDetailView.vue` et `GenreCard.vue`/`GenreDetailView.vue`** dupliquent les mêmes formules `oklch()` brutes (au lieu de tokens) entre la carte et sa vue détail — 6 paires de quasi-doublons identifiées.

---

## 1. Couleurs

### 1.1 Système de tokens (source de vérité : `src/styles/diggy-tokens.css`)

Toutes les couleurs sont définies en `oklch()`, avec surcharge complète en `[data-theme='dark']`. 64 valeurs `oklch()` brutes légitimes dans ce fichier (dont les surcharges dark mode), organisées en familles sémantiques :

| Famille | Tokens |
|---|---|
| Neutres | `--bg`, `--surface`, `--surface-2`, `--surface-3`, `--ink`, `--ink-2`, `--ink-3`, `--line`, `--line-2` |
| Accent (mauve) | `--accent`, `--accent-hover`, `--accent-soft`, `--accent-soft-2`, `--accent-ink`, `--on-accent`, `--accent-wash` |
| Positif (in-lib) | `--pos`, `--pos-soft`, `--pos-ink` |
| Négatif (dislike) | `--neg`, `--neg-soft`, `--neg-ink` |
| Warning / erreur | `--warn`, `--warn-soft`, `--warn-ink`, `--error` |
| Chips / genres | `--tag-bg-l/c`, `--tag-fg-l/c`, `--tag-dot-l/c`, `--hue-house/techno/trance/dnb/hardcore/harddance` |
| Overlays (theme-indep.) | `--overlay-modal`, `--overlay-soft`, `--overlay-text` |
| Radii | `--r-xs` (6px), `--r-sm` (9px), `--r-md` (13px), `--r-lg` (18px), `--r-xl` (24px) |
| Ombres | `--shadow-sm/md/lg` |

### 1.2 Usage des tokens — top 20 (sur 90 `var(--...)` distincts référencés)

| Token | Occurrences | Fichiers |
|---|---:|---:|
| `--ink-3` | 200 | 44 |
| `--font-ui` | 186 | 44 |
| `--font-mono` | 153 | 38 |
| `--ink` | 117 | 41 |
| `--ink-2` | 104 | 32 |
| `--surface-2` | 94 | 37 |
| `--accent-ink` | 93 | 30 |
| `--r-sm` | 88 | 31 |
| `--line` | 83 | 34 |
| `--surface` | 80 | 36 |
| `--accent` | 79 | 36 |
| `--line-2` | 73 | 31 |
| `--accent-soft` | 54 | 26 |
| `--neg-ink` | 38 | 19 |
| `--page-px-mobile` | 37 | 13 |
| `--pos-ink` | 34 | 21 |
| `--on-accent` | 31 | 21 |
| `--r-xs` | 26 | 16 |
| `--surface-3` | 22 | 15 |
| `--r-md` | 21 | 14 |

Bonne nouvelle : les tokens neutres/accent dominent très largement l'usage réel des couleurs — le système est adopté.

### 1.3 ⚠️ Couleurs brutes hors fichier de tokens (dette réelle)

**38 valeurs uniques, 59 occurrences**, réparties en deux catégories :

**A. Compositions `oklch()` locales par composant** (le composant redéclare sa propre formule `oklch(L C H)` au lieu d'un token unique) :

| Valeur | Occ. | Fichiers |
|---|---:|---|
| `oklch(var(--pos-l) var(--pos-c) var(--pos-h) / 0.06)` | 4 | `assets/table.css`, `CatalogView.vue`, `SetsView.vue`, `WatchlistView.vue` |
| `oklch(var(--tag-dot-l) var(--tag-dot-c) var(--th))` | 4 | `FamilyChips.vue`, `GenreCard.vue`, `HubView.vue` (×2) |
| `oklch(var(--pos-l) var(--pos-c) var(--pos-h) / 0.1)` | 4 | `CatalogView.vue` (×2), `SetsView.vue`, `WatchlistView.vue` |
| `oklch(var(--tag-fg-l) var(--tag-fg-c) var(--th))` | 3 | `ArtistCard.vue`, `GenreCard.vue`, `HubView.vue` |
| `oklch(var(--ct-l) var(--ct-c) var(--th))` | 2 | `ArtistCard.vue`, `GenreCard.vue` |
| `oklch(var(--tag-dot-l) var(--tag-dot-c) var(--th) / 0.28)` | 2 | `FamilyChips.vue`, `GenreCard.vue` |
| `oklch(var(--tag-dot-l) var(--tag-dot-c) var(--th, 0))` | 2 | `GenreDetailView.vue`, `PlaylistDetailView.vue` |

→ 4 combinaisons `--pos-l/c/h` avec transparence sont recomposées à l'identique dans 4 fichiers plutôt que d'être un token `--pos-wash` (sur le modèle de `--accent-wash` qui existe déjà). Même remarque pour le trio `--tag-dot-*` répété dans 4 fichiers.

**B. Couleurs 100% littérales (aucune variabilisation)** — quasi-doublons entre carte et vue détail :

| Valeur | Occ. | Fichiers | Constat |
|---|---:|---|---|
| `oklch(0.99 0.004 92)` | 4 | `GenreCard.vue` (×2), `GenreDetailView.vue` (×2) | dupliqué verbatim carte ↔ détail |
| `oklch(0.12 0.02 262 / 0.34)` | 2 | `ArtistCard.vue` (×2) | — |
| `oklch(0.2 0.02 70 / 0.42)` | 2 | `GenreCard.vue`, `GenreDetailView.vue` | dupliqué carte ↔ détail |
| `oklch(0.28 0.012 262)` | 2 | `GenreCard.vue`, `GenreDetailView.vue` | dupliqué carte ↔ détail |
| `oklch(0.2 0.02 70 / 0.6)` | 2 | `GenreCard.vue`, `GenreDetailView.vue` | dupliqué carte ↔ détail |
| `oklch(0.12/0.1 0.01/0.02 70 / *)` (5 variantes proches) | 5×1 | `ArtistDetailView.vue` | 5 nuances quasi-identiques d'un même noir chaud, non factorisées |
| `rgba(0, 0, 0, 0.2)` | 1 | `ToastNotification.vue` | seul usage de `rgba()` — incohérent avec le reste en `oklch()` |
| `rgba(0, 0, 0, 0.15)` | 1 | `AdminGenres.vue` | idem |

**Constat** : `GenreCard.vue` ↔ `GenreDetailView.vue` partagent au moins 6 valeurs `oklch()` littérales identiques (fond de tuile, overlay, ligne de séparation) qui ne sont dans aucun token. `ArtistCard.vue` a la même logique de "fallback gradient" que `GenreCard.vue` (tokens `--fb-l1/c1/l2/c2` vs `--ml`/`--mc`) réimplémentée différemment plutôt que partagée.

`ToastNotification.vue` et `AdminGenres.vue` sont les deux seuls fichiers du projet à utiliser `rgba()` — anomalie de syntaxe par rapport au reste du codebase en `oklch()`.

### 1.4 🐛 Variables référencées mais jamais définies (bug)

| Variable | Utilisée dans | Devrait probablement être |
|---|---|---|
| `var(--border)` | `AdminBeatport.vue:137`, `AdminGenres.vue:310` | `var(--line)` |
| `var(--ink-muted)` | `AdminBeatport.vue:131`, `AdminGenres.vue:304`, `TrackDetailView.vue:650` | `var(--ink-2)` ou `var(--ink-3)` |

Ces deux tokens n'existent nulle part dans `diggy-tokens.css`. Le navigateur traite la déclaration comme invalide et retombe sur la valeur héritée — l'effet visuel est probablement passé inaperçu (texte hérite d'une couleur parente proche), mais c'est un bug silencieux à corriger.

*(Note : `--th`, `--d`, `--ml`, `--mc`, `--art-l`, `--art-c` apparaissent aussi comme "non définis" par une recherche naïve, mais sont en réalité posés dynamiquement par sélecteur `[data-fam='...']` ou `:nth-child()` dans le même fichier — pattern voulu, pas un bug.)*

### 1.5 💀 Tokens définis mais jamais consommés

| Token | Valeur | Constat |
|---|---|---|
| `--page-px` | `30px` | Jamais référencé via `var()`. Les 7 vues qui en auraient besoin (`ArtistsView`, `CatalogView`, `CollectionDetailView`, `CollectionsView`, `GenresView`, `SetsView`, `WatchlistView`) hardcodent `30px` en dur dans leur `padding` de header (voir §2.3). Le pendant mobile `--page-px-mobile` lui est bien utilisé (37×). |
| `--r-xl` | `24px` | Jamais utilisé — la plus grande des 5 tailles de radius de l'échelle n'a aucun consommateur. |
| `--touch-min` | `44px` | Jamais utilisé — cible d'accessibilité tactile (44px, recommandation WCAG) définie mais non appliquée à un seul élément interactif. À vérifier si les zones tactiles mobiles (BottomNav, boutons) respectent réellement 44px sans passer par ce token. |

---

## 2. Font-sizes

**12 valeurs uniques, 57 occurrences.** Aucun token de type scale n'existe dans `diggy-tokens.css` (seulement `--font-ui` / `--font-mono` pour les familles) — chaque `font-size` est un nombre en dur.

| Valeur | Occ. | Fichiers |
|---|---:|---|
| `13px` | 16 | `GenreCard.vue`, `admin/AdminArtists.vue`, `admin/AdminBeatport.vue`, `admin/AdminCrawl.vue` (×3), `admin/AdminFlags.vue` (×2), `admin/AdminGenres.vue` (×4), `admin/AdminSets.vue`, `PlaylistDetailView.vue`, `SetDetailView.vue`, `TrackDetailView.vue` |
| `11px` | 7 | `PlayerBar.vue`, `admin/AdminArtists.vue` (×2), `admin/AdminFlags.vue` (×2), `ArtistDetailView.vue`, `SetDetailView.vue` |
| `14px` | 7 | `admin/AdminSets.vue`, `ArtistDetailView.vue`, `HubView.vue`, `PlaylistDetailView.vue`, `SetDetailView.vue`, `TagsView.vue`, `TrackDetailView.vue` |
| `12px` | 5 | `assets/buttons.css`, `admin/AdminArtists.vue`, `PlaylistDetailView.vue`, `SetDetailView.vue` (×2) |
| `28px` | 5 | `CollectionDetailView.vue`, `CollectionsView.vue`, `HubView.vue`, `SetsView.vue`, `WatchlistView.vue` |
| `14.5px` | 4 | `assets/table.css`, `CatalogView.vue`, `CollectionDetailView.vue`, `SetsView.vue` |
| `12.5px` | 4 | `assets/table.css`, `CatalogView.vue`, `CollectionDetailView.vue`, `SetsView.vue` |
| `10px` | 4 | `admin/AdminFlags.vue`, `admin/AdminGenres.vue`, `ArtistDetailView.vue`, `TrackDetailView.vue` |
| `18px` | 2 | `AppearRow.vue`, `TrackDetailView.vue` |
| `23px` | 1 | `CatalogView.vue` |
| `17px` | 1 | `HubView.vue` |
| `36px` | 1 | `HubView.vue` |

### ⚠️ Quasi-doublons

- **`12px` / `12.5px` / `13px`** — 3 valeurs à moins de 1px d'écart, coexistant dans des fichiers voisins (`assets/table.css`, `CatalogView.vue`, `SetsView.vue`, `CollectionDetailView.vue` utilisent `12.5px` alors que les vues admin utilisent `13px` pour un usage a priori similaire — libellés secondaires).
- **`14px` / `14.5px`** — même remarque, `14.5px` semble être un ajustement optique local (`table.css`) jamais propagé, alors que `14px` est le standard partout ailleurs.
- **`10px` / `11px`** — deux tailles de "micro-texte" (badges, labels) qui se chevauchent selon les fichiers sans règle apparente.

Sans token de type scale, il est impossible de savoir si `12.5px` est intentionnel (ajustement optique fin) ou une dérive de copier-coller depuis `13px`.

---

## 3. Spacing (margin / padding / gap)

**742 déclarations brutes (161 valeurs shorthand uniques) → 1054 tokens atomiques après éclatement des raccourcis, soit 45 valeurs atomiques distinctes.** Seuls 2 tokens sémantiques existent (`--pad`, `--page-px-mobile`) ; tout le reste est en dur.

### 3.1 Échelle numérique réellement utilisée (px-normalisé)

| px | Occ. (atomique) | Fichiers |
|---:|---:|---:|
| 0 | 153 | 37 |
| 1 | 7 | 5 |
| 2 | 44 | 23 |
| 3 | 22 | 13 |
| 4 | 48 | 26 |
| 5 | 26 | 19 |
| 6 | 46 | 22 |
| 7 | 41 | 20 |
| 8 | 99 | 35 |
| 9 | 30 | 19 |
| 10 | 79 | 29 |
| 11 | 13 | 10 |
| 12 | 85 | 32 |
| 13 | 3 | 3 |
| 14 | 81 | 27 |
| 15 | 2 | 2 |
| 16 | 57 | 35 |
| 18 | 19 | 11 |
| 20 | 28 | 18 |
| 22 | 9 | 7 |
| 24 | 16 | 13 |
| 26 | 9 | 9 |
| 28 | 4 | 3 |
| 30 | 39 | 11 |
| 32 | 2 | 2 |
| 34 | 1 | 1 |
| 36 | 9 | 9 |
| 40 | 10 | 10 |
| 48 | 1 | 1 |
| 56 | 1 | 1 |
| 60 | 6 | 6 |
| 100 | 1 | 1 |
| 156 | 1 | 1 |

**Constat central : chaque entier de 0 à 16 est utilisé au moins une fois**, sans grille 4/8px. Il n'existe littéralement aucune valeur "interdite" — 1px, 3px, 5px, 7px, 9px, 11px, 13px, 15px sont toutes présentes à côté de leurs voisines paires. C'est la dette la plus large du projet en volume (1054 occurrences).

### ⚠️ Clusters de quasi-doublons les plus problématiques

- **8px / 9px / 10px** — 99 + 30 + 79 = 208 occurrences à eux trois, dans 35/19/29 fichiers respectivement. Ce sont trois "petits espacements" qui se chevauchent presque partout — impossible de deviner l'intention sans lire chaque contexte.
- **12px / 13px / 14px** — 85 + 3 + 81 occurrences. `13px` est marginal (3×) au milieu de deux valeurs très employées — probablement une dérive isolée plutôt qu'un choix.
- **18px / 20px** vs **26px / 28px / 30px** — deux paires proches utilisées comme "grand espacement", sans qu'on sache laquelle est la référence.
- **`var(--pad)` (13× dans 7 fichiers) vs `16px` en dur (57× dans 35 fichiers)** — `--pad` vaut 16px par défaut (et varie avec `[data-density]`). Les 35 fichiers qui écrivent `16px` en dur **ignorent la densité compacte/confortable** que `--pad` est censé piloter (`[data-density='compact']` → 12px, `[data-density='comfy']` → 22px). Si la densité est une fonctionnalité active, la majorité des composants n'y réagissent pas.

### 3.2 Duplication de blocs entiers (pas juste des valeurs)

Le shorthand `padding: 26px 30px 18px;` combiné à `gap: 20px;` apparaît **verbatim dans 7 vues** :

`ArtistsView.vue:206`, `CatalogView.vue:578`, `CollectionDetailView.vue:183`, `CollectionsView.vue:140`, `GenresView.vue:213`, `SetsView.vue:389`, `WatchlistView.vue:410`

C'est un header de page dupliqué à l'identique 7 fois plutôt que factorisé en classe partagée ou composant `PageHero`-like (qui existe déjà comme composant pour un autre usage — `PageHero.vue` — mais n'est apparemment pas réutilisé ici).

Autres shorthands répétés à l'identique dans ≥ 5 fichiers différents : `0 14px` (11× / 6 fichiers), `3px 7px` (10× / 8 fichiers), `0 16px` (9× / 8 fichiers), `6px 14px` (6× / 5 fichiers), `8px 12px` (6× / 5 fichiers), `20px 24px` (6× / 6 fichiers) — tous candidats à une classe utilitaire de badge/pill/bouton partagée.

---

## 4. Border-radius

**20 valeurs uniques, 255 occurrences.** Contrairement au spacing, un token existe (`--r-xs/sm/md/lg/xl`) et il est majoritairement adopté :

| Valeur | Occ. | Nature |
|---|---:|---|
| `var(--r-sm)` (9px) | 88 | token — dominant |
| `50%` | 49 | légitime (cercles : avatars, dots, boutons ronds) |
| `var(--r-xs)` (6px) | 26 | token |
| `999px` | 23 | **littéral répété** — pattern "pill" (badge, chip) jamais promu en token malgré 23 usages dans 12 fichiers |
| `var(--r-md)` (13px) | 21 | token |
| `4px` | 17 | **littéral, proche de `--r-xs` (6px) sans y correspondre** — dérive possible |
| `2px` | 7 | littéral (petits éléments : ScorePill, PlayerBar) |
| `10px` | 4 | littéral, très proche de `var(--r-sm)` (9px) — quasi-doublon direct |
| `9px` | 3 | **littéral qui vaut exactement la valeur de `--r-sm` sans utiliser le token** (`BottomNav.vue`, `SidebarNav.vue`, `LoginView.vue`) |
| `var(--r-sm, 6px)` | 3 | fallback redondant : `--r-sm` vaut déjà 9px dans `:root`, ce fallback (6px, qui est en fait la valeur de `--r-xs`) ne peut jamais être visuellement cohérent s'il se déclenche |
| `var(--r-lg)` (18px) | 3 | token |
| `3px` | 2 | littéral |
| `8px` | 2 | littéral, proche de `--r-xs` |
| `var(--r-lg, 16px)` | 1 | fallback incohérent : `--r-lg` vaut 18px, pas 16px |
| `var(--r-md, 10px)` | 1 | fallback incohérent : `--r-md` vaut 13px, pas 10px |
| `0 0 2px 2px` | 1 | shorthand 4-coins, cas unique |
| `1px`, `15px`, `16px` | 1 chacun | littéraux isolés |

### ⚠️ Points notables

1. **`999px` (pattern "pill") mériterait un token dédié** (`--r-pill` ou `--r-full`) — 23 occurrences dans 12 fichiers, jamais varié, candidat évident.
2. **`9px` en dur dans 3 fichiers vaut exactement `--r-sm`** — copié en dur au lieu du token (`BottomNav.vue`, `SidebarNav.vue`, `LoginView.vue`).
3. **3 fallbacks `var(--x, Ypx)` avec une valeur de repli fausse** : `var(--r-sm, 6px)`, `var(--r-lg, 16px)`, `var(--r-md, 10px)` — le fallback ne correspond pas à la vraie valeur du token dans `:root` (respectivement 9px, 18px, 13px). Ces fallbacks ne se déclenchent en pratique jamais tant que `diggy-tokens.css` est chargé, mais s'il ne l'était pas (erreur de build, ordre CSS), l'un rendrait un radius plus petit que prévu et les deux autres plus petit aussi — incohérence à nettoyer même si le risque réel est faible (uniquement `ImportRekordboxModal.vue`).
4. **`4px` (17×) et `10px` (4×)** sont des radius "presque token" — assez proches de `--r-xs`/`--r-sm` pour suggérer une dérive plutôt qu'un choix délibéré, mais pas assez identiques pour l'affirmer sans relire chaque contexte.

---

## 5. Recommandations priorisées

1. **Corriger les 2 variables non définies** (`--border` → `--line`, `--ink-muted` → `--ink-2`/`--ink-3`) — 5 fichiers, 5 minutes, bug silencieux réel.
2. **Créer une échelle de spacing** (ex. `--space-1` à `--space-8` sur base 4px) et migrer au moins les valeurs à plus de 40 occurrences (8px, 10px, 12px, 14px, 16px) — le plus gros volume de dette (1054 occurrences atomiques).
3. **Créer une échelle de font-size** (ex. `--fs-xs/sm/base/md/lg`) — seulement 12 valeurs à couvrir, impact immédiat sur la lisibilité du code et la cohérence visuelle.
4. **Décider si `--pad` doit piloter tous les espacements de densité** — sinon documenter que `[data-density]` n'affecte que les composants qui l'utilisent explicitement (7 fichiers sur 55 actuellement).
5. **Factoriser le header de page dupliqué 7×** (`padding: 26px 30px 18px; gap: 20px;`) en classe partagée ou en généralisant `PageHero.vue`.
6. **Utiliser `var(--page-px)` sur desktop** au lieu des `30px` en dur (39 occurrences, 11 fichiers) — ou supprimer le token s'il n'a plus de raison d'être.
7. **Ajouter un token `--r-pill: 999px`** et migrer les 23 occurrences littérales.
8. **Nettoyer les 3 fallbacks `var(--r-*, Ypx)` incohérents** dans `ImportRekordboxModal.vue`.
9. **Vérifier `--touch-min` (44px)** : soit l'appliquer réellement aux cibles tactiles mobiles (BottomNav, boutons), soit le retirer s'il est obsolète.
10. **Uniformiser `rgba()` → `oklch()`** dans `ToastNotification.vue` et `AdminGenres.vue` (2 occurrences, cohérence de syntaxe uniquement).
