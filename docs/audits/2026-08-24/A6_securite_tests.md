# A6 — Sécurité & tests (audit 2026-08-24)

Périmètre : auth/authz `server/api/`, injection, secrets (delta), rate limiting des nouveaux
endpoints, deps, couverture des chemins critiques. **Priorité au delta 9b305d6 → 52a506f
(102 commits, depuis 2026-08-09)** : C7 albums, C9.a/C9.b embeddings, C5 v2 collections,
D8 voir-plus, C8 fiabilité sets, monitoring étendu, fixes Sentry.

## Ce qui va bien

- **Admin intégralement gaté** : `routers/admin.py` compte 29 routes et 29 `Depends(require_admin)`
  (vérifié par comptage mécanique) — les ajouts du delta (monitoring embeddings 1987fa3, backlog
  albums a6b5f77, tuile sets non fiables 879ed09, panneau flags artistes 15d0f5b/ef3afd2) sont tous
  dedans. `/api/admin` est en plus hors allowlist publique du middleware ET rate-limité (60/60s).
- **Ownership collections strict dans le code** : toutes les routes `collections.py` (collections,
  items, folders, assignation dossier) passent par `_get_user_collection`/`_get_user_folder` qui
  filtrent `user_id == user.id` et 404ent sinon (`routers/collections.py:343-370`) ; le
  `PATCH /{id}/folder` vérifie l'ownership des DEUX côtés (l.221-223). `POST /items` valide la cible
  (`_assert_target_exists`) avec `catalog_visible` pour un track (l.379-381), et la résolution
  d'items (`_resolve_items`, l.413-417) re-filtre les tracks par `catalog_visible` → un track privé
  étranger ressort `missing=True`, jamais ses métadonnées. Dédup 409 présente et testée.
- **C3 respecté sur toutes les surfaces neuves** : tracklist album (`album_service.get_detail`,
  l.54), voisins « sonne comme » (`similarity_service.get_content_neighbors`, l.1385), filtres D8
  (semi-join genre artistes avec `catalog_visible`, sous-requête dominance watchlist avec
  `catalog_visible` DANS la sous-requête — commit d687b76). Tests 2-users présents pour la
  visibilité album (`tests/api/test_albums.py::test_guest_never_sees_foreign_private_track`,
  `test_third_party_user_does_not_see_foreign_private_track`) et pour les voisins contenu
  (`tests/api/test_services/test_similarity_content.py::test_excludes_foreign_private_rows`,
  qui plante un vecteur privé PLUS PROCHE que le visible et vérifie qu'il ne fuit pas).
- **Injection : rien à signaler sur le delta.** Le scope de recherche `album` passe par
  `space_insensitive_ilike` → `like_escape` avec `escape="\\"` explicite
  (`search_service.py:281`, `utils.py:27-58`) ; les filtres D8 genre utilisent l'égalité
  `genres.any(g)` (comparator `array_any`, pas de LIKE), `artist_id` est parsé en ints ; le seul
  SQL brut du chemin recherche (`_search_genres`) est paramétré (`:pattern` + `ESCAPE '\'`,
  l.328-353). Le script local `backfill_embeddings.py` n'interpole que des ints castés et des
  constantes module dans son SQL.
- **Cache reco bien cloisonné par user** : `reco:<uid>` (`recommendation_service._cache_key`,
  l.81-84), lock single-flight `lock:reco:<uid>` par user aussi — aucune fuite croisée possible
  par la clé. Même discipline sur le cache « sonne comme » : clé `(seed, viewer|anon)`
  (`similarity_service.py:1281-1285`), les invités partagent une clé `anon` cohérente avec leur
  périmètre partagé-only.
- **Pas de secret dans le delta** : scan du diff 9b305d6..52a506f (hors docs/frontend) — seuls
  faux positifs = fixtures de test nommées « secret » ; `.env.example` n'ajoute qu'un placeholder
  `BACKUP_ALERT_WEBHOOK` commenté. Les CSV `docs/c9-benchmark/` sont des données de benchmark.
- **Rate limiting : identité anti-spoof saine** (X-Real-IP posé par nginx, X-Forwarded-For ignoré,
  `rate_limit.py:79-88`) et les tests de la table (`tests/api/test_rate_limit.py`) importent le
  VRAI module (`from rate_limit import RATE_LIMITS`) — pas de fausse couverture ici. Idem
  `test_deadline_exit.py` (horloge injectée dans le vrai module, pas une copie de la logique).
- **Middleware allowlist propre pour les nouveaux publics** : `/api/albums` ajouté aux
  `_PUBLIC_GET_PREFIXES` (GET only) et testé (`test_auth_middleware.py::test_albums_get_public`) ;
  `/api/collections` reste derrière JWT et les 401 sont testés.

---

### [A6-01] « Sonne comme » (C9.b) : gate admin front-only, l'endpoint back est public — divergence doc/code
- **Type** : sécu | doc
- **Sévérité** : moyenne
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** : `server/api/routers/catalog.py:135-149` — `GET /catalog/{id}/content-similar` avec
  `get_current_user_optional` et le docstring qui l'assume : « JWT-optional; the shelf is
  admin-gated on the FRONT while embeddings coverage ramps up ». `server/api/auth_middleware.py:12`
  — le préfixe public GET `/api/catalog` rend la route accessible ANONYMEMENT. Front :
  `server/frontend/src/views/TrackDetailView.vue:184` (`v-if="auth.user?.is_admin"`) et l.540
  (`if (!auth.user?.is_admin) return`) = gate client uniquement. Le commit de clôture 52a506f dit
  « C9.b … LIVRE **admin-only** ».
- **Constat** : le « gate admin » annoncé (roadmap + CLAUDE.md « gaté admin ») n'existe pas côté
  serveur : n'importe qui — y compris un invité sans compte — peut appeler
  `/api/catalog/{id}/content-similar` directement. Pas de fuite de données (les voisins sont
  `catalog_visible`-scopés, vérifié + testé), mais le gate est un gate de ROLLOUT produit
  (couverture embeddings ~24 %) que la doc présente comme effectif ; quiconque s'appuie sur
  « admin-only » pour raisonner sur l'exposition ou la charge se trompe. C'est exactement la
  divergence doc↔code que CLAUDE.md demande de signaler.
- **Recommandation** : trancher explicitement : (a) si le gate doit être réel → `require_admin`
  (ou check `is_admin` avec `get_current_user`) sur l'endpoint le temps du ramp-up, quitte à le
  retirer au GA ; (b) si l'exposition publique est assumée (cohérente avec le browsing invité
  délibéré) → corriger la roadmap/CLAUDE.md pour dire « shelf gaté admin au FRONT, endpoint
  public ». Dans les deux cas, coupler avec A6-02 (throttle).
- **Dépendances** : A6-02 (même surface ; le throttle reste nécessaire quel que soit l'arbitrage).
- **Tags** : QW-c (si option (b) : une phrase de doc ; si option (a) : 3 lignes + 1 test)

### [A6-02] `/content-similar` échappe au rate limiting (le suffixe `/similar` ne le matche pas)
- **Type** : sécu | perf
- **Sévérité** : moyenne
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** : `server/api/rate_limit.py:61-65` — `RATE_LIMIT_SUFFIXES = {"/preview-url": (30,60),
  "/similar": (20,60)}` et le match l.104 est `path.endswith(suffix)`. Or
  `"/api/catalog/123/content-similar".endswith("/similar")` est **False** (le path se termine par
  `t-similar`, pas `/similar`). Aucun préfixe `/api/catalog` dans `RATE_LIMITS`. Aucun test de
  `tests/api/test_rate_limit.py` ne mentionne `content-similar` (grep vide).
- **Constat** : le seul endpoint per-id coûteux ajouté depuis la mise en place des suffix buckets
  n'est couvert par aucun bucket — alors que ses jumeaux `/similar` et `/preview-url` le sont
  précisément parce que « costly per-id read endpoints » (commentaire l.53-58). Chaque cache-miss
  déclenche un KNN pgvector (ORDER BY `<=>` LIMIT 24 sous filtre `catalog_visible`, qui dégrade le
  parcours HNSW) + `_build_result_items` + une écriture Redis, le tout accessible anonymement
  (A6-01) et énumérable sur ~266k catalog_id — un scan remplit aussi Redis d'une clé
  `content_neighbors:<id>:anon` (payload 24 items, TTL 6h) par seed visité, sur un VPS 4 vCPU
  fair-use déjà mordu par des pics CPU (AV10).
- **Recommandation** : ajouter `"/content-similar": (20, 60)` dans `RATE_LIMIT_SUFFIXES` (aucun
  conflit d'ordre : un path ne peut matcher qu'un des deux suffixes) + le test miroir de
  `test_catalog_similar_is_throttled`.
- **Dépendances** : lié A6-01 (même surface).
- **Tags** : QW-c

### [A6-03] Dédup des items de collection app-level sans contrainte DB : une course crée un doublon qui rend ensuite `DELETE` 500
- **Type** : bug
- **Sévérité** : basse
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** : `server/api/routers/collections.py:257-267` — dédup check-then-insert (SELECT puis
  409) sans aucun index unique sur `collection_items` (modèle : PK surrogate seule, « NO native
  FK » par design, et la migration 0047/0048 ne pose pas d'unique applicatif). Puis l.324 :
  `remove_item` fait `(await db.execute(q)).scalar_one_or_none()` — sur DEUX lignes identiques,
  SQLAlchemy lève `MultipleResultsFound` → 500.
- **Constat** : deux `POST /collections/{id}/items` concurrents (double-clic + 2 workers uvicorn)
  passent tous deux le SELECT de dédup et insèrent deux items identiques ; à partir de là le
  `DELETE /{id}/items/{type}/{id}` de cet item répond 500 à chaque tentative — l'item devient
  insupprimable via l'API (il faut passer par psql). Fenêtre étroite et périmètre mono-user
  (sa propre collection), d'où la sévérité basse — mais c'est un état incohérent permanent.
- **Recommandation** : au choix (les deux sont bien) : (1) index unique partiel
  `(collection_id, item_type, item_id)` WHERE `item_id IS NOT NULL` + `(collection_id, item_type,
  item_name)` WHERE `item_id IS NULL`, en rattrapant l'`IntegrityError` en 409 ; (2) a minima,
  rendre `remove_item` tolérant (itérer/`.limit(1)` ou DELETE de toutes les lignes qui matchent)
  pour que le doublon reste réparable par l'API.
- **Dépendances** : aucune.
- **Tags** : —

### [A6-04] Trous de tests multi-user sur Collections v2 : ownership des collections et visibilité track privé jamais exercés
- **Type** : test
- **Sévérité** : moyenne
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** : `grep -n other_user tests/api/test_collections.py` → la fixture n'est consommée QUE
  par les 4 tests **folders** (l.486, 495, 505, 513). Aucun test n'accède à la COLLECTION d'un
  autre user (`GET/DELETE /collections/{id}`, `POST/DELETE .../items` sur un id étranger — le
  chemin `_get_user_collection` l.343-355 n'a aucun test cross-user). `grep -n "private\|scope="
  tests/api/test_collections.py` → vide : ni le 404 de `_assert_target_exists` sur un track privé
  étranger (ajout refusé, l.379-381), ni le `missing=True` de `_resolve_items` sur un track devenu
  invisible (l.463-467) ne sont couverts.
- **Constat** : le code EST correct (vérifié à la lecture, cf. « Ce qui va bien »), mais les deux
  garanties multi-user du chantier C5 v2 — « un user ne touche pas la collection d'un autre » et
  « une collection ne divulgue jamais un track privé étranger » — n'ont aucun filet de
  non-régression, alors que le pattern 2-users existe déjà dans le même fichier (folders) et dans
  `test_scope_visibility.py`/`test_albums.py`. Une refonte future du routeur (ex. extraction en
  service) peut casser l'ownership sans qu'aucun test ne rougisse.
- **Recommandation** : ~5 tests calqués sur les tests folders existants : GET/DELETE/add-item/
  remove-item sur la collection d'`other_user` → 404 ; add-item d'un track `scope='private'`
  étranger → 404 ; détail d'une collection contenant un track privé étranger → `missing=True`
  sans métadonnées.
- **Dépendances** : à écrire avant tout refactor du routeur collections ; complète A6-03.
- **Tags** : —

### [A6-05] Outil local `worker/embedding_backfill/` (écrit en prod) : zéro test, constantes modèle dupliquées sans garde de synchro
- **Type** : test | dette
- **Sévérité** : basse
- **Effort estimé** : M
- **Confiance** : haute
- **Preuve** : `grep -rln "backfill_embeddings\|embedding_backfill" tests/` → aucun résultat.
  `worker/embedding_backfill/backfill_embeddings.py:92-96` duplique volontairement
  `MODEL_NAME = "discogs-effnet"` / `MODEL_VERSION = "bs64-1"` / `EMBEDDING_DIM = 1280` (le
  commentaire renvoie à `server/api/models/embedding.py`), et aucun test n'asserte que les deux
  jeux restent égaux.
- **Constat** : c'est le mécanisme PRIMAIRE du backfill C9.a et il écrit en prod (`--apply` via
  ssh-psql). Ses briques pures et facilement testables (`build_pull_query` keyset,
  `eligible_inserts` gate dimension, `_parse_emb`, parsing des command tags `INSERT 0 n`,
  checkpoint) ne sont couvertes nulle part — contrairement aux scripts OPS serveur
  (`test_backfill_albums.py`, `test_backfill_set_reliability.py`… ont tous leurs tests). Un drift
  des constantes dupliquées ferait requêter le LEFT JOIN sous une mauvaise clé
  (model_name/version) → re-embedding intégral silencieux du catalog (~95 h de calcul) ou salve
  écrite sous une identité de modèle divergente de celle que lit `get_content_neighbors`.
  Atténuants réels : dry-run par défaut, idempotent `ON CONFLICT DO NOTHING`, outil local hors
  image — d'où basse.
- **Recommandation** : un petit module de tests worker (pattern `test_backfill_albums.py`) sur les
  helpers purs + un test « constants-in-sync » qui importe les deux modules et compare
  `MODEL_NAME/MODEL_VERSION/EMBEDDING_DIM` (le script est stdlib-only, importable depuis la
  suite).
- **Dépendances** : aucune.
- **Tags** : —
