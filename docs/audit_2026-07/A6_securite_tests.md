# Audit A6 — Sécurité & Tests

> Audit défensif READ-ONLY du projet Diggy (code du propriétaire, autorisé sur son propre repo).
> Date : 2026-07-09 · Agent A6 · Analyse statique uniquement, aucun test d'intrusion actif.

## Périmètre & méthode

- **Périmètre** : authentification (`auth.py`, `auth_middleware.py`, `dependencies.py`, `routers/auth.py`), gating des 93+ endpoints, validation d'input, `rate_limit.py`, secrets versionnés, couverture de tests backend (`tests/`) et frontend (Vitest).
- **Méthode** : lecture directe des fichiers d'auth + croisement de la liste d'endpoints (`_inventory.md` §5) avec le mécanisme de gate (`JWTAuthMiddleware`) et les dépendances FastAPI. Trois sweeps délégués (secrets, validation d'input, couverture de tests) avec vérification de chaque candidat. Toute affirmation est étayée par `fichier:ligne` + extrait. Les valeurs de secret réelles sont tronquées.
- **Contraintes respectées** : aucune écriture hors ce rapport, aucun commit, aucune requête contre la prod.

## Ce qui va bien

- **Gating des mutations solide** : tous les endpoints POST/PATCH/DELETE portent une dépendance `get_current_user` ou `require_admin` (`routers/*.py`, cf. §Angle 1). Tous les endpoints admin sans exception passent par `require_admin` (`routers/admin.py:72…662`, 26 occurrences ; `taxonomy.py:348`, `genres.py:70,174,187`, `watchlist.py:381`, `radar.py:144`).
- **Pas de fallback `user_id=1`** : `uid()` renvoie `None` pour les guests (`dependencies.py:67-69`), conforme au multi-user.
- **Isolation multi-user correcte sur les collections** : chaque accès passe par `_get_user_collection(db, id, user.id)` (`routers/collections.py:72,113,176,198`) → pas d'IDOR. Le statut d'import vérifie l'ownership (`import_rb.py:84`).
- **JWT_SECRET sans défaut** : `os.environ["JWT_SECRET"]` en fail-fast (`auth.py:10`), jamais défauté en dur.
- **Pas d'injection SQL** : requêtes ORM ou `text()` avec paramètres liés partout ; les rares interpolations f-string dans `text()` portent sur des fragments dérivés de whitelists/booléens serveur, jamais de saisie brute (`taxonomy.py:88,310,324`, `genre_service.py:496`).
- **Pas de path traversal MinIO** : toutes les clés S3 sont construites à partir d'IDs entiers ou d'UUID serveur (`tracks.py:83,153`, `import_rb.py:59`, `image_service.py:148`…), jamais d'une string libre utilisateur.
- **Bornage des `limit`** : tous les endpoints de listing bornent `limit` avec `le=…` (catalog, tracks, sets, artists, genres, radar, search, watchlist, taxonomy, admin).
- **CSRF OAuth robuste** : `state` généré via `secrets.token_urlsafe(32)`, stocké Redis TTL 5min, consommé one-shot par `redis.delete` (`routers/auth.py:32-33,57`).
- **Secrets** : `.env.example` = placeholders, workflows CI = `${{ secrets.* }}`, aucune clé AWS/SSH/PEM en dur trouvée. `POSTGRES_PASSWORD`/`MINIO_PASSWORD` sans repli `:-` en dur.
- **Couche dedup/merge de sets bien testée** : `set_dedup_service.py` 83%, 31+ tests, signature `match_set → tuple[list, list]` à jour dans les tests (pas de divergence de mock).
- **Flow 401 frontend testé** : l'intercepteur axios (logout + redirect `/login`) est couvert (`__tests__/utils/api.test.js:64-75`).

---

## Findings

### [A6-01] Tokens OAuth TIDAL réels commités dans le repo
- **ID** : A6-01
- **Type** : securite
- **Sévérité** : critique
- **Effort estimé** : M (1h-1j)
- **Confiance** : haute
- **Preuve** : `server/scripts/.tidal_tokens.json` (tracké, introduit commit `7627519` « feat(watchlist): add TIDAL + Spotify playlist sources », 2026-06-19) :
  ```json
  { "token_type": "Bearer",
    "access_token": "eyJraWQiOiJ2OU1Gb…",   // JWT ES256, uid=208621898, exp=1781874663
    "refresh_token": "eyJraWQiOiJoUzFKY…",   // JWT ES512, pas d'exp
    "expiry_time": "2026-06-19 13:11:02" }
  ```
  `.gitignore` (ligne 4) ne couvre que `.env`, pas ce fichier. Fichier encore utilisé par le code : `server/scripts/test_sources.py:87,132,230` et `server/workers/source_clients.py:247`.
- **Constat** : un `access_token` et surtout un `refresh_token` TIDAL réels (compte uid 208621898, scopes `r_usr w_sub w_usr`) sont versionnés et présents dans l'historique git. L'access_token est expiré (exp = 2026-06-19), mais le `refresh_token` ES512 ne porte aucune date d'expiration et reste potentiellement exploitable pour émettre de nouveaux access_tokens. C'est le seul fichier de credentials tracké mais il expose un compte tiers complet.
- **Recommandation** : (1) révoquer/rotationner le token côté TIDAL immédiatement ; (2) `git rm --cached server/scripts/.tidal_tokens.json` + ajout à `.gitignore` ; (3) purger de l'historique (`git filter-repo` ou BFG) — le fichier reste sinon accessible dans tous les clones. Confirmer que la prod lit bien ses tokens depuis Redis (`source_clients.py:132-216`) et pas depuis ce fichier.
- **Dépendances** : aucune
- **Tags optionnels** : QUICK-WIN-CANDIDAT (retrait du suivi), lié-chantier:watchlist

### [A6-02] Rate limiting contournable par spoof de X-Forwarded-For
- **ID** : A6-02
- **Type** : securite
- **Sévérité** : haute
- **Effort estimé** : S (< 1h)
- **Confiance** : haute
- **Preuve** : `server/api/rate_limit.py:36-40`
  ```python
  def _get_real_ip(request) -> str:
      forwarded = request.headers.get("X-Forwarded-For")
      if forwarded:
          return forwarded.split(",")[0].strip()   # ← 1re valeur = fournie par le client
      return request.client.host
  ```
  Nginx pose `X-Forwarded-For $proxy_add_x_forwarded_for` (`nginx/default.ssl.conf.template:45`), qui **ajoute** l'IP réelle à la valeur envoyée par le client sans l'écraser. Le code prend `split(",")[0]` = la valeur la plus à gauche = celle contrôlée par l'attaquant.
- **Constat** : la clé de rate-limit est `ratelimit:{path}:{ip}` (`:57`). Un attaquant qui envoie un header `X-Forwarded-For` arbitraire obtient un compteur distinct à chaque requête, contournant trivialement les limites — notamment sur `/api/auth/google/callback` (5/60s), `/api/import/rekordbox` (3/300s) et `/api/admin` (10/60s). Le rate limiting anti-bruteforce/anti-abus est donc inopérant.
- **Recommandation** : ne pas faire confiance au header côté application. Utiliser `request.client.host` (l'IP réelle vue par uvicorn derrière nginx = l'IP nginx… donc préférer prendre la **dernière** valeur du XFF, ajoutée par nginx, `forwarded.split(",")[-1]`), ou mieux : configurer nginx pour poser un header non-forgeable (`X-Real-IP $remote_addr`, déjà présent ligne 44) et lire **celui-là** exclusivement. `X-Real-IP` est écrasé par nginx à chaque hop → non spoofable ici.
- **Dépendances** : aucune
- **Tags optionnels** : QUICK-WIN-CANDIDAT

### [A6-03] Parsing XML Rekordbox vulnérable à l'expansion d'entités (billion laughs)
- **ID** : A6-03
- **Type** : securite
- **Sévérité** : moyenne
- **Effort estimé** : S (< 1h)
- **Confiance** : haute
- **Preuve** : `server/api/services/rekordbox_xml.py:4,14,24`
  ```python
  import xml.etree.ElementTree as ET
  root = ET.fromstring(content)   # validate_rekordbox_xml (:14) ET parse (:24)
  ```
  La **validation** tourne de façon synchrone dans le process API sur le contenu brut uploadé, avant tout offload Celery (`routers/import_rb.py:39`). Le parsing tourne dans le worker (`workers/tasks/import_rb.py:66`).
- **Constat** : `xml.etree.ElementTree` est documenté comme non sûr contre des données malveillantes. L'XXE classique (lecture `file:///`) n'est pas exploitable (ElementTree ne résout pas les entités externes par défaut), mais l'expansion d'entités internes (« billion laughs » / quadratic blowup) n'est pas protégée : un fichier < 10 Mo peut définir des entités qui explosent en plusieurs Go de RAM. La validation étant synchrone dans le web worker (`import_rb.py:39`), l'attaque frappe directement l'API, pas seulement Celery.
- **Recommandation** : remplacer `xml.etree.ElementTree` par `defusedxml.ElementTree` (drop-in) dans `rekordbox_xml.py`. Ajouter `defusedxml` aux dépendances.
- **Dépendances** : aucune
- **Tags optionnels** : QUICK-WIN-CANDIDAT, lié-chantier:import

### [A6-04] Pipeline d'enrichissement (code prod actif) à 0 % de couverture, masqué par le `omit`
- **ID** : A6-04
- **Type** : dette
- **Sévérité** : moyenne
- **Effort estimé** : L (> 1j)
- **Confiance** : haute
- **Preuve** : `server/workers/enrichment.py` (0 %, 272 stmts) importé en prod par `tasks/catalog.py:55,175`, `tasks/genres.py:41`, `tasks/radar.py:248`, `tasks/sets.py:121,248`. Le gate de couverture l'**exclut explicitement** : `pyproject.toml:49-61`
  ```toml
  omit = [
      "server/workers/tasks/*",
      "server/workers/source_clients.py",
      "server/workers/enrichment.py",
      ...
      "server/api/beatport/*",
  ]
  ```
- **Constat** : `enrichment.py` (cascade de recherche Deezer, stratégie ISRC/release Beatport, résolution de conflits ISRC) n'a **aucun test réel** — les 3 occurrences « enrichment » dans `tests/` sont des docstrings. Or c'est du code prod critique appelé par 4 modules de tâches. Le `omit` du `[tool.coverage.run]` exclut précisément les modules les plus risqués (`workers/tasks/*`, `source_clients.py`, `enrichment.py`, `beatport/*`), si bien que le gate CI `--cov-fail-under=55` (`.github/workflows/deploy.yml`) mesure une couverture aveugle aux zones à 0-9 %. La couverture réelle hors `omit` est ~52 % (`_inventory.md` §4).
- **Recommandation** : ajouter des tests unitaires sur `enrichment.py` (mock des clients HTTP), en priorité la résolution de conflits ISRC et la cascade Deezer. Retirer progressivement les modules du `omit` au fur et à mesure qu'ils sont testés, pour que le gate reflète le vrai risque.
- **Dépendances** : aucune
- **Tags optionnels** : lié-chantier:C2

### [A6-05] Payloads non bornés (listes et strings) sur plusieurs endpoints mutants
- **ID** : A6-05
- **Type** : securite
- **Sévérité** : moyenne
- **Effort estimé** : S (< 1h)
- **Confiance** : haute
- **Preuve** :
  - `routers/radar.py:131` `body: list[RadarBatchItem]` — liste sans `max_length` (contraste avec `/tracks/bulk` borné à `MAX_BULK_IMPORT_SIZE`, `tracks.py:36`).
  - `schemas/tracks.py:63` `image_base64: Optional[str] = None` — string sans `max_length`, décodée en base64 sans borne (`tracks.py:79,149`), × 5000 items possibles.
  - `schemas/watchlist.py:11-14` `external_id/source/description: str` — aucune borne.
  - `schemas/sets.py:130-132` `SetImportIn.url/slug: str | None` — aucune borne (mineur, parsés par regex ensuite).
- **Constat** : plusieurs bodies de POST/PATCH acceptent des listes ou strings arbitrairement grandes. Le cas le plus concret est `image_base64` (jusqu'à 5000 strings illimitées décodées en mémoire) et `PATCH /radar/state/batch` (liste illimitée d'items → charge DB non bornée). Vecteur de DoS mémoire/CPU authentifié.
- **Recommandation** : borner les listes avec `Body(max_length=…)` (radar batch) et les strings Pydantic avec `Field(max_length=…)` (image_base64 → limite raisonnable ex. 2–4 Mo de base64 ; external_id/source/description ex. 255/32/500).
- **Dépendances** : aucune
- **Tags optionnels** : QUICK-WIN-CANDIDAT, lié-chantier:C3

### [A6-06] Métacaractères LIKE (`%`, `_`) non échappés dans les recherches
- **ID** : A6-06
- **Type** : securite
- **Sévérité** : basse
- **Effort estimé** : M (1h-1j)
- **Confiance** : haute
- **Preuve** : ~11 emplacements construisent `f"%{q}%"` passé à `.ilike()`/`LIKE` sans échapper `%`/`_` : `search.py:49,100,166,211,248`, `tracks.py:238`, `sets.py:111`, `radar_service.py:122`, `catalog_service.py:169`, `artist_service.py:109-110`, `genre_service.py:493`.
- **Constat** : les termes sont liés en paramètre (**pas d'injection SQL**), mais les wildcards `%`/`_` fournis par l'utilisateur restent actifs → wildcard injection (un `%` matche tout) et requêtes lentes potentielles (pattern à `%` en tête = scan séquentiel). Atténué par le bornage `max_length=200` des termes.
- **Recommandation** : échapper `%`, `_`, `\` dans le terme avant interpolation et passer `.ilike(pattern, escape="\\")`. Centraliser dans un helper `like_escape()`.
- **Dépendances** : aucune
- **Tags optionnels** : lié-chantier:C2

### [A6-07] LoginCallbackView (point d'entrée des credentials OAuth dans la SPA) sans aucun test
- **ID** : A6-07
- **Type** : dette
- **Sévérité** : moyenne
- **Effort estimé** : M (1h-1j)
- **Confiance** : haute
- **Preuve** : `server/frontend/src/views/LoginCallbackView.vue` — 0 test. Toute la logique cookie y est confinée : `readCookie('auth_callback')` (`:21-24,40`), `deleteCookie` (`:26-28,41`), décodage base64url→base64 + re-padding (`:49-51`), `auth._persist(token, user)` (`:53`), 3 branches d'erreur (`route.query.error` `:32`, cookie manquant `:43`, base64 malformé `:55`).
- **Constat** : le cœur du flow d'auth mobile (cookie `auth_callback`, décrit comme fragile et non-simplifiable dans CLAUDE.md à cause de Safari iOS) est entièrement à découvert côté frontend. Le backend teste bien le contenu du cookie (`test_auth.py:69`) mais le consommateur JS — re-padding base64url, purge du cookie, gestion des 3 erreurs — n'est jamais exercé. Une régression silencieuse ici casse l'auth pour tous.
- **Recommandation** : ajouter un test Vitest sur `LoginCallbackView` couvrant : cookie valide → persist + redirect, cookie absent, base64 malformé, `?error=` présent. Mocker `document.cookie` et le store auth.
- **Dépendances** : aucune
- **Tags optionnels** : lié-chantier:auth

### [A6-08] Tâche d'import Rekordbox (code utilisateur) non testée
- **ID** : A6-08
- **Type** : dette
- **Sévérité** : moyenne
- **Effort estimé** : M (1h-1j)
- **Confiance** : haute
- **Preuve** : `server/workers/tasks/import_rb.py:51-205` (19 %) jamais exécuté par un test ; `tests/api/test_integration.py:8` documente explicitement le skip (« `import_rekordbox_xml` use PG-specific SQL »). Le parsing pur `services/rekordbox_xml.py` n'a aucun test dédié (grep `parse_rekordbox_xml tests` → 0 hit).
- **Constat** : la seule voie par laquelle un utilisateur alimente sa bibliothèque n'est pas testée : batching, comptage inserted/updated via snapshot, upsert `on_conflict_do_update` PostgreSQL, progression Redis, `finally` de nettoyage/lock. Le blocage est structurel : l'upsert utilise du SQL PG non exécutable en SQLite (défaut des tests).
- **Recommandation** : ajouter des tests exécutés en mode PG (le job CI tourne déjà sur PG réel, `DATABASE_URL=postgresql…`) couvrant l'upsert et le comptage ; tester `parse_rekordbox_xml` en pur sur des fixtures XML (nominal, COLLECTION absente, entités).
- **Dépendances** : A6-03 (même surface d'import)
- **Tags optionnels** : lié-chantier:import

### [A6-09] Test qui valide une réplique d'un module inexistant (fausse couverture)
- **ID** : A6-09
- **Type** : dead-code
- **Sévérité** : basse
- **Effort estimé** : S (< 1h)
- **Confiance** : haute
- **Preuve** : `tests/worker/test_check_sync.py:51-59` appelle `_detect_duplicates`, une **copie locale** de la logique. La vraie fonction visée `_run_duplicate_check` (`:10-38`) qui patcherait `worker.check_sync.DeezerExtractor` n'est jamais appelée, et le module `worker/check_sync.py` **n'existe pas** (le dossier racine `worker/` ne contient que `import_rekordbox.py` et `relocate_tracks.py`).
- **Constat** : ces 6 tests passeraient même si le code cible avait disparu (c'est le cas) → faux sentiment de couverture. De plus `test_relocate_tracks.py:4` importe `worker.relocate_tracks` (dossier legacy hors `server/`, donc invisible au `--cov=server`).
- **Recommandation** : soit rebrancher les tests sur le vrai code de prod (`server/workers/…`), soit supprimer `test_check_sync.py` et le dossier legacy `worker/` (singulier) confirmé mort. À croiser avec l'agent hygiène/dead-code.
- **Dépendances** : aucune
- **Tags optionnels** : QUICK-WIN-CANDIDAT, hors-domaine:hygiène

### [A6-10] Endpoints internes exposés aux invités (divulgation d'information)
- **ID** : A6-10
- **Type** : securite
- **Sévérité** : basse
- **Effort estimé** : S (< 1h)
- **Confiance** : haute
- **Preuve** :
  - `auth_middleware.py:29` `_OPEN_PREFIXES` inclut `/api/watchlist/active` ; le handler `list_active_playlists` (`watchlist.py:103-115`) n'a aucune dépendance user → liste toutes les playlists suivies à un appelant non authentifié. Commentaire : « Used by crawl_radar » (endpoint interne).
  - `main.py:66-67` `docs_url="/api/docs"`, `openapi_url="/api/openapi.json"` — schéma OpenAPI complet public en prod (les deux sont dans `_OPEN_PREFIXES`, `auth_middleware.py:26-27`).
- **Constat** : un endpoint destiné au crawler interne est accessible aux guests, et le schéma d'API complet (tous les endpoints, y compris admin) est exposé publiquement. Pas de fuite de données utilisateur sensibles, mais surface de reconnaissance offerte aux scanners.
- **Recommandation** : retirer `/api/watchlist/active` de `_OPEN_PREFIXES` et le passer derrière `require_admin` (ou l'appeler en interne sans exposition HTTP) ; désactiver `/api/docs` + `/api/openapi.json` en `ENV=production` (les conditionner à `os.getenv("ENV") != "production"`).
- **Dépendances** : aucune
- **Tags optionnels** : QUICK-WIN-CANDIDAT, lié-chantier:C3

### [A6-11] Logging du corps de réponse du endpoint token Google
- **ID** : A6-11
- **Type** : securite
- **Sévérité** : basse
- **Effort estimé** : S (< 1h)
- **Confiance** : moyenne
- **Preuve** : `server/api/auth.py:50-52`
  ```python
  logger.warning("Google token endpoint %s — body: %s", resp.status_code, resp.text)
  ```
- **Constat** : logge le corps brut de la réponse de `oauth2.googleapis.com/token`. Ce log ne se déclenche que sur `status_code != 200` (cas d'erreur, où Google renvoie `{"error":"invalid_grant",…}` sans token) — le risque réel est faible, mais logger `resp.text` d'un endpoint OAuth reste une mauvaise pratique (contexte potentiellement sensible selon l'API, et pollution des logs JSON).
- **Recommandation** : ne logger que `resp.status_code` (et éventuellement `resp.json().get("error")`), pas `resp.text` intégral.
- **Dépendances** : aucune
- **Tags optionnels** : QUICK-WIN-CANDIDAT

### [A6-12] Contrôle de taille d'upload après bufferisation complète + incohérence nginx/app
- **ID** : A6-12
- **Type** : perf
- **Sévérité** : basse
- **Effort estimé** : S (< 1h)
- **Confiance** : haute
- **Preuve** : `routers/import_rb.py:34-37`
  ```python
  content = await file.read()          # lit tout le corps en mémoire
  if len(content) > MAX_FILE_SIZE:     # 10 Mo — contrôle APRÈS lecture
      raise HTTPException(status_code=413, …)
  ```
  nginx autorise `client_max_body_size 50M` (`nginx/default.ssl.conf.template:19`).
- **Constat** : un fichier de 10–50 Mo est intégralement lu en RAM avant d'être rejeté à 10 Mo. L'écart nginx (50M) / app (10M) laisse passer 5× la limite applicative jusqu'au buffer. Impact faible (authentifié, borné à 50M par nginx) mais gaspillage mémoire évitable.
- **Recommandation** : aligner `client_max_body_size` sur 10M dans nginx (rejet au bord), ou lire le flux par chunks avec arrêt anticipé au dépassement.
- **Dépendances** : aucune
- **Tags optionnels** : QUICK-WIN-CANDIDAT

### [A6-13] Rate limiter fail-open silencieux si Redis indisponible
- **ID** : A6-13
- **Type** : securite
- **Sévérité** : basse
- **Effort estimé** : S (< 1h)
- **Confiance** : haute
- **Preuve** : `rate_limit.py:72-74`
  ```python
  except Exception:
      # If Redis is unavailable, let the request through
      pass
  ```
- **Constat** : toute erreur Redis désactive silencieusement le rate limiting pour la requête. Un attaquant capable de saturer/faire tomber Redis contourne toutes les limites. Choix de disponibilité assumé (commentaire explicite), mais combiné à A6-02 le rate limiting offre une garantie faible.
- **Recommandation** : au minimum logger l'événement (aujourd'hui totalement muet) pour détecter la dégradation ; envisager un fail-closed sur les endpoints sensibles (`/api/auth/*`, `/api/import/*`).
- **Dépendances** : A6-02
- **Tags optionnels** : aucune

### [A6-14] Branches d'échec du flow OAuth et cycle de vie radar non couverts en CI
- **ID** : A6-14
- **Type** : dette
- **Sévérité** : basse
- **Effort estimé** : M (1h-1j)
- **Confiance** : haute
- **Preuve** :
  - `routers/auth.py:64-68` (exception `verify_google_token` → `error=google_failed`), `:82-87` (boucle de collision de username), `:102-104` (update `picture_url`) — aucun test ne les déclenche (`test_auth.py` mocke toujours un `verify_google_token` réussi et le même `google_id`).
  - `verify_google_token` lui-même (`auth.py:36-68`, échange HTTP Google + vérif id_token) jamais exercé.
  - `tests/api/test_radar.py:318` `@pytest.mark.skipif(not DATABASE_URL.startswith("postgresql"))` sur toute la classe `TestCrawlDiffLifecycle` → en CI SQLite (défaut) tout le cycle `removed_at` est silencieusement skippé.
- **Constat** : les chemins d'échec de l'auth (le plus critique pour la sécurité) et le lifecycle radar ne sont pas testés dans la configuration de test par défaut. Fixtures Redis partagées non réinitialisées entre tests (`conftest.py:112` singleton `_fake_redis`, `_store` jamais purgé) → fuite d'état `oauth_state:*` possible entre tests, fragilité.
- **Recommandation** : ajouter des tests sur les 3 branches d'échec de `google_callback` (mock d'exception, 2 users même `name`, changement de picture) ; s'assurer que `TestCrawlDiffLifecycle` tourne dans le job CI PG ; réinitialiser `_fake_redis._store` en fixture autouse.
- **Dépendances** : aucune
- **Tags optionnels** : lié-chantier:C3

---

## Non couvert (budget / hors-portée)

- **Vérification dynamique** : aucun test d'intrusion actif (contrainte). Les findings A6-02/03/05 sont établis par analyse statique ; une PoC confirmerait l'exploitabilité mais dépasse le mandat READ-ONLY.
- **`stores/audioPlayer.js`** : test existant court (`__tests__/stores/audioPlayer.test.js`) non audité en profondeur (file de lecture/preview HTML5).
- **Rotation/gestion des tokens TIDAL/Deezer/Spotify en Redis** (`source_clients.py`) : le stockage Redis semble correct (pas de log de token vérifié), mais la logique de refresh n'a pas été auditée ligne à ligne (0 % de couverture, cf. A6-04).
- **Composables frontend** (`useInfiniteScroll`, `useTheme`, `useStyleMap`) : 0 test, non détaillés ici (risque plus faible que l'auth).
