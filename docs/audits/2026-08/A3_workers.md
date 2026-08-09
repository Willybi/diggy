# Audit 2026-08 — A3 : Workers

> Date : 2026-08-09
> Agent : A3
> HEAD audité : `9b305d6` (2026-08-08). Audit précédent : `docs/audit_2026-07/A3_workers.md` (fixes livrés via AU4 + E1 + MON + chantiers C6/X1/X3/E2).
> Périmètre : `server/workers/` intégral — celery_app.py, tasks/ (9 modules : artists, bpm, catalog, genres, import_rb, monitoring, radar, sets, trends), deezer_enrich.py, source_clients.py, rate_limiter.py, enrichment.py, bpm_analysis.py, artist_merge.py, catalog_merge.py, catalog_dedup.py, crawl_logger.py, db.py, async_http.py. Lecture intégrale des 23 fichiers + vérifications croisées côté `server/api` (admin.py, import_rb.py, beatport/client.py, models/catalog.py) quand un contrat de tâche l'exigeait.
> Méthode : lecture + greps croisés + `git log -S`. Aucune requête prod. Aucune modification hors ce rapport.

## Ce qui va bien

Le gros des findings A3 2026-07 est réellement corrigé (vérifié dans le code, pas sur parole) :

- **2026-07/A3-01 corrigé** — la promotion `private` → `shared` existe dans le pipeline async : `enrichment.py:347-350` (`_enrich_entry_async`) porte le même bloc que le chemin sync (`deezer_enrich.py:447-450`).
- **2026-07/A3-02 corrigé** — `compute_trends` purge les lignes périmées : `_purge_stale_trends` (`tasks/trends.py:101-114`), appelée dans la même transaction que l'upsert (`:324`), stat `purged` loggée.
- **2026-07/A3-03 corrigé** — `reclassify_genres_chunk` ne vide plus les genres sur erreur source : le clear est gaté `if not found and not source_error` (`tasks/genres.py:148-150`).
- **2026-07/A3-04 corrigé côté Deezer** — `deezer_get` lève `DeezerHTTPError` sur tout non-200 final (`async_http.py:140-142`) ; `_mark_searched` n'est jamais appelé dans les branches `except DeezerHTTPError` (`enrichment.py:431-435`, docstring `:197-202` explicite « an outage is not an attempt »). Même règle sur les artistes (`tasks/artists.py:423-429`, `_link_artist_deezer` renvoie `("error", None)` sans stamper). **MAIS le jumeau Beatport viole toujours la règle — voir A3-02 ci-dessous.**
- **2026-07/A3-05 corrigé** — rate limiting partagé inter-process via fenêtre fixe Redis pour deezer/beatport (`rate_limiter.py:43-46`, `_SharedWindow` `:105-162`), fail-open assumé (résidu accepté AU4).
- **2026-07/A3-06/A3-07 corrigés** — `_deezer_get` de `source_clients.py:58-77` valide statut HTTP ET la clé JSON `error` (code 800 / DataException → `PlaylistGoneError` typée) ; une page de pagination en échec lève au lieu de retourner une tracklist partielle (`:98-101`). La suppression destructive de playlist n'est déclenchée QUE sur `PlaylistGoneError` (`tasks/radar.py:316`), TIDAL traduit uniquement `ObjectNotFound`/vrai 404 (`source_clients.py:309-324`). Plus aucun string-matching d'exception dans le périmètre.
- **2026-07/A3-08 corrigé (périmètre workers)** — les 3 `except Exception: pass` de `materialize_parent` dans `tasks/sets.py` loggent désormais (`:491-497`, `:622-630`, `:876-882`) ; le lien artiste raté logge un warning avec `exc_info` (`enrichment.py:425-429`).
- **2026-07/A3-09 corrigé** — `link_set_artists` est instrumenté `CrawlLogger` (`tasks/artists.py:1358-1361`) ; `crawl_followed_sets` n'existe plus (remplacée par `check_followed_artists`, instrumentée `:1998-2003`). Toutes les tâches beat écrivent dans `crawl_logs`.
- **2026-07/A3-10 corrigé** — plus aucun `result.get()` dans une task : `reclassify_all_genres` dispatch un `chord` + callback `finalize_reclassify` + errback `reclassify_genres_error` qui écrit la ligne `crawl_logs` d'échec (`tasks/genres.py:224-229`, `:273-307`).
- **2026-07/A3-11 corrigé** — `resolve_set_tracks` a son lock Redis (`lock:resolve_set_tracks`, TTL 2700 > time_limit 2400, `tasks/sets.py:17`, `:128-142`).
- **2026-07/A3-12 corrigé** — les artistes ont leur backoff E1 (`deezer_searched_at`/`deezer_search_attempts`, tiers 30/90j, abandon à 3, `tasks/artists.py:264-266`, `_link_tiers` `:334-366`) ; le sentinel `NOT_FOUND` reste une décision humaine (exclu des tiers).
- **2026-07/A3-13 corrigé** — lock `crawl:playlist:{id}` timeout 4600 > time_limit 4500 (`tasks/radar.py:265-266`).
- **2026-07/A3-14 corrigé** — l'import Rekordbox verrouille atomiquement côté routeur (`SET NX EX`, TTL 3700 > time_limit global 3600, `routers/import_rb.py:19-21`, `:51-57`) avec release conditionnelle des deux côtés (routeur `:79-80`, task `tasks/import_rb.py:222-226`).
- **2026-07/A3-16 mitigé côté code** — le fallback fichier TIDAL est surchargeable hors repo via `TIDAL_TOKEN_FILE` (`source_clients.py:283-289`) ; le fichier commité relève de Q4 option B (token révoqué, résidu accepté — non re-signalé).

**Pattern lock Redis : conforme sur les 10 tâches verrouillées.** Toutes utilisent `SET NX EX` atomique, TTL strictement > time_limit, release conditionnelle à la propriété (`if r.get(lock_key) == self.request.id`) :

| Tâche | Lock | TTL | time_limit | Réf. |
|---|---|---|---|---|
| `enrich_catalog_beatport` | `lock:enrich_beatport` | 3900 | 3300 | catalog.py:17, 174-188 |
| `analyze_bpm_previews` (E2.c) | `lock:analyze_bpm` | 3900 | 3300 | bpm.py:32, 74-88 |
| `resolve_set_tracks` | `lock:resolve_set_tracks` | 2700 | 2400 | sets.py:17, 128-142 |
| `recrawl_incomplete_sets` | `lock:recrawl_incomplete_sets` | 4200 | 3900 | sets.py:20, 293-309 |
| `backfill_trackid_sets` | `lock:backfill_trackid_sets` | 4200 | 3900 | sets.py:23, 700-716 |
| `link_artists_deezer` | `lock:link_artists` | 1800 | 1500 | artists.py:281, 530-544 |
| `fetch_artist_artworks` | `lock:fetch_artist_artworks` | 3600 | 3300 | artists.py:282, 1198-1214 |
| `check_followed_artists` | `lock:check_followed_artists` | 4200 | 3900 | artists.py:306, 1967-1983 |
| `crawl_single_playlist` | `crawl:playlist:{id}` (r.lock) | 4600 | 4500 | radar.py:265-277 |
| `import_rekordbox_xml` | `import:lock:{user_id}` (routeur) | 3700 | 3600 (global) | import_rb.py:51-57 |

- **E2.c `analyze_bpm_previews` : exemplaire.** Clone fidèle annoncé du drain Beatport, vérifié : pas d'`autoretry`, budget `min(batch_size, ANALYSIS_BPM_NIGHTLY_BUDGET)` (`bpm.py:110-111`), `progress` hissé + commit par lot de 50 pour qu'un soft-timeout flush le partiel (`:114-123`, `:158`), catch `SoftTimeLimitExceeded` → run « success » avec stats partielles + lock libéré par le `finally` externe (`:171-185`). **Essentia tourne bien hors boucle async** : `loop.run_in_executor(executor, _analyze_blocking, …)` (`bpm_analysis.py:136-140`), `ThreadPoolExecutor` borné (2 workers, `bpm.py:42`, `:134`), instance Essentia fraîche par appel (thread-safety, `bpm_analysis.py:68-82`), import Essentia lazy (CI sans essentia/ffmpeg), temp MP3 toujours supprimé (`:141-145`).
- **Comptabilité d'attempt BPM fidèle à E1** : un VERDICT (ok / low_conf / no_preview) stampe `bpm_analyzed_at` + incrémente `bpm_analysis_attempts` ; un échec réseau/download/decode ne stampe RIEN (`bpm_analysis.py:106-157`, branches `DeezerHTTPError`/`Exception` → `errors`, pas de stamp). Garde défensive `bpm IS NULL` re-vérifiée au moment de l'écriture même si le filtre candidat la garantit (`:97-100`, invariant #3). Prédicat partagé unique `bpm_analysis_candidate_filter()` (`models/catalog.py:117-129`) consommé par la tâche, `snapshot_backlogs` et l'admin.
- **Beat schedule = CLAUDE.md.** Les 12 entrées de `celery_app.py:103-179` correspondent exactement au tableau (horaires, kwargs `batch_size` 550/2000, fenêtres 6-23h et 0-3h, `snapshot_backlogs` à :30 sur la queue par défaut). `visibility_timeout` 30000 > plus long time_limit réel (16200, reclassify chunk).
- **Cadence slack appliquée aux deux gates quotidiennes** : `CADENCE_SLACK_DAYS = 0.25` dans `_crawl_decision` (`tasks/radar.py:21`, `:97`) et `_recrawl_decision` (`tasks/sets.py:31`, `:244`), avec le commentaire de justification. Aucun nouveau point d'usage manquant.
- **Idempotence des re-runs** : `bulk_get_or_create_catalog` / `bulk_insert_radar_tracks` en `ON CONFLICT DO NOTHING` (`db.py:127-134`, `:204-213`), upsert import RB `(user_id, catalog_id)` (`tasks/import_rb.py:160-171`), activités artistes dédupliquées par la contrainte unique + `_activity_exists` (`tasks/artists.py:1576-1594`), `is_initial_detection` propagé pour exclure les diffs de réveil de la vélocité (`tasks/radar.py:148-159`, `:384-401`), `backfill_trackid_sets` curseur Redis avancé inline + re-raise explicite de `SoftTimeLimitExceeded` avant le handler générique (`tasks/sets.py:871-875`, `:893-899` — le pattern de référence).
- **Dédup/merge conformes à l'invariant #4** : `fold_if_platform_id_taken` ne fusionne que sur `same_track` confirmé (`catalog_dedup.py:60-64`), `merge_catalog_entries` repointe toutes les FK (y compris `user_radar_state` et le pseudo-FK `user_opinions`) avant delete, union NULL-fill only, jamais de downgrade `shared`→`private` (`catalog_merge.py:199-399`). `merge_artist_into` collecté pendant le gather, exécuté séquentiellement hors gather, chaque merge dans son propre commit avec rollback isolé (`tasks/artists.py:611-682`) — exactement le contrat documenté.

---

## Findings

### [A3-01] `POST /admin/genres/auto-classify` dispatch un kwarg `genre_only` que `enrich_catalog_beatport` n'a jamais accepté — la tâche échoue en `TypeError` à chaque déclenchement
- **Type** : bug
- **Sévérité** : haute
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** :
  - `server/api/routers/admin.py:607-609` :
    ```python
    result = celery.send_task(
        "workers.tasks.enrich_catalog_beatport", kwargs={"genre_only": True}
    )
    ```
  - Signature réelle : `server/workers/tasks/catalog.py:162` — `def enrich_catalog_beatport(self, batch_size: int = 0)`. Aucun paramètre `genre_only`.
  - `git log --oneline -S "genre_only" -- server/workers/` → **vide** : le paramètre n'a JAMAIS existé côté workers. Il n'apparaît que dans `admin.py` (introduit par 5b6c7f7, page genres).
- **Constat** : `send_task` (dispatch par nom) ne valide rien localement ; le worker lève `TypeError: enrich_catalog_beatport() got an unexpected keyword argument 'genre_only'` à l'exécution. L'endpoint répond « queued » 200, le bouton admin « auto-classifier » semble fonctionner, et la classification ne tourne jamais. L'échec est de surcroît invisible : pas de ligne `crawl_logs` (le `CrawlLogger` n'est jamais atteint) et pas de DLQ (cf. A3-06). Fonctionnalité admin silencieusement morte.
- **Recommandation** : soit retirer le kwarg et dispatcher la tâche nue (comportement = drain Beatport standard, qui stampe les genres au passage), soit implémenter réellement un mode `genre_only` dans la tâche (filtre candidats `array_length(genres)=0`), soit rebrancher le bouton sur `reclassify_all_genres`. Ajouter un test qui appelle la tâche avec les kwargs que l'admin envoie (contrat routeur↔tâche).
- **Dépendances** : A3-06 (le même trou d'observabilité a masqué ce bug)
- **Tags** : QW-c

### [A3-02] Un échec HTTP Beatport est indistinguable d'un « not found » dans le drain async : l'outage consomme une tentative E1 (violation de l'invariant « outage ≠ attempt »)
- **Type** : bug
- **Sévérité** : moyenne
- **Effort estimé** : M
- **Confiance** : haute
- **Preuve** :
  - `server/workers/enrichment.py:506-508` (`_do_search`), `:533-535` (`_do_release_search`), `:580-582` (`_fetch_release_tracks`) — les trois retournent une liste vide sur tout statut non-200 :
    ```python
    resp = await pool.beatport_get(path)
    if resp.status_code != 200:
        return []
    ```
  - `server/workers/enrichment.py:653-678` (`enrich_beatport_batch._enrich_one`) : cascade vide → `bp_track is None` → `not_found += 1` → **`_mark_searched(entry, "beatport", …)`** ligne 678.
  - `server/workers/async_http.py:146-165` : `beatport_get` n'a NI retry NI gestion 429 (contrairement à `deezer_get` qui passe par `_request_with_retry` et lève `DeezerHTTPError` sur non-200 final, `:140-142`).
  - Contraste : le jumeau sync fait `resp.raise_for_status()` (`server/api/beatport/client.py:242`) — son caller compte une erreur sans stamper.
- **Constat** : pendant une vague de 403 Cloudflare ou un 5xx Beatport, chaque entrée du run horaire (jusqu'à 550) est marquée « cherchée, introuvable » : `beatport_searched_at` + `beatport_search_attempts` brûlés à tort. Trois incidents étalés sur les fenêtres 30/90j suffisent à faire basculer les mêmes lignes en `abandoned` définitif. C'est exactement le bug 2026-07/A3-04, corrigé côté Deezer (via `DeezerHTTPError`) mais jamais porté côté Beatport — alors que CLAUDE.md affirme l'invariant tenu partout (« An HTTP failure never stamps `*_searched_at` ») : **divergence doc/code à corriger dans CLAUDE.md si le fix n'est pas retenu**. Seules les erreurs réseau (exception curl) sont correctement comptées en `errors` sans stamp.
- **Recommandation** : miroir du fix Deezer — lever une `BeatportHTTPError` typée depuis les trois helpers sur non-200 (éventuellement en tolérant le 404 comme réponse valide « pas de page »), la catcher dans `_enrich_one` → `errors += 1` sans `_mark_searched`. Optionnel : donner à `beatport_get` le même retry/backoff 429 que `deezer_get`.
- **Dépendances** : sibling de 2026-07/A3-04 (même famille, source différente)
- **Tags** : aucun

### [A3-03] RÉCURRENCE — `enrich_catalog` (Deezer) garde `autoretry_for=(Exception,)` avec soft-limit 2h, et n'a toujours pas de lock
- **Type** : dette
- **Sévérité** : moyenne
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** : `server/workers/tasks/catalog.py:52-60` :
  ```python
  @celery_app.task(
      name="workers.tasks.enrich_catalog",
      bind=True,
      autoretry_for=(Exception,),
      retry_kwargs={"max_retries": 3, "countdown": 60},
      retry_backoff=True,
      soft_time_limit=7200,
      time_limit=9000,
  )
  ```
  Aucun lock Redis (contraste : le jumeau `enrich_catalog_beatport` juste en dessous, `:174-188`).
- **Constat** : point OUVERT suivi depuis 2026-07 (fiche mémoire `enrich-beatport-autoretry` : « reste le jumeau enrich_catalog Deezer » — issu du chantier MON, pas d'ID A3 2026-07). `SoftTimeLimitExceeded` EST une `Exception` : sur un gros backlog (ex. après un run `reverify_platform_ids` qui remet des milliers de lignes en éligibilité), un dépassement à 2h déclenche jusqu'à 3 retries → jusqu'à ~8h de runs Deezer sur le worker enrich (-c 2), en collision avec les fenêtres artistes (05:10/05:20) et les drains Beatport. Atténuation réelle constatée : les `DeezerHTTPError` par entrée sont avalées (comptées `errors`), donc le retry ne se déclenche que sur exception inattendue ou soft-limit — le risque est dormant, pas quotidien. Les commits par lot de 100 rendent au moins les retries résumables.
- **Recommandation** : appliquer le pattern désormais standard du fichier : retirer `autoretry_for`, catcher `SoftTimeLimitExceeded` avec flush des stats partielles, et (par cohérence) ajouter `lock:enrich_deezer` TTL ≥ 9000. Clore la fiche mémoire au passage.
- **Dépendances** : aucune
- **Tags** : RÉCURRENCE (2026-07, suivi mémoire — hors rapport A3-nn)

### [A3-04] Huit tâches gardent `autoretry_for=(Exception,)` malgré le pitfall documenté — dont `reclassify_genres_chunk` à 4h30 de time_limit
- **Type** : dette
- **Sévérité** : moyenne
- **Effort estimé** : M
- **Confiance** : haute
- **Preuve** — décorateurs `autoretry_for=(Exception,)` restants (hors A3-03) :
  - `tasks/genres.py:18` `reclassify_genres_chunk` — **soft 14400 / time 16200** (admin)
  - `tasks/artists.py:1438` `backfill_multi_artists` — soft 7200 / time 9000 (admin, sans lock)
  - `tasks/artists.py:737` `sync_artists` — soft 3600 / time 4500 (admin, sans lock)
  - `tasks/artists.py:1948` `check_followed_artists` — soft 3600 / time 3900 (beat 04:45, lock OK)
  - `tasks/sets.py:276` `recrawl_incomplete_sets` — soft 3600 / time 3900 (beat 04:00, lock OK)
  - `tasks/radar.py:253` `crawl_single_playlist` — soft 3600 / time 4500 (fan-out)
  - `tasks/sets.py:532` `crawl_trackid_latest` — limites globales 1800/3600 (beat 03:30, durée observée 15-17 min : marge faible)
  - `tasks/artists.py:1338` `link_set_artists` — limites globales (admin ; scan complet sets × noms, per-set commit `:1427` → durée croissante avec le volume)
  - (courtes/dispatchers, risque faible : `radar.py:165` crawl_radar, `trends.py:120` compute_trends, `genres.py:181/237` orchestrateur+callback)
- **Constat** : le pitfall CLAUDE.md (« SoftTimeLimitExceeded IS an Exception ») n'a été appliqué qu'aux tâches ayant déjà provoqué un incident (artists 2026-07-13, beatport MON, enrich_set_tracks c0c7392 — retirée pour EXACTEMENT ce cocktail autoretry×soft-limit). Les autres restent armées : un soft-timeout devient jusqu'à 3 re-runs pleine longueur — jusqu'à ~13h cumulées pour un chunk reclassify sur la queue `celery` (3 chunks en parallèle saturent `diggy_worker` -c 3 et affament la queue `crawl`). Les tâches admin (`sync_artists`, `backfill_multi_artists`, `link_set_artists`) n'ont par ailleurs aucun lock : un double-clic admin = deux runs concurrents.
- **Recommandation** : passe systématique — remplacer `autoretry_for=(Exception,)` par le trio budget-cap / catch `SoftTimeLimitExceeded` / lock sur les 6 tâches longues ; conserver l'autoretry uniquement sur les tâches courtes idempotentes (crawl_radar, compute_trends) où il protège d'un blip DB. Prioriser `reclassify_genres_chunk` (la plus longue) et `backfill_multi_artists`.
- **Dépendances** : A3-03 (même passe de code), A3-05 (à corriger ensemble sur sets.py)
- **Tags** : aucun

### [A3-05] `recrawl_incomplete_sets` et `crawl_trackid_latest` avalent `SoftTimeLimitExceeded` dans leur `except Exception` par-item — le soft-limit est inopérant, l'arrêt se fait par SIGKILL
- **Type** : bug
- **Sévérité** : moyenne
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** :
  - `server/workers/tasks/sets.py:498-503` (boucle par set de `_run_recrawl_incomplete_sets._crawl_all`) :
    ```python
    except Exception:
        errors += 1
        logger.exception("recrawl_incomplete_sets: failed for set %s", ...)
    ```
  - `server/workers/tasks/sets.py:635-640` (boucle par audiostream de `crawl_trackid_latest`) : même `except Exception` générique, `skipped += 1`.
  - Contraste dans le MÊME fichier : `backfill_trackid_sets` re-raise explicitement AVANT le handler générique, avec le commentaire expliquant pourquoi (`sets.py:893-899` : « without this clause it would be swallowed and the loop would run to the hard time_limit SIGKILL »).
- **Constat** : quand le soft-limit frappe pendant le traitement d'un set (là où la tâche passe ~tout son temps), l'exception est comptée comme un échec de set et la boucle CONTINUE jusqu'au hard limit → SIGKILL. Conséquences en chaîne : la ligne `crawl_logs` (flushée, jamais commitée — cf. A3-07) disparaît, les stats sont perdues, et pour `crawl_trackid_latest` le curseur `trackid_crawl_last_run` n'est pas avancé (le `r.set` est après le `asyncio.run`, `sets.py:658`) — la nuit suivante re-scanne toute la fenêtre. Le lock de recrawl s'auto-guérit par TTL (4200), pas de blocage. Avec `autoretry` (A3-04), un soft-timeout survenant HORS des try par-item déclenche en plus un retry pleine longueur : les deux mécanismes se cumulent.
- **Recommandation** : dupliquer le clause-guard de backfill (`except SoftTimeLimitExceeded: raise` avant le `except Exception`) dans les deux boucles, et catcher au niveau tâche pour finir proprement (stats partielles + crawl_log commité), comme `enrich_catalog_beatport`.
- **Dépendances** : A3-04 (même fichiers), A3-07 (perte de la ligne crawl_logs sur SIGKILL)
- **Tags** : aucun

### [A3-06] La DLQ ne reçoit JAMAIS les échecs des tâches sans autoretry — le garde-fou `retries < max_retries` filtre à tort les échecs déjà finaux
- **Type** : bug
- **Sévérité** : moyenne
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** :
  - `server/workers/celery_app.py:196-199` :
    ```python
    # Only route to DLQ after all retries are exhausted
    if hasattr(task, "request") and task.request.retries < task.max_retries:
        return
    ```
  - Celery : `Task.max_retries` vaut **3 par défaut** même pour une tâche qui ne retry jamais ; et le signal `task_failure` ne se déclenche QUE sur échec final (un retry émet `task_retry`). Donc pour toute tâche SANS `autoretry` — `enrich_catalog_beatport`, `analyze_bpm_previews`, `resolve_set_tracks`, `recrawl_*`/`backfill_trackid_sets`, `link_artists_deezer`, `fetch_artist_artworks`, `snapshot_backlogs` — un échec (final par construction) arrive avec `retries=0 < 3` → early return → jamais poussé dans `dead_letter`.
  - Consommateur : la carte admin lit `LLEN dead_letter` (`server/api/routers/admin.py:811-815`).
- **Constat** : le garde-fou visait à ne pas pousser les échecs intermédiaires, mais `task_failure` ne les voit de toute façon pas — il ne fait donc qu'exclure les échecs finaux des tâches modernes. Or depuis MON/E2.c le pattern maison est précisément de NE PAS avoir d'autoretry : la DLQ ne capture plus que `import_rekordbox_xml` (`max_retries=0` → `0 < 0` faux) et les vieilles tâches autoretry épuisées. Le `TypeError` permanent d'A3-01 en est la démonstration : jamais vu en DLQ. La carte admin « DLQ » observe une file quasi structurellement vide — fausse tranquillité.
- **Recommandation** : supprimer le garde (ou le réduire à `if isinstance(exception, Retry): return` par ceinture-bretelles) : quand `task_failure` se déclenche, l'échec est final par définition. Vérifier ensuite sur un échec provoqué en staging que la carte admin monte à 1.
- **Dépendances** : A3-01 (bug masqué par ce trou)
- **Tags** : aucun

### [A3-07] `CrawlLogger` tient une transaction PG ouverte (INSERT flushé, non commité) pendant TOUTE la durée du run — jusqu'à ~55 min par drain horaire ; sur SIGKILL, aucune trace du run
- **Type** : perf
- **Sévérité** : moyenne
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** : `server/workers/crawl_logger.py:55-59` :
  ```python
  def __enter__(self):
      self._session.add(self._log)
      self._session.flush()   # INSERT envoyé, transaction OUVERTE
      ...
  ```
  Le premier `commit()` n'arrive qu'au `__exit__` (`:79-82`). Toutes les tâches longues suivent le pattern `with Session(engine) as log_session: with CrawlLogger(...)` autour du corps entier (ex. `tasks/catalog.py:201-283`, `tasks/bpm.py:101-189`) tandis que le travail réel se fait sur d'AUTRES sessions.
- **Constat** : chaque run tient une connexion du pool en *idle in transaction* pour toute sa durée — 18 drains Beatport/jour jusqu'à 55 min chacun, 4 runs BPM/nuit, etc. Effets : (1) le xmin de ces transactions bloque l'horizon VACUUM de toute la base pendant les fenêtres de drain (bloat sur les tables chaudes `radar_tracks`/`set_tracks`/`crawl_logs`) ; (2) le statut `running` du modèle n'est JAMAIS observable (la ligne n'est visible qu'au commit final, déjà passée à success/error) ; (3) sur hard-kill SIGKILL (cf. A3-05), la transaction est annulée → le run tué ne laisse AUCUNE ligne `crawl_logs`, alors que c'est précisément le cas qu'on veut voir en monitoring.
- **Recommandation** : commiter la ligne `running` dans `__enter__` puis faire du `__exit__` un simple UPDATE+commit. Bénéfices immédiats : transactions courtes, statut `running` réel dans l'admin, et une ligne `running` orpheline devient le marqueur détectable d'un run tué.
- **Dépendances** : A3-05 (rend le cas SIGKILL plus fréquent)
- **Tags** : aucun

### [A3-08] Routing queues : `sync_artists`, `backfill_multi_artists` et les tâches reclassify (Deezer/Beatport) tournent sur la queue `celery` au lieu d'`enrich`
- **Type** : archi
- **Sévérité** : moyenne
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** : `server/workers/celery_app.py:90-100` — `task_routes` ne route vers `enrich` que `enrich_catalog[_beatport]`, `analyze_bpm_previews`, `check_followed_artists`, `link_artists_deezer`, `fetch_artist_artworks`. Or : `sync_artists` Phase B fait des recherches Deezer concurrentes (`tasks/artists.py:877-1084`), `backfill_multi_artists` enchaîne des `GET /track/{id}` Deezer sur tout son périmètre (`:1514`), `reclassify_genres_chunk` scrape Beatport + interroge Deezer pendant des heures (`tasks/genres.py:85-143`). Tous atterrissent sur la queue par défaut `celery` → `diggy_worker` (-Q celery,crawl -c 3).
- **Constat** : la règle CLAUDE.md (« tâches d'enrichissement (APIs externes rate-limitées) → queue `enrich` ») n'est appliquée qu'aux tâches beat. Les limites de débit tiennent quand même (fenêtres Redis partagées, AU4) — le problème est l'occupation des slots : un `reclassify_all_genres` admin dispatche 3 chunks qui saturent les 3 slots de `diggy_worker` pendant des heures, queue `crawl` comprise (les crawls nocturnes 02:00-04:00 attendent). Le 2026-07 avait noté le symptôme sur l'orchestrateur (A3-10, corrigé par chord) ; la saturation par les chunks eux-mêmes demeure.
- **Recommandation** : ajouter les routes `enrich` pour `sync_artists`, `backfill_multi_artists`, `reclassify_genres_chunk` (les 2 slots d'`enrich` bornent naturellement la concurrence et isolent la queue `crawl`) ; garder `link_set_artists` (DB-only) sur `celery`. Documenter dans CLAUDE.md si un choix contraire est acté.
- **Dépendances** : A3-04 (mêmes tâches)
- **Tags** : aucun

### [A3-09] `merge_catalog_entries` ne reporte pas `bpm_analyzed_at`/`bpm_analysis_attempts` (colonnes E2.c postérieures au module)
- **Type** : dette
- **Sévérité** : basse
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** : `server/workers/catalog_merge.py:364-376` unionne explicitement l'historique de recherche (« Keep the richer search history so the merged row is not re-searched ») pour `deezer_searched_at/attempts` et `beatport_searched_at/attempts`, mais aucun report des marqueurs d'analyse BPM (migration 0043) — grep `bpm_analyzed_at` dans le fichier : 0 occurrence.
- **Constat** : un canonical jamais analysé qui absorbe un loser déjà analysé « low_conf » redevient candidat (`bpm_analyzed_at IS NULL` + `bpm IS NULL` si aucun bpm n'est porté) → il sera re-téléchargé/re-analysé une nuit pour re-conclure la même chose. Bénin (gaspillage borné, aucune corruption — le cas bpm porté est couvert par le NULL-fill `:351-353`), mais incohérent avec le principe affiché du bloc.
- **Recommandation** : ajouter le même traitement que les paires deezer/beatport : `max` des attempts, `_latest` des `analyzed_at`.
- **Dépendances** : aucune
- **Tags** : aucun

### [A3-10] Code mort : `DEFAULT_ANALYSIS_BPM_BATCH_SIZE` (mort-né E2.c) et `workers/db.py get_session`
- **Type** : mort
- **Sévérité** : basse
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** :
  - `server/workers/tasks/bpm.py:36` — `DEFAULT_ANALYSIS_BPM_BATCH_SIZE = 2000` : grep repo entier (code + tests) → seule la définition. Le beat passe le littéral `"kwargs": {"batch_size": 2000}` (`celery_app.py:145`) et le défaut de la fonction est `batch_size: int = 0` (`bpm.py:63`). Candidat inventaire confirmé.
  - `server/workers/db.py:32-33` — `def get_session()` : grep code + tests → aucun appelant (tout le monde fait `Session(get_engine())` directement). Candidat inventaire confirmé.
- **Constat** : deux symboles morts ; le premier est trompeur (il suggère que le 2000 du beat en dérive alors qu'ils peuvent diverger silencieusement).
- **Recommandation** : supprimer `get_session` ; pour le batch BPM, soit supprimer la constante, soit — mieux — la référencer réellement depuis le beat (`"kwargs": {"batch_size": DEFAULT_ANALYSIS_BPM_BATCH_SIZE}`) pour une source unique.
- **Dépendances** : aucune
- **Tags** : aucun

### [A3-11] Commentaires périmés : la justification du défaut `TRACKID_BACKFILL_SETS_PER_DAY=1000` repose sur les chiffres réfutés le 2026-07-31 ; le commentaire `visibility_timeout` désigne le mauvais maximum
- **Type** : doc
- **Sévérité** : basse
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** :
  - `server/workers/tasks/sets.py:739-742` : « 1000 sets/night matches the downstream capacity: Beatport enrichment handles ~6000 tracks/night and a set yields ~5 new tracks, so ~750-1400 new tracks/day here stays within that budget ». Le sanity check prod du 2026-07-31 (CLAUDE.md) a MESURÉ ~7,6 tracks/set, un inflow réel ~12000/j à 1000 sets, une capacité Beatport ~9900/j (pas 6000) et un break-even ~800 — d'où l'override prod à 600.
  - `server/workers/celery_app.py:86-87` : « Must exceed the longest task time_limit (enrich_catalog Deezer: 9000s) » — le plus long est en réalité `reclassify_genres_chunk` à 16200s (`tasks/genres.py:22`). 30000 reste suffisant, seul le repère est faux.
- **Constat** : le choix de garder 1000 en défaut CODE avec override `.env` est acté (CLAUDE.md), mais le commentaire qui le justifie affirme l'inverse de la réalité mesurée — le prochain lecteur qui « nettoie » l'override prod en croyant le code serait reconduit droit vers l'accumulation de backlog constatée fin juillet.
- **Recommandation** : réécrire le commentaire de sets.py avec les chiffres mesurés (7,6 tracks/set, plafond ~9900/j, break-even ~800, prod à 600) et corriger le repère du commentaire visibility_timeout.
- **Dépendances** : aucune
- **Tags** : aucun

### [A3-12] `backfill_multi_artists` commite la Session sync partagée AU MILIEU du `asyncio.gather` (et gather non borné sur tout le périmètre)
- **Type** : dette
- **Sévérité** : basse
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** : `server/workers/tasks/artists.py:1511-1538` — `_process_one` fait `session.commit()` tous les 50 (`:1524-1526`) pendant que jusqu'à N coroutines sœurs (gather intégral ligne `:1538`, non chunké) tiennent encore des objets ORM de la même session ; chaque commit les expire, et tout accès post-await (`entry.id` ligne `:1522`) déclenche un refresh lazy.
- **Constat** : pas de corruption démontrée (Session sync : aucune opération DB ne yield), mais c'est le pattern que le repo a précisément banni ailleurs — `link_artists_deezer` collecte pendant le gather et commite APRÈS (`:646-655`, avec le commentaire expliquant le hazard), et le pitfall CLAUDE.md documente la corruption de session partagée en gather. Un objet expiré dont la ligne a été supprimée par le drain Beatport concurrent lèverait `ObjectDeletedError` en plein gather — c'est le scénario exact qui a tué `enrich_set_tracks` (commit c0c7392). La tâche est admin-only et sans lock (cf. A3-04), ce qui augmente la fenêtre.
- **Recommandation** : chunker en lots de `ARTIST_BACKLOG_BATCH` avec commit entre les gathers (copier la boucle de `fetch_artist_artworks` `:1311-1320`), retirer le commit du corps de la coroutine.
- **Dépendances** : A3-04 (même tâche, à traiter dans la même passe)
- **Tags** : aucun

---

## Hypothèses réfutées

- **« Le tableau beat de CLAUDE.md diverge peut-être du code »** — non : les 12 entrées de `celery_app.py:103-179` (tâches, horaires Europe/Paris, kwargs batch, fenêtres) correspondent exactement au tableau CLAUDE.md, routing compris (`snapshot_backlogs` sans route → queue `celery`, `check_followed_artists`/`analyze_bpm_previews` → `enrich`).
- **« `result.get()` résiduel dans une task »** — aucun : grep `\.get(` sur les AsyncResult → rien ; l'unique orchestrateur (`reclassify_all_genres`) est en chord + errback depuis le fix A3-10 2026-07.
- **« Essentia pourrait bloquer la boucle async »** — réfuté : l'analyse passe par `run_in_executor` sur un `ThreadPoolExecutor(max_workers=2)` borné (`bpm.py:42,134` ; `bpm_analysis.py:136-140`), instance fraîche par appel, import lazy. Conforme à l'annonce E2.c.
- **« Le lock `analyze_bpm` serait approximatif »** — réfuté : `SET NX EX` atomique, TTL 3900 ≥ time_limit 3300, release conditionnelle, skip avec holder loggé (`bpm.py:74-88`) — clone conforme du pattern de référence.
- **« `snapshot_backlogs` sans lock = danger »** — non : lecture seule + INSERT d'une ligne horodatée par run, aucun invariant à protéger ; un doublon horaire serait bénin. Pas de finding.
- **« La cadence slack manquerait sur de nouveaux gates »** — non : les deux seuls gates quotidiens (`_crawl_decision` radar, `_recrawl_decision` sets) appliquent `CADENCE_SLACK_DAYS = 0.25` ; les drains horaires (Beatport, BPM) sont des locks single-instance, pas des gates de cadence.
- **« String-matching d'exception encore présent (suppression de playlist) »** — réfuté : seul `PlaylistGoneError` typée par source déclenche le cleanup destructif (`radar.py:316` ; `source_clients.py:41-47`, `:69-76`, `:309-324`).
- **« `worker/` (racine) et `server/deezer/` = code mort »** — hors périmètre par consigne (outillage LOCAL documenté A7-07, `worker/bpm_backfill/` accélérateur manuel optionnel depuis E2.c). Non signalés.
- **« batch 2000 BPM tiendrait dans le créneau »** — probablement pas à froid (2000 × résolution+download+analyse ≈ > 3000s à 2 threads), mais c'est ABSORBÉ par design : soft-limit catché, partiel commité par lots de 50, lock libéré, run suivant à h+1 — comportement vérifié dans le code, pas de finding.
- **Résidus acceptés non re-signalés** (aucune réévaluation nécessaire) : autorité basse `bpm_source='analysis'` alimentant similarity (E2 acté), `uq_artists_deezer_id` hors migrations (MANUAL), absence d'index unique plateforme (X1/X3), rate limiter fail-open (AU4), fichier tokens TIDAL non purgé de l'historique (Q4 option B, token révoqué — le fallback code est désormais surchargeable via `TIDAL_TOKEN_FILE`), recréation ciblée `--no-deps worker` (pitfall documenté).
