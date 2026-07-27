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
- **(recap C3)** : **pastille cadence** (Quotidien / Hebdo / Mensuel) sur la row, dérivée de `last_changed_at` (pilote déjà C6.e) → distingue les sources **vivantes** des **dormantes**. Donnée underlying : « dernière nouveauté » (last_changed_at relatif), affichable en tooltip. ⚠️ **précisée au pré-vol** (voir ci-dessous) : dérivation **stricte**, **pas de fallback `created_at`**.
- **Gardé** : form **Ajouter** (URL), tri, statut crawl **live** + bouton Crawl, avis, row → détail.
- **Pas d'exclusion** (playlists peu nombreuses).

### Précisions pré-vol chantier (2026-07-25)

> Vérif code réel + **données PROD** (56 playlists). Ces précisions **priment** sur les formulations amont.

- **Format = TABLEAU enrichi** (jumelle de la liste Sets) — cohérent avec §5, on reste en tableau (pas de grille de cartes).
- **Source → logo `<PlatformLink>` variante `glyph`** (marqueur non-cliquable). Donnée prod = **multi-plateforme réel** : deezer 33 / tidal 22 / spotify 1 → **contrairement à /sets** (100 % trackid, colonne retirée), le logo a de la valeur ici. `<PlatformLink>` couvre déjà les 3 sources. **Glyph et pas bouton cliquable** : la row entière est un `RouterLink` vers `/playlists/:id` → un `<a>` cliquable dans la cellule imbriquerait deux ancres (HTML invalide). Le logo est un marqueur de source, pas un lien.
- **Genre déduit** : **56/56** playlists produisent ≥1 genre (radar_tracks→catalog genrées). Back renvoie `top_genres: list[TopGenreOut]` (même agrégat que le détail, périmètre `catalog_visible`), DA affiche **1–2 `<StyleTag>`**. Résidu : genre bruité sur une playlist à peu de tracks détectées — **accepté**, non bloquant (comme /sets).
- **Créateur (`owner`)** : 56/56 rempli → colonne toujours renseignée. **Tracks (`track_count`)** : 56/56 rempli (c'est le compte **source**, pas les détectées — décision §5 : détectées écartées).
- **Pastille cadence — arbitrage William (A)** : dérivée **STRICTEMENT de `last_changed_at`**, **aucune pastille quand NULL** (pas de fallback `created_at`, qui fabriquerait une fausse cadence). Donnée prod : `last_changed_at` peuplé **8/56** seulement (les 33 Deezer = tous NULL) — mais c'est un artefact **transitoire mono-utilisateur** (peu de follows/crawls actifs à un seul user), **pas** une constante structurelle comme la Source /sets : elle se peuplera à l'ouverture (plusieurs DJs → plancher de crawl quotidien sur plus de playlists → plus de changements détectés). On **garde donc la feature** mais on l'affiche **honnêtement** : la row montre une pastille **uniquement** si `last_changed_at` existe. Tooltip = « dernière nouveauté » (relatif).
- **Filtre d'avis** (Toutes/Liked/Disliked/À explorer) → résolution `ids`/`exclude_ids` **server-side façon Artistes** (le back gagne ces params). **Tri par colonne « Avis » retiré** (opinion = filtre, pas tri) ; boutons avis conservés dans la row. Colonnes triables server-side = **Titre · Créateur · Tracks · Dernier crawl**.
- **Infinite scroll** (`usePaginatedList`) : les 56 playlists tiennent largement → **cohérence** (jumelle Sets/Artistes), pas perf. Corrige au passage un bug existant : `/browse` a `limit=50` par défaut et le front l'appelle sans params → il ne charge aujourd'hui que **50/56** alors que le header affiche 56.
- **Retrait `external_id`** sous le titre (bruit technique) — confirmé.
- **Composants transverses : tous déjà livrés** (`<PlatformLink>`, `<Artwork>`, `<StyleTag>`, `<LikeDislike>`, `usePaginatedList`). **Aucun nouveau composant** → pas de lot composant (comme /sets).
- **Lot back confirmé** (patron `routers/sets.list_sets`, quasi-copiable) : `browse` gagne `sort` (titre/créateur/tracks/crawl) + `ids`/`exclude_ids` (`_parse_id_csv`) + `top_genres` batché (radar_tracks→catalog, `catalog_visible`, warm pillar cache) + **expose `last_changed_at`** — additif à `WatchedEntityBrowseOut`. **Aucune migration** (`last_changed_at` déjà en base, C6.e).

### Décisions du handoff Design (round Claude Design, 2026-07-26 — voir `handoff-playlists-list/`)
- **Bouton Crawl révélé au survol** (≠ actuel toujours-visible) ; **toujours visible < 640 px / tactile**. En **cooldown 12 h** : pas de bouton, libellé mono `cooldown 12 h` au survol seulement.
- **Statut live prioritaire** : `En attente`/`En cours`(animé)/`Crawlé` remplacent **date ET bouton** — mappe `queued`/`running`/`done` du polling `useTaskPoll` existant (aucun changement back).
- **Bloc « Dernier crawl » sur 2 lignes** (cellule ~184 px) : L1 date relative **ou** statut live ; L2 pastille cadence (gauche) + bouton Crawl (droite). Hauteurs réservées → aucun décalage.
- **Pastille cadence = libellé mono nano** (`Quotidien`/`Hebdo`/`Mensuel`, pill `--surface-2`), **pas de code couleur**, **absente si `last_changed_at` nul**. Dérivée client-side (seuils 14 j / 60 j).
- **Panneau Ajouter → MODAL** (recentré desktop, bottom-sheet mobile), 1 champ URL, bouton **« Ajouter »**. Flux inchangé.
- **Column-drop** : Créateur < 1040 → Genre replié sous le titre < 880 → **Dernier crawl replié en méta mono < 720** (tombe **tard**, pas en premier : c'est le cœur de veille) → mobile < 640 (Playlist+genre+méta crawl · Tracks · Avis, avis toujours visible). Bouton Crawl non repris en mobile.
- **Tracks = nombre brut aligné droite** (pas d'anneau). **Créateur non cliquable** (string libre, pas d'entité Diggy → pas de besoin back `[{id,name}]`).
- **Aucun composant transverse créé** ; pilote 100 % tokens (hex = harness bundler uniquement). **Verdict handoff : GO.**

### Retour post-déploiement (2026-07-26)
- **Pastille cadence → « fraîcheur brute »** (décision William après recette prod) : le libellé bucketé `Quotidien/Hebdo/Mensuel` était ambigu (mot de **fréquence** pour une donnée d'**activité/fraîcheur** — « ça veut dire quoi Quotidien ? »). Remplacé par l'**âge relatif de la dernière nouveauté** (ex. « MAJ 3 j » / « MAJ 2 sem »), toujours **uniquement si `last_changed_at` existe**, tooltip inchangé « Dernière nouveauté il y a X ». Tweak front copy-only, appliqué dans le **lot correctif Phase 6**.
- **Placements à revoir** : William a ressenti des éléments « pas bien placés » (non spécifiés) → traqués par la **revue design Phase 5** (Claude Design), correctifs groupés en Phase 6.
- Recette prod OK par ailleurs : back (`top_genres`/`last_changed_at`/tri), front (rendu desktop+mobile, cadence stricte confirmée), bouton crawl, filtres, light mode, mobile — tous validés.

## 6. Sortie next-step
**Handoff Design**
- [ ] Row playlist : **+ genre (StyleTag)** + **source (logo)**, **retrait `external_id`** ; layout + responsive.

**Chantier work_manager**
- **Back** : `/api/watchlist/browse` (ou endpoint paginé) — **pagination + sort server-side** ; **construire** le **genre dominant** (déduction depuis les tracks détectées ; `top_genres` n'existe pas encore côté back — même travail que le détail « Dans cette playlist » à câbler) ; renvoyer **`last_changed_at`** (déjà stocké C6.e) pour la **pastille cadence** (C3).
- **Front** : `WatchlistView` → **`usePaginatedList`** ; row + genre + source logo ; retrait `external_id` ; garder crawl **live** (`useTaskPoll`) + form Ajouter. Filtres opinion à gérer comme la liste Artistes.
- **Transverse** : `<PlatformLink>`.

**Dépend de** : `<PlatformLink>` (transverse).

> **Résolu (validé)** : le concept « suivre une playlist » est **masqué de l'UI** (liste + détail) — ajoutée = surveillée par défaut ; mécanisme back `user_follows`/priorité **conservé** (sans effet tant que la watchlist reste sous le cap de 200).
