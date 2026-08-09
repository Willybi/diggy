# Audit 2026-08 — A1 : Backend (`server/api/` hors alembic)

- **Date** : 2026-08-09
- **HEAD audité** : `9b305d6` (2026-08-08)
- **Agent** : A1 (Backend)
- **Périmètre** : `server/api/` hors `alembic/` — 15 routers (lus intégralement), services (lecture intégrale de radar, recommendation, catalog, similarity, watchlist, search, genre, artist, following, monitoring, opinion_sync, image, external_search, artist_connection ; skim structurel de set_dedup), `main.py`, `dependencies.py`, `rate_limit.py`, `auth_middleware.py`, `auth.py`, `utils.py`, `database.py`, `trackid/`, `beatport/`.
- **Méthode** : lecture + croisement systématique des candidats morts avec le frontend (`server/frontend/src`, grep exhaustif des appels `api.*`), les workers (`server/workers`), les scripts (`scripts/`, `server/api/scripts/`, `worker/`) et les tests (`tests/`). Aucune modification hors ce rapport.

---

## Ce qui va bien

Points vérifiés conformes — à ne PAS re-signaler dans un audit futur :

- **La série AU a réellement soldé l'essentiel de l'audit 2026-07.** Vérifié un par un :
  - *2026-07/A1-01 + A1-02 corrigés* : `routers/search.py` est tombé à 43 LOC, la logique vit dans `services/search_service.py` (403 LOC) ; chaque helper a un ORDER BY stable avec tie-break id (`search_service.py:75`, `:114`, `:195`, `:243`, `:287`) et l'offset est poussé en DB pour un scope unique, l'ignore documenté pour `scope=all` (`search_service.py:342-347`, `:399-402`).
  - *A1-03 corrigé* : `get_set_detail` filtre `UserTrack.user_id == uid` (`routers/sets.py:437-445`), guests → `in_lib=False`.
  - *A1-05/A1-06 corrigés* : `watchlist_service.py` (559 LOC) extrait, router mince (166 LOC) ; `PATCH /watchlist/{id}/crawled` supprimé ; MinIO/HTTP passés en `httpx` async + `run_in_threadpool` (`watchlist_service.py:22-51`).
  - *A1-08/A1-09 corrigés* : le router `tracks.py` n'existe plus.
  - *A1-13/A1-16 corrigés* : `refresh-pillars` supprimé ; les routers consomment l'API publique `ensure_pillar_cache`/`genre_pillar` (`routers/sets.py:33`, `routers/catalog.py:21`), plus aucun import `_PILLAR_CACHE` hors du service.
  - *A1-17 corrigé* : `/api/watchlist/active` n'existe plus, ni dans le router ni dans `_OPEN_PREFIXES` (`auth_middleware.py:24-29`) ; aucun worker n'appelle l'API par HTTP (grep `server/workers` = 0).
  - *A1-19/A1-20 corrigés* : `GET /opinions/` a un `response_model` (`routers/opinions.py:20`) et `int(entity_key)` est gardé → 422 (`opinions.py:81-87`).
  - *A1-21 corrigé* : `BUCKET_PLAYLIST` importé partout depuis `image_service` (`watchlist_service.py:45`).
  - *A1-22 corrigé* : CLAUDE.md situe bien `workers/deezer_enrich.py`.
  - *A1-24 corrigé* : `BottomNav.vue:61` appelle `'/api/radar/new-count'` avec le préfixe.
  - *A1-25 corrigé* : `POST /sets/import` passe par `sync_set_opinion` (`routers/sets.py:382`).
  - *A1-18 amélioré* : `taxonomy.py` est réécrit en ORM (`GenreNode`/`GenreEdge`) avec `like_escape` (le camelCase de réponse subsiste, résidu accepté Q1b-2).
- **`response_model` : couverture 100 %** sur les 105 endpoints, seules exceptions légitimes : `/auth/google/callback` (RedirectResponse), `/api/health`, les DELETE 204 (grep exhaustif des décorateurs).
- **Gestion d'erreurs homogène** : le contrat « services raise LookupError/ValueError, never HTTPException » est documenté et tenu dans tous les services lus ; les routers mappent 404/400/409/429 uniformément. Cas soigné : `PreviewUnavailableError` → 503 + `Retry-After` avec un retry côté service (`catalog_service.py:42-46`, `routers/catalog.py:155-161`).
- **Pagination déterministe sur les grandes listes refondues** : `list_catalog` (tie-break id, commentaire « lesson A1-02 », `catalog_service.py:345-349`), `artist_service.list_artists` (tie-break id sur toutes les branches + commentaire expliquant le bug d'infinite-scroll qu'il corrige, `artist_service.py:210-222`), `watchlist_service.browse` (`WatchedEntity.id.asc()`, `:141`), `search_service` (id partout), `list_bi_score` (tri en mémoire avec tie-break id ascendant documenté, `radar_service.py:384-397`), `following_service.get_activity` (`detected_at.desc(), id.desc()`).
- **Le pitfall asyncpg est respecté partout** : aucun `asyncio.gather` sur une même `AsyncSession` (les commentaires « never gather on db » sont présents aux points sensibles : `radar_service.py:300-301`, `similarity_service.py:330-334`, `watchlist_service.py:151-153`, `artist_connection_service.py:184-186`). Le seul `gather` trouvé (`external_search_service.py:116`) porte sur deux appels HTTP, pas sur la session.
- **`catalog_visible` appliqué sur les chemins de lecture ajoutés depuis juillet** : radar feed/trends, genre lists (via `catalog_visible_sql` + bind `:viewer_id`), agrégats top_genres des sets/playlists, similar tracks/sets (via le pool), collections, activity feed.
- **Verrous et rate limits** : lock d'import atomique `SET NX EX` avec release conditionnelle (`import_rb.py:53-81`), rate limiting Redis partagé fail-open avec identité `X-Real-IP` uniquement (`rate_limit.py:52-61`), state OAuth one-shot Redis (`routers/auth.py:57`).
- Ruff : 0 violation (inventaire Phase 0).

---

## Findings

### [A1-01] `artist_service.get_detail` : `lib_sub` sans filtre `user_id` — fuite inter-utilisateurs + lignes dupliquées
- **Type** : bug
- **Sévérité** : haute
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** : `server/api/services/artist_service.py:319-324` :
  ```python
  lib_sub = select(
      UserTrack.catalog_id,
      UserTrack.rb_mytags.label("tags"),
      UserTrack.rb_bpm.label("bpm"),
      UserTrack.rb_key.label("key"),
  ).subquery()
  ```
  Aucune clause `UserTrack.user_id == user_id` — contraste avec le même service 250 lignes plus haut (`list_artists`, `artist_service.py:67-71`, correctement filtré) et avec le fix 2026-07/A1-03 sur `get_set_detail`. `git log -L` : le bloc est inchangé depuis l'extraction service (`5ca078c`), hors retrait de `rating` (D6.0) — résidu de l'ère mono-user, jamais couvert par l'audit 2026-07 (les intérieurs de services étaient « non couverts »).
- **Constat** : sur la page Artist Detail, (1) `in_lib` et `nb_lib` reflètent l'union des bibliothèques de TOUS les utilisateurs (un guest voit « en bib ») ; (2) `bpm`/`key`/`style` affichés proviennent du `rb_bpm`/`rb_key`/`rb_mytags` de N'IMPORTE QUEL utilisateur — donnée de performance Rekordbox privée d'autrui, servie avec `bpm_source="rekordbox"` (`:377-381`) ; (3) si deux utilisateurs possèdent le même track, le `outerjoin` produit une ligne par `user_track` → tracks dupliqués dans la liste et `nb_lib` gonflé. Violation directe de l'invariant multi-user (« every user-conditional query must handle None »).
- **Recommandation** : ajouter `.where(UserTrack.user_id == user_id)` au `lib_sub` (avec le même comportement guest que `list_catalog` : `user_id=None` → aucune ligne). Ajouter un test à deux utilisateurs (pattern `test_import_multiuser`).
- **Dépendances** : aucune
- **Tags** : QW-c

### [A1-02] Gabarit « pool de similarité » : tout le catalog (~212k lignes) reconstruit en mémoire par requête ; `GET /api/catalog/{id}/similar` public, non caché, non throttlé
- **Type** : perf
- **Sévérité** : haute
- **Effort estimé** : M
- **Confiance** : haute
- **Preuve** :
  - `services/similarity_service.py:386-435` : `load_candidate_pool` — « The pool IS the viewer's visible catalog » : une projection de TOUTES les lignes visibles (id, bpm, label, release_date, genres) matérialisée en `dict[int, PooledCandidate]` avec expansion de genres et frozensets par ligne. Volumétrie prod : 212 179 entrées catalog (mesure du 2026-08, `docs/refonte-ui/genre-detail.md:9`).
  - `similarity_service.py:752-772` : `get_similar_tracks` reconstruit ce pool à CHAQUE requête (seul le contexte 4-maps est caché 6h en processus) et score le seed contre les ~212k candidats (`_score_seed_against_pool`, boucle Python `:483-565`). **Aucun cache résultat** — contrairement à la reco (Redis 1h/user) et à `similar_sets` (Redis 6h, dont le commentaire `:782-784` documente « ~21 s per uncached call » mesuré en prod).
  - Consommation : `TrackDetailView.vue:586` appelle `/api/catalog/${id}/similar?limit=8` à chaque vue de page Track Detail ; l'endpoint est public (préfixe `/api/catalog` dans `_PUBLIC_GET_PREFIXES`, `auth_middleware.py:12`) et absent de `RATE_LIMITS` (`rate_limit.py:18-38`) — alors que le commentaire de `/api/recommendations` (`rate_limit.py:35-37`) justifie son cap précisément par ce coût de calcul.
- **Constat** : approfondissement du bug mémoire OUVERT `/radar/feed` (~550 Mo/req, cap api 1G→3G le 2026-08-01) — la charge vient de `get_recommendations → load_candidate_pool`, PAS du fetch des lignes trend (borné à ~quelques centaines via `list_catalog(catalog_ids=...)`, `radar_service.py:319-344`). Le même gabarit tourne SANS cache ni limite sur deux endpoints guests : `/api/catalog/{id}/similar` (chaque vue Track Detail = fetch 212k lignes + scoring + dizaines/centaines de Mo transitoires) et `/api/sets/{id}/similar` sur cache-miss (~21 s CPU). Un guest qui itère des ids froids fait un déni de service CPU/mémoire à coût nul. Corollaire : durcir `/radar/feed` seul ne suffit pas, le correctif doit viser le pool partagé. Annexe même famille : `artist_connection_service.get_connections` recharge le contexte genres à chaque requête (`_load_genre_context` direct, `artist_connection_service.py:190`) au lieu du `load_similarity_context` caché.
- **Recommandation** : (1) cache résultat Redis par `(seed_id, viewer)` pour `get_similar_tracks` (même pattern que `similar_sets`, TTL 6h) ; (2) ajouter `/api/catalog/` et `/api/sets/` similar aux `RATE_LIMITS` ; (3) à moyen terme, le « fix durable » déjà noté dans `RecommendationConfig` (`recommendation_service.py:37-39`) : candidate pooling précalculé nightly plutôt qu'un pool par requête. Ne PAS toucher au barème C2 lui-même.
- **Dépendances** : bug ouvert `/api/radar/feed` (mémoire projet `api-oom-radar-feed`) — même racine, à traiter ensemble.
- **Tags** : —

### [A1-03] Invalidation du cache reco absente du chemin d'avis principal (`PATCH /catalog/{id}/avis`)
- **Type** : bug
- **Sévérité** : moyenne
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** : `routers/opinions.py:97-102` invalide le cache reco après commit (« Track opinions only (they are the reco seeds) ») via `recommendation_service.invalidate_user(redis, uid)`. Son jumeau `catalog_service.update_avis` (`catalog_service.py:819-847`) fait la MÊME écriture logique (`sync_track_opinion`) mais n'invalide rien — le router `update_avis` (`routers/catalog.py:166-176`) ne prend même pas la dépendance `get_redis`. Or c'est LE chemin vivant : `audioPlayer.js:239`, `ExplorerView.vue:885`, `RadarView.vue:884`, `GenreDetailView.vue:493`, `TrackDetailView.vue:457` passent tous par `/api/catalog/{id}/avis` ; le front n'utilise `PATCH /opinions/` que pour les entités non-track (`stores/opinions.js:34`).
- **Constat** : un like/dislike posé depuis le player ou une liste (le flux « écoute active », dislike=skip) laisse le cache reco (`reco:{user}`, TTL 1h) et donc « Pour toi » du Radar servir jusqu'à 1h une liste calculée AVANT l'avis — y compris le track qu'on vient de disliker. Les deux jumeaux censés partager « the same code path » (docstring d'`opinion_sync`) divergent sur l'effet de bord cache.
- **Recommandation** : passer `redis` à `catalog_service.update_avis` et appeler `invalidate_user` après commit (copie du bloc d'`opinions.py`, même commentaire sur la race pré-commit). Alternative plus robuste : déplacer l'invalidation DANS `sync_track_opinion` (un seul point).
- **Dépendances** : aucune
- **Tags** : —

### [A1-04] `POST /admin/playlists/fetch-artworks` n'est jamais commité : `has_artwork=True` perdu à chaque run
- **Type** : bug
- **Sévérité** : moyenne
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** : `routers/admin.py:651-657` — `return await ImageService.fetch_playlist_artworks(db)`, aucun commit. `services/image_service.py:116-157` mute `pl.has_artwork = True` (`:150`) mais ne commite jamais. `database.py:20-22` : `get_db` fait `async with SessionLocal() as session: yield session` — pas de commit à la sortie, la session est fermée et les mutations non commitées sont jetées. Contraste : le chemin unitaire `watchlist_service.fetch_artwork` commite bien (`watchlist_service.py:528`).
- **Constat** : le bouton admin « fetch artworks playlists » (`AdminArtists.vue:378`) uploade réellement les images vers MinIO mais ne persiste jamais `has_artwork=True` → le front (qui affiche sur ce flag) ne montre jamais les artworks obtenus, et chaque run re-télécharge exactement les mêmes playlists (le filtre `has_artwork.is_(False)` ne se vide jamais). Échec silencieux : le compteur `fetched` renvoyé est correct, l'admin croit l'opération faite.
- **Recommandation** : `await db.commit()` en fin de `fetch_playlist_artworks` (ou dans le router après l'appel). Test : vérifier `has_artwork` en DB après l'appel, pas seulement le dict retourné.
- **Dépendances** : le passage async de la boucle relève de 2026-07/A1-04 (récurrence ci-dessous) — fix du commit indépendant.
- **Tags** : QW-c (impact réel modéré mais fix 1 ligne, zéro risque)

### [A1-05] Surface « Radar v1 » morte : 4 endpoints + 4 fonctions service sans aucun appelant produit
- **Type** : mort
- **Sévérité** : moyenne
- **Effort estimé** : S
- **Confiance** : haute (sur l'absence d'appelant) — la suppression reste une décision produit
- **Preuve** : définis dans `routers/radar.py` : `GET /radar/full` (l.104), `PATCH /radar/{catalog_id}/state` (l.173), `PATCH /radar/state/batch` (l.183), `DELETE /radar/{entry_id}` (l.194) ; côté service : `radar_service.list_full` (l.16, ~170 LOC), `update_state` (l.432), `batch_update_state` (l.468), `add_track` (l.514 — candidat vulture confirmé). Grep exhaustif : zéro hit dans `server/frontend/src` (la page Radar D6 consomme `/api/radar/feed`, `RadarView.vue:749`, et pose les avis via `/api/catalog/{id}/avis`, `RadarView.vue:884` ; le Hub consomme `/trends`), zéro dans `server/workers`, `scripts/`, `server/api/scripts/`, `worker/` (seul hit : un `.pyc` orphelin d'un fichier supprimé). Seuls appelants : `tests/api/test_radar.py`, `test_validation.py`, `test_opinions.py:230`, `test_services/test_radar_service.py`, `test_auth_middleware.py:114`.
- **Constat** : la refonte Radar (D6, 2026-07-23) a remplacé l'ancienne page (qui consommait `/full` + `/state`) sans retirer l'API. ~350 LOC de code + tests entretenus pour rien ; `list_full` porte en outre un tri sans tie-break (l.156-162) qu'il faudrait corriger s'il survivait. `UserRadarState` reste VIVANT par ailleurs (alimenté par `sync_track_opinion`) — seule la surface HTTP est orpheline.
- **Recommandation** : décision produit : soit supprimer les 4 endpoints + `list_full`/`update_state`/`batch_update_state`/`add_track` et leurs tests (en gardant `opinion_sync` intact), soit documenter pourquoi on les garde (client externe ?). Ne pas supprimer `/trends` ni `/new-count` ni `/feed` (vivants).
- **Dépendances** : aucune
- **Tags** : —

### [A1-06] Tris paginés sans tie-break stable : listes Genre Detail (infinite scroll) et `GET /watchlist/`
- **Type** : bug
- **Sévérité** : moyenne
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** :
  - `services/genre_service.py:552-561` (`list_genre_tracks`) : `ORDER BY c.created_at DESC NULLS LAST` / `c.bpm ASC NULLS LAST` / … — aucun `c.id` final. Consommé en offset-pagination infinite-scroll par `GenreDetailView.vue:448` (`usePaginatedList`).
  - `genre_service.py:516` (`list_genre_playlists`) : `ORDER BY genre_track_count DESC` seul — ex-aequo massifs garantis (toutes les playlists à 1 track du genre) ; `:482` (`list_genre_sets`) : `genre_track_count DESC, played_date DESC NULLS LAST` — même exposition sur les ties/date NULL ; `:444` (`list_genre_artists`) : `track_count DESC, a.name` (name non contraint unique). Tous paginés (`limit/offset`) par Genre Detail.
  - `services/watchlist_service.py:78-86` (`list_followed`) : `select(WatchedEntity).join(...)` sans AUCUN `order_by`, puis `offset/limit`.
- **Constat** : exactement le bug que `artist_service.list_artists` documente et corrige chez lui (`artist_service.py:210-213` : « ex-aequo rows can be reordered between two LIMIT/OFFSET pages, which surfaced/skipped rows and returned the same artist twice in the infinite scroll ») : le tri `bpm` d'une tracklist de genre (valeurs très répétées) peut dupliquer/sauter des lignes entre deux pages. `list_followed` sans ORDER BY est non déterministe par construction (ordre de scan PG).
- **Recommandation** : suffixer chaque ORDER BY d'un `c.id` / `we.id` / `a.id` (une ligne par requête, même convention que le reste du code). Pour `list_followed`, `ORDER BY followed_at DESC, entity_id` .
- **Dépendances** : 2026-07/A1-07 (si `GET /watchlist/` est supprimé, sa part tombe)
- **Tags** : QW-c

### [A1-07] Proxys d'API externes publics sans rate limit : `GET /api/sets/search` (TrackID) et `GET /api/catalog/{id}/preview-url` (Deezer)
- **Type** : sécu
- **Sévérité** : moyenne
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** :
  - `routers/sets.py:54-90` : `search_trackid_sets` — aucun Depends user (public via le préfixe `/api/sets` de `_PUBLIC_GET_PREFIXES`), chaque requête ouvre un `TrackIDClient` neuf et interroge `trackid.net` ; le rate-limit interne du client (1 s, `trackid/client.py:19,38-40`) est PAR INSTANCE donc inopérant entre requêtes. `RATE_LIMITS` (`rate_limit.py:18-38`) ne matche pas ce chemin (le préfixe `/api/search` ne couvre pas `/api/sets/search`).
  - `routers/catalog.py:145-163` + `catalog_service.get_preview_url` : public, appelle `api.deezer.com/track/{id}` sur cache-miss (cache Redis 30 min par deezer_id, `catalog_service.py:38-39`) — un balayage d'ids froids consomme le quota Deezer partagé avec l'enrichissement.
- **Constat** : n'importe quel guest peut faire de Diggy un relais de charge vers TrackID.net (risque de bannissement du scraper — le même User-Agent sert aux imports nocturnes) ou épuiser le quota Deezer du serveur. La logique qui a plafonné `/api/search/external` (10/60) et `/api/recommendations` s'applique à l'identique.
- **Recommandation** : ajouter à `RATE_LIMITS` : `"/api/sets/search": (10, 60)` et un cap raisonnable pour `/api/catalog` preview (attention à la règle d'ordre d'insertion des préfixes documentée dans le module ; un préfixe fin `/api/sets/search` doit précéder tout futur `/api/sets`). Optionnel : exiger le JWT sur `/sets/search` (feature d'import, pas de découverte guest).
- **Dépendances** : A1-02 (même famille pour les endpoints similar)
- **Tags** : QW-c

### [A1-08] Routers ré-engraissés : `sets.list_sets` (~190 LOC), `admin.get_backlog` (~140 LOC), `radar.list_trends`, `admin.list_set_flags`
- **Type** : archi
- **Sévérité** : moyenne
- **Effort estimé** : M
- **Confiance** : haute
- **Preuve** :
  - `routers/sets.py:123-316` : `list_sets` — construction de requête complète dans le router (agrégats identified/total, filtre de dominance de genre avec sous-requête `HAVING hit*100 >= total*25`, tri, batch artists, batch top_genres). C'est la liste Sets livrée en D6 (2026-07-24).
  - `routers/admin.py:698-836` : `get_backlog` — ~7 COUNT/EXISTS + parsing snapshot dans le router ; le docstring dit « Thin — the snapshot read is delegated » mais seule la lecture snapshot l'est.
  - `routers/radar.py:39-101` : `list_trends` — requête + assemblage dans le router ; `routers/admin.py:318-384` : `list_set_flags` — requête, batch member-titles et assemblage.
- **Constat** : la règle projet « new business logic goes in a service, routers stay thin » (CLAUDE.md) est retenue partout ailleurs mais s'érode sur les endpoints ajoutés depuis juillet — le pattern qui avait produit `search.py`/`watchlist.py` version 2026-07 (2026-07/A1-01/05) recommence. Coût concret : `list_sets` n'est testable qu'en HTTP, et sa logique de dominance de genre n'est pas réutilisable (la carte Sets du Hub ou un futur endpoint devrait la dupliquer).
- **Recommandation** : extraire `set_service.list_sets` (ou l'adosser à `set_dedup_service`), `monitoring_service.get_backlog_counters`, `radar_service.list_trends`. Mouvement mécanique, zéro changement de comportement — même geste que AU/PROMPT-A1-service-layer.
- **Dépendances** : récurrence 2026-07/A1-10 (même fichier admin.py, à traiter dans le même lot)
- **Tags** : —

### [A1-09] Divergence CLAUDE.md : `similar_from_context` n'est plus la primitive de la reco (plus aucun appelant produit) ; la reco consomme des membres privés
- **Type** : doc
- **Sévérité** : basse
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** : CLAUDE.md (Architecture) : « similarity (C4: load_similarity_context + similar_from_context multi-seed primitive … ) ». Réalité : `recommendation_service._compute` importe `_build_result_items`, `_score_seed_against_pool`, `load_candidate_pool`, `load_similarity_context` (`recommendation_service.py:154-159`) — pas `similar_from_context`. Grep repo : `similar_from_context` n'est appelé que par `tests/api/test_services/test_similarity_service.py` (l.553-598). Même motif privé cross-module dans `artist_connection_service.py:13-17` (`_expand_genre_nodes`, `_load_genre_context`).
- **Constat** : conformément à la consigne de CLAUDE.md (« If you notice a divergence… SAY SO ») : la description de la couche similarity est périmée depuis l'optimisation « pool » ; `similar_from_context` est devenu un wrapper public testé mais sans consommateur, pendant que les VRAIS points d'entrée de la reco sont des fonctions préfixées `_`. Un refactor « nettoyage des privés » casserait la reco en croyant ne toucher que du privé.
- **Recommandation** : mettre à jour la ligne CLAUDE.md (primitives réelles : `load_similarity_context` + `load_candidate_pool` + `_score_seed_against_pool`), et soit promouvoir `score_seed_against_pool`/`build_result_items` en API publique (retirer le `_`), soit faire repasser la reco par `similar_from_context`. Trancher aussi le sort du wrapper (garder = le documenter comme API de test/futur usage).
- **Dépendances** : aucune
- **Tags** : QW-c (la partie CLAUDE.md)

### [A1-10] Méthode morte : `TrackIDClient.get_styles`
- **Type** : mort
- **Sévérité** : basse
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** : `server/api/trackid/client.py:98-101`. Grep repo-wide (frontend, workers, scripts, tests) : uniquement la définition et l'inventaire d'audit. (À la différence de `search_tracks`, vivant via `server/api/scripts/discover_trackid_sets.py:54`.)
- **Constat** : candidat vulture confirmé — 4 lignes, aucun risque.
- **Recommandation** : supprimer la méthode.
- **Dépendances** : aucune
- **Tags** : QW-c

### [A1-11] Excepts muets sur les intégrations Deezer admin : une panne réseau est indiscernable de « aucun résultat »
- **Type** : dette
- **Sévérité** : basse
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** : `routers/admin.py:145-146` (`search_deezer_artist`) : `except Exception: return []` — ni log ni statut. `services/watchlist_service.py:36-37` (`_fetch_deezer_playlist`) : `except Exception: return {}` → l'entité watched est créée avec `title=NULL`/`track_count=NULL` sans signal. `artist_service.link_to_deezer` (`artist_service.py:555-556`) : `except Exception: pass` → un lien est posé sans nom/artwork Deezer, silencieusement.
- **Constat** : angle « gestion d'erreurs » — le pattern fail-open est assumé ailleurs (cache, rate-limit) mais y est LOGGÉ (`logger.warning`). Ici l'admin qui cherche un artiste pendant une panne Deezer voit « aucun résultat » et peut conclure à tort à un `NOT_FOUND` (sentinelle = décision humaine irréversible sans intervention).
- **Recommandation** : a minima `logger.warning` dans les trois excepts ; idéalement distinguer côté réponse (`search_deezer_artist` → 503 sur exception réseau, comme le pattern preview-url).
- **Dépendances** : 2026-07/A1-04 (mêmes blocs de code à toucher pour l'async)
- **Tags** : QW-c

### [A1-12] Redis côté API : client SYNC dans le middleware de rate-limit + connexion neuve par requête dans `get_redis`
- **Type** : perf
- **Sévérité** : basse
- **Effort estimé** : S
- **Confiance** : moyenne
- **Preuve** : `rate_limit.py:43-49` + `:81-85` — `redis.from_url` (client sync) puis `r.incr/expire/ttl` (3 aller-retours bloquants) exécutés dans `async def dispatch` sur chaque requête matchée. `dependencies.py:72-80` — `get_redis` crée un client + pool `aioredis.from_url` par requête puis `aclose()` (pas de pool partagé process).
- **Constat** : Redis est local et sub-ms, donc invisible aujourd'hui ; mais un stall Redis (BGSAVE, saturation) bloque TOUT l'event loop uvicorn (le fail-open ne couvre que l'exception, pas la lenteur), et le coût connexion/requête s'additionne sur les endpoints chauds (preview-url, reco, feed).
- **Recommandation** : basculer le middleware sur `redis.asyncio` (le module l'utilise déjà ailleurs), et partager un pool module-level dans `get_redis` (créé au lifespan, fermé au shutdown).
- **Dépendances** : aucune
- **Tags** : —

---

## Récurrences (clés 2026-07 conservées)

### [2026-07/A1-04] I/O synchrone bloquante dans l'event loop — RÉCURRENCE partielle (corrigée sur watchlist/import externe, subsiste sur 5 points)
- **Type** : perf
- **Sévérité** : moyenne
- **Effort estimé** : M
- **Confiance** : haute
- **Preuve** :
  - `routers/admin.py:128-135` : `import requests as req` + `req.get("https://api.deezer.com/search/artist", timeout=5)` dans `async def search_deezer_artist` (inchangé depuis 2026-07).
  - `services/artist_service.py:527-556` : `link_to_deezer` — `requests.get` + `ImageService.upload_from_url` sync (`:611`, `:634`) dans le flux async.
  - `services/artist_service.py:796-817` : `enrich_single_beatport` — `BeatportClient` 100 % sync (`beatport/client.py:233-241` : `requests.get` timeout 20 s + `time.sleep(1.5)` de rate-limit) appelé directement en async ; le docstring annonce « sync, ~3s » : ~3 s d'event loop gelé PAR APPEL, jusqu'à ~1 min sur le fallback release (2-12 scrapes).
  - `services/image_service.py:138-155` : `fetch_playlist_artworks` — boucle `requests.get` + upload sync sur N playlists dans une méthode `async`.
  - `routers/import_rb.py:62-68` : `s3.upload_fileobj` boto3 sync (≤10 Mo) dans l'endpoint async (+ accès au membre privé `ImageService._get_s3`).
- **Constat** : pendant ces appels, TOUTES les requêtes du worker uvicorn sont gelées. Le projet a le pattern correct depuis AU (`run_in_threadpool` : `watchlist_service.py:48-51`, `catalog_service.py:1162-1167`, `external_search_service.py:72`) — ces cinq points sont les survivants, tous sur des chemins admin/import (fréquence faible, d'où la sévérité maintenue moyenne).
- **Recommandation** : `httpx.AsyncClient` pour les deux appels Deezer ; `run_in_threadpool` pour `BeatportClient`, la boucle artworks et l'upload MinIO de l'import. Exposer un `ImageService.upload_fileobj` public au passage.
- **Dépendances** : A1-04 (commit manquant, même fonction), A1-11 (mêmes excepts)
- **Tags** : —

### [2026-07/A1-07] `GET /api/watchlist/` : toujours aucun consommateur produit
- **Type** : mort
- **Sévérité** : basse
- **Effort estimé** : S
- **Confiance** : moyenne
- **Preuve** : défini `routers/watchlist.py:39-48` (service `watchlist_service.list_followed`). Grep frontend : seuls `POST /api/watchlist/` (`WatchlistView.vue:624`), `/browse` (`:446`), `/{id}` , `/{id}/crawl`, `/{id}/fetch-artwork` sont appelés ; `GET /` n'apparaît que dans `tests/api/test_watchlist.py:48,58,335`. Situation identique à 2026-07 (l'onglet « suivies » passe par `/browse?followed`).
- **Constat** : l'endpoint a survécu à l'extraction service sans gagner de consommateur. Il porte en outre le défaut d'ORDER BY signalé en A1-06.
- **Recommandation** : même arbitrage qu'en 2026-07 : brancher ou supprimer (avec réécriture des tests follow sur `/browse`). Deux audits sans consommateur = pencher vers la suppression.
- **Dépendances** : A1-06
- **Tags** : —

### [2026-07/A1-10] Orchestration attach/detach de la dédup sets toujours dans `routers/admin.py`
- **Type** : archi
- **Sévérité** : moyenne
- **Effort estimé** : M
- **Confiance** : haute
- **Preuve** : `routers/admin.py:387-466` (`attach_set_flag` : choix parent, rattachement des membres au-delà de la première paire l.424-428, matérialisation, gestion group-flag — la logique a même GROSSI avec les flags de groupe du chantier scoring 2026-08-07) et `admin.py:503-537` (`detach_set` : détachement + règle « dernier sibling → suppression du parent »). `set_dedup_service` (1240 LOC) expose toujours uniquement les primitives (`find_or_create_virtual_parent` l.980, `materialize_parent` l.1042).
- **Constat** : inchangé depuis 2026-07, aggravé par la branche group-flags. Les règles métier (« ≥2 membres », « min des played_date », « dernier sibling ») ne sont testables que par HTTP admin.
- **Recommandation** : identique à 2026-07 : déplacer les corps dans `set_dedup_service.attach_flag(db, flag)` / `detach_set(db, set_id)`, le router gardant 404/audit/commit.
- **Dépendances** : 2026-07/A1-11 (même zone), A1-08 (même lot admin.py)
- **Tags** : lié-chantier:set-dedup

### [2026-07/A1-11] `detach_set` supprime le parent sans vérifier `is_virtual`
- **Type** : bug
- **Sévérité** : basse
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** : `routers/admin.py:528-531` :
  ```python
  if len(siblings) <= 1:
      if len(siblings) == 1:
          siblings[0].parent_set_id = None
      await db.execute(sa_delete(DJSet).where(DJSet.id == parent_id))
  ```
  Toujours aucune condition `DJSet.is_virtual.is_(True)` — inchangé au caractère près depuis 2026-07.
- **Constat** : sain tant que seuls des parents virtuels existent, mais rien ne l'impose au modèle ; un attachement futur sous un set réel ferait supprimer un vrai set et ses `set_tracks` (invariant n°4).
- **Recommandation** : ajouter la garde `DJSet.is_virtual.is_(True)` au `sa_delete` — une ligne.
- **Dépendances** : 2026-07/A1-10
- **Tags** : QW-c

---

## Hypothèses réfutées (candidats d'inventaire écartés)

| Candidat (Phase 0) | Verdict | Preuve |
|---|---|---|
| `similarity_service.py:80/90/138` `sim_bpm`/`sim_key`/`sim_cooc` (vulture) | **Écarté** — conservation DÉLIBÉRÉE actée par le brief C2.d (« elles sont importées et testées dans les tests unitaires. Ne pas les supprimer », `docs/completed/brief_C2d_bareme_v2.md:186`) ; testées dans `test_similarity_service.py`. Pas un registry dynamique : simplement de l'API de calibration/tests. | grep repo |
| `similarity_service.py:314` `reset_similarity_context_cache` | **Écarté** — API d'isolation de tests vivante : fixture autouse `tests/api/conftest.py:295-296` + tests dédiés du cache. Nécessaire à la parallélisation xdist. | grep |
| `similarity_service.py:731` `similar_from_context` | **Partiellement confirmé** — pas appelé par la reco (contrairement à CLAUDE.md) ; requalifié en divergence doc + API sans consommateur → **A1-09**. | grep |
| `radar_service.py:514` `add_track` | **Confirmé mort** (tests-only) → intégré à **A1-05** (surface Radar v1). | grep |
| `genre_service.py:83` `pillar_map` | **Écarté (limite)** — consommé uniquement par les tests (`test_genres_unit.py:29,43`, `test_genre_service.py:39-93`) mais sert d'accès encapsulé au cache pour eux ; 3 lignes, suppression sans gain. Noter que les tests MUTENT à travers lui, contredisant son docstring — cosmétique. | grep |
| `trackid/client.py:98` `get_styles` | **Confirmé mort** → **A1-10**. | grep |
| `routers/admin.py` (836 LOC, 42 commits de churn) « resté mince ? » | **Partiellement** : la majorité des endpoints délèguent proprement (link-deezer, resolve_flag, monitoring, crawl-logs) ; les exceptions sont circonscrites → **A1-08** (backlog, list_set_flags) + récurrence **2026-07/A1-10** (attach/detach). | lecture intégrale |
| Endpoints curl-only admin (reset-beatport, backfill-multi-artists, POST /watchlist/) | Résidu accepté Q1b-4 — non re-signalé. `POST /api/watchlist/` a d'ailleurs gagné un consommateur UI (`WatchlistView.vue:624`). | grep |
| Taxonomy 11 endpoints réservés | Résidu accepté Q1b-2 — non re-signalé ; noté : réécrits en ORM + `like_escape` depuis 2026-07 (amélioration, pas de RÉÉVALUATION nécessaire). | lecture |
| `GET /auth/me` | Résidu accepté #13 (gardé) — non re-signalé. | — |

### Non couvert (budget contexte)
- `set_dedup_service.py` (1240 LOC) : skim structurel seulement (inventaire des fonctions, vérification A1-10/11) — le chantier scoring venant d'être clos (2026-08-07) avec rescore prod vérifié, une lecture ligne à ligne a été dépriorisée.
- `trackid/importer.py`, `trackid/parsing.py`, `beatport/enrich.py` : non lus en détail (spot-checks seulement).
- `schemas/*` : non audités individuellement (couverture `response_model` vérifiée mécaniquement).
