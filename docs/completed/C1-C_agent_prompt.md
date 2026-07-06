# C1.c — Surface produit "Decouvrir" (frontend)

Tu dois creer la surface produit pour les tendances radar : shelves trend sur le Hub, endpoint top trends, badge trend.

Lis `CLAUDE.md` a la racine pour les conventions du projet.

---

## Contexte

C1.a+b a ete implemente : `compute_trends` calcule desormais un score pondere avec rang par famille de genre. L'API expose :

- `GET /api/radar/trends?family=House&limit=20` → top tracks par famille
- `GET /api/radar/full` inclut `trend_rank`, `trend_family`, `trend_rank_family`, `velocity`, `source_count`

Le modele `RadarTrend` a les colonnes : `trend_score`, `family`, `rank_in_family`, `rank_global`, `velocity`, `source_count`, `detection_count`, `computed_at`.

Les familles de genre existantes : House, Techno, Trance, D&B, Hardcore, Hard Dance, Autre.

---

## Tache 1 : Shelves trend sur le HubView

**Fichier** : `server/frontend/src/views/HubView.vue`

Le Hub a actuellement : search bar + genres populaires + suggestions. Pas de shelves trend.

### Ce qu'il faut ajouter

Sous la search bar et les extras (quand l'utilisateur est connecte et que la recherche est vide), ajouter une section **"Ca sort en ce moment"** avec des shelves par famille de genre.

Structure :

```html
<div v-if="auth.isAuthenticated && isEmpty" class="discover">
  <h2 class="discover-title">Ca sort en ce moment</h2>
  <FamilyChips v-model="trendFamily" :families="families" show-all />
  <div class="trend-shelf">
    <div v-for="track in trendTracks" :key="track.catalog_id" class="trend-card">
      <!-- artwork -->
      <!-- titre + artiste -->
      <!-- rang badge -->
      <!-- bouton play -->
    </div>
  </div>
</div>
```

### Logique

- Au mount, fetcher `GET /api/radar/trends?limit=20` (global)
- Quand `trendFamily` change, fetcher `GET /api/radar/trends?family=X&limit=20`
- Utiliser le composant `FamilyChips` existant pour filtrer par famille
- Afficher les tracks sous forme de cartes horizontales scrollables (shelf pattern, comme GenreDetailView)

### Style des trend cards

Chaque carte :
- Artwork 80x80px (cover catalog), coins `--r-sm`
- Titre (font-ui 14px 500, `--ink`, ellipsis) + artiste (12px, `--ink-3`, ellipsis)
- Badge rang : `#1`, `#2`, etc. — pastille `--accent-soft` / `--accent-ink`, mono 11px
- Bouton play au hover/tap (overlay sur l'artwork)
- `min-width: 200px; flex: none` dans un container scroll horizontal

### Shelf scroll

```css
.trend-shelf {
  display: flex;
  gap: 14px;
  overflow-x: auto;
  scrollbar-width: none;
  padding: 0 var(--page-px) 16px;
  -webkit-overflow-scrolling: touch;
}
.trend-shelf::-webkit-scrollbar { display: none; }
```

Sur mobile (< 640px) : `padding: 0 var(--page-px-mobile) 16px`.

---

## Tache 2 : Badge trend sur les cartes tracks (CatalogView)

**Fichier** : `server/frontend/src/views/CatalogView.vue`

Dans la table Catalog, quand une track a un `trend_rank` (expose par `/api/radar/full`), afficher un petit badge a cote du titre.

### Affichage conditionnel

Si `e.trend_rank` existe et est <= 50 (top 50 global) :

```html
<span v-if="e.trend_rank && e.trend_rank <= 50" class="trend-badge">
  #{{ e.trend_rank }}
</span>
```

Placer ce badge dans la cellule Track, apres le titre.

### Style

```css
.trend-badge {
  display: inline-flex;
  align-items: center;
  padding: 1px 6px;
  border-radius: var(--r-xs);
  background: var(--accent-soft);
  color: var(--accent-ink);
  font: 600 10px/1 var(--font-mono);
  margin-left: 8px;
  flex: none;
}
```

---

## Tache 3 : Lien "Decouvrir" dans la navigation

Le Hub sert deja de page "Decouvrir" avec les shelves trend. Pas besoin d'une vue separee.

Cependant, verifier que le Hub est la destination par defaut quand on est connecte (route `/`). C'est deja le cas.

---

## Points d'attention

- **Zero couleur hardcodee** — tout via `var(--...)`
- **Responsive** : les shelves doivent scroller horizontalement sur mobile (pattern deja utilise dans GenreDetailView)
- **Play preview** : utiliser le store `audioPlayer` existant pour lancer les previews Deezer 30s
- **FamilyChips** : composant existant dans `server/frontend/src/components/FamilyChips.vue` — le reutiliser
- **Artwork URL** : `/storage/catalog-artworks/{catalog_id}.jpg` (si `has_artwork`)
- **Token `--page-px`** / `--page-px-mobile` pour les paddings

---

## Definition of Done

```bash
# Hub (connecte, recherche vide) :
# - Section "Ca sort en ce moment" visible
# - FamilyChips pour filtrer par famille
# - Shelf horizontale avec cartes trend (artwork + titre + rang)
# - Click sur une carte → navigate vers /catalog/{id}
# - Play button → preview Deezer
#
# CatalogView :
# - Badge #N visible a cote du titre pour les tracks top 50
#
# Mobile (375px) :
# - Shelf scrollable horizontalement
# - Badge trend lisible
#
# Lint :
cd server/frontend && npm run lint
```

## Commit

```
feat(frontend): discover shelves + trend badges on Hub and Catalog (C1.c)
```

Ne pousse PAS sur master — je review avant.
