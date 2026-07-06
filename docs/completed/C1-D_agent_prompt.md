# C1.d — Vue Collections (frontend CRUD)

Tu dois creer la vue frontend pour les collections personnalisees. L'API backend est deja 100% live (6 endpoints).

Lis `CLAUDE.md` a la racine pour les conventions du projet.

---

## Contexte

### API existante (`server/api/routers/collections.py`)

| Methode | Route | Action |
|---------|-------|--------|
| `GET` | `/api/collections/` | Lister les collections (avec item_count) |
| `POST` | `/api/collections/` | Creer une collection (name, type) |
| `GET` | `/api/collections/{id}` | Detail (avec tracklist enrichie) |
| `POST` | `/api/collections/{id}/items` | Ajouter un track (catalog_id) |
| `DELETE` | `/api/collections/{id}/items/{catalog_id}` | Retirer un track |
| `DELETE` | `/api/collections/{id}` | Supprimer la collection |

Toutes les routes sont authentifiees et scopees par user (un user ne voit que ses collections).

### Schemas reponse

```python
# CollectionOut
{ id, name, type, created_at, item_count }

# CollectionDetailOut (extends CollectionOut)
{ ..., items: [{ catalog_id, position, added_at, title, artist, bpm, key, duration_ms, has_artwork, has_preview }] }
```

### Modeles DB

- `user_collections` : id, user_id, name, type, created_at
- `collection_items` : collection_id (PK), catalog_id (PK), position, added_at

---

## Tache 1 : Creer CollectionsView.vue

**Fichier** : `server/frontend/src/views/CollectionsView.vue` (nouveau)

### Layout

Suivre le pattern des vues existantes (page-head + contenu). Structure :

```html
<div class="collections-view">
  <header class="page-head">
    <div class="titles">
      <h1>Collections</h1>
      <div class="sub">{{ total }} collection{{ total > 1 ? 's' : '' }}</div>
    </div>
    <div class="head-tools">
      <button class="chip chip--create" @click="showCreateModal = true">
        <svg><!-- icone + --></svg>
        Nouvelle collection
      </button>
    </div>
  </header>

  <!-- liste des collections -->
  <div class="coll-grid">
    <div v-for="coll in collections" :key="coll.id" class="coll-card" @click="goToDetail(coll.id)">
      <!-- nom, item_count, date -->
    </div>
  </div>

  <!-- empty state -->
  <div v-if="!collections.length && !loading" class="state">
    Aucune collection — crée ta première playlist
  </div>
</div>
```

### Logique

- `onMounted` : fetch `GET /api/collections/`
- Bouton "Nouvelle collection" : ouvre une modale simple (input nom + bouton creer)
- Click sur une carte → `router.push('/collections/' + id)`
- Supprimer une collection : bouton avec confirmation

### Style des cartes collection

```css
.coll-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 14px;
  padding: 16px 30px 30px;
}
.coll-card {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--r-md);
  padding: 18px;
  cursor: pointer;
  transition: background 0.12s;
}
.coll-card:hover { background: var(--surface-2); }
```

Responsive mobile : `padding: 16px var(--page-px-mobile)` sous 640px.

---

## Tache 2 : Creer CollectionDetailView.vue

**Fichier** : `server/frontend/src/views/CollectionDetailView.vue` (nouveau)

### Layout

```html
<div class="collection-detail">
  <header class="page-head">
    <div class="titles">
      <h1>{{ collection.name }}</h1>
      <div class="sub">{{ collection.item_count }} track{{ collection.item_count > 1 ? 's' : '' }}</div>
    </div>
    <div class="head-tools">
      <button class="chip" @click="confirmDelete">Supprimer</button>
    </div>
  </header>

  <!-- tracklist -->
  <div class="table-wrap">
    <table class="dt">
      <!-- colonnes : Play, Track (cover+titre+artiste), BPM, Key, Duration, Retirer -->
    </table>
  </div>
</div>
```

### Logique

- `onMounted` : fetch `GET /api/collections/{id}`
- Tracklist : reutiliser les styles de `table.dt` (meme pattern que CatalogView)
- Bouton "Retirer" par track : `DELETE /api/collections/{id}/items/{catalog_id}` + refresh
- Bouton "Supprimer collection" : `DELETE /api/collections/{id}` + redirect vers `/collections`
- Play preview : utiliser le store `audioPlayer`

### Colonnes table

Reutiliser les classes existantes de `table.css` : `.td-track`, `.aw`, `.tt-title`, `.tt-art`, `.td-bpm`, `.td-key`.

Responsive mobile : memes breakpoints que CatalogView (colonnes BPM et Duration masquees).

---

## Tache 3 : Ajouter les routes

**Fichier** : `server/frontend/src/router/index.js` (ou equivalent)

```javascript
{
  path: '/collections',
  name: 'Collections',
  component: () => import('../views/CollectionsView.vue'),
},
{
  path: '/collections/:id',
  name: 'CollectionDetail',
  component: () => import('../views/CollectionDetailView.vue'),
},
```

---

## Tache 4 : Bouton "Ajouter a une collection" sur TrackDetailView

**Fichier** : `server/frontend/src/views/TrackDetailView.vue`

Ajouter un bouton d'action sur la page detail d'une track :

```html
<button class="btn btn--ghost" @click="showAddToCollection = true">
  <svg><!-- icone collection --></svg>
  Ajouter a une collection
</button>
```

Au click : ouvre un mini-dropdown/modale listant les collections de l'utilisateur (fetch `GET /api/collections/`). Click sur une collection → `POST /api/collections/{id}/items` avec le `catalog_id`.

---

## Tache 5 : Acces depuis la navigation

Les collections ne sont PAS dans la BottomNav (trop d'items). Ajouter un lien dans la **sidebar desktop** (`SidebarNav.vue`), dans la section Library, apres "Genres" :

```javascript
{ to: '/collections', label: 'Collections', icon: iconCollection, count: null },
```

Icone suggestion : dossier ou liste avec coeur.

Sur mobile : accessible via le Hub ou un lien dans le profil.

---

## Points d'attention

- **Auth obligatoire** : toutes les routes collections necessitent un token. Verifier que le router guard redirige vers `/login` si non connecte.
- **Modale creation** : reutiliser le pattern modal existant (overlay + box). Style identique a `ImportRekordboxModal` mais plus simple (juste un input + 2 boutons).
- **Empty state** : quand la collection est vide, afficher un message encourageant ("Ajoute des tracks depuis le catalog").
- **Responsive** : grille `minmax(240px, 1fr)` → 1 colonne sous 500px. Table detail → memes breakpoints que Catalog.
- **Zero couleur hardcodee**
- **Pas de Tailwind** — tout en CSS scoped avec tokens

---

## Definition of Done

```bash
# /collections : liste les collections avec item_count
# Bouton "Nouvelle collection" → cree via API → apparait dans la liste
# Click sur une collection → /collections/{id} avec tracklist
# Bouton "Retirer" par track → supprime via API
# Bouton "Supprimer collection" → supprime + redirect
# TrackDetailView : bouton "Ajouter a une collection" fonctionnel
# SidebarNav : lien Collections dans la section Library
# Mobile : responsive, pas de debordement
# Lint :
cd server/frontend && npm run lint
```

## Commit

```
feat(frontend): add CollectionsView + CollectionDetailView CRUD (C1.d)
```

Ne pousse PAS sur master — je review avant.
