# PROMPT Claude Code — Max-width global + correctifs DA (audit #1)

> Lire `design/CLAUDE.md` avant tout. Respecter les conventions (zéro valeur hors-tokens, container queries, `var(--…)` uniquement).

---

## Contexte

Sur grand écran (≥ 1440 px), le contenu Diggy s'étire sur toute la largeur disponible dans `.app-main`.
Résultat : tableaux aux colonnes trop larges, headers qui s'écartent, grilles avec trop de colonnes.
Un `GenreDetailView` a déjà `max-width: 1080px` en dur — il faut généraliser et tokeniser.

---

## 1. Ajouter 2 tokens dans `diggy-tokens.css`

Ajouter dans la section `/* Layout */` (ou en créer une si absente) :

```css
/* ── Layout constraints ── */
--page-max-w:   1400px;   /* listes / tables / grilles (catalog, radar, sets…) */
--detail-max-w: 1080px;   /* pages détail (genre, artiste, track, set, playlist) */
```

---

## 2. Pages liste — appliquer le max-width sur le root

Pour chacune des vues ci-dessous, ajouter sur la classe root scoped :

```css
.xxx-view {
  /* existant */
  min-width: 0;
  display: flex;
  flex-direction: column;

  /* AJOUTER : */
  max-width: var(--page-max-w);
  margin-inline: auto;
  width: 100%;
}
```

Vues concernées (fichier → classe root) :

| Vue | Classe root |
|---|---|
| `CatalogView.vue` | `.catalog-view` |
| `RadarView.vue` | `.radar-view` |
| `ArtistsView.vue` | `.artists-view` |
| `GenresView.vue` | `.genres-view` |
| `SetsView.vue` | root à identifier (même pattern) |
| `WatchlistView.vue` | root à identifier |

> **Ne pas toucher aux paddings internes.** Chaque section (`.page-head`, `.table-wrap`, `.artist-grid`, `.fam-chips`…) garde ses propres `padding: 26px 30px`. Seul le root reçoit le max-width + margin-inline.

> **AdminView.vue** → laisser pleine largeur, pas de max-width.

---

## 3. Pages détail — tokeniser les max-width existants

### `GenreDetailView.vue`
```css
/* AVANT */
.detail-view {
  max-width: 1080px;
  margin-inline: auto;
  padding: 26px 30px 56px;
}

/* APRÈS */
.detail-view {
  max-width: var(--detail-max-w);
  margin-inline: auto;
  padding: 26px 30px 56px;
}
```

### `ArtistDetailView.vue`
```css
/* AVANT */
.detail-view {
  padding: var(--pad) calc(var(--pad) * 1.5);
  max-width: 900px;
  margin: 0 auto;
}

/* APRÈS */
.detail-view {
  padding: var(--pad) calc(var(--pad) * 1.5);
  max-width: var(--detail-max-w);
  margin-inline: auto;
}
```

> Note : 900 px était trop étroit pour les tableaux de tracks et le bloc admin. `--detail-max-w` (1080 px) est plus adapté.

### `TrackDetailView.vue`, `SetDetailView.vue`, `PlaylistDetailView.vue`
Même opération : repérer la classe root, ajouter/remplacer par :
```css
max-width: var(--detail-max-w);
margin-inline: auto;
```

---

## 4. Correctif DA — bloc admin dans `ArtistDetailView.vue`

Le bloc admin utilise `var(--warn-ink, #e67e22)` comme couleur d'accent, ce qui est hors-DA.
La décision **D2** impose : `surface-2` + bordure tiretée `--line-2` + label `--ink-3`.

### `.admin-card` — remplacer :
```css
/* AVANT */
.admin-card {
  border: 1px solid var(--warn-ink, #e67e22);
  background: var(--surface);
  …
}

/* APRÈS */
.admin-card {
  border: 1px dashed var(--line-2);
  background: var(--surface-2);
  border-radius: var(--r-md);
  …
}
```

### `.admin-label` dans `.admin-card` — remplacer :
```css
/* AVANT */
.admin-label {
  color: var(--warn-ink, #e67e22);
}

/* APRÈS */
.admin-label {
  color: var(--ink-3);
}
```

### `.admin-msg` — virer les fallbacks hex :
```css
/* AVANT */
.admin-msg.ok  { color: var(--pos-ink, #27ae60); background: var(--pos-soft, #d4edda); }
.admin-msg.err { color: var(--neg-ink, #c0392b); background: var(--neg-soft, #fde);    }

/* APRÈS */
.admin-msg.ok  { color: var(--pos-ink); background: var(--pos-soft); }
.admin-msg.err { color: var(--neg-ink); background: var(--neg-soft); }
```

---

## 5. Container queries — pas d'impact attendu

Les container queries des vues (`@container (max-width: N)`) s'appliquent sur `.app-main`
(qui porte `container: app / inline-size`). Le max-width sur les vues n'affecte pas la
valeur mesurée par ces queries — elles continuent de réagir à la largeur réelle de `.app-main`.

Vérifier visuellement que les breakpoints responsifs restent cohérents après la mise en place.

---

## 6. Checklist de validation

- [ ] Sur viewport 1920 px : le contenu est centré avec des marges latérales visibles dans chaque vue liste
- [ ] Sur viewport 1440 px : idem, marges plus réduites
- [ ] Sur viewport 1280 px : peu ou pas de marge (contenu ≈ pleine largeur)
- [ ] Sidebar collapse (≤ 900 px) : comportement normal, aucune régression
- [ ] Grille artistes et genres : toujours `auto-fill` correctement contraint
- [ ] Sticky header de tableau (`position: sticky; top: 0`) : toujours fonctionnel
- [ ] Dark mode : aucune régression visuelle
- [ ] `AdminView.vue` : toujours pleine largeur (ne pas y toucher)
- [ ] Zéro valeur hors-tokens dans les fichiers modifiés

---

## Résumé des fichiers à modifier

| Fichier | Action |
|---|---|
| `src/styles/diggy-tokens.css` | Ajouter `--page-max-w` + `--detail-max-w` |
| `src/views/CatalogView.vue` | Max-width root |
| `src/views/RadarView.vue` | Max-width root |
| `src/views/ArtistsView.vue` | Max-width root |
| `src/views/GenresView.vue` | Max-width root |
| `src/views/SetsView.vue` | Max-width root |
| `src/views/WatchlistView.vue` | Max-width root |
| `src/views/GenreDetailView.vue` | Tokeniser `1080px` → `var(--detail-max-w)` |
| `src/views/ArtistDetailView.vue` | Tokeniser `900px` → `var(--detail-max-w)` + fix bloc admin (D2) |
| `src/views/TrackDetailView.vue` | Max-width root (tokenisé) |
| `src/views/SetDetailView.vue` | Max-width root (tokenisé) |
| `src/views/PlaylistDetailView.vue` | Max-width root (tokenisé) |
