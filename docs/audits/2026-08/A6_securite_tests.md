# Audit A6 — Sécurité & Tests (2026-08)

> Audit défensif READ-ONLY. HEAD audité : `9b305d6` (2026-08-08). Agent A6.
> Delta depuis l'audit 2026-07 (`67162e3`) : 164 commits — C3 (visibilité multi-user),
> C4 (reco), radar/feed, watchlist/browse, search/external + POST /import (F5),
> admin backlog/monitoring, preview-url→avis, scripts `--apply`, file de lecture
> audioPlayer, E2 BPM. Méthode : lecture endpoint par endpoint des nouveaux chemins
> de lecture catalog + croisement allowlist middleware / dépendances / rate limits,
> greps injection/secrets, inventaire des suites de tests. Aucune écriture hors ce
> rapport, aucun test d'intrusion actif.

## Ce qui va bien

- **Tous les fixes AU1 de l'audit 2026-07 sont en place et ont tenu 164 commits** :
  X-Real-IP seul lu pour le rate limiting, XFF explicitement ignoré et TESTÉ contre le
  spoof (`rate_limit.py:52-61`, `tests/api/test_rate_limit.py:155` `test_spoofed_x_forwarded_for_shares_same_counter`) ;
  `defusedxml` sur l'import Rekordbox (`services/rekordbox_xml.py:7`) ; nginx 12M aligné
  sur l'app 10M (`nginx/default.ssl.conf.template:23`, `routers/import_rb.py:17`) ;
  `/api/watchlist/active` retiré de l'allowlist (2026-07/A6-10) ; docs/OpenAPI désactivés
  en prod (testé, `tests/api/test_docs_prod.py`) ; fail-open Redis loggé (`rate_limit.py:93-96`) ;
  corps de la réponse token Google plus jamais loggé (`auth.py:49-52`, 2026-07/A6-11) ;
  payloads bornés (2026-07/A6-05 : `radar.py:36,185` `Body(max_length=1000)`,
  `schemas/tracks.py:25` `image_base64` borné, `schemas/watchlist.py:12-14`).
- **Discipline C3 remarquable sur les nouvelles surfaces** — vérifié chemin par chemin :
  `list_catalog` + param `catalog_ids` (`catalog_service.py:259,266`), `get_detail`
  (`:464` + related `same_artist` `:585`), preview-url (`:739`), `update_avis` (`:829`),
  radar `list_full`/`new_count`/`trends`/`feed` (`radar_service.py:104,140,323,425`,
  `routers/radar.py:74`), pool de similarité par viewer (`similarity_service.py:413`,
  jamais caché globalement ; caches reco `reco:{user_id}` et similar-sets par
  (set, viewer)), reco C4 via le pool, sets liste `top_genres` + filtre genre + détail
  (`routers/sets.py:212,289,516`), watchlist browse/détail (`watchlist_service.py:166,255`),
  genre tracklist D8.b / artworks / random (`genre_service.py:577,250,379,691`), artistes
  liste/détail/random (`artist_service.py:244,336,347,499`), search tracks
  (`search_service.py:74`), collections (`routers/collections.py:89,119`). Les fragments
  `catalog_visible_sql` bindent `:viewer_id` conditionnellement à CHAQUE call site vérifié.
- **Allowlist middleware exacte** : `_PUBLIC_GET_PREFIXES` (catalog, artists, sets, genres,
  search, taxonomy, radar/trends) ne couvre que des GET de découverte ; toutes les mutations
  sous ces préfixes portent `get_current_user`/`require_admin` (vérifié genres merge/rename,
  sets import) ; `/api/recommendations`, `/api/radar/feed`, `/api/watchlist` restent derrière
  JWT ; les 29 endpoints admin passent tous par `require_admin` (y compris les nouveaux
  `/admin/backlog` et `/admin/monitoring`).
- **Pas d'injection SQL** : tout le SQL brut nouveau (genre_service, artist_service,
  search_service, catalog_visible_sql) est à paramètres bindés ; les colonnes de tri sont
  whitelistées partout (regex Pydantic `routers/genres.py:48,136`, dicts à fallback
  `routers/sets.py:231-241`, `watchlist_service.py:128-139`, `sort_map` radar) ; les seuls
  f-strings dans `text()` interpolent des fragments serveur (alias, clauses whitelistées).
- **OAuth conforme au design documenté (angle 9)** : state `secrets.token_urlsafe(32)` +
  Redis TTL 300s consommé one-shot par `redis.delete` (`routers/auth.py:32-33,57`) ; cookie
  `auth_callback` max_age=60, Secure, SameSite=Lax, base64url sans padding
  (`routers/auth.py:113-130`) ; JWT décodé avec `algorithms=["HS256"]` épinglé (`auth.py:30`).
- **Secrets sains** : arbre propre (grep motifs token/secret/password : 0 hit hors tests),
  `.env.example` = placeholders uniquement, `.tidal_tokens.json` désormais non tracké et
  gitignoré (`.gitignore:20`), aucun fichier porteur de secret ajouté dans le delta
  (`git log 67162e3..HEAD --diff-filter=A`).
- **Le filet de tests sur les chemins critiques a changé de catégorie** (angle 7 largement
  satisfait) : visibilité C3 testée en suite dédiée (`tests/api/test_scope_visibility.py`,
  13 tests dont le twin SQL), non-promotion private→shared testée
  (`tests/api/test_import_rb_scope.py` : `test_foreign_private_collision_stays_private_visible_via_user_track`),
  preview-url + avis (13 tests dont cache et quota), rate limiting (16 tests dont spoof XFF),
  middleware auth (`test_auth_middleware.py`), file de lecture audioPlayer **23 tests** dont
  tout le contrat queue (skip sans preview, pagination, dislike=skip, rollback PATCH,
  close sans ghost-advance), `LoginCallbackView.test.js` présent (2026-07/A6-07 corrigé).
- **Les scripts destructifs `--apply` sont testés sur le VRAI code** (pas de pattern M6) :
  `tests/worker/test_reverify_platform_ids.py` importe `scripts.reverify_platform_ids.reverify_by_column`,
  `test_artist_merge.py` importe `workers.artist_merge.merge_artist_into` (session SQLite
  réelle, contraintes UNIQUE actives), `test_catalog_merge.py`/`test_catalog_merge_script.py`
  couvrent `same_track`/`merge_catalog_entries`/le script, `test_dedup_artists_deezer.py`
  exerce `find_candidate_pairs` avec le vrai fold NFKD.
- **Le `omit` du coverage gate a été RÉDUIT, pas re-gonflé** (angle 8) : `enrichment.py`
  et `source_clients.py` en sont sortis (fix du 2026-07/A6-04 core ; tests
  `test_enrichment_async.py`, `test_enrichment_isrc.py`, `test_source_clients_errors.py`,
  `test_count_enrich_backlog.py`) ; `tests/worker/test_check_sync.py` (fausse couverture
  2026-07/A6-09) a été SUPPRIMÉ. Les nouvelles tâches E2/MON sont testées malgré l'omit
  `tasks/*` (`test_bpm_analysis.py`, `test_bpm_schedule.py`, `test_snapshot_backlogs.py`,
  `test_task_locks.py`).

---

## Findings

### [A6-01] Détail artiste : `lib_sub` sans filtre `user_id` — fuite inter-utilisateurs des données Rekordbox et de l'appartenance bibliothèque
- **Type** : sécu
- **Sévérité** : haute
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** : `server/api/services/artist_service.py:319-324` (`get_detail`) :
  ```python
  lib_sub = select(
      UserTrack.catalog_id,
      UserTrack.rb_mytags.label("tags"),
      UserTrack.rb_bpm.label("bpm"),
      UserTrack.rb_key.label("key"),
  ).subquery()          # ← AUCUN .where(UserTrack.user_id == user_id)
  ```
  Consommé par l'outerjoin `:335` puis `in_lib=row[1] is not None` (`:355,391`),
  `bpm=lib_bpm if lib_bpm else entry.bpm` + `bpm_source="rekordbox"` (`:377-381`),
  `style` depuis `rb_mytags` (`:364-367`), stat `nb_lib` (`:361,483`), tri « en-lib
  d'abord » (`:337`). Le jumeau `list_artists` dans le MÊME fichier filtre correctement :
  `artist_service.py:67-71` (`.where(UserTrack.user_id == user_id)`). L'endpoint
  `GET /api/artists/{id}` est PUBLIC (préfixe `/api/artists` dans `_PUBLIC_GET_PREFIXES`,
  `auth_middleware.py:13`) et passe `_uid(user)` (`routers/artists.py:76`) — le paramètre
  arrive au service qui l'ignore pour ce subquery.
- **Constat** : la page Artist Detail sert à TOUT viewer (invités compris) les
  `user_tracks` de N'IMPORTE QUEL utilisateur : un track détenu par un autre utilisateur
  apparaît `in_lib=True` chez le viewer, avec le `rb_bpm`/`rb_key` Rekordbox de cet autre
  utilisateur (étiqueté `bpm_source='rekordbox'` comme si c'était le sien) et son premier
  `rb_mytag` en `style`. C'est une fuite de données de performance personnelles (invariant
  « Rekordbox BPM = donnée perso du user ») + de l'appartenance bibliothèque, hors du
  périmètre des résidus C3 acceptés (qui ne couvrent que des COMPTES agrégés). Effet
  secondaire : si plusieurs utilisateurs détiennent le même track, l'outerjoin multiplie
  les lignes (doublons visibles dans la liste des tracks de l'artiste). Le code pré-date
  C3 (déjà non filtré à `67162e3`, avec `rating` en plus), mais C3 (multi-user réel) l'a
  transformé en fuite — non détecté en 2026-07, ce n'est pas une récurrence.
- **Recommandation** : ajouter `.where(UserTrack.user_id == user_id)` au `lib_sub` de
  `get_detail` (une ligne — `user_id=None` donne alors correctement zéro match pour les
  invités), et un test jumeau de `test_scope_visibility` : user B + invité sur le détail
  d'un artiste dont A détient un track → `in_lib=False`, bpm catalogue, pas de doublon.
- **Dépendances** : aucune
- **Tags** : QW-c

### [A6-02] `/api/radar/feed` hors rate limiting malgré l'incident OOM prod documenté
- **Type** : sécu
- **Sévérité** : haute
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** : `RATE_LIMITS` (`rate_limit.py:18-38`) couvre `/api/recommendations` (30/60)
  mais AUCUNE entrée pour `/api/radar/feed`. Or `radar_feed` (`routers/radar.py:129-162`)
  appelle `list_bi_score` qui exécute `get_recommendations` (compute de similarité complet
  sur cache froid) PUIS `list_catalog` sur l'union des ids tendance (`radar_service.py:311,341`)
  — le chemin est strictement plus coûteux que `/api/recommendations` qui, lui, est capé.
  Incident prod : `/api/radar/feed` mesuré ~550 Mo/req a OOM-killé l'API (cap mémoire
  1G→3G relevé le 2026-08-01, suivi actif « adoucir les salves parallèles fetchUpTo »).
- **Constat** : passer par `/api/radar/feed` contourne le cap posé sur
  `/api/recommendations` : un seul utilisateur authentifié (ou un token volé) qui envoie
  une salve parallèle reproduit l'OOM → 502 sur toute l'API (constaté en prod, pas
  théorique). Le front lui-même a déjà déclenché ce mode de défaillance avec ses
  `fetchUpTo` parallèles.
- **Recommandation** : ajouter `"/api/radar/feed": (10, 60)` (ou similaire) dans
  `RATE_LIMITS` — insertion AVANT tout préfixe plus court si un bucket `/api/radar`
  apparaît un jour (match par ordre d'insertion). Le lissage côté front reste le fix
  durable complémentaire (déjà suivi).
- **Dépendances** : aucune
- **Tags** : QW-c

### [A6-03] Dépendances vulnérables : python-jose 3.3.0 porte l'auth, python-multipart 0.0.9 l'upload, starlette 0.38.6 le framework — 26 avis, dérive non bloquée
- **Type** : sécu
- **Sévérité** : haute
- **Effort estimé** : M
- **Confiance** : haute
- **Preuve** : `server/api/requirements.txt:16,18` (`python-jose[cryptography]==3.3.0`,
  `python-multipart==0.0.9`), starlette 0.38.6 transitif de `fastapi==0.115.0` (`:1`),
  `requests==2.32.3` (`:10`), `curl_cffi==0.7.4` (`:12`), `python-dotenv==1.0.1` (`:8`).
  pip-audit Phase 0 : 26 vulns / 7 packages. Évaluation d'exposition RÉELLE dans Diggy :
  - **python-jose 3.3.0** (PYSEC-2024-232 confusion d'algorithme, -233 DoS JWE,
    PYSEC-2025-185 sans fix sur la 3.3) : c'est LA lib de l'auth (`auth.py:6,23,30` —
    encode/decode de tous les JWT). Atténuation constatée : décode épinglé
    `algorithms=["HS256"]` sur secret symétrique → la confusion RS/HS classique (-232,
    qui suppose une clé publique ECDSA côté vérif) n'a pas de chemin ici, et -233 vise
    `jwe.decrypt`, non utilisé. Reste PYSEC-2025-185 non corrigeable sans monter de version.
  - **python-multipart 0.0.9** (7 avis, DoS parsing) : parse l'upload XML
    (`/api/import/rekordbox`). Atténuations : le middleware JWT rejette AVANT que le corps
    soit parsé (le parsing multipart n'a lieu que dans le handler), rate limit 3/300s,
    corps ≤12M nginx → DoS authentifié seulement, débit très limité.
  - **starlette 0.38.6** (9 avis dont CVE-2024-47874 DoS multipart) : même logique — les
    seuls endpoints exemptés du middleware (`/api/auth/*`, `/api/health`, GET publics)
    ne parsent jamais de form-data, donc pas de chemin PRE-AUTH identifié.
  - **requests 2.32.3 / curl-cffi 0.7.4 / python-dotenv 1.0.1 / ecdsa** : usages
    server-initiated vers des hôtes fixes (Deezer/Beatport), `.env` = input opérateur,
    ecdsa = code path inutilisé en HS256 → exposition négligeable.

  Aucun chemin d'exploitation pré-auth n'a donc été identifié — la sévérité vient de la
  POSITION des paquets (la lib qui signe/vérifie chaque session est 2 majors en retard
  avec un avis sans fix sur sa branche) combinée à l'absence de tout frein : le job CI
  `audit` est `continue-on-error: true` ET absent du `needs:` du deploy
  (`.github/workflows/deploy.yml:80-90,108`) — porté par l'agent A5, référencé ici.
- **Constat** : la dette de vulnérabilités s'accumule silencieusement sur les composants
  les plus critiques (auth, upload, framework HTTP) ; chaque nouveau CVE arrivera aussi
  sans bruit tant que le gate ne bloque pas.
- **Recommandation** : upgrade coordonné : `python-jose` 3.3.0→3.4.0 (drop-in, corrige
  -232/-233 ; vérifier PYSEC-2025-185), `python-multipart`→≥0.0.18 (FastAPI 0.115 le
  supporte), puis un lot `fastapi`+`starlette` (starlette ≥0.40 exige un bump fastapi —
  suite de tests API complète = filet). `requests`/`curl-cffi`/`python-dotenv` dans la
  foulée. En parallèle : rendre le job pip-audit bloquant (finding A5).
- **Dépendances** : finding A5 (gate pip-audit non bloquant) — les deux se renforcent
- **Tags** : aucun

### [A6-04] preview-url et /similar accessibles aux invités sans rate limit — amplification vers l'API Deezer et CPU non bornés
- **Type** : sécu
- **Sévérité** : moyenne
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** : `GET /api/catalog/{id}/preview-url` et `GET /api/catalog/{id}/similar` sont
  publics (préfixe `/api/catalog` dans `_PUBLIC_GET_PREFIXES`, `auth_middleware.py:12`) et
  absents de `RATE_LIMITS` (`rate_limit.py:18-38`). preview-url déclenche un fetch live
  `api.deezer.com/track/{id}` par miss de cache (`catalog_service.py:697-698`, cache Redis
  30 min par track, `:39`) ; `/similar` construit le pool candidats complet du viewer à
  CHAQUE requête (`similarity_service.py:405-415` — projection de tout le catalog visible,
  ~30k+ lignes, puis scoring en mémoire).
- **Constat** : un client non authentifié qui énumère les `catalog_id` (séquentiels)
  transforme l'API en proxy d'appels sortants Deezer — le quota Deezer partagé s'épuise
  et les VRAIES previews des utilisateurs passent en 503 (auto-DoS de la feature play) ;
  le même client peut marteler `/similar` (CPU + allocation du pool par requête). Les
  buckets existants montrent que le coût externe est le critère retenu ailleurs
  (`/api/search/external` 10/60, `/api/catalog/import` 20/60) — ces deux chemins ont été
  oubliés.
- **Recommandation** : ajouter `"/api/catalog/"`-scoped buckets ciblés — impossible par
  préfixe simple (l'id est au milieu), donc soit un bucket large `"/api/catalog": (120, 60)`
  en DERNIÈRE position (les préfixes plus spécifiques `/api/catalog/import` matchent
  avant, ordre d'insertion), soit étendre le matcher à un motif. Prioriser preview-url
  (coût externe partagé).
- **Dépendances** : A6-02 (même fichier, même mécanique de préfixes)
- **Tags** : aucun

### [A6-05] Recherche externe / import manuel : lookup catalog sans `catalog_visible` — divulgation d'existence de lignes privées étrangères
- **Type** : sécu
- **Sévérité** : basse
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** : `external_search_service._match_catalog` (`:78-103`) :
  `select(CatalogEntry.id, ...).where(or_(isrc.in_(...), normalized_key.in_(...)))` —
  aucun `catalog_visible`, le `catalog_id` matché est renvoyé au client
  (`ExternalSearchItem.catalog_id`, `:154`). Même absence dans le lookup de dédup de
  `import_external` (`catalog_service.py:1109-1129`).
- **Constat** : un utilisateur qui recherche un titre via `GET /search/external` voit le
  badge « déjà au catalogue » (catalog_id non nul) même quand la seule ligne correspondante
  est la ligne PRIVÉE d'un autre utilisateur — divulgation d'existence (« quelqu'un a
  importé ce track ») + lien mort côté UI (le détail 404 via `catalog_visible`). Violation
  formelle de la règle C3 (« any new catalog read path must add the predicate »), impact
  informationnel faible (id + existence, pas de contenu — même classe que l'énumération
  `/storage/*` acceptée). NB : le lookup de `import_external` doit, LUI, rester global —
  `normalized_key` est UNIQUE, filtrer la dédup par visibilité ferait échouer l'INSERT en
  collision ; c'est une exception d'intégrité légitime (même logique que l'import RB), à
  documenter. Le cas résiduel « match sur une ligne privée invisible → created=False avec
  un id inutilisable » mérite au minimum un commentaire.
- **Recommandation** : appliquer `catalog_visible(user_id)` dans `_match_catalog` (passer
  le `user_id` depuis le router — le badge est une aide de navigation, il ne doit pointer
  que vers des lignes que le viewer peut ouvrir). Documenter l'exception d'intégrité dans
  `import_external`.
- **Dépendances** : aucune
- **Tags** : aucun

### [A6-06] RÉCURRENCE (2026-07/A6-06) : wildcards LIKE non échappés sur les chemins refondus — le helper existe mais n'est appliqué qu'à moitié
- **Type** : sécu
- **Sévérité** : basse
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** : le fix a créé `utils.like_escape` (`utils.py:25-33`) et l'a appliqué à
  `search_service` (7 sites, `escape="\\"`) et `taxonomy.py:37`. Mais les chemins refondus
  D6/D8 construisent toujours `f"%{q}%"` brut : `catalog_service.py:276-281` (recherche
  Explorer) et `:314` (filtre label), `radar_service.py:124-127` (`list_full`),
  `artist_service.py:137-138` (liste artistes), `genre_service.py:197→212` (liste genres)
  et `:563→578` (tracklist Genre Detail), `routers/sets.py:172` (liste sets).
- **Constat** : identique à 2026-07 — paramètres bindés donc PAS d'injection SQL, mais
  `%`/`_` utilisateur restent actifs (un `%` matche tout, patterns lents). L'inconsistance
  est le vrai problème : deux conventions coexistent dans le même codebase, et chaque
  nouvelle page copie l'une ou l'autre au hasard (les 6 sites ci-dessus datent tous du
  delta).
- **Recommandation** : passer les 8 sites restants à `like_escape` + `escape="\\"`
  (mécanique, le pattern à copier est dans `search_service.py:71-72` ; pour le SQL brut de
  genre_service, `ESCAPE '\'` comme `search_service.py:285`).
- **Dépendances** : aucune
- **Tags** : aucun

### [A6-07] RÉCURRENCE partielle (2026-07/A6-14) : branches d'échec de `google_callback` toujours non testées
- **Type** : test
- **Sévérité** : basse
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** : `tests/api/test_auth.py` couvre désormais `invalid_state` (`:79`,
  progrès vs 2026-07) et le contenu du cookie (`:69-77`), mais aucun test ne déclenche
  la branche `google_failed` (`routers/auth.py:64-68`, exception de `verify_google_token`)
  ni la boucle de collision de username (`:82-87`) ni l'update de `picture_url` (`:100-104`).
  `verify_google_token` lui-même (`auth.py:36-68`) reste non exercé.
- **Constat** : les chemins d'échec du point d'entrée d'auth restent à découvert ; une
  régression y casse le login pour tous sans qu'aucun test ne rougisse. Le reste du
  finding 2026-07/A6-14 (lifecycle radar PG-skip, fake_redis partagé) n'a pas été réévalué
  en profondeur ici — la partie auth est la seule re-vérifiée.
- **Recommandation** : 3 tests : mock de `verify_google_token` qui lève → redirect
  `?error=google_failed` ; deux users même `name` → suffixe ; picture changée → update.
- **Dépendances** : aucune
- **Tags** : aucun

### [A6-08] RÉCURRENCE partielle (2026-07/A6-08) : le cœur upsert PG de l'import Rekordbox reste non testé
- **Type** : test
- **Sévérité** : basse
- **Effort estimé** : M
- **Confiance** : haute
- **Preuve** : gros progrès depuis 2026-07 — le lock atomique et son cycle de vie sont
  testés (`tests/api/test_import_rb.py` 6 tests, `tests/worker/test_task_locks.py:232`
  appelle la vraie tâche), le parsing XML l'est (`test_rekordbox_xml.py`), la résolution
  de scope l'est (`test_import_rb_scope.py`). Mais `tests/api/test_integration.py:8`
  documente toujours le skip : « import_rekordbox_xml use PG-specific SQL » — le batching,
  l'upsert `on_conflict_do_update` et le comptage inserted/updated ne tournent dans aucune
  config de test, et `workers/tasks/*` reste dans l'`omit` du gate (`pyproject.toml:53`).
- **Constat** : la voie d'alimentation de la bibliothèque utilisateur garde son angle mort
  central (l'upsert), alors que le job CI dispose déjà d'un PostgreSQL réel.
- **Recommandation** : test PG-only (`skipif` inverse du pattern existant
  `test_radar.py`) exerçant l'upsert : import initial → ré-import avec modifications →
  compteurs inserted/updated corrects, `user_tracks` non dupliqués.
- **Dépendances** : aucune
- **Tags** : aucun

### [A6-09] `GET /watchlist/{id}/crawl-status` sans aucune dépendance user — protégé par la seule signature JWT du middleware
- **Type** : sécu
- **Sévérité** : basse
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** : `routers/watchlist.py:128-137` — ni `get_current_user`, ni
  `get_current_user_optional` ; seul le middleware s'applique (`/api/watchlist` n'est pas
  dans les préfixes publics). Or le middleware ne vérifie que la signature/expiration
  (`auth_middleware.py:67-68` → `decode_token`), PAS l'existence ni `is_active` du user
  (contrairement à `get_current_user`, `dependencies.py:31-38`). L'endpoint a de plus un
  effet d'écriture : il purge `current_task_id` (`watchlist_service.py:481-499`).
- **Constat** : un utilisateur désactivé garde jusqu'à 7 jours (durée du JWT) un accès à
  cet endpoint — et à tout futur endpoint ajouté sans dépendance. Donnée exposée anodine
  (statut de crawl), mais c'est le seul endpoint du codebase dans ce cas : une convention
  s'érode par l'exception.
- **Recommandation** : ajouter `user: User = Depends(get_current_user)` (une ligne,
  aligne sur le reste du router).
- **Dépendances** : aucune
- **Tags** : aucun

---

## Hypothèses réfutées

- **« Le `omit` du coverage gate a été re-gonflé »** — NON : il a été réduit
  (`enrichment.py` et `source_clients.py` sortis et testés ; `pyproject.toml:49-61` ne
  garde que `tasks/*`, infra celery, alembic, scripts, beatport — dette documentée AU5+).
- **« Les tests des scripts `--apply` testent une copie locale (pattern M6/A6-09) »** —
  NON : les 5 suites importent les vrais modules (`scripts.reverify_platform_ids`,
  `workers.artist_merge`, `workers.catalog_merge`…) ; `test_check_sync.py` (la fausse
  couverture de 2026-07) a été supprimé.
- **« Le tri server-side de watchlist/browse ou de la tracklist genre est injectable »** —
  NON : dict whitelist + fallback (`watchlist_service.py:128-139`), regex Pydantic
  (`routers/genres.py:136`) + `order_clauses` dict (`genre_service.py:552-562`).
- **« Un call site `catalog_visible_sql` oublie le bind `:viewer_id` »** — NON : les 8
  sites (artist_service ×3, genre_service ×5) bindent tous conditionnellement.
- **« Le cache Redis reco/similar-sets peut servir la vue d'un autre user »** — NON :
  clés `reco:{user_id}` (`recommendation_service.py:62-65`) et similar-sets par
  (set_id, viewer) (`similarity_service.py:862-877`).
- **« Des secrets ont été réintroduits dans le delta »** — NON : aucun fichier sensible
  ajouté depuis `67162e3`, arbre propre, tokens TIDAL non trackés (l'historique non purgé
  reste le résidu accepté Q4-B).
- **« Le flux OAuth state/cookie a dérivé du design documenté »** — NON : one-shot Redis
  5 min, cookie 60s Secure/Lax conformes, testés.
- **« `/api/search/external` est accessible aux invités via le préfixe public
  `/api/search` »** — NON en pratique : le middleware l'exempte, mais la dépendance
  `get_current_user` du handler (`routers/search.py:40`) rejette les guests — défense en
  couche 2 effective (et bucket 10/60 dédié).

## Non couvert (budget / hors-portée)

- Vérification dynamique (pas de PoC — mandat READ-ONLY) : A6-01/02/04 sont établis par
  lecture statique + historique d'incident prod pour A6-02.
- Le contenu exact de PYSEC-2025-185 (python-jose, sans fix) n'a pas pu être vérifié
  hors-ligne — l'évaluation d'exposition A6-03 le traite prudemment comme motif d'upgrade.
- Les volets non-auth de 2026-07/A6-14 (lifecycle radar PG-skip, hygiène `_fake_redis`)
  n'ont pas été re-audités ligne à ligne.
- Frontend hors auth/player (composables de fenêtrage, vues) : survolé via l'inventaire
  des suites, pas d'audit de profondeur.
