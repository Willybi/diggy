# Audit 2026-07 — A1 : Backend (`server/api/` hors alembic)

- **Date** : 2026-07-09
- **Agent** : A1 (Backend)
- **Périmètre** : `server/api/` hors `alembic/` — routers, services (inspections ciblées), modèles, fichiers racine (`main.py`, `catalog.py`, `opinion_sync.py`, `dependencies.py`, `auth_middleware.py`).
- **Méthode** : lecture intégrale des 14 routers + `main.py`, `dependencies.py`, `models/__init__.py`, `auth_middleware.py`, `catalog.py`, `opinion_sync.py` ; croisement systématique de chaque endpoint candidat mort de `_inventory.md` §5/§6 avec grep exhaustif sur frontend (`server/frontend/src`), workers (`server/workers`), scripts (`server/api/scripts`, `server/scripts`, `worker/`, `scripts/`) et tests (`tests/`). Aucune modification hors ce rapport.

---

## Ce qui va bien

Points structurants vérifiés et respectés — à ne PAS re-signaler comme problèmes :

- **Routers minces conformes** pour `radar.py`, `catalog.py`, `genres.py`, `artists.py` : délégation quasi totale aux services, avec un pattern d'erreur homogène `except LookupError → HTTPException(404)` / `ValueError → 400/409` (ex. `routers/genres.py:88-91`, `routers/catalog.py:111-114`, `routers/artists.py:68-71`).
- **`response_model` quasi systématique** : sur les 103 endpoints extraits, une seule exception trouvée (voir A1-19).
- **Split `models/` complet et cohérent** : `models/__init__.py` réexporte les 27 classes depuis 10 modules, aucun import circulaire constaté, aucun modèle orphelin dans le package. Vulture sur `GenreNode` (§2 inventaire) = faux positif confirmé (utilisé via SQL brut dans `taxonomy.py` et via `genre_service`).
- **`dependencies.py` propre** : `uid()` retourne bien `None` pour les guests, pas de fallback `user_id=1` résiduel trouvé nulle part.
- **`main.py` sain** : exception handler global, logs JSON, Sentry optionnel, `create_all` désactivé en production (`main.py:54`).
- **Audit log admin réellement utilisé** : `_audit()` appelé sur les actions destructives (merge artiste, detach set, reset beatport…).
- **`health` (main.py:105)** n'est PAS du code mort : c'est le healthcheck — le hit vulture §2 est à écarter.
- Ruff : 0 violation (inventaire §1).

---

## Findings

### [A1-01] `routers/search.py` est une couche service déguisée en router
- **ID** : A1-01
- **Type** : archi
- **Sévérité** : moyenne
- **Effort estimé** : M
- **Confiance** : haute
- **Preuve** : `server/api/routers/search.py` — 365 LOC pour 1 endpoint. Cinq fonctions métier privées dans le module router : `_search_tracks` (l.42), `_search_artists` (l.93), `_search_sets` (l.161), `_search_playlists` (l.206), `_search_genres` (l.241), plus le scoring `_relevance` (l.30).
- **Constat** : toute la logique de recherche multi-entités (requêtes, scoring, cap guest) vit dans le router. La règle projet (CLAUDE.md : « new business logic goes in a service, routers stay thin ») est violée. C'est le seul domaine avec `watchlist` (A1-05) sans service.
- **Recommandation** : extraire les helpers vers `services/search_service.py`, le router ne gardant que la validation des query params et l'appel au service. Aucun changement de comportement.
- **Dépendances** : A1-02 (à corriger dans le même mouvement)
- **Tags** : —

### [A1-02] `/search` : pagination cassée au-delà de la page 1 et ordre DB non déterministe
- **ID** : A1-02
- **Type** : bug
- **Sévérité** : moyenne
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** : `server/api/routers/search.py:72` (`rows = (await db.execute(base.limit(limit))).all()` — aucun `ORDER BY`), idem l.109, l.189, l.224 ; puis l.364 : `page = all_items[offset : offset + limit]`.
- **Constat** : chaque helper tronque en DB à `per_type_limit` résultats **sans ORDER BY**, puis l'endpoint applique `offset` en mémoire sur cette liste déjà tronquée. Conséquences : (1) `offset >= limit` retourne toujours `[]` même si `total` annonce des centaines de résultats ; (2) quand plus de `limit` lignes matchent, le sous-ensemble retourné est arbitraire (ordre de scan PostgreSQL) — le tri par pertinence (l.348) ne s'applique qu'aux lignes déjà arbitrairement sélectionnées.
- **Recommandation** : ajouter un `ORDER BY` stable dans chaque helper (pertinence SQL ou popularité + id), et soit pousser `offset` dans les requêtes, soit documenter que `offset` n'est pas supporté et le retirer de la signature.
- **Dépendances** : A1-01
- **Tags** : —

### [A1-03] `GET /sets/{id}` : `in_lib` calculé sans filtre `user_id` (fuite inter-utilisateurs)
- **ID** : A1-03
- **Type** : bug
- **Sévérité** : haute
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** : `server/api/routers/sets.py:264-267` :
  ```python
  lib_result = await db.execute(
      select(UserTrack.catalog_id).where(UserTrack.catalog_id.in_(catalog_ids))
  )
  ```
  L'endpoint `get_set_detail` (l.233) n'a d'ailleurs aucune dépendance user (`get_current_user_optional` absent de la signature l.234).
- **Constat** : le flag `in_lib` de chaque track d'un set reflète l'union des bibliothèques de TOUS les utilisateurs, pas celle de l'utilisateur courant. Un guest voit `in_lib=true` sur les tracks possédés par n'importe qui. Violation de l'invariant multi-user du projet (« every user-conditional query must handle None »). À comparer avec `search.py:51` et `sets.py` n'importe où ailleurs où `UserTrack.user_id == user_id` est bien filtré.
- **Recommandation** : ajouter `user: User | None = Depends(get_current_user_optional)` et filtrer `UserTrack.user_id == uid` (avec `in_lib=False` pour les guests, comme dans `search.py:87`).
- **Dépendances** : aucune
- **Tags** : QUICK-WIN-CANDIDAT

### [A1-04] I/O synchrone bloquante (requests, MinIO) dans des endpoints async
- **ID** : A1-04
- **Type** : perf
- **Sévérité** : moyenne
- **Effort estimé** : M
- **Confiance** : haute
- **Preuve** :
  - `server/api/routers/admin.py:113-120` : `import requests as req` + `req.get("https://api.deezer.com/search/artist", timeout=5)` dans `async def search_deezer_artist`.
  - `server/api/routers/watchlist.py:41` : `requests.get(f"{DEEZER_API}/playlist/{external_id}", timeout=5)` (appelé depuis les endpoints async `add_watched` l.224 et `fetch_playlist_artwork` l.394).
  - `server/api/routers/watchlist.py:65` : `ImageService.upload_from_url(...)` (download HTTP + upload MinIO synchrones) dans le flux async.
  - `server/api/routers/tracks.py:83,153` : `ImageService.upload_file(...)` synchrone dans la boucle de `bulk_import` async.
- **Constat** : ces appels réseau synchrones bloquent l'event loop uvicorn jusqu'à 5 s par appel (et N fois dans la boucle de `bulk_import`). Pendant ce temps, TOUTES les requêtes de l'instance sont gelées. `httpx` est déjà une dépendance transitive du projet (inventaire §3) et le worker a déjà un client async (`workers/async_http.py`).
- **Recommandation** : remplacer par `httpx.AsyncClient` (ou `run_in_executor` pour MinIO), en commençant par les deux endpoints Deezer qui partent sur Internet.
- **Dépendances** : aucune
- **Tags** : —

### [A1-05] `routers/watchlist.py` : 435 LOC de logique métier sans couche service
- **ID** : A1-05
- **Type** : archi
- **Sévérité** : moyenne
- **Effort estimé** : M
- **Confiance** : haute
- **Preuve** : `server/api/routers/watchlist.py` — helpers métier dans le router : `_fetch_deezer_playlist` (l.38), `_upload_playlist_artwork` (l.57), `_trigger_crawl` (l.70) ; logique de cooldown 12 h inline (l.300-310) ; gestion d'état de task Celery avec expiration 15 min inline (l.353-374) ; création d'entité + follow + artwork inline (l.207-253). Aucun import de `services.*` hormis `ImageService`.
- **Constat** : c'est, avec `search.py` (A1-01), le seul domaine sans service. Le fichier mélange intégration Deezer, stockage MinIO, orchestration Celery et règles métier (cooldown, staleness). La duplication follow-check/follow-create entre `add_watched` (l.212-248) et `follow_playlist` (l.269-280) en découle.
- **Recommandation** : extraire un `services/watchlist_service.py` (métadonnées Deezer, artwork, trigger crawl, cooldown). À combiner avec A1-04 pour l'async.
- **Dépendances** : A1-04
- **Tags** : —

### [A1-06] Endpoint mort : `PATCH /watchlist/{id}/crawled`
- **ID** : A1-06
- **Type** : dead-code
- **Sévérité** : basse
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** : défini à `server/api/routers/watchlist.py:316`. Grep exhaustif `crawled` sur tout le repo : aucun appel frontend, aucun appel worker (le worker écrit `entity.last_crawled_at` directement en DB — `server/workers/tasks/radar.py:349`), aucun test, aucun script. Seuls hits : la définition et l'inventaire d'audit.
- **Constat** : l'endpoint date probablement d'un flux où le worker notifiait l'API par HTTP ; ce flux a été remplacé par l'écriture DB directe. Il reste exposé, authentifié mais sans contrôle d'ownership (n'importe quel user connecté peut réinitialiser `current_task_id` d'une playlist).
- **Recommandation** : supprimer l'endpoint et son schema de réponse si non partagé. Preuve mécanique complète (grep frontend + workers + scripts + tests = 0 appelant).
- **Dépendances** : aucune
- **Tags** : QUICK-WIN-CANDIDAT

### [A1-07] `GET /watchlist/` (list_watched) : appelé uniquement par les tests
- **ID** : A1-07
- **Type** : dead-code
- **Sévérité** : basse
- **Effort estimé** : S
- **Confiance** : moyenne
- **Preuve** : défini à `server/api/routers/watchlist.py:83`. Le frontend n'appelle que `/browse`, `/{id}`, `/{id}/crawl-status`, `/{id}/follow`, `/{id}/crawl`, `/{id}/fetch-artwork`, `POST /`, `DELETE /{id}` (grep `watchlist` dans `server/frontend/src` : `WatchlistView.vue:266,301,317,338`, `PlaylistDetailView.vue:233-290`). `GET /api/watchlist/` n'apparaît que dans `tests/api/test_watchlist.py:48,58,203`.
- **Constat** : la vue « mes playlists suivies » du frontend passe par `/browse` (qui porte le flag `followed`). `GET /` est fonctionnel mais sans consommateur produit.
- **Recommandation** : décision produit : soit le frontend devrait l'utiliser pour un onglet « suivies seulement », soit le supprimer avec ses tests. Confiance moyenne (les tests l'utilisent comme proxy pour tester le follow).
- **Dépendances** : aucune
- **Tags** : —

### [A1-08] Router `tracks` (350 LOC, 5 endpoints) : seuls appelants = script legacy `worker/` et tests
- **ID** : A1-08
- **Type** : dette
- **Sévérité** : moyenne
- **Effort estimé** : M
- **Confiance** : moyenne
- **Preuve** :
  - Frontend : grep `api/tracks|'/tracks|"/tracks` dans `server/frontend/src` → un seul hit, une redirection : `router.js:25 { path: '/tracks', redirect: '/catalog?inlib=true' }`. Zéro appel API.
  - Le chemin d'import actuel (`workers/tasks/import_rb.py:86-94,127`) écrit `UserTrack` directement en DB, sans passer par `/tracks/bulk` ni `/existing-ids`.
  - Seuls appelants réels : `worker/import_rekordbox.py:31,69` (dossier `worker/` singulier à la racine du repo, identifié legacy par l'inventaire §11, derniers commits 2026-06-01/05) et `tests/api/test_tracks.py` + `test_import_multiuser.py` + `test_integration.py`.
- **Constat** : les 5 endpoints (`/existing-ids`, `POST /bulk`, `/tags`, `GET /`, `GET /{id}`) ne servent plus que l'ancien script d'import desktop. `GET /tags` servait la `TagsView` déjà identifiée morte dans CLAUDE.md. `bulk_import` contient en outre ~150 LOC de logique métier dans le router (upsert catalog + artwork), en violation de la règle service.
- **Recommandation** : trancher le sort du flux d'import legacy `worker/import_rekordbox.py` (question pour l'orchestrateur/A5). Si le flux XML est le seul officiel : déprécier le router `tracks` entier. Si le script est conservé : extraire au minimum `bulk_import` vers un service. Ne PAS supprimer sans cette décision (asymétrie).
- **Dépendances** : aucune (coordination avec l'agent qui audite `worker/`)
- **Tags** : hors-domaine:scripts

### [A1-09] `tracks.py` : bloc d'upload artwork copié-collé à l'identique
- **ID** : A1-09
- **Type** : dette
- **Sévérité** : basse
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** : `server/api/routers/tracks.py:76-94` et `tracks.py:146-164` — deux blocs de 19 lignes identiques (base64 decode → NamedTemporaryFile → `ImageService.upload_file` → cleanup), y compris le `import logging` local dupliqué (l.87 et l.157).
- **Constat** : duplication interne stricte dans `bulk_import`, branche UPDATE vs INSERT.
- **Recommandation** : extraire une fonction `_upload_artwork(rb_id, image_base64) -> bool`. (Si A1-08 aboutit à une suppression du router, ce finding devient sans objet.)
- **Dépendances** : A1-08
- **Tags** : QUICK-WIN-CANDIDAT

### [A1-10] Logique de dedup de sets codée dans `routers/admin.py` au lieu de `set_dedup_service`
- **ID** : A1-10
- **Type** : archi
- **Sévérité** : moyenne
- **Effort estimé** : M
- **Confiance** : haute
- **Preuve** : `server/api/routers/admin.py:379-458` (`attach_set_flag` : ~60 lignes de logique — choix du parent, rattachement des membres au-delà de la première paire l.416-420, matérialisation) et `admin.py:495-529` (`detach_set` : détachement + gestion des siblings + suppression du parent l.516-523).
- **Constat** : le service `services/set_dedup_service.py` (1082 LOC) existe et expose déjà `find_or_create_virtual_parent` / `materialize_parent`, mais l'orchestration attach/detach (règles « ≥2 membres », « dernier sibling → détacher et supprimer le parent ») vit dans le router. Contraste net avec le reste d'`admin.py` qui délègue correctement (`artist_service.link_to_deezer` l.143, `resolve_flag` l.232, etc.).
- **Recommandation** : déplacer les corps de `attach_set_flag` et `detach_set` dans `set_dedup_service` (ex. `attach_flag(db, flag, admin_id)`, `detach_set(db, set_id)`), le router gardant 404/audit/commit.
- **Dépendances** : A1-11
- **Tags** : lié-chantier:C6

### [A1-11] `detach_set` supprime le parent sans vérifier `is_virtual`
- **ID** : A1-11
- **Type** : bug
- **Sévérité** : basse
- **Effort estimé** : S
- **Confiance** : moyenne
- **Preuve** : `server/api/routers/admin.py:520-523` :
  ```python
  if len(siblings) <= 1:
      if len(siblings) == 1:
          siblings[0].parent_set_id = None
      await db.execute(sa_delete(DJSet).where(DJSet.id == parent_id))
  ```
  Aucune condition `DJSet.is_virtual` — alors que `set_dedup_service` ne crée des parents que virtuels (`set_dedup_service.py:863 is_virtual=True`) mais que rien ne l'impose au niveau du modèle.
- **Constat** : aujourd'hui tous les parents créés par le service sont virtuels, donc le DELETE est sain en pratique. Mais si un futur chemin (C6.x parts, script, SQL manuel) attache des enfants à un set réel, ce endpoint supprimerait silencieusement un vrai set avec ses `set_tracks` — exactement le type de corruption que l'invariant n°4 (« bad merges are expensive ») veut éviter.
- **Recommandation** : ajouter la garde `DJSet.is_virtual.is_(True)` au `sa_delete` (une ligne) — le parent réel orphelin serait alors simplement conservé.
- **Dépendances** : A1-10 (même zone de code)
- **Tags** : QUICK-WIN-CANDIDAT | lié-chantier:C6

### [A1-12] Taxonomy : 8 endpoints sur 11 sans aucun appelant
- **ID** : A1-12
- **Type** : dead-code
- **Sévérité** : moyenne
- **Effort estimé** : S
- **Confiance** : moyenne
- **Preuve** : définis dans `server/api/routers/taxonomy.py` : `GET /nodes/{id}` (l.61), `/children` (l.74), `/parents` (l.113), `/ancestors` (l.143), `/descendants` (l.176), `/neighbors` (l.209), `/roots` (l.247), `/stats` (l.267). Grep frontend : seuls `/api/taxonomy/mappings` (x3) et `/api/taxonomy/nodes` sont appelés (`AdminGenres.vue:177-217`). Grep tests : `tests/api/test_genres_unit.py` matche « taxonomy » mais aucun appel `api/taxonomy` (grep `api/taxonomy` dans le fichier → 0 hit). Grep repo-wide `taxonomy/(nodes/|roots|stats)` : uniquement docs (`BRIEF_DESIGN_GENRES.md` — archive frozen) et l'inventaire. Le endpoint frontend `GenreDetailView.vue:514` appelle `/api/genres/neighbors/...` (autre router).
- **Constat** : ces 8 endpoints (dont 2 CTE récursives soignées) ont été construits pour le brief design Genres (archivé dans `docs/completed/`) mais la version livrée du frontend ne les consomme pas. Ils sont publics (préfixe `/api/taxonomy` dans `_PUBLIC_GET_PREFIXES`, `auth_middleware.py:17`), non testés (cohérent avec le coverage 43 % du fichier).
- **Recommandation** : décision produit : les brancher (exploration du graphe de genres, prévue par le brief) ou les supprimer. En cas de suppression : retirer aussi les 4 schemas dédiés (`TaxonomyEdgeNodeList`, `TaxonomyDepthNodeList`, `TaxonomyNeighborNodeList`, `TaxonomyStats`). Confiance moyenne car ce sont des GET publics potentiellement appelés hors repo (curl, notebooks).
- **Dépendances** : aucune
- **Tags** : —

### [A1-13] Endpoint mort : `POST /genres/refresh-pillars` (+ cache par process)
- **ID** : A1-13
- **Type** : dead-code
- **Sévérité** : basse
- **Effort estimé** : S
- **Confiance** : moyenne
- **Preuve** : défini à `server/api/routers/genres.py:171-179`. Grep repo-wide `refresh-pillars|refresh_pillars` : aucun hit frontend, aucun test, aucun script — seulement la définition et l'inventaire.
- **Constat** : outil admin jamais branché dans l'UI ni testé. Note fonctionnelle : il vide `_PILLAR_CACHE`, un dict au niveau module (`genres.py:177`) — avec plusieurs workers uvicorn, seul le process qui reçoit la requête est rafraîchi ; l'endpoint ne peut donc pas tenir sa promesse en multi-process.
- **Recommandation** : supprimer, ou le brancher dans AdminGenres ET documenter la limite multi-process (voire invalider via Redis). Confiance moyenne (usage curl admin possible).
- **Dépendances** : aucune
- **Tags** : —

### [A1-14] Endpoints admin sans UI : `POST /reset-beatport` et `POST /artists/backfill-multi-artists`
- **ID** : A1-14
- **Type** : dead-code
- **Sévérité** : basse
- **Effort estimé** : S
- **Confiance** : basse
- **Preuve** : définis à `server/api/routers/admin.py:547` et `admin.py:100`. Grep repo-wide `reset-beatport|backfill-multi-artists` : aucun hit dans `server/frontend/src` (les composants `components/admin/*` n'y font pas référence), aucun test, aucun script.
- **Constat** : deux actions admin destructive/lourde accessibles uniquement par curl. `reset-beatport` est auditée (`_audit` l.554) donc conçue pour un usage réel ; `backfill-multi-artists` est un simple `send_task`.
- **Recommandation** : confiance basse pour toute suppression (outillage admin volontairement hors UI plausible). Demander à l'owner : si usage curl assumé, les documenter ; sinon supprimer.
- **Dépendances** : aucune
- **Tags** : —

### [A1-15] Logique métier à la racine d'`api/` : `catalog.py` et `opinion_sync.py` hors de `services/`
- **ID** : A1-15
- **Type** : convention
- **Sévérité** : basse
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** : `server/api/catalog.py` (53 LOC, `get_or_create_catalog` — dedup ISRC/normalized_key) importé par `services/radar_service.py:293`. `server/api/opinion_sync.py` (151 LOC, sync opinions↔follows↔avis) importé par `services/catalog_service.py:563`, `services/radar_service.py:213,248` et `routers/opinions.py:5`.
- **Constat** : ce n'est PAS du code mort (contrairement à ce que leur emplacement laisse craindre) — c'est de la logique métier partagée qui vit à la racine du package au lieu de `services/`. Le docstring d'`opinion_sync` le décrit d'ailleurs comme du « shared sync logic ». Risque : un futur refactor le prend pour un vestige (il a failli l'être dans cet audit).
- **Recommandation** : déplacer vers `services/catalog_dedup_service.py` (ou fusionner dans `catalog_service`) et `services/opinion_sync_service.py`, mise à jour mécanique des 6 imports. Zéro changement de comportement.
- **Dépendances** : aucune
- **Tags** : QUICK-WIN-CANDIDAT

### [A1-16] Membres privés de `genre_service` importés par 3 routers
- **ID** : A1-16
- **Type** : convention
- **Sévérité** : basse
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** : `routers/search.py:18 from services.genre_service import _ensure_pillar_cache, genre_pillar` ; `routers/catalog.py:19` (idem) ; `routers/genres.py:24-27 from services.genre_service import _PILLAR_CACHE, _load_pillar_cache`.
- **Constat** : trois routers manipulent l'état interne préfixé `_` du service (cache des pillars), y compris une mutation directe (`_PILLAR_CACHE.clear()` dans `genres.py:177`). Le contrat public/privé du service n'existe plus de fait.
- **Recommandation** : exposer une API publique (`genre_service.ensure_pillar_cache(db)`, `genre_service.refresh_pillar_cache(db)`) et renommer/encapsuler le reste.
- **Dépendances** : A1-13 (refresh-pillars touche le même cache)
- **Tags** : —

### [A1-17] Le worker radar appelle l'API par HTTP via un endpoint ouvert à tous
- **ID** : A1-17
- **Type** : archi
- **Sévérité** : moyenne
- **Effort estimé** : M
- **Confiance** : haute
- **Preuve** : `server/workers/tasks/radar.py:36 requests.get(f"{API_BASE}/api/watchlist/active", timeout=10)` ; endpoint défini sans dépendance user (`routers/watchlist.py:102-115`) et exempté d'auth toutes méthodes dans `auth_middleware.py:29` (`_OPEN_PREFIXES` contient `"/api/watchlist/active"`).
- **Constat** : unique cas où un worker consomme l'API par HTTP — toutes les autres tâches accèdent à la DB directement (`workers/db.py`). Coûts : (1) l'endpoint doit rester public → n'importe quel guest peut lister les playlists suivies (donnée peu sensible mais incohérente : `GET /watchlist/browse` équivalent est, lui, derrière JWT) ; (2) `crawl_radar` échoue si l'API est down alors que la DB est up ; (3) l'exemption `_OPEN_PREFIXES` est un cas particulier de sécurité à maintenir.
- **Recommandation** : remplacer l'appel HTTP par une requête directe dans le worker (la requête EXISTS de `list_active_playlists` tient en 8 lignes SQLAlchemy sync dans `workers/db.py`), puis retirer l'endpoint ET son entrée `_OPEN_PREFIXES`.
- **Dépendances** : aucune
- **Tags** : hors-domaine:workers

### [A1-18] `taxonomy.py` : SQL brut intégral + réponses camelCase, à rebours du reste de l'API
- **ID** : A1-18
- **Type** : convention
- **Sévérité** : basse
- **Effort estimé** : M
- **Confiance** : haute
- **Preuve** : `server/api/routers/taxonomy.py` — 100 % des 11 endpoints en `text(...)` (ex. l.35-53, l.88 avec f-string `{type_filter}`, l.310 f-string `{where}`), zéro usage des modèles `GenreNode`/`GenreEdge`/`GenreMapping` pourtant existants. Clés de réponse camelCase : `wikidataId` (l.56), `rawName`, `nodeId`, `nodeLabel` (l.332-336) — alors que tout le reste de l'API répond en snake_case (`has_artwork`, `track_count`…).
- **Constat** : les f-strings n'injectent que des littéraux internes (pas d'injection SQL), mais le pattern est fragile au copier-coller. L'incohérence camelCase/snake_case oblige le frontend à jongler entre deux conventions selon l'endpoint.
- **Recommandation** : au minimum, documenter l'exception camelCase dans les schemas ; si A1-12 aboutit à ne garder que 3 endpoints, migrer ces 3 vers l'ORM devient un chantier S.
- **Dépendances** : A1-12 (trancher d'abord ce qui survit)
- **Tags** : —

### [A1-19] `GET /opinions/` sans `response_model` + validation manuelle redondante avec Pydantic
- **ID** : A1-19
- **Type** : convention
- **Sévérité** : basse
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** : `server/api/routers/opinions.py:15 @router.get("/")` — seul endpoint du backend sans `response_model` (retourne un dict brut l.25-28). Et `opinions.py:40-43` : validation à la main de `entity_type`/`opinion` par `HTTPException(422)` alors que le schema `OpinionUpdate` pourrait porter des `Literal` (pattern utilisé partout ailleurs, ex. `radar.py:88`, `admin.py:212`).
- **Constat** : double système de validation dans le même fichier ; la doc OpenAPI de `GET /opinions/` est vide de type.
- **Recommandation** : typer la réponse (`dict[str, dict[str, str]]` via un schema) et déplacer la validation dans `OpinionUpdate` avec `Literal["artist","set","playlist","genre","track"]` et `Literal["liked","disliked"] | None`.
- **Dépendances** : A1-20
- **Tags** : QUICK-WIN-CANDIDAT

### [A1-20] `PATCH /opinions/` : `int(entity_key)` non protégé → 500 sur clé non numérique
- **ID** : A1-20
- **Type** : bug
- **Sévérité** : basse
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** : `server/api/routers/opinions.py:75,77,79` : `await sync_set_opinion(db, uid, int(body.entity_key), body.opinion)` — `entity_key` est un `str` libre ; pour `entity_type` ∈ {set, playlist, track}, `int("abc")` lève `ValueError`, attrapée seulement par le handler global → 500 « Internal server error » au lieu d'un 422.
- **Constat** : un payload `{"entity_type": "track", "entity_key": "abc", "opinion": "liked"}` produit un 500 (et une ligne d'erreur Sentry/logs) pour une simple erreur de saisie client.
- **Recommandation** : valider `entity_key.isdigit()` pour les types numériques (ou validator Pydantic conditionnel) et répondre 422.
- **Dépendances** : A1-19 (même refactor de validation)
- **Tags** : QUICK-WIN-CANDIDAT

### [A1-21] Bucket `playlist-artworks` défini en dur à 3 endroits
- **ID** : A1-21
- **Type** : dette
- **Sévérité** : basse
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** : `server/api/services/image_service.py:22 BUCKET_PLAYLIST = "playlist-artworks"` (la constante canonique) ; `server/api/routers/watchlist.py:35 PLAYLIST_ARTWORK_BUCKET = "playlist-artworks"` (redéfinition locale) ; `server/workers/tasks/radar.py:211,213` (littéral en dur, deux fois).
- **Constat** : trois sources de vérité pour le même nom de bucket MinIO. Un renommage en raterait deux.
- **Recommandation** : importer `BUCKET_PLAYLIST` depuis `image_service` dans `watchlist.py` et `workers/tasks/radar.py` ; supprimer les redéfinitions.
- **Dépendances** : aucune
- **Tags** : QUICK-WIN-CANDIDAT

### [A1-22] Divergences documentation : `deezer_enrich.py` mal situé dans CLAUDE.md ; `image_service` référence un `storage.py` disparu
- **ID** : A1-22
- **Type** : dead-doc
- **Sévérité** : basse
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** : CLAUDE.md (section Architecture) liste `server/api/deezer_enrich.py  # Deezer search + enrichment` — or ce fichier n'existe pas : `Glob server/api/deezer_enrich.py` → 0 résultat ; le module réel est `server/workers/deezer_enrich.py` (importé par `workers/enrichment.py:54`, `workers/tasks/artists.py:744`, `server/api/scripts/enrich_catalog_deezer.py:28`). Par ailleurs `server/api/services/image_service.py:4` : « Replaces the duplicated S3 code in storage.py and deezer_enrich.py » — `server/api/storage.py` n'existe plus (Glob → 0).
- **Constat** : conformément à la consigne de CLAUDE.md lui-même (« If you notice a divergence… SAY SO »), signalement explicite : l'arborescence documentée est fausse pour ce module, et un docstring pointe vers un fichier supprimé.
- **Recommandation** : corriger la ligne dans CLAUDE.md (`workers/deezer_enrich.py`), rafraîchir le docstring d'`image_service.py`.
- **Dépendances** : aucune
- **Tags** : QUICK-WIN-CANDIDAT

### [A1-23] `GET /auth/me` : aucun appelant frontend
- **ID** : A1-23
- **Type** : dead-code
- **Sévérité** : basse
- **Effort estimé** : S
- **Confiance** : basse
- **Preuve** : défini à `server/api/routers/auth.py:134`. Grep `auth/me|'/me'` dans `server/frontend/src` → 0 hit ; `stores/auth.js` (lu en entier) construit `user` depuis le payload du cookie callback et le persiste en localStorage, sans jamais rafraîchir via `/me`. Seuls appelants : `tests/api/test_auth.py:89-100`.
- **Constat** : endpoint d'introspection standard, testé, mais non consommé. Effet de bord notable : le frontend ne rafraîchit JAMAIS l'objet user — un passage `is_admin: false→true` en DB n'est visible qu'après re-login.
- **Recommandation** : garder (endpoint d'auth standard, utile debug/curl, marqué « GARDER » dans `docs/completed/F3_GOOGLE_OAUTH_PROMPT.md:24`) — mais envisager côté frontend de l'appeler au boot pour rafraîchir `user`. Suppression déconseillée.
- **Dépendances** : aucune
- **Tags** : hors-domaine:frontend

### [A1-24] Badge radar « new-count » silencieusement mort : appel sans préfixe `/api`
- **ID** : A1-24
- **Type** : bug
- **Sévérité** : haute
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** : `server/frontend/src/utils/api.js:7` : `baseURL: '/'` ; `server/frontend/src/components/BottomNav.vue:58` : `api.get('/radar/new-count')` → requête réelle `GET /radar/new-count` (sans `/api`). Le backend monte le router sur `/api` (`main.py:92 app.include_router(radar.router, prefix="/api")`). En prod, `/radar/new-count` ne matche pas `^~ /api/` → Nginx sert l'index.html du SPA en 200 → `res.data` est du HTML → `res.data.count ?? 0` = 0, et le `catch` (l.60) masquerait toute erreur.
- **Constat** : le badge de nouveaux tracks du BottomNav (feature R1 documentée dans la mémoire projet) affiche toujours 0, sans erreur ni log, à chaque changement de route. Tous les autres appels du frontend utilisent le préfixe `/api/...` explicite — c'est le seul oubli (grep `api.get('/` sur src : un seul hit sans `/api`).
- **Constat bis** : trouvé pendant l'audit backend en croisant les appels frontend ; le fix est frontend.
- **Recommandation** : `api.get('/api/radar/new-count')` — une ligne. À vérifier ensuite en prod (badge > 0 pour un user avec du nouveau radar).
- **Dépendances** : aucune
- **Tags** : QUICK-WIN-CANDIDAT | hors-domaine:frontend

### [A1-25] `POST /sets/import` réimplémente le like→follow au lieu d'utiliser `opinion_sync`
- **ID** : A1-25
- **Type** : dette
- **Sévérité** : basse
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** : `server/api/routers/sets.py:196-219` — création manuelle de `UserOpinion` + `UserSetFollow` ; le commentaire l.195 (« Auto-like (which also auto-follows via _sync_set_follow) ») référence même un helper qui n'est pas utilisé (et n'existe plus sous ce nom). La logique canonique est `opinion_sync.sync_set_opinion` (`server/api/opinion_sync.py:95`), dont le docstring du module exige que « every router uses the same code path ».
- **Constat** : duplication de la logique d'opinion que `opinion_sync.py` a justement été créé pour centraliser. Si la règle de sync évolue (ex. liked → aussi UserRadarState), ce chemin divergera.
- **Recommandation** : remplacer le bloc par la création du `UserOpinion` + appel `sync_set_opinion(db, user.id, dj_set.id, "liked")` (ou enrichir `opinion_sync` d'un helper `like_set`). Corriger le commentaire mensonger.
- **Dépendances** : A1-15 (si `opinion_sync` déménage dans `services/`)
- **Tags** : QUICK-WIN-CANDIDAT

---

## Non couvert (budget contexte)

Rapport honnête sur les angles NON instruits — à couvrir par un passage ultérieur ou d'autres agents :

- **Intérieur des services** : `genre_service.py` (681 LOC, 25 % coverage), `artist_service.py` (679), `catalog_service.py` (633), `set_dedup_service.py` (1082) n'ont fait l'objet que d'inspections ciblées (usages croisés, `is_virtual`), pas d'une lecture ligne à ligne. Le coverage 25 % de `genre_service` mériterait une instruction dédiée.
- **`beatport/`, `trackid/`, `deezer/`** (clients externes) : non lus, hors spot-checks.
- **`routers/auth.py` et `routers/import_rb.py`** : non relus en détail (le flux OAuth a été audité récemment — F3 — et documenté dans CLAUDE.md ; je n'ai vérifié que l'usage de `/me`).
- **`rate_limit.py`, `schemas/*`** : non audités (bien couverts par les tests d'après l'inventaire §4).
- **`server/api/scripts/*`** (10 scripts one-shot) : usage/actualité non instruits — recoupe le périmètre hygiène repo (A5 ?).
- Les candidats vulture restants à 60 % (hors ceux traités ici) n'ont pas tous été arbitrés individuellement ; les hits sur colonnes SQLAlchemy et endpoints FastAPI sont des faux positifs structurels confirmés par échantillonnage.
