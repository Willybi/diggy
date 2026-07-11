# Implémentation Like / Dislike — toutes entités

> Lis `design/CLAUDE.md` et la maquette de référence [`LikeDislike (pilote).html`](./LikeDislike%20(pilote).html) avant de commencer.
> Tous les tokens viennent de `diggy-tokens.css`. Zéro valeur en dur.
> **Un seul composant**, réutilisé tel quel partout — pas de copier-coller de CSS par page.

---

## 0. Token à formaliser dans `diggy-tokens.css`

Le couple positif (`--pos*`) existe ; le négatif n'existe pas encore. Ajouter dans `:root` (light) **et** `[data-theme="dark"]` :

```css
/* :root / light */
--neg-h: 28;
--neg:      oklch(0.585 0.132 var(--neg-h));
--neg-soft: oklch(0.942 0.040 var(--neg-h));
--neg-ink:  oklch(0.490 0.130 var(--neg-h));

/* [data-theme="dark"] */
--neg:      oklch(0.705 0.130 var(--neg-h));
--neg-soft: oklch(0.340 0.072 var(--neg-h));
--neg-ink:  oklch(0.818 0.108 var(--neg-h));
```

`--pos` (vert prairie) = **liked** ; `--neg` (rouge-orangé) = **disliked**. `--neg` est réservé au dislike, jamais en décoration.

---

## Composant partagé `LikeDislike`

Crée un composant Vue réutilisable `LikeDislike.vue` :

```vue
<!-- props: entityType, entityId, modelValue ('liked' | 'disliked' | null) -->
<!-- émet: update:modelValue -->
```

### Forme
- Deux boutons **carrés arrondis 30×30px**, `border-radius: var(--r-sm)` (PAS de ronds)
- SVG **15×15px**, `fill: none; stroke: currentColor; stroke-width: 1.8; stroke-linecap/linejoin: round`
- Ordre : **like puis dislike**, `gap: 6px`

### Icônes (figées — cœur A + cœur barré diagonale)
```html
<!-- LIKE : cœur classique -->
<svg viewBox="0 0 24 24">
  <path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"/>
</svg>

<!-- DISLIKE : même cœur + barré pleine diagonale (débord équilibré) -->
<svg viewBox="0 0 24 24">
  <path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"/>
  <path d="M4.5 19.5 22 2"/>
</svg>
```
> Le `like` engagé se **remplit** (`fill: var(--pos-ink); stroke: var(--pos-ink)`). Le `dislike` reste en contour.

### États (CSS, intégral)
```css
.ld { display: inline-flex; align-items: center; gap: 6px; }
.ld-btn {
  width: 30px; height: 30px; flex: none;
  display: grid; place-items: center;
  border-radius: var(--r-sm);
  border: 1px solid var(--line-2);
  background: var(--surface);
  color: var(--ink-3);
  cursor: pointer; padding: 0;
  transition: color .14s, border-color .14s, background .14s, opacity .16s;
}
.ld-btn svg { width: 15px; height: 15px; fill: none; stroke: currentColor;
  stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; }

.ld-btn.like:hover    { color: var(--pos); border-color: var(--pos); }
.ld-btn.dislike:hover { color: var(--neg); border-color: var(--neg); }

.ld[data-state="liked"] .ld-btn.like {
  background: var(--pos-soft); border-color: transparent; color: var(--pos-ink);
}
.ld[data-state="liked"] .ld-btn.like svg { fill: var(--pos-ink); stroke: var(--pos-ink); }

.ld[data-state="disliked"] .ld-btn.dislike {
  background: var(--neg-soft); border-color: transparent; color: var(--neg-ink);
}
```
- Like et dislike **mutuellement exclusifs** ; re-clic sur l'état actif → retour à `null`.
- Visibilité (repos masqué / révélé) = géré par le **conteneur**, pas par le composant (voir contextes).

---

## Règle de gouttière des listes (le point à corriger en prio)

Le problème en prod : la gouttière gauche/droite n'est pas constante d'une liste à l'autre. Règle unique :

```css
/* la zone de table a la gouttière de page */
.table-wrap { padding-left: var(--gutter); padding-right: var(--gutter); } /* 30px */
/* toute cellule a le même padding horizontal */
thead th, tbody td { padding-left: 14px; padding-right: 14px; }
/* colonne play (gauche) ET colonne avis (droite) = MÊME largeur fixe */
.c-play, .c-avis { width: 60px; }
.c-avis { text-align: right; }
.c-avis .ld { justify-content: flex-end; }
```

→ 1er élément (play) et dernier élément (avis) tombent à **`gutter + 14px`** de chaque bord, **identique** sur Catalog / Radar / Sets / Playlists. La clé : `.c-play` et `.c-avis` ont la **même largeur** et le même padding ; ne jamais coder la gouttière au cas par cas.

---

## 1. Artistes `/artists` — carte portrait

**Placement :** footer de la carte, à droite des stats, séparé par un trait.

```
[ CATALOG | IN LIB | LIKED ]  |  [♥] [♥/]
```

- `border-left: 1px solid var(--line)` avant le `.ld`, padding `0 12px`
- Sur carte : LikeDislike **toujours visible** (pas de hover-reveal)
- **Card liked** : `border-color: var(--pos)` + `box-shadow: 0 0 0 2px var(--pos-soft)`
- **Card disliked** : `opacity: 0.55` (`0.8` au hover)
- Tri **Liked** filtre sur `state === 'liked'`

---

## 2. Sets `/sets` & 3. Playlists `/playlists` — listes

**Placement :** colonne **Avis** en dernière position (`.c-avis`), remplace le bouton "Suivre / Ne plus suivre".

- Header `AVIS`, aligné à droite, style mono identique aux autres headers
- `opacity: 0` au repos → `opacity: 1` au `:hover tr` ET si état engagé :
  ```css
  .c-avis .ld-btn { opacity: 0; }
  tr:hover .c-avis .ld-btn { opacity: 1; }
  .c-avis .ld[data-state="liked"]    .ld-btn.like,
  .c-avis .ld[data-state="disliked"] .ld-btn.dislike { opacity: 1; }
  ```
- **Ligne liked** : `background: oklch(var(--pos-l) var(--pos-c) var(--pos-h) / .06)` (`.10` en dark)
- **Ligne disliked** : `opacity: .5` sur toutes les `td:not(.c-avis)` (`.72` au hover)
- **Sémantique :** like = suivre / crawl actif. Dislike = jamais proposé dans le Radar.
- Playlists : le badge **"Crawlé"** (statut technique) reste dans `Dernier crawl`, séparé de l'avis. Filtre **Suivies** = `state === 'liked'`.

---

## 4. Genres `/tags` — carte riche

**Placement :** overlay **haut-droite** de la zone image (`.gc-art`).

```css
.gc-acts { position: absolute; top: 10px; right: 10px; z-index: 3; opacity: 0; transition: opacity .16s; }
.gc-acts .ld-btn { background: oklch(0.995 0.004 92 / .92); backdrop-filter: blur(4px); border-color: oklch(0.2 0.02 70 / .1); }
/* dark */
[data-theme="dark"] .gc-acts .ld-btn { background: oklch(0.238 0.014 262 / .9); border-color: oklch(1 0 0 / .12); }
.genre-card:hover .gc-acts,
.genre-card.is-liked .gc-acts,
.genre-card.is-disliked .gc-acts { opacity: 1; }
```
- **Card liked** : `border-color: var(--pos)` + `box-shadow: 0 0 0 2px var(--pos-soft)`
- **Card disliked** : `opacity: 0.55`

---

## 5. Catalog `/catalog` — liste fusionnée (absorbe Radar)

> Maquette de référence : [`Catalog + Radar fusionnés (pilote).html`](./Catalog%20+%20Radar%20fusionn%C3%A9s%20(pilote).html)

**Décision produit (validée) : la page `/radar` est supprimée.** Catalog devient la page unique, avec un
segment **Catalog / Radar** dans l'en-tête qui bascule un jeu de colonnes. L'entrée « Radar » de la sidebar
pointe désormais vers `/catalog?view=radar` (ou route `/catalog` + query/state `view`).

### Inventaire des colonnes

| Groupe | Colonnes | Comportement |
|---|---|---|
| **Communes** | Play · Track · Style · BPM · Key · Radar(score) · Avis | Toujours visibles, **position figée** dans les 2 vues |
| **Catalog-only** | Durée · Rating · In&nbsp;lib | Masquées en vue Radar |
| **Radar-only** | Source · Détecté | Affichées seulement en vue Radar |

### Règle d'or anti-décalage (le point critique)

Les colonnes spécifiques vivent dans **une seule zone d'échange contiguë**, placée **entre Key et Radar**,
de **largeur totale identique (300px)** dans les deux vues :
- Catalog : Durée (86) + Rating (110) + In&nbsp;lib (104) = **300**
- Radar : Source (196) + Détecté (104) = **300**

Grâce à cette égalité, **la somme des largeurs fixes est identique (858px) dans les 2 vues** → la colonne
Track (auto) flexe à l'identique et **toutes les colonnes communes restent exactement à la même position
horizontale** d'une vue à l'autre. Seul **In&nbsp;lib** change de place vs l'ancien Catalog (passe avant Radar,
dans la zone d'échange) — compromis assumé pour la stabilité.

### Implémentation

- `table-layout: fixed`, largeurs portées par les `<th>` (pas de `<colgroup>` — plus fiable pour
  masquer/afficher : `display:none` sur un `th`/`td` retire proprement la colonne).
- Bascule : `display:none` / `table-cell` sur les classes `.col-source/.col-detect` (radar-only) et
  `.col-dur/.col-rating/.col-lib` (catalog-only), pilotées par `.app[data-mode="radar"]`.
- **Pas de masquage responsive par colonne** (il casserait l'égalité des largeurs). Sous ~1060px,
  la table **défile horizontalement** (`overflow-x:auto` + `min-width:1060px`).
- **Aucun saut vertical** : la barre de contexte sous l'en-tête (`.sub-bar`) est **toujours présente à
  hauteur fixe (46px)** dans les 2 vues. Catalog = **vide** (pas de phrase descriptive) ; Radar = filtre
  **Période** aligné à droite. ⚠️ Ne PAS ajouter de texte type « 6835 résultats · triés par Radar » — retiré.
- **Transition douce** : au switch, fondu de `#rows` (`opacity` .16s) ; bascule des colonnes au point bas
  du fondu (`setTimeout` ~150ms). Les colonnes communes ne bougeant pas, seule la zone d'échange
  se cross-dissolve.
- Filtres communs (`Pas dans RB`, `Radar ≥ 2`, `In lib`) conservés ; **Période (24h/7j/30j/Tout)**
  n'apparaît qu'en vue Radar (param backend `detected_after`). **Défaut = 24h.**
  ```js
  const recencyOptions = [
    { value: '24h', label: '24h' },
    { value: '7d',  label: '7j'  },
    { value: '30d', label: '30j' },
    { value: null,  label: 'Tout' },
  ]
  const recency = ref('24h')  // défaut
  // buildParams : hours = '24h'?24 : '7d'?168 : '30d'?720 : 0
  ```
- Colonne **Avis** = composant `LikeDislike` unifié (cf. §1).
- Tri par défaut : Catalog = `nb_radar_playlists` ↓ ; Radar = `detected_at` ↓.
- Mêmes règles de tint de ligne liked/disliked que Sets/Playlists.
- L'onglet de filtre "Liked" garde le **cœur** ; "Disliked" prend le **cœur barré** (cohérence bouton).

### Backend — DÉJÀ SUPPORTÉ (vérifié sur `server/api/routers/catalog.py`)

Ne rien redévelopper côté API — `GET /catalog/` gère déjà tout. Paramètres utiles côté front :

| Param | Rôle |
|---|---|
| `view=radar` | filtre les tracks ayant des apparitions Radar + ajoute les champs `detected_at`, `source_name`, `source_kind` à chaque item |
| `detected_after` (datetime) | filtre Période (7j/30j/Tout) — actif en vue radar |
| `sort` | `detected_at`, `nb_radar_playlists`, `rating`, `bpm`, `key`, `style`, `in_lib`, `avis`, `duration_ms` |
| `order` | `asc` / `desc` |
| `in_lib`, `min_radar_playlists`, `search`, `genre`, `avis` | filtres (chips + recherche) |

Champs renvoyés par item (`CatalogEntryOut`) : `bpm`, `key`, `style`, `rating`, `in_lib`,
`nb_radar_playlists` (= score Radar), `avis` (`liked`/`disliked`/null), et en vue radar
`detected_at` + `source_name` + `source_kind`.

**Source** = la playlist surveillée la plus récente : `source_name` = titre playlist,
`source_kind` = **plateforme** (`deezer`/`spotify`/`tidal`). → réutiliser le **badge source** existant
(DEEZER → `--accent-soft/--accent-ink` ; SPOTIFY → `--pos-soft/--pos-ink` ; TIDAL → `--surface-3`/`--line-2`),
**pas** un libellé SET/PLAYLIST.

**Avis** : `PATCH /catalog/{id}/avis` body `{avis: "liked"|"disliked"|null}` (ou `PATCH /opinions/`
avec `entity_type:"track"`). Côté serveur c'est déjà synchronisé vers `user_tracks.avis`,
`user_opinions` et `user_radar_state.status` (liked→added, disliked→ignored, null→new).

---

## 6. Ajustements détail — round 2 (constats VÉRIFIÉS dans le code source)

> Audit fait directement sur `server/frontend/src/` (master). Fichiers concernés indiqués.

1. **Gouttière incohérente ENTRE listes — confirmé.**
   - `CatalogView.vue` est **correct et symétrique** : `.table-wrap { padding: 4px 30px 30px }`,
     `td { padding: 0 14px }`, `.c-play { width: 44px; padding: 0 14px }` → bord gauche et bord droit
     tous deux à **30 + 14 = 44px**. ✅ **C'est la référence.**
   - `TrackTable.vue` (table partagée utilisée par d'autres vues) est **faux** :
     `.col-play { width: 38px; padding: 0 8px !important }` (8px ≠ 14px) et `.play-btn` fait **26px**
     (≠ 30px). → gouttière gauche 8px d'un côté, 14px de l'autre, **et** différente de Catalog.
   - **Action** : aligner `TrackTable.vue` sur Catalog → `.col-play { width: 44px; padding: 0 14px }`,
     play-btn **30px**, retirer le `!important`. Vérifier que **toutes** les listes (Sets, Playlists,
     Artist/Genre detail) tombent sur le même gabarit play/avis.

2. **Bug Source en mode Radar — confirmé (`CatalogView.vue`).**
   Le template fait `e.source_kind === 'set' ? 'SET' : 'PLAYLIST'` et choisit une icône set/playlist.
   Or l'API renvoie `source_kind` = **la plateforme** (`deezer` / `spotify` / `tidal`), jamais `'set'`.
   Résultat : affiche toujours « PLAYLIST », n'indique jamais la plateforme.
   **Action** : remplacer par le **badge source** existant (cf. CLAUDE.md) :
   `DEEZER` → `--accent-soft/--accent-ink`, `SPOTIFY` → `--pos-soft/--pos-ink`,
   `TIDAL` → `--surface-3` + `--line-2`. Le sous-label = `source_kind.toUpperCase()`.

3. **Boutons Avis — DÉJÀ CORRECTS, rien à faire.** `LikeDislike.vue` a bien le carré arrondi 30×30,
   `border: 1px solid var(--line-2)`, et le **cœur barré** (2e `<path d="M4.5 19.5 22 2"/>`). Mon retour
   précédent (chrome manquant / barre absente) était une **mauvaise lecture du screenshot** — la bordure
   fine est juste peu visible au zoom. ~~#3/#4 round 1~~ annulés.

4. **Dernières lignes masquées par le player — confirmé.** Aucune réserve de hauteur : la `PlayerBar`
   (fixe en bas) recouvre la dernière ligne. **Action** : padding-bas sur le conteneur de scroll **=
   hauteur de la PlayerBar quand un morceau est actif** (idéalement au niveau `App.vue` / layout, pour
   que ça profite à toutes les vues, pas seulement Catalog).

5. **Phrase d'en-tête à retirer (`CatalogView.vue`).** Supprimer le `<span class="sb-info">` du mode
   catalog (« {{ total }} résultats · triés par … »). Garder `.sub-bar` à `min-height: 46px` (vide en
   catalog) pour l'absence de saut vertical. En radar : ne garder que **Période** (retirer aussi la note
   « Mode Radar — pistes détectées… » pour cohérence).

6. **Tooltip Style (`StyleTag.vue` / `CatalogView.vue`).** `Techno (Peak T…` est clampé : ajouter
   `:title="name"` sur le StyleTag pour exposer la valeur complète au survol.

7. **En-têtes de colonnes rognés (`CatalogView.vue`).** Le haut des libellés (TRACK, STYLE…) est coupé :
   `thead th` a `font: 600 10.5px/1` (line-height 1) + `padding: 0 14px 12px` (0 en haut), et
   `.table-wrap` a `overflow-x: auto` → `overflow-y` calculé à `auto`, donc le conteneur **clippe**
   le haut des glyphes du header sticky. **Action** : `font: 600 10.5px/1.5` + `padding: 8px 14px 12px`
   (donner de l'air au-dessus du texte). — répercuté dans la maquette.

8. **Filtre Période — ajouter 24h par défaut (`CatalogView.vue`).** Voir le bloc `recencyOptions` au §5 :
   ajouter l'option `24h` (= `detected_after` à -24h) **en première position et active par défaut**.

> Note : les gouttières de `CatalogView.vue` étant déjà bonnes, **le vrai chantier gouttière est
> `TrackTable.vue` + l'harmonisation inter-listes**, pas Catalog.

---

## Checklist DA

- [ ] `--neg` / `--neg-soft` / `--neg-ink` ajoutés dans `diggy-tokens.css` (light + dark)
- [ ] `LikeDislike.vue` unique, réutilisé partout — zéro CSS dupliqué
- [ ] Icônes = cœur A (like) + cœur barré diagonale (dislike), 15px, stroke 1.8
- [ ] Boutons carrés arrondis `var(--r-sm)`, 30×30
- [ ] Gouttière listes : `.c-play` et `.c-avis` même largeur → équidistance vérifiée large → narrow
- [ ] Visibilité : repos masqué en liste / toujours visible sur carte artiste / hover sur carte genre
- [ ] États hover / liked / disliked + tint de ligne + état de carte vérifiés
- [ ] Mutuellement exclusifs + re-clic → null
- [ ] Transitions `.14s` / `.16s`
- [ ] Dark mode + densité (compact/regular/comfy) vérifiés
- [ ] **Fusion Catalog/Radar** : page `/radar` supprimée, segment Catalog/Radar, zone d'échange 300px égale, colonnes communes non décalées, pas de saut vertical, fondu au switch
- [ ] **Round 2 (vérifié code)** : `TrackTable.vue` aligné sur Catalog (play 44/14, btn 30) + harmonisation inter-listes ; bug Source `source_kind`=plateforme corrigé (badge DEEZER/SPOTIFY/TIDAL) ; padding-bas = hauteur PlayerBar ; phrase d'en-tête retirée ; tooltip Style. (Boutons Avis déjà OK.)
