# Brief — Mobile responsive (pilote réaligné)

> Maquette : `handoff-mobile/Mobile (pilote).html` · Tokens : `diggy-tokens.css`
> Cible Vue 3. L'app est desktop-only aujourd'hui — **responsive progressif** (pas de version séparée).
> La barre sombre en haut + le cadre device sont des **outils de revue**, PAS dans le produit.

---

## Décisions DA (figées)

| # | Décision | Valeur |
|---|---|---|
| M1 | Approche | **Responsive progressif** — un seul code, on ajoute des breakpoints. Au-dessus de 640px, **rien ne change**. |
| M2 | Breakpoint mobile | **640px** = la coupure. En dessous : sidebar → BottomNav. Nouveau breakpoint principal. |
| M3 | Container vs media queries | Le flux reste piloté par `@container` sur `.app` (comme tout le projet). **Exception** : les éléments `position: fixed` hors flux — PlayerBar, BottomNav, modales — sont dimensionnés par `@media` en prod. |
| M4 | Cible tactile | **44px minimum** de hauteur pour tout interactif. Les états `opacity:0` révélés au hover deviennent **toujours visibles** (pas de hover tactile). |
| M5 | Zones sûres iPhone | BottomNav et PlayerBar réservent `env(safe-area-inset-bottom)`. |
| M6 | Priorité vues | Vues listes d'abord. Login et Admin = faible priorité (Admin desktop, un seul user). |

## Arbitrages produit (actés 2026-07-02)

| Point | Décision |
|---|---|
| Playlists dans la BottomNav | **Non** — 5 items (Hub, Catalog, Artistes, Sets, Genres) + Admin conditionnel. Playlists accessible via Hub/liens. |
| Like/Dislike Catalog mobile | Colonne Avis tombe normalement (≤900px). **Tap → Track Detail** pour like/dislike. |
| Modale import mobile | **Plein écran** (pas sheet bas). |
| Badge count BottomNav | **Oui, dès maintenant** — brancher sur `/api/radar/new-count`. |

---

## a. BottomNav (nouveau composant)

Sous 640px, la sidebar disparaît. Elle est remplacée par une **barre fixe en bas**.

**Items** (route active mise en avant) :

| Ordre | Item | Route | Icône |
|---|---|---|---|
| 1 | Hub | `/` | maison |
| 2 | Catalog | `/catalog` | grille 2×2 |
| 3 | Artistes | `/artists` | 2 personnes |
| 4 | Sets | `/sets` | disque |
| 5 | Genres | `/genres` | tag |
| 6 | **Admin** | `/admin` | étoile — **role-gated** : rendu seulement si `user.isAdmin` (pas masqué CSS, non-rendu) |

**Anatomie** : icône SVG **22px** + label mono **10px** dessous, centrés, colonne. Largeur = `flex: 1`.

**Dimensions** : rangée `height: 56px` + `padding-bottom: env(safe-area-inset-bottom)`.

**Badge count** : pastille `--accent` / texte `--on-accent`, mono 9px, en haut-droite de l'icône Catalog. Branché sur `/api/radar/new-count`.

**Tokens** :

| Élément | Token |
|---|---|
| Fond barre | `--surface` |
| Bordure haute | `1px solid var(--line)` |
| Icône/label inactif | `--ink-3` (hover `--ink-2`) |
| Icône/label actif | `--accent` |
| Highlight route active | barre 26×3px `--accent`, collée en haut de l'item |
| Badge count | pastille `--accent` / texte `--on-accent`, mono 9px |

**Z-index** : `50` — en dessous du PlayerBar (`60`) et des modales (`90`).

---

## b. Layout shell mobile

| Propriété | Desktop | Mobile (≤ 640px) |
|---|---|---|
| `grid-template-columns` | `var(--sidebar-w) 1fr` | **`1fr`** |
| Sidebar | visible | **`display: none`** |
| BottomNav | absente | **visible** |
| `padding-bottom` scroll | ~100px si player | **~160px** si player, **~64px** sinon |

---

## c. PlayerBar mobile

| Propriété | Desktop / tablette | Mobile (≤ 640px) |
|---|---|---|
| `bottom` | `16–18px` | **`calc(56px + env(safe-area-inset-bottom) + 8px)`** |
| Marges latérales | `16–24px` | **`8px`** |
| Hauteur `.pl-inner` | `74px` | `66px` |

État final sur 375px : **Play/Pause + equalizer + identité + barre scrub + ✕**.

---

## d. Tables mobile — ordre de chute

### Table Catalog — sur 375px survivent : `Play · Track · Key · InLib`

| Largeur | Colonne qui tombe |
|---|---|
| ≤ 1160px | Duration |
| ≤ 1010px | Rating |
| ≤ 900px | Avis · sidebar → rail |
| ≤ 760px | Radar |
| ≤ 640px | sidebar masquée · BottomNav · paddings 16px |
| ≤ 620px | Style |
| ≤ 560px | BPM |

### Table Sets — sur 375px survivent : `Set (nom + métas empilées) · Avis`

### Tracklists — sur 375px survivent : `# · Play · Cover+Titre · Key · LibDot`

---

## e. Modales mobile

**Plein écran** sous 640px : `max-width: 100%; height: 100%; border-radius: 0;`

---

## f. Cibles tactiles

- **44px minimum** pour tout interactif
- `.pbtn` et `.act` : `opacity: 1` sous 640px (pas de hover)

---

## g. Vue par vue — adaptations sous 640px

| Vue | Changements mobile |
|---|---|
| **CatalogView** | Table allégée (§d), padding 16px, h1 ~23px, chips scroll horizontal, search pleine largeur |
| **ArtistsView** | Grille `minmax(150px, 1fr)`, padding 16px |
| **ArtistDetailView** | Hero empilé, mini-rows simplifiées (masquer BPM/Key ≤500px) |
| **SetsView** | Formulaire ajout en column, grille artistes 2→1 col |
| **SetDetailView** | Tracklist allégée, anneau centré |
| **GenresView** | Grille `minmax(150px, 1fr)`, padding 16px |
| **GenreDetailView** | Shelves scroll horizontal, tracks allégées, padding 16px |
| **HubView** | Search pleine largeur, résultats empilés, shelves scroll horizontal |
| **TrackDetailView** | Hero empilé, `.rel-cols` 1 colonne |
| **WatchlistView** | Padding réduit, table playlists allégée |
| **LoginView** | Aucun changement attendu |
| **AdminView** | Faible priorité, vérification minimale |

---

## Grille d'audit mobile

- [ ] 640px : sidebar disparaît, BottomNav apparaît, aucun chevauchement
- [ ] BottomNav : 5 items (6 si admin), route active, safe-area, badge count radar
- [ ] PlayerBar : au-dessus de la BottomNav, marges 8px, sur 375px = play + identité + scrub + ✕
- [ ] Tables : ordre de chute respecté, Track + Key + InLib survivent sur 375px
- [ ] Cibles ≥ 44px · `.pbtn`/`.act` visibles
- [ ] Modale = plein écran sur mobile
- [ ] Aucun débordement horizontal sur 375px
- [ ] Dark mode vérifié sur 375 / 390 / 768
- [ ] Tokens : zéro valeur hors `var(--…)`
