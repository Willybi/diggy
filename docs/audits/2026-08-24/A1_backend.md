# A1 — Audit Backend (`server/api/` hors `alembic/`)

- **Date** : 2026-08-24
- **HEAD audité** : 52a506f (delta depuis 9b305d6, audit 2026-08-09)
- **Périmètre** : routers/services/schemas/middleware. Priorité au delta (C7 albums, C5 v2 collections, C9.b content-similar, D8 voir-plus, precompute reco/single-flight, monitoring étendu, fixes Sentry 3d31ce5, panneau artistes 6df954e/15d0f5b) ; passe légère sur le reste (déjà audité 2×).
- **Méthode** : lecture intégrale des fichiers neufs, diffs git des commits delta, croisement front (`server/frontend/src`) + workers + scripts + tests avant toute conclusion « mort ».

---

## Ce qui va bien

Points vérifiés conformes — à ne PAS re-signaler dans les audits suivants.

- **Convention d'erreurs homogène tenue à 100 %** : aucun `HTTPException` dans `server/api/services/` (grep vérifié — seules des mentions en docstring « never HTTPException »). Chaque service neuf porte le contrat en tête de module (`album_service.py:4`, `radar_service.py:4`, `recommendation_service.py:10`). Les routers mappent `LookupError`→404 / `ValueError`→400 (`routers/albums.py:19-22`, `routers/catalog.py:103-110`).
- **`response_model` présent partout** : seuls `routers/auth.py:48` (callback OAuth = RedirectResponse, légitime) et les DELETE 204 n'en portent pas. Les décorateurs multi-lignes de `collections.py:242,291` en portent bien un ou sont des 204.
- **`catalog_visible` (C3) appliqué sur toutes les surfaces NEUVES** : tracklist album (`album_service.py:54`), voisins contenu (`similarity_service.py:1385`), items track des collections (`routers/collections.py:381,415`), filtres genre D8 (dominance sets `set_service.py:119`, playlists `watchlist_service.py` genre_sub, artistes `artist_service.py` genre_artist_ids — le commentaire D8 documente même le résidu accepté).
- **Tie-break id déterministe** sur les listes neuves/modifiées : `set_service.py:163` (`DJSet.id.desc()` final, commentaire explicite sur la leçon created_at), `watchlist_service.browse` (`id.asc()`), `list_bi_score` (`radar_service.py:280` tri stable secondaire par id AVANT le tri principal), `_search_albums` (`search_service.py:294` `order_by(Album.title, Album.id)`). Les filtres D8 sont appliqués AVANT le count → `total` cohérent avec la page (`set_service.py:130`, commentaire watchlist « Placed before the count/offset »).
- **Aucun `asyncio.gather` sur session partagée dans le code neuf** : awaits séquentiels documentés et respectés (`album_service.py` étapes 1-3, `radar_service.py:187-188`, `monitoring_service.py:8-9`, `_resolve_items` docstring `collections.py:400-402`).
- **Candidat inventaire RÉFUTÉ — `GET /sets/search` n'est PAS mort** : consommé par `server/frontend/src/views/SetsView.vue:922` (modal recherche TrackID) + `POST /sets/import` à 936/955. Ne pas le re-proposer en suppression.
- **Fixes Sentry 3d31ce5 corrects** : `ensure_bucket` (`image_service.py:55-69`) n'avale QUE `BucketAlreadyOwnedByYou`/`BucketAlreadyExists` et re-lève le reste ; le guard `resolve_flag` (`artist_service.py:783-797`) vérifie le holder avant de stamper `deezer_id` (invariant #4 respecté, E1 relinkera). Tests ajoutés dans le même commit.
- **Single-flight reco bien conçu dans son principe** : lock `SET NX EX` atomique, TTL 120s > compute ~35s, release conditionnel en `finally`, fail-open Redis partout, dégradation en liste vide plutôt que 504 (`recommendation_service.py:284-321`). Cache non keyé par `limit` (une entrée sert tous les limits, invalidation 1 clé).
- **Caches Redis homogènes** : content-neighbors (`similarity_service.py:1271-1329`) suit exactement le patron similar_sets/AV3 — fail-open, TTL 6h, sérialisation via TypeAdapter pydantic, payload corrompu → recompute.
- **`get_content_neighbors` scope et bornes corrects** : exclusion du seed, filtre modèle versionné (`MODEL_NAME`/`MODEL_VERSION`), `LIMIT CONTENT_NEIGHBORS_MAX_CACHED` (24) aligné sur le plafond du router (`le=24`).
- **Schémas collections défensifs** : `CollectionItemAddIn._check_polymorphic_key` (`schemas/collections.py:22-35`) impose `item_name` pour un genre / `item_id` sinon, types restreints à la whitelist de 5. Parse CSV défensif partagé (`_parse_id_csv`/`_parse_str_csv`, jumeaux sets/watchlist).
- **Routes littérales `/collections/folders` déclarées avant `/{collection_id}`** avec commentaire expliquant le piège (`routers/collections.py:83-86`) — vérifié dans l'ordre du fichier.
- **`monitoring_service.get_backlog_counters`** : lecture snapshot défensive (`.get` en cascade, payload partiel toléré), DLQ fail-open, prédicat `to_link` aligné sur le panneau (commentaire l.461) — pas de double vérité.
- **Tests présents sur tout le delta** : `tests/api/test_collections.py`, `test_albums.py`, `test_album_model.py`, `test_services/test_similarity_content.py`, `test_recommendations.py`, + tests dans chaque commit panneau artistes.
- **Middleware allowlist à jour** : `/api/albums` ajouté en GET public (f234944, `auth_middleware.py:15`), `/api/following` et `/api/recommendations` volontairement absents (commentaires dans les routers).

---

## Findings

### [A1-01] Collections C5 v2 : toute la logique métier vit dans le router (529 lignes, zéro service)
- **Type** : archi
- **Sévérité** : moyenne
- **Effort estimé** : M
- **Confiance** : haute
- **Preuve** : `server/api/routers/collections.py` = 529 lignes (2ᵉ plus gros router après admin, `wc -l`) ; il n'existe AUCUN `services/collection_service.py` (listing de `server/api/services/`). Le router contient : dédup applicative 409 (`collections.py:257-267`), calcul de position (`:269-274`), validation polymorphe d'existence `_assert_target_exists` (`:373-392`), résolution polymorphe d'affichage `_resolve_items` (`:395-529`, ~135 lignes), orphaning explicite des collections au delete_folder (`:174-181`).
- **Constat** : viole la règle du repo « new business logic goes in a service, routers stay thin » (CLAUDE.md, Architecture) — et c'est du code NEUF (664ff41, C5 v2), pas un legacy toléré. AV6 a extrait `list_sets`, `get_backlog_counters` et set-flags des routers pour exactement cette raison ; C5 v2 recrée la dette au même endroit. Conséquences concrètes : `_resolve_items` (le cœur polymorphe, réutilisable pour de futures surfaces « collections partagées » ou un shelf Hub) n'est pas testable ni réutilisable hors HTTP, et les règles (dédup, missing=True) sont couplées aux HTTPException.
- **Recommandation** : extraction ADDITIVE façon AV6 : créer `services/collection_service.py` portant `add_item` (lève `ValueError` sur doublon → 409 au router), `_assert_target_exists` (lève `LookupError`), `_resolve_items`, `delete_folder` ; le router garde auth, 404 ownership et commits. Déplacement à comportement identique, aucun changement d'API.
- **Dépendances** : aucune.
- **Tags** : —

### [A1-02] `get_match_candidates` : N+1 (un COUNT par candidat) pour un champ `total_identified` sans consommateur prod
- **Type** : perf + mort
- **Sévérité** : basse
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** : `server/api/services/set_dedup_service.py:295-304` — boucle `for row in rows:` exécutant un `select(func.count())` par candidat pour peupler `MatchCandidate.total_identified` (`:309`). Grep exhaustif : `total_identified` n'est lu NULLE PART dans `server/` (seules occurrences = la déclaration `:222` et l'assignation `:309`) ; unique consommateur = l'assertion `tests/api/test_set_matching.py:64`.
- **Constat** : le scoring composite (IDF/date/ordre, refonte 2026-08-07) n'utilise plus ce champ — c'est un reliquat. Le coût est borné (candidats = sets partageant ≥3 tracks, typiquement peu nombreux) mais c'est un aller-retour DB par candidat exécuté à chaque import de set (funnel TrackID nocturne, ~1000-1600 sets/nuit), pour produire une valeur jetée.
- **Recommandation** : supprimer le champ `total_identified` de `MatchCandidate`, la boucle de COUNT (`:294-311` simplifiée en list-comprehension sur `rows`) et l'assertion de test associée. Si le champ devait resservir, le récupérer en une seule requête agrégée conditionnelle jointe au GROUP BY principal.
- **Dépendances** : aucune.
- **Tags** : —

### [A1-03] `similar_from_context` toujours sans caller prod — décision de suppression à acter
- **Type** : mort
- **Sévérité** : basse
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** : `server/api/services/similarity_service.py:850`. Grep repo entier : seuls consommateurs = `tests/api/test_services/test_similarity_service.py:684-740` (6 usages) + la mention « caller-less » de CLAUDE.md:52. Aucun caller dans `server/`, `workers/`, `scripts/`.
- **Constat** : déjà documenté « currently caller-less » dans CLAUDE.md depuis AV7 — l'état n'a pas changé en 2 audits (ni C9.b ni le precompute reco ne l'ont repris ; `get_content_neighbors` réutilise `_build_result_items` directement). Le corps partagé vit dans `_score_seed_against_pool` (`:809`), donc la suppression ne perd aucune logique. Garder un wrapper public testé-mais-mort entretient une fausse surface d'API interne.
- **Recommandation** : DÉCISION à arbitrer : (a) supprimer `similar_from_context` + ses 4 tests dédiés (les invariants restent couverts via `get_similar_tracks`/reco) et amender CLAUDE.md ; ou (b) le conserver explicitement comme API de composition future C9.c (fusion contenu×co-occurrence) — auquel cas le documenter comme tel et clore le sujet au LEDGER pour ne plus le re-signaler.
- **Dépendances** : à trancher avant C9.c (qui pourrait soit le ressusciter, soit confirmer la suppression).
- **Tags** : —

### [A1-04] Waiter du single-flight reco : connexion DB épinglée jusqu'à 48 s pendant le poll
- **Type** : perf
- **Sévérité** : moyenne
- **Effort estimé** : S
- **Confiance** : moyenne
- **Preuve** : `server/api/services/recommendation_service.py:311-318` — la branche waiter boucle `asyncio.sleep(1.5)` jusqu'à 48 s en ne touchant QUE Redis. Mais la requête a déjà exécuté du SQL avant d'y entrer : `get_current_user` partage la session request-scoped (`dependencies.py:16-18`, `Depends(get_db)`) et fait un SELECT user → transaction implicite ouverte → connexion checked-out pour toute la durée du poll. Pool : `database.py:10` `pool_size=10, max_overflow=5` (15/worker, 2 workers uvicorn).
- **Constat** : le scénario que le single-flight vise (stampede de cache-miss sur `/radar/feed`, mesuré 2026-08-13) est précisément celui où N waiters s'accumulent. Chaque waiter épingle une connexion idle-in-transaction pendant ≤48 s ; à >15 waiters sur un worker, le pool est épuisé et TOUTES les routes de ce worker (y compris celles sans reco) prennent des TimeoutError/500 — le remède déplacerait la panne du 504 reco vers un déni transverse. Confiance moyenne : le precompute nightly + le front dé-doublé (702dd70) rendent le stampede rare, et il faudrait >15 requêtes simultanées du MÊME cache-miss ; mais le coût du fix est trivial.
- **Recommandation** : dans la branche waiter (avant la boucle de poll), relâcher la connexion : `await db.rollback()` (la session async rend la connexion au pool en fin de transaction ; lecture seule à ce stade, aucun état perdu, la requête suivante ré-ouvre une transaction transparente). Alternative équivalente : passer le rollback dans `radar_service.list_bi_score` avant l'appel reco quand on sait qu'on peut attendre.
- **Dépendances** : aucune.
- **Tags** : —

### [A1-05] `GET /catalog/{id}/content-similar` (C9.b) : gate admin front-only, endpoint public jusqu'aux invités
- **Type** : sécu / archi (décision à ratifier)
- **Sévérité** : basse
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** : `server/api/routers/catalog.py:135-149` — `get_current_user_optional`, aucun `require_admin` ; la docstring l'assume : « JWT-optional; the shelf is admin-gated on the FRONT while embeddings coverage ramps up ». `auth_middleware.py:12` : le préfixe GET public `/api/catalog` couvre la route → accessible sans aucun token. Le gate n'existe que côté front (`TrackDetailView.test.js:236` « never renders … for a non-admin »).
- **Constat** : la roadmap/CLAUDE.md décrivent C9.b comme « gaté admin », mais le gate est purement cosmétique : n'importe quel client anonyme peut appeler l'endpoint (KNN pgvector + `_build_result_items` par (seed, viewer), cache 6h par seed×'anon'). Pas de fuite de données (catalog_visible appliqué) — le risque est (1) un coût compute/cache ouvert au scraping pendant la phase de ramp-up, (2) une divergence doc↔code du type que CLAUDE.md demande de signaler. C'est cohérent avec l'intention d'ouvrir la feature à terme, donc probablement un choix assumé — mais nulle part acté comme tel hors docstring.
- **Recommandation** : ratifier explicitement (entrée ROADMAP/LEDGER « endpoint public par design, gate front = gate produit ») OU ajouter `require_admin` temporairement le temps du ramp-up (retrait au moment du dé-gate front, 2 lignes). Le rate-limit per-IP existant borne déjà le pire cas.
- **Dépendances** : à trancher au dé-gate C9.b/C9.c.
- **Tags** : —

### [A1-06] `content-similar` renvoie 200 `[]` (et le met en cache) pour un catalog_id inexistant, là où `/similar` renvoie 404
- **Type** : dette
- **Sévérité** : basse
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** : `similarity_service.py:1363-1374` — seed absent de `track_embeddings` → `[]` caché 6h, sans distinguer « track existe mais pas encore embeddé » (cas légitime documenté) de « catalog_id inexistant ». Comparer `get_similar_tracks` (`:960+`) qui lève `LookupError` → 404 au router (`routers/catalog.py:131-132`) ; le router content-similar (`:147-149`) n'a d'ailleurs aucun try/except.
- **Constat** : incohérence de contrat entre deux endpoints jumeaux du même router. Impact faible aujourd'hui (le front n'appelle que depuis un Track Detail déjà résolu), mais l'ID inexistant pollue le cache Redis avec des entrées `content_neighbors:{id}:anon` fabricables à volonté par un client anonyme (clé par id arbitraire, TTL 6h) — un léger vecteur de remplissage combiné à A1-05.
- **Recommandation** : soit vérifier l'existence du seed (1 SELECT id) et lever `LookupError` → 404 comme `/similar` en réservant `[]` au cas « pas encore embeddé » ; soit à minima ne PAS mettre en cache le résultat vide quand le catalog_id n'existe pas.
- **Dépendances** : même arbitrage que A1-05 (peut se faire dans le même lot).
- **Tags** : —

### [A1-07] `_MAX_SEARCH_ATTEMPTS` : constante worker dupliquée à la main dans l'API (drift silencieux possible)
- **Type** : dette
- **Sévérité** : basse
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** : `server/api/services/artist_service.py:26-31` — `_MAX_SEARCH_ATTEMPTS = 3`, commentaire « MIRROR of workers.tasks.artists.ARTIST_MAX_SEARCH_ATTEMPTS (kept in sync by hand; the API must not import the workers package) ». Même patron que `_fold` dupliqué dans `monitoring_service.py:32-44` (« Local copy of workers.deezer_enrich._fold »).
- **Constat** : deuxième copie main-synced worker→API en deux chantiers. Si le seuil worker change (ex. tuning du tier résurrection 6df954e), le panneau admin « Lier » et le `dormant_count` divergent silencieusement du comportement réel du worker — aucun test ne lie les deux valeurs. La contrainte « pas d'import workers depuis l'API » est légitime, mais elle n'interdit pas un module partagé neutre (précédent existant : `trackid/reliability.py`, importé des deux côtés).
- **Recommandation** : au choix : (a) un test de cohérence qui importe les DEUX constantes et les compare (le harness de tests, lui, voit les deux packages — verrou anti-drift à coût quasi nul) ; (b) déplacer la constante dans un module partagé côté `api/` (ex. `models/` ou un `constants.py`) importé par le worker (le sens worker→api est déjà pratiqué). Idem pour `_fold` si (b).
- **Dépendances** : aucune.
- **Tags** : —

### [A1-08] Commentaire `auth_middleware` périmé : référence `/radar/full` supprimé par AV6
- **Type** : doc
- **Sévérité** : basse
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** : `server/api/auth_middleware.py:19-20` — « The other radar GET routes (/full, /new-count) expose per-user state and stay behind auth ». `GET /radar/full` a été supprimé par AV6 (f15b52c) ; les routes radar restantes sont `/trends`, `/feed`, `/new-count` (`routers/radar.py`).
- **Constat** : commentaire de sécurité qui décrit une surface qui n'existe plus — trompeur pour le prochain qui étend l'allowlist (il pourrait chercher `/full` ou croire la liste exhaustive alors que `/feed` n'y figure pas).
- **Recommandation** : réécrire le commentaire : « The other radar GET routes (/feed, /new-count) expose per-user state and stay behind auth ».
- **Dépendances** : aucune.
- **Tags** : QW-c (trivial, zéro risque — mais sévérité basse donc tag indicatif seulement).

### [A1-09] Router sets : résidu de logique métier (détail ~150 lignes, import+opinion ~70 lignes, client TrackID appelé du router)
- **Type** : dette
- **Sévérité** : basse
- **Effort estimé** : M
- **Confiance** : haute
- **Preuve** : `server/api/routers/sets.py` — `get_set_detail` `:230-376` (assemblage complet : selectinload, batch lib/artists, tracklist, top_genres) ; `import_set_url` `:156-224` (parsing slug, appel `TrackIDClient`, import, auto-like + `sync_set_opinion`, commit, dispatch Celery) ; `search_trackid_sets` `:45-81` (appel HTTP TrackID externe directement dans le router).
- **Constat** : AV6 a extrait `list_sets` vers `set_service` mais a laissé ces trois blocs — le router sets reste le seul non-admin où un client HTTP externe et une écriture d'opinion vivent dans la couche route. Passe légère assumée (zone déjà auditée 2×, code fonctionnel et testé) : signalé pour le stock de dette, PAS comme urgence. À traiter opportunistiquement, p.ex. si C9.b touche le détail set ou si A1-01 crée la dynamique d'extraction.
- **Recommandation** : extraction à comportement identique vers `set_service` (`get_detail`, `import_from_trackid`, `search_external`) sur le modèle AV6 — le service lève LookupError/ValueError et ne commit pas, le router garde 404/422 + commit.
- **Dépendances** : après A1-01 (même patron d'extraction, mutualiser la revue).
- **Tags** : —

### [A1-10] Tracklist d'album ordonnée par `catalog.id`, pas par la position sur l'album
- **Type** : dette
- **Sévérité** : basse
- **Effort estimé** : M
- **Confiance** : haute
- **Preuve** : `server/api/services/album_service.py:55` — `.order_by(CatalogEntry.id)` ; le M2M `CatalogAlbum` (`models/album.py:68-74`) n'a que `catalog_id`/`album_id`, aucune colonne de position/track_number (migration 0046 idem).
- **Constat** : l'ordre affiché sur `AlbumView` est l'ordre de création des lignes catalog — corrélé à l'ordre de crawl, pas à l'ordre du disque. Déterministe (tie-break id, bien) mais produit-faux pour un album : la piste 7 peut s'afficher première. Le funnel Deezer a la donnée (`track_position` dans les payloads tracklist) mais ne la stocke pas.
- **Recommandation** : SI l'ordre disque compte pour le produit (à arbitrer avec William) : ajouter `track_position SMALLINT NULL` sur `catalog_albums` (migration), peuplée au funnel `link_catalog_album_from_hit` + backfill via `scripts/backfill_albums.py` ; `order_by(coalesce(track_position, id))`. Sinon, acter l'ordre actuel comme résidu accepté au LEDGER.
- **Dépendances** : migration + funnel worker (coordonner avec A2 si retenu).
- **Tags** : —

---

## Candidats inventaire — verdicts

| Candidat | Verdict |
|---|---|
| `similarity_service.py:850` `similar_from_context` sans caller | CONFIRMÉ → A1-03 (décision) |
| `routers/sets.py:45` `search_trackid_sets` | RÉFUTÉ — consommé par `SetsView.vue:922` (voir « Ce qui va bien ») |
| `set_dedup_service.py:222` `total_identified` | CONFIRMÉ, aggravé d'un N+1 → A1-02 |

## Résidus acceptés — rien à réévaluer

Taxonomy (11 endpoints), `/storage/*` non authentifié, Redis sync middleware, upsert import RB par piste, pool C10 conditionnel, agrégats/tracklists sans catalog_visible, endpoints admin curl-only : tous revérifiés inchangés, aucun changement matériel → non re-signalés.
