# Audit 2026-08-24 — A3 : Workers

> Date : 2026-08-24
> Agent : A3
> Périmètre : `server/workers/` intégral (celery_app, 10 modules tasks/, deezer_enrich, enrichment, bpm_analysis, rate_limiter, source_clients, crawl_logger, artist_merge, artist_names, async_http, catalog_merge/dedup, db) + `server/api/trackid/` (importer, reliability). Priorité au delta depuis 2026-08-09 (AV4/AV8/AV9, C8, hygiène artistes, precompute reco, throttle BPM, DIGGY-APP-4/10, auto-heal).
> Méthode : lecture + greps croisés + git log. Aucune requête prod, aucune modification hors ce rapport.

## Ce qui va bien

Le delta 2026-08-09 → 2026-08-24 a réellement durci le socle — vérifié dans le code, pas sur parole :

- **Plus AUCUN `autoretry_for=(Exception,)` dans `workers/tasks/`** (2026-08/A3-03/A3-04 soldés par AV4) : grep `autoretry_for` → uniquement des commentaires « NO autoretry » sur les 20 occurrences. Toutes les tâches longues portent le trio lock/budget/catch.
- **Pattern lock Redis conforme sur TOUTES les tâches longues**, y compris les nouvelles : `lock:precompute_reco` TTL 2100 > time_limit 1800 (`tasks/recommendations.py:30,53`), `lock:analyze_bpm` 3900 > 3300 (`bpm.py:33,92`), `lock:backfill_trackid_sets` 4200 > 3900 (`sets.py:24,825`), `lock:sync_artists` 4800 > 4500, `lock:enrich_deezer`… Partout `SET NX EX` atomique + release conditionnelle `if r.get(lock_key) == self.request.id`.
- **Garde deadline AV9 en place et bien placée** : `enrich_catalog` Deezer (`catalog.py:138,184`), `enrich_catalog_beatport` (`catalog.py:300,339`), `analyze_bpm_previews` (`bpm.py:133,168` — check EN TÊTE de chaque batch de 50, jamais mid-batch), et `backfill_trackid_sets` (3dcb68c) porte bien le check **en tête des DEUX boucles imbriquées** — collecte (`sets.py:937`) ET import (`sets.py:1002`). Constantes soft-limit module partagées décorateur+garde, stat `deadline_hit` dans crawl_logs. (Mais la sortie deadline du backfill retombe dans le mauvais chemin de persistance — voir A3-01.)
- **Fixes DIGGY-APP-4/10 (616b430) vérifiés** : `DeezerQuotaError` catchée au niveau wrapper de `crawl_single_playlist` → skip gracieux `reason="deezer_quota"` sans DLQ (`tasks/radar.py:267-287`) ; `ObjectDeletedError` contenue par entrée avec PK résolue en tête, `errors+=1` SANS `_mark_searched` (`enrichment.py:452-527`).
- **`CrawlLogger.__enter__` committe la ligne `running`** (2026-08/A3-07 soldé, `crawl_logger.py:57-67`) et `__exit__` préfixe `error_message` du type d'exception + `exc_info` (AV8, `:74-92`) — plus de transaction longue ni de run tué invisible.
- **C8 conforme au design annoncé** : `trackid/reliability.py` PUR (règle unique `compute_set_unreliable`, ratio dominant 0.8, signal secondaire source_url ET placeholder — conservateur invariant #4) ; flag calculé au funnel `import_audiostream` à chaque (re-)import (`importer.py:177-182`) ; le recrawl repasse par lui (`min_age_hours=0`, `sets.py:472-474`) avec le commentaire explicite « deliberately NOT recomputed a second time » (`sets.py:503-512`) — c'est bien un choix, pas un oubli ; `_check_new_sets` applique `set_reliable()` (`artists.py:2144-2145`).
- **Heartbeat + auto-heal (080d34b) réels** : `snapshot_backlogs` est enveloppé d'un Sentry Cron monitor auto-upserté (`tasks/monitoring.py:33-63`, no-op sans DSN et en tests) ; les 3 conteneurs Celery portent le label `autoheal: 'true'` + healthcheck `celery inspect ping` (beat : mtime du schedule file), sidecar `willfarrell/autoheal:1.2.0` dans l'overlay prod (`docker-compose.ssl.yml:43-48`) — ferme le trou 2026-08-10→14. Le `--max-memory-per-child` recycle ENTRE les tâches, avant l'OOM cgroup silencieux.
- **Routing queues conforme** (2026-08/A3-08 soldé) : `sync_artists`, `backfill_multi_artists`, `reclassify_genres_chunk` routés `enrich` (`celery_app.py:101-103`) ; `precompute_recommendations` et `snapshot_backlogs` (aucune API externe) restent sur `celery` — correct ; `link_set_artists` (DB-only) sur `celery` — correct.
- **Hygiène artistes : les gardes anti-faux-positifs sont réelles.** `_matching_deezer_hits` (source unique des 2 matchers) hiérarchise 4 signaux avec les gates annoncées : fold vide non-latin refusé, acronymes des DEUX côtés, `FAN_FLOOR` sur les signaux faibles, space-fold accepté SEULEMENT en candidat distinct unique (`artists.py:467-561`) ; tri fans STABLE (rétro-compat). Les merges détectés en gather sont exécutés SÉQUENTIELLEMENT hors gather, chacun dans son commit avec rollback isolé, et le commit de batch précède les merges pour que leur rollback ne coûte jamais le stamping (`artists.py:767-803`). La résurrection 180j est le tier le plus bas (ne draine que le budget restant, `artists.py:432-443`) ; `NOT_FOUND` jamais ressuscité. `_should_skip`/placeholders `is_placeholder_artist` au funnel `_get_or_create` (`artists.py:952-958`).
- **Chord toujours propre** : `reclassify_all_genres` en chord + `finalize_reclassify` (release conditionnelle par token) + errback `reclassify_genres_error` (release best-effort, TTL 6h backstop). Aucun `result.get()` dans une task.
- **Candidats inventaire tranchés** : `tasks/genres.py:422` `traceback` = **faux positif** — c'est le 3ᵉ argument du contrat errback Celery (`link_error` passe `request, exc, traceback`), même catégorie que les hooks `on_task_failure`/`init_sentry` déjà actés résidus. `crawl_logger.py:52/:104` = **mort confirmé** (voir A3-06).
- **Résidus acceptés non re-signalés** : VPS fil-de-l'eau embeddings différé (C9.a), `ANALYSIS_BPM_EXECUTOR_WORKERS=1` en `.env` VPS, `TRACKID_BACKFILL_SETS_PER_DAY` override prod, signal secondaire C8 inerte (suivi OPS documenté), outils locaux `worker/`+`server/deezer/`, rate limiter fail-open.

---

## Findings

### [A3-01] `backfill_trackid_sets` : la sortie deadline AV9 retombe dans le chemin de complétion NORMALE — faux `trackid_backfill_done` terminal sur batch vide, et curseur/page clobbés sur import partiel (sets sautés définitivement)
- **Type** : bug
- **Sévérité** : haute
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** : `server/workers/tasks/sets.py`
  - Les deux breaks deadline (`:937-947` collecte, `:1002-1011` import) sortent des boucles puis l'exécution CONTINUE dans le flux normal :
    ```python
    # :994-996 — deadline pendant la collecte, rien collecté :
    if not batch:
        await async_engine.dispose()
        return 0, 0, None, None
    # :1066 — deadline pendant l'import, batch partiellement traité :
    new_cursor = batch[-1].get("addedOn", "")
    ```
  - Côté orchestrateur (`:1099-1110`) : `new_cursor is None` → `r.set("trackid_backfill_done", "1")` + `r.delete("trackid_backfill_page")` ; sinon `r.set("trackid_backfill_cursor", new_cursor)` + persistance de `end_page`.
  - Contraste : le chemin `SoftTimeLimitExceeded` (`:1078-1097`) fait exactement ce qu'il faut — curseur inline conservé, page délibérément NON persistée, avec le commentaire expliquant pourquoi (« saving it would skip the un-imported tail »).
- **Constat** : deux corruptions d'état par le même défaut (le `break` deadline n'est pas aiguillé vers le chemin « interrupted ») :
  1. **Faux done terminal** : deadline pendant la collecte avec `batch` vide (scénario réel : offset invalidé par Guard 1/2 → re-page depuis 0 → skip-scan à ~1,5 s/page ; à 3480 s de deadline ≈ 2300 pages ≈ 46k items, or le curseur historique est bien plus profond) → retour `(0, 0, None, None)` → `trackid_backfill_done=1`. Le early-exit `:858` fait alors skipper TOUS les runs futurs : le backfill s'auto-termine silencieusement alors qu'il a juste manqué de temps. Avant 3dcb68c, ce même scénario levait `SoftTimeLimitExceeded` → chemin « interrupted » sans marquage — la garde AV9 a donc introduit une régression sur ce cas. Seule trace : `{"status": "done", "deadline_hit": true}` dans crawl_logs, que personne ne guette.
  2. **Perte de données sur import partiel** : deadline en cours d'import → le curseur inline (avancé par set traité, `:1049-1051`) est ÉCRASÉ par `batch[-1]` = le plus VIEUX item collecté (`:1105`) → tous les sets collectés-mais-non-importés entre le point d'arrêt et la fin du batch sont sautés à jamais (le backfill remonte le temps, ces sets historiques ne seront jamais revus par `crawl_trackid_latest`). `end_page` est en plus persisté (`:1109-1110`), là où le chemin soft-limit s'en garde explicitement.
- **Recommandation** : après `asyncio.run(_backfill_all())`, si `deadline_hit` est vrai, prendre le MÊME chemin que le catch `SoftTimeLimitExceeded` : ne pas toucher `trackid_backfill_done`, ne pas écraser le curseur (déjà avancé inline), ne pas persister la page, `resolve_set_tracks.delay()`, stats `{"status": "interrupted", "deadline_hit": True}`. Simple : faire retourner `deadline_hit` par `_backfill_all` ou tester la variable `nonlocal` avant les écritures Redis. Ajouter 2 tests (deadline-collecte-vide ≠ done ; deadline-import-partiel conserve le curseur inline).
- **Dépendances** : régression introduite par 3dcb68c (extension AV9) ; à corriger avant tout re-run où le curseur/offset serait invalidé (Guard 1/2).
- **Tags** : QW-c

### [A3-02] La garde deadline AV9 manque sur les drains asyncio restants — `precompute_recommendations` (le plus récent), `crawl_trackid_latest`, `recrawl_incomplete_sets`, `sync_artists` Phase B ne reposent que sur le catch signal dont AV9 a prouvé qu'il peut être avalé
- **Type** : dette
- **Sévérité** : moyenne
- **Effort estimé** : M
- **Confiance** : haute
- **Preuve** :
  - Doctrine CLAUDE.md (Known Pitfalls, AV9) : « Le catch SoftTimeLimitExceeded ne suffit PAS sur un drain asyncio … Toute NOUVELLE tâche à drain long par batches sur asyncio doit porter la même garde ». Prouvé Sentry DIGGY-APP-J (« Fatal write error on socket transport »), et DIGGY-APP-4 a démontré que le mode de panne s'étend aux drains TrackID (d'où 3dcb68c).
  - `tasks/recommendations.py:120-136` — boucle par-user dans `asyncio.run(_run())`, soft 1500/hard 1800, seul un `except SoftTimeLimitExceeded: break` par-user ; aucun `time.monotonic()`. Créée le 2026-08-13 (702dd70), 4 jours avant la passe AV9 (0daada7) qui ne l'a pas balayée.
  - `tasks/sets.py:639-789` (`crawl_trackid_latest`, boucle pages+items) et `:446-576` (`recrawl_incomplete_sets`, boucle par set) — catches per-item `raise` + task-level présents, aucune deadline interne.
  - `tasks/artists.py:1029-1225` (`sync_artists` Phase B, gathers Deezer par chaîne) — aucun catch soft-limit du tout : la levée propage vers l'`except Exception … raise` (`:1221-1225`, `:1291-1293`), et si le signal est avalé par le transport, run jusqu'au hard 4500 → SIGKILL.
- **Constat** : si le signal billiard est avalé par le handler du transport asyncio, ces runs courent jusqu'au hard limit puis SIGKILL : ligne crawl_logs figée `running` (commitée à l'`__enter__` — au moins visible depuis A3-07 2026-08), lock orphelin ≤TTL, et pour `crawl_trackid_latest` le curseur `trackid_crawl_last_run` non avancé (re-scan complet la nuit suivante — bénin mais coûteux). Impact borné pour `precompute_recommendations` (chaque cache user est écrit immédiatement, cadence quotidienne, lock auto-guéri en 2100 s) — mais c'est précisément la tâche la plus longue de la queue `celery` (~30 s/user à froid) et la plus susceptible de dépasser 1500 s quand la base users grandit.
- **Recommandation** : appliquer le pattern AV9 exact (constante soft-limit module + `deadline = time.monotonic() + SOFT − MARGIN` vérifiée en tête de boucle, `break` propre, stat `deadline_hit`) : à `precompute_recommendations` en priorité (tête de la boucle users), puis `crawl_trackid_latest` (tête des boucles page ET item), `recrawl_incomplete_sets` (tête de la boucle sets), et `sync_artists` (tête de la boucle `needs_deezer` Phase B — plus un catch task-level pour finir en succès partiel plutôt qu'en error). Chaque garde tient en ~10 lignes, testable avec l'horloge factice via l'attribut `time` du module (pattern `tests/worker/test_deadline_exit.py`).
- **Dépendances** : A3-01 (corriger d'abord l'aiguillage deadline du backfill avant de dupliquer le pattern ailleurs).
- **Tags** : aucun

### [A3-03] Drain BPM : `batch_size=2000` est mathématiquement inatteignable sous le throttle preview ~1 req/s — `deadline_hit=True` devient la sortie NORMALE de chaque run saturé et le signal d'anomalie AV9 est neutralisé
- **Type** : perf
- **Sévérité** : moyenne
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** :
  - `rate_limiter.py:41-44` — `"deezer_preview": (BPM_PREVIEW_CONCURRENCY=2, BPM_PREVIEW_RATE=1.0)` (~1 download/s, mesuré 2026-08-23 : ~6 % de 429 à 0,86 req/s vs ~60 % à 3 req/s).
  - `celery_app.py:158-162` — beat `{"batch_size": 2000}` × fenêtre `hour="0-4"` (5 créneaux).
  - `bpm.py:133-135` — deadline interne = 3000 − 120 = **2880 s** de fenêtre utile par run. Or 2000 downloads à 1/s ≈ 2000 s À EUX SEULS, plus la résolution `/track/{id}` (fenêtre deezer partagée) et l'analyse Essentia (executor à **1 worker en prod**, résidu AV10 — quelques s/preview CPU) : un run à backlog plein ne peut jamais traiter 2000 candidats dans sa fenêtre.
  - `bpm.py:168-179` — la deadline coupe le run avec `deadline_hit=True` dans crawl_logs, conçu AV9 comme marqueur d'ANOMALIE (« a deadline exit is a SUCCESS with partial work, distinguishable from a full run »).
- **Constat** : tant que le backlog `bpm_missing` (~six chiffres) sature les runs, chaque créneau se termine par la deadline. Trois effets : (1) `deadline_hit` toujours vrai = le signal AV9 ne distingue plus rien (une vraie dérive de durée — CDN plus lent, executor saturé — est indiscernable du régime nominal) ; (2) le débit réel est ~500-1500/run selon le facteur limitant (download vs analyse à 1 worker), très en dessous des « 2000/run » affichés partout — le sizing du burn-down (courbe monitoring) se lit faux ; (3) le run occupe TOUTE sa fenêtre de 48 min sur un slot du worker enrich (-c 2), y compris le créneau 04h qui chevauche désormais `check_followed_artists` (04:45, même queue, même fenêtre API deezer partagée) et jouxte `enrich_catalog` (05:00) — la promesse « kept clear of the 05h Deezer window » du module (`bpm.py:14-16`) n'est plus tenue en fin de fenêtre. Le comportement reste SÛR (partiels commités par 50, lock relâché, idempotent) — c'est un problème de dimensionnement et d'observabilité, pas de correction.
- **Recommandation** : dimensionner `batch_size` au débit atteignable sous throttle (~`(2880 − marge_résolution) × BPM_PREVIEW_RATE`, soit ~1500-1800 à 1 req/s, moins si l'analyse à 1 worker est le goulot — mesurer sur les stats crawl_logs réelles), pour que `deadline_hit` redevienne un signal d'exception. Alternative : garder 2000 et introduire une stat distincte `throttle_bound` — mais retailler le batch est plus simple et rend aussi le « débit/nuit » affiché honnête.
- **Dépendances** : A3-04 (mêmes commentaires/doc à rafraîchir dans la même passe) ; couplé au diagnostic « ~50 % erreurs BPM » en cours (A3-05).
- **Tags** : aucun

### [A3-04] Divergences doc/code sur la fenêtre BPM : CLAUDE.md et les docstrings du module disent 00h→03h / 4 créneaux / ~8000/nuit, le code fait 00h→04h / 5 créneaux, et le plafond « /nuit » n'existe pas (pas de comptabilité inter-runs)
- **Type** : doc
- **Sévérité** : basse
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** :
  - `celery_app.py:160` — `crontab(minute=0, hour="0-4")` (5 créneaux, le 04h ajouté 2026-08-21 pour compenser le throttle, dixit le commentaire `:150-157` qui dit « 00h→04h … ≈ 10000/nuit »).
  - `bpm.py:14-16` — docstring module : « hourly 00h→03h » ; `bpm.py:36-38` — « 4 slots (00h-03h) × 2000 ≈ 8000/night » ; `DEFAULT_ANALYSIS_BPM_NIGHTLY_BUDGET = 8000` est un cap PAR RUN via `min()` (`bpm.py:127`), jamais un compteur trans-runs — à 5 créneaux le théorique est 10000, le réel throttle-borné bien moins (A3-03).
  - CLAUDE.md (tableau Celery Beat Schedule) : « `analyze_bpm_previews` … 00:00→03:00 (chaque h) … batch 2000, ~8000/nuit » ; même chiffre dans la section pitfalls (« no-op … 00h→03h »).
- **Constat** : trois sources se contredisent (beat = vérité, module = périmé, CLAUDE.md = périmé). Même famille que le pitfall Beatport déjà documenté (« batch_size × runs, PAS le budget » ) : le prochain lecteur qui dimensionne un backfill ou lit la courbe burn-down à partir de « 8000/nuit » se trompe doublement (fenêtre ET débit). Signalé explicitement comme divergence CLAUDE.md, conformément à la consigne du fichier.
- **Recommandation** : corriger CLAUDE.md (tableau + pitfall : 00h→04h, 5 créneaux, débit réel throttle-borné à documenter après mesure A3-03) et les deux docstrings de `bpm.py`. À faire dans la même passe que le retaillage A3-03 pour n'écrire les chiffres qu'une fois.
- **Dépendances** : A3-03 (le chiffre honnête dépend du retaillage).
- **Tags** : QW (doc pure, S, zéro risque — mais sévérité basse donc pas QW-c)

### [A3-05] Sélection BPM déterministe (`id DESC`) + échecs download sans aucune comptabilité : à ~50 % d'erreurs mesurées, une moitié du budget de chaque run re-traite la même tête de file
- **Type** : dette
- **Sévérité** : basse
- **Effort estimé** : M
- **Confiance** : moyenne
- **Preuve** :
  - `bpm_analysis.py:56-65` — `select_bpm_candidates` : `WHERE bpm_analysis_candidate_filter() ORDER BY id DESC LIMIT budget` — fenêtre déterministe, toujours la même tête tant que rien n'est stampé.
  - `bpm_analysis.py:129-134` + `:153-161` — un échec download/CDN (`audio_bytes` vide, `DeezerHTTPError`, decode) ne stampe RIEN (« NOT a verdict, retry ») : conforme à l'invariant E1 « outage ≠ tentative », mais sans AUCUN plafond — contrairement aux 3 tentatives des recherches Deezer/Beatport/artistes.
  - Mémoire projet `monitoring-backlogs-tuning` : « diagnostic ~50 % erreurs BPM en attente (download preview échoué) ».
- **Constat** : si les erreurs sont du 429 CDN aléatoire (rate-based), le retry sans stamp est CORRECT et le throttle 1 req/s (19d7b38) est le bon remède. Mais si une fraction est PERSISTANTE par track (preview géo-bloquée, URL morte côté Deezer alors que `has_preview=True`), ces entrées restent éternellement dans la fenêtre `id DESC` et re-consomment le budget chaque nuit sans jamais converger — un E1 sans tier d'abandon. Le point est indécidable depuis le code seul ; il dépend du diagnostic en cours.
- **Recommandation** : instrumenter d'abord (le diagnostic en attente) : logger les `catalog_id` en erreur sur 2-3 nuits et mesurer le taux de récidive par id. Si récidive forte : introduire un compteur d'échecs download distinct (nouvelle colonne ou réutiliser `bpm_analysis_attempts` avec un tier « verdict no_preview après N échecs consécutifs ») — en préservant l'invariant « un 429 transitoire ne brûle rien ». Si récidive faible : no-op, clore.
- **Dépendances** : diagnostic OPS en cours (mémoire monitoring-backlogs-tuning) ; A3-03 (le même passage de mesure sur crawl_logs sert les deux).
- **Tags** : aucun

### [A3-06] Code mort : `CrawlLogger.update_stats` et la propriété `CrawlLogger.log_id` n'ont aucun appelant
- **Type** : mort
- **Sévérité** : basse
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** : `server/workers/crawl_logger.py:52-55` (`update_stats`) et `:104-106` (`log_id`). Grep `update_stats|\.log_id` sur tout `server/` (code + tests) → seules les définitions. Tous les consommateurs passent par `set_stats` (assignation entière).
- **Constat** : candidats inventaire vulture confirmés. `update_stats` est en outre subtilement piégeux s'il était réutilisé : il mute le dict JSON en place (`self._log.stats.update(...)`) sans `flag_modified`, ce qui sur une colonne JSON non-mutable-trackée ne serait pas toujours persisté — une raison de plus de le supprimer plutôt que de le laisser traîner.
- **Recommandation** : supprimer les deux (avec le `@property` associé) ; `set_stats` reste l'unique API.
- **Dépendances** : aucune.
- **Tags** : aucun

### [A3-07] `link_set_artists` : scan complet sets × noms (O(N·M) substring en Python) + 1 SELECT `set_artists` et 1 commit PAR set, sous les limites globales 1800/3600 — durée quadratique avec le volume, sans garde soft-limit par item
- **Type** : perf
- **Sévérité** : basse
- **Effort estimé** : M
- **Confiance** : haute
- **Preuve** : `server/workers/tasks/artists.py:1536-1589` — `select(DJSet)` intégral (tous les sets, ~12k+ et +~1000/j d'inflow TrackID), boucle `for dj_set in sets` × `for norm_name in sorted_names` (tous les artistes + alias, en substring `in`), puis par set : `select(SetArtist...)` (`:1565-1572`) et `session.commit()` (`:1589`). Décorateur sans limites explicites (`:1473-1476`) → soft 1800 / hard 3600 globaux. Aucun `except SoftTimeLimitExceeded: raise` par item ni catch task-level (contrairement aux boucles de `sets.py`).
- **Constat** : reliquat déjà effleuré dans 2026-08/A3-04 (le volet autoretry a été purgé par AV4, le scan reste). Tâche admin-only, idempotente, progrès commité par set — donc pas de corruption ; mais la complexité croît en (sets × artistes) et les ~12k commits/SELECTs par run pèsent. Le jour où elle dépasse 1800 s, elle finit en `error` (soft-limit propagé au milieu d'un commit) puis, relancée, refait tout le scan depuis zéro.
- **Recommandation** : (1) filtrer les sets candidats — p. ex. seulement ceux sans `SetArtist` OU créés depuis le dernier run (la matcher-passe est idempotente, inutile de re-scanner l'historique) ; (2) précharger `SetArtist` existants en UNE requête groupée ; (3) committer par lots de 100 plutôt que par set ; (4) au minimum, ajouter le clause-guard `except SoftTimeLimitExceeded: raise` + catch task-level, pattern du fichier voisin. Bench avant/après sur un dump.
- **Dépendances** : aucune.
- **Tags** : aucun

### [A3-08] `precompute_recommendations` est la seule tâche longue du beat sans ligne `crawl_logs` — invisible de la page admin Monitoring
- **Type** : dette
- **Sévérité** : basse
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** : `server/workers/tasks/recommendations.py` — grep `CrawlLogger` : 0 occurrence ; le module ne journalise que via `logger.info` (`:141`). Toutes les autres tâches longues du beat (drains, crawls, link/fetch artistes, backfills, `analyze_bpm_previews`) écrivent leurs stats dans `crawl_logs`, agrégées par `monitoring_service` pour la page admin.
- **Constat** : le run nightly le plus lourd de la queue `celery` (~30 s/user, pic ~1 Go RSS) n'apparaît ni dans l'admin crawl-logs ni dans les agrégats débit/durée/erreurs — un run raté (`errors` par user, soft-limit, SIGKILL) ne se voit que dans les logs conteneur/Sentry. Incohérent avec la convention du dossier ; c'est aussi ce qui rendrait diagnosticable le scénario A3-02.
- **Recommandation** : envelopper `_run_precompute` du `with Session(engine): with CrawlLogger(task_type="precompute_reco", ...)` standard et `clog.set_stats(stats)` (users/computed/errors, + `deadline_hit` quand A3-02 sera fait).
- **Dépendances** : A3-02 (même fichier, même passe).
- **Tags** : aucun

---

## Hypothèses vérifiées / réfutées

- **« La garde AV9 du backfill serait mal placée »** — réfuté : elle est bien EN TÊTE des deux boucles imbriquées (`sets.py:937`, `:1002`) ; c'est l'AVAL de la sortie qui est faux (A3-01).
- **« Le throttle preview ferait déborder le créneau BPM »** — confirmé mais absorbé par la deadline (aucun SIGKILL) ; le problème réel est le dimensionnement/l'observabilité (A3-03), pas la sûreté.
- **« `genres.py:422` traceback = code mort »** — réfuté : argument positionnel du contrat errback Celery, même catégorie que les hooks déjà actés FP.
- **« Un autoretry résiduel traînerait »** — réfuté : 0 `autoretry_for` actif dans `workers/tasks/` (20 occurrences = commentaires).
- **« L'auto-heal pourrait tuer un run enrich en cours »** — vrai en théorie (restart sur unhealthy = même classe que le kill de deploy), mais c'est le compromis documenté : locks TTL courts auto-guéris ≤1 créneau, et le healthcheck `inspect ping` répond depuis le master même quand les enfants travaillent. Pas de finding.
- **« `set_reliable()` ORM (`IS FALSE`) diverge de `set_reliable_sql` (`IS NOT TRUE`) sur NULL »** — vrai mais sans effet : colonne NOT NULL défaut false, et la docstring l'assume (« defensive »). Pas de finding.
