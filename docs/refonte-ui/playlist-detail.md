# Détail playlist — `/playlists/:id`

Statut : ✅ figé  |  Vue : `views/PlaylistDetailView.vue`

## 1. Ce qu'on a (actuel)

C'est le détail d'une **playlist surveillée** (watchlist / radar) — un **objet de veille** : on la suit, on la crawle, on affiche les tracks **détectées**.

**Données** : `GET /api/watchlist/{id}` : id, external_id, source, title, description, owner, has_artwork, track_count, **tracks[]** (détectées : catalog_id, title, artist(s), bpm, key, duration_ms, has_artwork, has_preview, in_lib), followed, last_crawled_at, created_at, current_task_id, **top_artists[]**, **top_genres[]** (avec %). Statut crawl : poll `/api/watchlist/{id}/crawl-status` (`useTaskPoll`). Follow : POST/DELETE. Fetch artwork Deezer.

**Structure actuelle** :
1. **PageHero (square)** : artwork, titre, sous-titre (owner), **SourceBadge**, actions : **« Voir sur {source} ↗ »** + **Suivre / Ne plus suivre**.
2. **Bannière crawl** (running / queued) — poll live.
3. **StatStrip** : Tracks (track_count source) · **Tracks radar** (détectées) · Dernier crawl · Ajoutée le.
4. **Description** (si présent).
5. **« Dans cette playlist »** : top artistes (avatars → `/artist`) + **genres dominants** (barres teintées + %). ⚠️ **actuellement MORT** — le front rend `top_artists`/`top_genres` mais l'API ne les renvoie **jamais** (vérifié : absents du back).
6. **Tracks** : mini-table cover · Track (titre + artiste) · BPM · Key · Durée · Lib · play preview.
7. **AdminCard** : « Fetch artwork Deezer » (si pas d'artwork & source deezer) — **pas gardé `is_admin`**.

**Note** : « Tracks » = total dans la source ; « Tracks radar » = ce qu'on a détecté/catalogué. La liste n'affiche que les tracks **détectées**.

**Dette** : table tracks bespoke (≠ Explorer) · colonne LibDot (→ `<Artwork>` in-lib) · bouton « Voir sur » en **texte** (→ `<PlatformLink>` logo) · Admin fetch-artwork non gardé (`is_admin`).

## 2. Vision (William)

- Appliquer le **même raisonnement que les autres pages détail** (set / artiste / genre) : cohérence, hero immersif, enrichissement sobre, composants partagés → **Claude propose**.
- (Collection detail traitée **à la toute fin** — vraie feature complète à designer.)

## 3. Proposition (Claude)

**Structure proposée** :
1. **Hero « cover + infos à côté »** — la cover est **un seul carré** (pas une bande) → on l'**agrandit un peu** et on met les infos **à côté** (pas en overlay) : titre + **source (logo)** + owner + stats (Tracks · Dernier crawl). Actions : **lien source en logo** (`<PlatformLink>`). **Bannière crawl live** conservée (sous le hero). *(Bouton « Suivre » retiré — cf. §5.)*
2. **« Dans cette playlist »** — top artistes + **genres dominants** (barres %) : gardé, c'est le bloc vivant (déjà mieux que les sets — les genres/top-artistes sont **déjà calculés** ici).
3. **Tracks (détectées)** — rangées alignées **Explorer** (cover + in-lib, titre, artiste, BPM, Key, durée, play), **sobre**, composant partagé + `<Artwork>`. Libellé clair : ce sont les tracks **détectées**.
4. **Admin** (fetch artwork) → **tout en bas**, réservé `is_admin`.

*(Écarté : « Playlists similaires » — trop peu de playlists surveillées pour que ce soit pertinent.)*

**Keep / Improve / Remove**
- ✅ **Garder** : hero, follow, **bannière crawl live**, « Dans cette playlist », stats, description (si présent).
- ➕ **Améliorer** : hero immersif ; tracks → composant Explorer partagé + `<Artwork>` in-lib ; bouton source → `<PlatformLink>` (logo).
- ➖ **Retirer / gate** : Admin → `is_admin`. (Rien de mort ici.)

## 4. Ré-allocation des points retirés
- **Admin** → tout en bas, restreint `is_admin`.
- **Bouton source** → `<PlatformLink>` (logo) → transverse.
- **« Playlists similaires »** → écarté (trop peu de playlists).
- Rien de mort à retirer, rien à déplacer.

## 5. Décisions figées
- **Hero « cover + infos à côté »** : cover (1 carré) **un peu agrandie**, infos **à côté** (pas en overlay) : titre + **source (logo)** + owner + stats **Tracks · Dernier crawl**. Actions : **lien source logo** (`<PlatformLink>`). **Bannière crawl live** conservée.
- **Pas de bouton « Suivre »** : concept follow-playlist **masqué de l'UI** (une playlist ajoutée est surveillée par défaut). Le mécanisme back `user_follows`/priorité est **conservé** (sans effet tant que la watchlist reste sous le cap de 200 — re-surfaçable plus tard).
- **Stat « Tracks radar » retirée** : c'est la même notion que les « tracks détectées » écartées sur la liste (la détection doit être ~100 %). On garde **Tracks · Dernier crawl** (+ owner).
- **« Dans cette playlist »** (top artistes + genres dominants %) : **gardé — mais à CÂBLER**. L'API ne renvoie **pas** `top_artists`/`top_genres` (bloc mort aujourd'hui) → le back doit les **calculer depuis les tracks détectées**.
- **Tracks (détectées)** : rangées = **Explorer** (cover + in-lib, titre, artiste, BPM, Key, durée, play), **comme Catalog**, composant partagé + `<Artwork>`. ⚠️ **`in_lib` des tracks n'est pas renvoyé** aujourd'hui (LibDot toujours false) → le back doit le renvoyer pour l'indicateur in-lib. Idem `artists[]` (chaîne plate → liens morts) → renvoyer des artistes structurés.
- **Admin** (fetch artwork) : **tout en bas**, `is_admin`.
- **Playlists similaires** : **écarté**.

## 6. Sortie next-step
**Handoff Design**
- [ ] Hero « cover + infos à côté » (cover agrandie, infos latérales, source logo).
- [ ] Tracks = rangées Explorer + `<Artwork>` in-lib.
- [ ] `<PlatformLink>` (logo) — transverse.

**Chantier work_manager**
- **Front** : hero cover+infos ; tracks → composant Explorer partagé + `<Artwork>` ; source → `<PlatformLink>` ; Admin en bas + `is_admin` ; garder la **bannière crawl** (`useTaskPoll`).
- **Back** : rien de neuf (endpoint watchlist déjà complet).
- **Transverse** : composant rangée Explorer / `<TrackCard>`, `<Artwork>`, `<PlatformLink>`.

**Dépend de** : composants partagés (Explorer, `<PlatformLink>`).
