# Playlists / watchlist (liste) — `/playlists`

Statut : ✅ figé  |  Vue : `views/WatchlistView.vue`

## 1. Ce qu'on a (actuel)

Liste des **playlists surveillées** (watchlist / sources radar).

**Données** : `GET /api/watchlist/browse` (**tous** les items, pas de pagination server-side). Item : id, title, external_id, source, has_artwork, owner, track_count, last_crawled_at, current_task_id. Statut crawl via `useTaskPoll` par playlist. Ajout via `POST /api/watchlist/` (parse URL Deezer/Tidal/Spotify). Crawl déclenchable par playlist.

**Structure** :
- **Header** : « Playlists » + count, SegFilter (Toutes / Liked / Disliked / À explorer), bouton **Ajouter** (URL).
- **Table** : Playlist (cover + titre + **SourceBadge texte** + `external_id`) · Créateur (owner) · Tracks (track_count) · **Dernier crawl** (date + bouton **Crawl** + chip statut **live**) · Avis. Sortable, row → détail, liked/disliked.
- **Pagination client-side** (page N/M, perPage 25) — sort/filtre client-side.

**Dette (même que Sets liste)** :
- Charge tout + sort/filtre/pagination **client-side** (≠ `usePaginatedList`).
- **Source en texte** (SourceBadge), pas logo.
- **Pas de genre**.
- `external_id` technique affiché (bruit).
- Manque la **valeur de veille** : combien de tracks **détectées** (on affiche `track_count` de la source, pas les détectées).

## 2. Vision (William)

- **Même schéma que Sets liste**, **pas fan, manque d'info**.
- **Claude propose** en s'inspirant de Sets liste (cohérence).

## 3. Revue de cohérence (Claude) — aligné sur Sets liste

**Analogues directs de Sets liste** :
- **Source → logo** (`<PlatformLink>`) au lieu du badge texte.
- **Genre dominant** (à **déduire** des tracks détectées dans la row). ⚠️ correction : `top_genres` **n'existe pas** côté back (contrairement à ce que je pensais) → c'est une déduction à **construire**, comme pour les sets.
- **Infinite scroll** (`usePaginatedList`) — pour la cohérence (NB : playlists **peu nombreuses ~56** → surtout cohérence, pas perf).

**Comble le « manque d'info »** :
- **Tracks détectées** (radar yield) : afficher les **détectées**, pas juste `track_count` source — c'est la vraie valeur d'une playlist surveillée.
- **Retirer `external_id`** sous le titre (bruit technique).
- *(option)* **Follow toggle** sur la row (comme Artistes) — une watched playlist peut être **suivie** (signal de priorité) → pastille-toggle cohérente.

**Pas d'exclusion « 0 % »** : contrairement aux sets (des milliers à 0 %), les playlists sont peu nombreuses et toutes utiles → on garde tout.

**Keep / Improve / Remove**
- ✅ **Garder** : cover, titre, créateur, **Dernier crawl** (+ statut live + bouton Crawl), avis, form Ajouter, tri.
- ➕ **Améliorer** : source → logo ; **+ genre dominant** ; **+ tracks détectées** ; infinite scroll ; *(option)* follow toggle.
- ➖ **Retirer** : `external_id` (bruit).

**Réponses (William)** : genre dominant ✅ · source en logo ✅ (standard `<PlatformLink>`) · infinite scroll ✅ · **tracks détectées ❌** (la détection doit être à ~100 %, sinon échec — rien à exposer) · **follow toggle ❌** (une playlist ajoutée est surveillée par défaut, pas de concept « suivre » à surfacer) · `external_id` retiré.

## 4. Ré-allocation des points retirés
- **`external_id`** → retiré (bruit technique).
- **Tracks détectées** → écarté (cible = 100 %, sinon échec ; ~100 % en pratique → inutile).
- **Follow toggle** → écarté (ajoutée = surveillée par défaut, pas de concept follow à surfacer).

## 5. Décisions figées
- **Row** : cover · titre + **Source (logo, `<PlatformLink>`)** · **Genre dominant (déduit, StyleTag)** · Créateur (owner) · Tracks (`track_count`) · **Dernier crawl** (date + statut **live** + bouton Crawl) · Avis.
- **Retirer** l'`external_id` sous le titre.
- **Infinite scroll** (`usePaginatedList`) + sort/filtre **server-side**.
- **Écarté** : tracks détectées, follow toggle.
- **(recap C3)** : **pastille cadence** (Quotidien / Hebdo / Mensuel) sur la row, dérivée de `last_changed_at` (pilote déjà C6.e) → distingue les sources **vivantes** des **dormantes**. Donnée underlying : « dernière nouveauté » (last_changed_at relatif), affichable en tooltip.
- **Gardé** : form **Ajouter** (URL), tri, statut crawl **live** + bouton Crawl, avis, row → détail.
- **Pas d'exclusion** (playlists peu nombreuses).

## 6. Sortie next-step
**Handoff Design**
- [ ] Row playlist : **+ genre (StyleTag)** + **source (logo)**, **retrait `external_id`** ; layout + responsive.

**Chantier work_manager**
- **Back** : `/api/watchlist/browse` (ou endpoint paginé) — **pagination + sort server-side** ; **construire** le **genre dominant** (déduction depuis les tracks détectées ; `top_genres` n'existe pas encore côté back — même travail que le détail « Dans cette playlist » à câbler) ; renvoyer **`last_changed_at`** (déjà stocké C6.e) pour la **pastille cadence** (C3).
- **Front** : `WatchlistView` → **`usePaginatedList`** ; row + genre + source logo ; retrait `external_id` ; garder crawl **live** (`useTaskPoll`) + form Ajouter. Filtres opinion à gérer comme la liste Artistes.
- **Transverse** : `<PlatformLink>`.

**Dépend de** : `<PlatformLink>` (transverse).

> **Résolu (validé)** : le concept « suivre une playlist » est **masqué de l'UI** (liste + détail) — ajoutée = surveillée par défaut ; mécanisme back `user_follows`/priorité **conservé** (sans effet tant que la watchlist reste sous le cap de 200).
