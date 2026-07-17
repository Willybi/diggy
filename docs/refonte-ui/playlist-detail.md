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

**Dette** : table tracks bespoke (≠ Explorer) · colonne LibDot (→ `<Artwork>` in-lib) · bouton « Voir sur » en **texte** (→ `<PlatformLink>` logo) · ~~Admin fetch-artwork non gardé (`is_admin`)~~ — **OBSOLÈTE** (vérifié 2026-07-17) : le gate `is_admin` est intégré à `AdminCard.vue` depuis le chantier Track Detail, et l'endpoint back est `require_admin`. Reste seulement à **déplacer** la card en bas de page.

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

## 5bis. Décisions des rounds Design (handoff reçu 2026-07-17)

Handoff versionné dans `docs/refonte-ui/handoff-playlist-detail/` (BRIEF page + BRIEF extension TrackCard + pilote). Évolutions actées pendant les rounds William × Claude Design — complètent les décisions figées §5 :

- **StatStrip supprimée** : stats **Tracks · Dernier crawl** intégrées au hero en data-row mono (même patron que Track Detail) ; « Ajoutée le » retiré.
- **Lien source** : `<PlatformLink>` 38 px + micro-label `SOURCE` + nom de plateforme en texte — unique action du hero.
- **« Dans cette playlist »** : une seule carte 2 colonnes (top **6** artistes | top **5** genres), avatars fallback initiales, barres % via la mécanique piliers existante.
- **Titre absent → `external_id` en mono** ; owner masqué si absent ou redondant avec la source.
- **État vide « jamais crawlée »** : carte engageante (« La playlist est surveillée — les tracks apparaîtront après le premier crawl »), bannière crawl possiblement active au-dessus.
- **Durée = 5ᵉ colonne du TrackCard étendu** (grille `36px 1fr 42px 30px 44px [auto]`), masquée < 640 px ; artistes cliquables avec `stopPropagation` et fallback chaîne plate.

## 6. Sortie next-step

> **Arbitrages pré-vol 2026-07-17 (William)** — corrige la version antérieure de ce § qui affirmait « Back : rien de neuf » (contradictoire avec §5, invalidé par vérification code) :
> 1. **Lot 0 back = câblage complet** : `top_artists[]` (id/name/has_artwork/count, calculés depuis les tracks détectées, `catalog_visible` appliqué), `top_genres[]` (name/pillar/depth/pct, pattern `artist_service._artist_genres`), `in_lib` par track (EXISTS `user_tracks` du viewer), `artists[]` peuplés (bulk-load `catalog_artists`, le champ schéma existe déjà mais n'est jamais rempli) + fix du champ `genre` mort (le service sélectionne `genres` TEXT[], le schéma attend `genre` str → toujours None).
> 2. **Rangées tracks = évolution transverse ADDITIVE de `<TrackCard>`** (props optionnelles : durée, `artists[]` cliquables) spécifiée par Claude Design, implémentée en lot dédié avec tests + vitrine DS — zéro changement de comportement pour les consommateurs existants (TrackDetailView).

**Handoff Design**
- [ ] Hero « cover + infos à côté » (cover agrandie, infos latérales, source logo).
- [ ] Tracks = rangées `<TrackCard>` étendu (durée + artistes cliquables, spec transverse) + `<Artwork>` in-lib.
- [ ] `<PlatformLink>` (logo) — existe (variants button/glyph), rien à créer.

**Chantier work_manager**
- **Lot 0 back** : contrat `GET /api/watchlist/{id}` — cf. arbitrage ci-dessus.
- **Lot 1 transverse** : extension additive `<TrackCard>` (durée + artistes cliquables optionnels) + tests Vitest + vitrine DesignSystemView.
- **Lot 2 front** : hero cover+infos ; tracks → `<TrackCard>` étendu ; source → `<PlatformLink>` ; retrait boutons Suivre ; AdminCard déplacée en bas (gate déjà intégré au composant) ; garder la **bannière crawl** (`useTaskPoll`).

**Dépend de** : composants partagés Track Detail (`Artwork`, `TrackCard`, `PlatformLink`) — TOUS livrés le 2026-07-17.
