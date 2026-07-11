# FIX — Genre Detail : images des playlists manquantes

> Diagnostic à partir du code réel (`genres.py`, `watchlist.py`, `models.py`, `GenreDetailView.vue`).
> Ce n'est **pas** un bug de layout : les covers de playlists **n'existent nulle part** dans le système (≠ sets/artistes qui ont un sync d'artwork).

## Cause

1. `watchlist.py › _fetch_deezer_playlist()` ne capture que `title / track_count / owner` — **jamais l'image**. À l'ajout, `WatchedEntity.has_artwork` est forcé à `False`.
2. Aucun job ne produit de fichier `playlist-artworks` (MinIO). Donc rien à servir sur `/storage/playlist-artworks/{id}.jpg`.
3. `genres.py › get_genre_playlists()` renvoie `hasArtwork` (toujours `false`) et **aucune URL d'image**.
4. `GenreDetailView.vue` — la `<ShelfCard>` des playlists n'a **pas** de `fallback-letter` (les sets si) → placeholder totalement vide.

## Fix 1 — dégradé propre tout de suite (front, 1 ligne)

`views/GenreDetailView.vue`, shelf Playlists : ajouter le fallback lettre (comme les sets).

```vue
<ShelfCard
  v-for="p in playlists"
  :key="p.id"
  :image-src="p.image || null"
  :title="p.title"
  :subtitle="`${p.genreTrackCount} tracks`"
  :fallback-letter="(p.title || '?')[0]"
>
  <template #badge>
    <span class="source-badge" :class="p.source">{{ p.source }}</span>
  </template>
</ShelfCard>
```

→ Les playlists sans cover affichent une tuile-lettre (cohérent avec les sets), plus de boîte vide. `:image-src="p.image"` est prêt pour le Fix 2.

## Fix 2 — vraies covers (backend) — **recommandé : URL distante, pas de MinIO**

Les playlists Deezer exposent leur cover dans l'API (`/playlist/{id}` → `picture_xl` / `picture_big`). URLs hotlinkables → inutile de les rapatrier dans MinIO. Stocke l'URL et sers-la.

1. **Modèle** (`models.py`) : ajouter `WatchedEntity.artwork_url = Column(Text, nullable=True)` + migration Alembic.
2. **Fetch** (`watchlist.py › _fetch_deezer_playlist`) : récupérer aussi l'image →
   ```python
   "artwork_url": data.get("picture_xl") or data.get("picture_big") or data.get("picture_medium"),
   ```
   et la passer à la création du `WatchedEntity` (au lieu de `has_artwork=False`, set `artwork_url=meta.get("artwork_url")`).
3. **Crawl/backfill** (`workers/.../tasks.py › crawl_single_playlist`) : remplir `artwork_url` pour les playlists déjà en base (sinon seules les nouvelles auront une image). Idéalement aussi pour Spotify/Tidal quand ces sources sont crawlées (même champ).
4. **Endpoint** (`genres.py › get_genre_playlists`) : ajouter `we.artwork_url` au SELECT et renvoyer `"image": r.artwork_url` dans l'item.
5. **Front** : déjà couvert par Fix 1 (`:image-src="p.image"`).

> Alternative cohérente sets/artistes : rapatrier l'image dans MinIO sous `playlist-artworks/{id}.jpg` + flag `has_artwork`, et servir `/storage/playlist-artworks/{id}.jpg`. Plus lourd (download + stockage) ; l'URL distante suffit pour Deezer.

## Ordre conseillé
Fix 1 maintenant (cosmétique immédiat) → Fix 2 ensuite (vraies images, nécessite migration + backfill crawl). Les deux sont indépendants.
