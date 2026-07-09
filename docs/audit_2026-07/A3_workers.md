# Audit 2026-07 — A3 : Workers & intégrations externes

> Date : 2026-07-09
> Agent : A3
> Périmètre : `server/workers/` (celery_app.py, tasks/*, source_clients.py, async_http.py, rate_limiter.py, crawl_logger.py, deezer_enrich.py, enrichment.py, db.py), `server/api/beatport/` (client.py, enrich.py), `server/api/trackid/` (client.py, importer.py).
> Note périmètre : le brief mentionnait `server/api/deezer_enrich.py` — ce fichier N'EXISTE PAS. Le module réel est `server/workers/deezer_enrich.py` (voir A3-15, divergence CLAUDE.md).
> Méthode : lecture intégrale des 17 fichiers du périmètre + docker-compose.yml, greps croisés (imports, scope, triggers celery), 3 requêtes SQL READ-ONLY sur la prod via SSH pour quantifier. Aucune modification hors ce rapport.

## Ce qui va bien (réfutations et points solides)

- **`workers/enrichment.py` n'est PAS du dead code**, contrairement à l'hypothèse de l'inventaire (§4, 272 stmts à 0%). Il est importé par 4 modules de tasks actifs : `tasks/catalog.py:55,175`, `tasks/radar.py:248`, `tasks/sets.py:121,248`, `tasks/genres.py:41`. Le 0% de coverage est un trou de tests, pas de l'obsolescence. Idem `source_clients.py` (importé par `tasks/radar.py:33,134`) et `db.py` (importé partout). `BeatportClient` (classe sync de `api/beatport/client.py:204`) est vivant : utilisé par `api/services/artist_service.py:640-656`.
- **Routage des queues cohérent** : `task_routes` (celery_app.py:90-94) route `crawl_single_playlist`→`crawl` et les 2 enrich→`enrich` ; docker-compose.yml:106 (`-Q celery,crawl -c 3`) et :134 (`-Q enrich -c 2`) consomment bien toutes les queues. Le beat schedule (celery_app.py:97-126) est conforme au tableau de CLAUDE.md (7 tasks, mêmes horaires).
- **`visibility_timeout` (30000s, celery_app.py:88, commit a311e5e) > plus long `time_limit` (28800s)** : le risque de re-livraison broker de tasks encore en cours est couvert.
- **Lock Beatport correct** (tasks/catalog.py:136-150) : `SET NX EX` avec TTL 30000s couvrant le time_limit 28800s, release conditionnel à la propriété (`if r.get(lock_key) == self.request.id`).
- **HTTP async solide** : `HttpPool` (async_http.py) pose timeouts explicites (20s/10s connect), retry backoff exponentiel sur 429 et erreurs réseau (lignes 79-114), limites de connexions.
- **TIDAL : gestion 401/refresh exemplaire** (source_clients.py:168-264) : cascade Redis → env → fichier, refresh automatique via `token_refresh`, persistance des nouveaux tokens dans Redis (`tidal:tokens`).
- **Observabilité de base présente** : DLQ Redis sur échec final (celery_app.py:131-174), logging structuré avec task_id (lignes 25-55), hook Sentry, `CrawlLogger` qui persiste succès/échec/durée/stats en DB sur la majorité des tasks (avec `status="error"` + `error_message`, crawl_logger.py:66-75).
- **`import_rekordbox_xml` idempotent** : upsert `ON CONFLICT (user_id, catalog_id)` (tasks/import_rb.py:136-159), `max_retries=0` assumé, progress Redis avec TTL.
- **Dossier legacy `worker/` (singulier, racine)** : aucun code actif ne l'importe. Seuls `tests/worker/test_check_sync.py:32`, `tests/worker/test_relocate_tracks.py:4` et un notebook gelé (`docs/completed/deezer_vs_rekordbox.ipynb`) y font référence. Signalé pour A7.

---

## Findings

### [A3-01] La promotion `private` → `shared` n'est jamais exécutée par le pipeline d'enrichissement Celery
- **ID** : A3-01
- **Type** : bug
- **Sévérité** : haute
- **Effort estimé** : S (< 1h)
- **Confiance** : haute
- **Preuve** :
  - La promotion n'existe QUE dans le chemin sync legacy `server/workers/deezer_enrich.py:334-337` :
    ```python
    # Promote private → shared when Deezer confirms the track exists
    if changed and getattr(entry, "scope", None) == "private" and entry.deezer_id:
        entry.scope = "shared"
        entry.owner_id = None
    ```
  - Le pipeline async utilisé en prod, `server/workers/enrichment.py:110-166` (`_enrich_entry_async`), applique deezer_id/isrc/duration/preview/artwork mais **ne contient aucun bloc de promotion**.
  - `enrich_entry` (le porteur de la promotion) n'est appelé par AUCUNE task Celery — uniquement par 2 scripts one-shot : `server/api/scripts/enrich_catalog_deezer.py:28,101` et `server/api/scripts/import_trackid_sets.py:150,203` (grep exhaustif).
  - Quantification prod (SQL read-only, 2026-07-09) : **235 entrées `scope='private'` ont un `deezer_id`** (donc enrichies avec succès par le pipeline) mais n'ont jamais été promues ; 24 autres privées ont été cherchées sans hit.
- **Constat** : contrairement à l'hypothèse du brief (« skip des entrées private »), les queries d'enrichissement ne filtrent PAS sur scope (`tasks/catalog.py:70-81` : seulement `deezer_id IS NULL AND deezer_searched_at IS NULL`) — les tracks Rekordbox privées SONT enrichies. C'est la promotion qui a été perdue lors du passage au pipeline async : le commentaire de `generate_schema_doc.py:95` (« private = Rekordbox-only entries before enrichment ») décrit un invariant que le code ne réalise plus. Impact atténué par le fait qu'aucune query API ne filtre actuellement sur `catalog.scope` (seul usage : `routers/tracks.py:116` et `tasks/import_rb.py:119`), mais l'invariant sémantique du modèle est violé et tout futur usage de `scope` (C3, partage multi-user) héritera de 235+ lignes incohérentes.
- **Recommandation** : porter le bloc de promotion dans `_enrich_entry_async` (enrichment.py, fin de fonction, mêmes 4 lignes) + une migration/script one-shot `UPDATE catalog SET scope='shared', owner_id=NULL WHERE scope='private' AND deezer_id IS NOT NULL AND deezer_id != 'NOT_FOUND'` pour rattraper les 235 lignes. Ajouter un test sur la promotion dans le chemin async.
- **Dépendances** : aucune
- **Tags optionnels** : lié-chantier:C3, QUICK-WIN-CANDIDAT

### [A3-02] `radar_trends` n'est jamais purgée : scores et rangs obsolètes coexistent avec les frais
- **ID** : A3-02
- **Type** : bug
- **Sévérité** : moyenne
- **Effort estimé** : S (< 1h)
- **Confiance** : haute
- **Preuve** :
  - `tasks/trends.py:292-308` : `compute_trends` fait uniquement un UPSERT (`on_conflict_do_update` sur catalog_id). Aucun DELETE des lignes dont le catalog_id n'apparaît plus dans la fenêtre de 30 jours.
  - `api/routers/radar.py` (endpoint /trends) : aucune référence à `computed_at` — les lignes sont triées par `rank_in_family` / `rank_global` sans filtre de fraîcheur (lignes 43-62).
  - Prod (2026-07-09) : `SELECT computed_at::date, count(*) FROM radar_trends GROUP BY 1` → **8309 lignes du 09-07, 3613 du 08-07, 7 du 06-07**. 3620 lignes périmées (28%) sont servies au même titre que les fraîches.
- **Constat** : une track sortie de la fenêtre de tendance conserve indéfiniment son dernier score et son dernier rang. Les `rank_global`/`rank_in_family` d'un run précédent entrent en collision avec ceux du run courant (deux lignes peuvent porter le même rang), ce qui fausse le tri du Hub « Ça sort en ce moment » et les FamilyChips.
- **Recommandation** : dans `compute_trends`, après l'upsert et dans la même transaction, `DELETE FROM radar_trends WHERE computed_at < :now` (les lignes non touchées par le run courant) — ou filtrer côté router sur `computed_at = MAX(computed_at)`. La première option est plus simple et nettoie la table.
- **Dépendances** : aucune
- **Tags optionnels** : QUICK-WIN-CANDIDAT

### [A3-03] `reclassify_genres_chunk` efface les genres AVANT la recherche : perte de données sur erreur réseau
- **ID** : A3-03
- **Type** : bug
- **Sévérité** : moyenne
- **Effort estimé** : S (< 1h)
- **Confiance** : haute
- **Preuve** : `server/workers/tasks/genres.py:77-79` puis :142-154 :
  ```python
  for i, entry in enumerate(entries):
      entry.genres = []
      found = False
      # 1) Try Beatport first ...
      except Exception as e:  # ligne 102 — erreur réseau comptée, mais genres déjà vidés
      ...
      if (i + 1) % 50 == 0:
          session.commit()   # commit du vidage même si found=False
  ```
- **Constat** : si Beatport ET Deezer échouent pour une entrée (timeout, 5xx, Cloudflare), ses genres existants sont vidés puis commités (`stats["cleared"]`). Le run n'est pas idempotent en présence d'erreurs : re-lancer la task après un incident réseau détruit des classifications valides au lieu de les conserver. La task est déclenchée par l'admin (`routers/admin.py:599,620`).
- **Recommandation** : ne vider `entry.genres` qu'au moment où une nouvelle valeur est trouvée (affectation directe), ou restaurer la valeur initiale dans les branches d'erreur. Distinguer « aucun genre trouvé (200) » de « erreur source » : ne clearer que dans le premier cas.
- **Dépendances** : aucune
- **Tags optionnels** : QUICK-WIN-CANDIDAT

### [A3-04] Un échec HTTP Deezer est indistinguable d'un « not found » : `deezer_searched_at` exclut définitivement l'entrée
- **ID** : A3-04
- **Type** : bug
- **Sévérité** : moyenne
- **Effort estimé** : M (1h-1j)
- **Confiance** : haute
- **Preuve** :
  - `server/workers/async_http.py:118-125` : `deezer_get` retourne `{}` sur tout status non-200 (sauf 429 retenté), sans log ni distinction :
    ```python
    if resp.status_code != 200:
        return {}
    ```
  - `server/workers/enrichment.py:204-208` : hit absent → `entry.deezer_searched_at = now` sans distinction de cause.
  - `server/workers/tasks/catalog.py:73-76` : la query d'enrichissement filtre `deezer_searched_at.is_(None)` → une entrée marquée n'est plus jamais retentée.
- **Constat** : pendant une indisponibilité Deezer (5xx, 403 sur parenthèses — cas documenté dans `deezer_enrich.py:120`), toutes les entrées du batch en cours sont marquées « cherchées » et sortent définitivement du pipeline nightly, alors qu'elles n'ont jamais été réellement cherchées. En prod, 460 entrées sont en état « searched, not found » (436 shared + 24 private) sans moyen de savoir lesquelles sont des victimes d'erreurs.
- **Recommandation** : faire remonter le status code (ou lever) depuis `deezer_get` ; dans `_enrich_one`, ne poser `deezer_searched_at` que sur une réponse 200 avec `data` vide. Optionnel : re-essayer périodiquement les « not found » anciens (ex. > 90 jours).
- **Dépendances** : aucune
- **Tags optionnels** : aucun

### [A3-05] Le rate limiting est en mémoire par process : les limites par source sont multipliées par la concurrence réelle
- **ID** : A3-05
- **Type** : archi
- **Sévérité** : moyenne
- **Effort estimé** : M (1h-1j)
- **Confiance** : haute
- **Preuve** :
  - `server/workers/rate_limiter.py:20-26` : `_SOURCE_CONFIG` définit p.ex. deezer (5 concurrent, 10 rps), beatport (2, 0.66 rps) — état purement en mémoire (semaphores + token bucket, aucun backend partagé).
  - Chaque task instancie SON limiteur : `tasks/catalog.py:58`, `tasks/radar.py:254`, `tasks/sets.py:127,251`, `tasks/artists.py:208,469,696` (`limiter = RateLimiter()`).
  - `docker-compose.yml:106,134` : `diggy_worker` en `-c 3` (pool prefork = 3 process) + `diggy_worker_enrich` en `-c 2`.
- **Constat** : le fan-out `crawl_radar` (radar.py:77, 56 watched_entities en prod) peut faire tourner jusqu'à 3 `crawl_single_playlist` en parallèle, chacun avec son propre bucket Deezer à 10 rps → jusqu'à 30 rps vers Deezer, 3× la limite configurée (elle-même calée sur les 50 req/5s officiels). Idem Beatport si un crawl et l'enrich nightly se chevauchent (worker_enrich est un process séparé). Le commentaire du module (« Replaces all manual time.sleep() ») suggère une protection globale qu'il n'assure pas.
- **Recommandation** : soit borner structurellement (le worker crawl à `-c 1` pour la queue crawl, déjà proche du comportement actuel), soit implémenter un token bucket partagé Redis (`INCR`+`EXPIRE` par fenêtre, ou script Lua) pour deezer/beatport uniquement. Ne pas viser la perfection : Deezer tolère des dépassements ponctuels (429 déjà retenté).
- **Dépendances** : aucune
- **Tags optionnels** : aucun

### [A3-06] Clients Deezer sync sans vérification de statut ni d'erreur API : tracklist partielle → `removed_at` posés à tort
- **ID** : A3-06
- **Type** : bug
- **Sévérité** : moyenne
- **Effort estimé** : S (< 1h)
- **Confiance** : moyenne
- **Preuve** :
  - `server/workers/source_clients.py:46-82` : `fetch_deezer_meta` et `fetch_deezer_tracks` font `requests.get(...).json()` sans `raise_for_status()` ni inspection de la clé `error` que Deezer renvoie en HTTP 200. La pagination s'arrête silencieusement (`url = resp.get("next")` → None) si une page intermédiaire renvoie une erreur → liste partielle retournée comme si elle était complète. Aucun retry, aucun rate limiting (le `_limiter` module n'est utilisé que pour TIDAL, ligne 286).
  - `server/workers/db.py:212-220` : `bulk_insert_radar_tracks` marque `removed_at = now` toute track absente de la liste crawlée. (La liste **vide** est protégée par l'early return ligne 159-160, mais pas la liste partielle.)
- **Constat** : une erreur Deezer en milieu de pagination (quota, 5xx) fait passer les tracks des pages suivantes pour « retirées de la playlist », polluant le lifecycle C0.1 et la vélocité des trends. Le mécanisme est auto-réparant (removed_at est effacé à la réapparition, db.py:223-231) mais chaque incident injecte de fausses données de retrait/réapparition dans le signal.
- **Recommandation** : dans les 3 fonctions Deezer de source_clients, vérifier `resp.status_code == 200` et l'absence de clé `"error"` dans le JSON ; lever une exception sinon (la task a déjà autoretry + le CrawlLogger enregistrera l'échec). Optionnel : passer ces appels par le rate limiter deezer.
- **Dépendances** : aucune
- **Tags optionnels** : QUICK-WIN-CANDIDAT

### [A3-07] Suppression destructive de playlist déclenchée par un matching de chaîne `"404"` dans le message d'exception
- **ID** : A3-07
- **Type** : bug
- **Sévérité** : moyenne
- **Effort estimé** : S (< 1h)
- **Confiance** : moyenne
- **Preuve** : `server/workers/tasks/radar.py:156-184` :
  ```python
  except Exception as e:
      err_str = str(e).lower()
      if "not found" in err_str or "404" in err_str:
          ...
          session.execute(sa_delete(RadarTrack).where(...))
          session.execute(sa_delete(UserFollow).where(...))
          ...
          session.delete(entity)
  ```
- **Constat** : la détection « la playlist n'existe plus sur la source » repose sur la présence de `"404"` ou `"not found"` dans `str(e)` de n'importe quelle exception de `fetch_meta`. Une erreur réseau TIDAL/Spotify dont le message contient « 404 » (URL d'image, message HTML d'un proxy, id contenant 404…) supprime définitivement la watched_entity, ses radar_tracks et les follows utilisateurs. À noter : pour Deezer ce chemin ne se déclenche jamais (les playlists supprimées renvoient HTTP 200 + JSON `error`, cf. A3-06), donc les playlists Deezer mortes ne sont jamais nettoyées — l'heuristique est à la fois trop large (TIDAL/Spotify) et inopérante (Deezer).
- **Recommandation** : typer la détection par source : pour Deezer, tester explicitement le JSON d'erreur (code 800 « no data ») dans `fetch_deezer_meta` et lever une exception dédiée `PlaylistGoneError` ; pour TIDAL/Spotify, ne matcher que les exceptions HTTP portant un vrai status 404. Ne supprimer que sur `PlaylistGoneError`.
- **Dépendances** : A3-06 (même zone de code)
- **Tags optionnels** : aucun

### [A3-08] Six `except Exception: pass` sans aucun log dans les chemins d'import/enrichissement
- **ID** : A3-08
- **Type** : dette
- **Sévérité** : moyenne
- **Effort estimé** : S (< 1h)
- **Confiance** : haute
- **Preuve** :
  - `server/workers/tasks/sets.py:424-425, 541-542, 697-698` : `materialize_parent` (dedup C6) — `except Exception: pass  # ne pas bloquer le crawl` ×3.
  - `server/api/trackid/importer.py:177-178` : tout le post-import dedup (`backfill_normalized_titles` + `match_set` + `apply_match_results`) — `except Exception: pass  # matching failure must never abort import`.
  - `server/api/trackid/importer.py:124-125` : upload artwork — `except Exception: pass`.
  - `server/workers/enrichment.py:219-220` : `link_catalog_artist_from_hit` — `except Exception: pass  # non-critical, sync_artists will catch up`.
- **Constat** : le choix de ne pas bloquer le crawl est défendable, mais l'absence totale de log rend invisible une régression du service de dedup (C6) ou du linking artistes : si `match_set`/`materialize_parent` se met à lever systématiquement (ex. après le changement de signature C6.1 qui a déjà cassé des callers, cf. MEMORY), les sets s'importent sans jamais être dédupliqués et personne ne le voit — ni logs, ni crawl_logs, ni Sentry.
- **Recommandation** : remplacer chaque `pass` par `logger.warning("...: %s", exc, exc_info=True)` (voire un compteur dans les stats du CrawlLogger pour `materialize_parent` et le match dedup). Aucun changement de comportement fonctionnel.
- **Dépendances** : aucune
- **Tags optionnels** : QUICK-WIN-CANDIDAT, lié-chantier:C6

### [A3-09] Tasks sans trace `crawl_logs` : `crawl_followed_sets` et `link_set_artists`
- **ID** : A3-09
- **Type** : dette
- **Sévérité** : basse
- **Effort estimé** : S (< 1h)
- **Confiance** : haute
- **Preuve** : `server/workers/tasks/sets.py:308-443` (`crawl_followed_sets`, schedulée en beat à 04:00) et `server/workers/tasks/artists.py:572-656` (`link_set_artists`, déclenchée par admin.py:245) : aucun import ni usage de `CrawlLogger`, contrairement aux 9 autres tasks instrumentées.
- **Constat** : ces deux tasks n'apparaissent pas dans `/api/admin/crawl-logs` ; un échec ne laisse que les logs conteneur (rotation 50 Mo ×3). Pour une task beat quotidienne (crawl_followed_sets), la panne silencieuse peut durer des semaines.
- **Recommandation** : envelopper le corps des deux tasks dans `CrawlLogger` comme les autres (task_type `crawl_followed_sets` / `link_set_artists`).
- **Dépendances** : aucune
- **Tags optionnels** : QUICK-WIN-CANDIDAT

### [A3-10] `reclassify_all_genres` bloque un slot worker jusqu'à 7h avec `result.get()` dans une task
- **ID** : A3-10
- **Type** : archi
- **Sévérité** : basse
- **Effort estimé** : M (1h-1j)
- **Confiance** : haute
- **Preuve** : `server/workers/tasks/genres.py:219-223` :
  ```python
  job = group(reclassify_genres_chunk.s(chunk, i) for i, chunk in enumerate(chunks))
  result = job.apply_async()
  result.get(disable_sync_subtasks=False, timeout=25200)
  ```
- **Constat** : attendre des sous-tâches de façon synchrone dans une task est l'anti-pattern documenté par Celery (d'où le garde-fou `disable_sync_subtasks` qu'il faut désactiver explicitement). L'orchestrateur occupe 1 des 3 slots de `diggy_worker` pendant jusqu'à 25200s, et les 3 chunks (queue `celery` par défaut) se partagent les 2 slots restants — pendant toute la reclassification, la queue `crawl` du même worker est de fait saturée. Pas de deadlock avec les valeurs par défaut (num_chunks=3), mais `num_chunks >= 3` + un autre run concurrent en créerait un.
- **Recommandation** : remplacer par `chord(group(...), finalize_reclassify.s())` où le callback agrège les stats et ferme le CrawlLogger — libère le slot orchestrateur et supprime le timeout arbitraire.
- **Dépendances** : aucune
- **Tags optionnels** : aucun

### [A3-11] `resolve_set_tracks` sans lock, déclenchée en cascade par 3 tasks beat + l'API
- **ID** : A3-11
- **Type** : dette
- **Sévérité** : basse
- **Effort estimé** : S (< 1h)
- **Confiance** : haute
- **Preuve** : dispatchs multiples : `tasks/sets.py:437` (crawl_followed_sets, 04:00), :573 (crawl_trackid_latest, 03:30), :726 (backfill_trackid_sets, 02:00), `api/routers/sets.py:225` (import utilisateur). La task (sets.py:46-198) traite TOUT le backlog global (`SetTrack.catalog_id IS NULL`) et n'a aucun lock, contrairement à `enrich_catalog_beatport`.
- **Constat** : les nuits chargées (backfill 500 sets), deux `resolve_set_tracks` peuvent se chevaucher (time_limit 7500s ; la 2e démarre à 03:30+) et traiter le même backlog : double trafic Deezer/Beatport sur les mêmes entrées (cumulé avec A3-05). L'intégrité DB est protégée (`bulk_get_or_create_catalog` en `ON CONFLICT DO NOTHING`, db.py:120-127), c'est un gaspillage + risque de rate limit, pas une corruption.
- **Recommandation** : appliquer le même pattern de lock Redis que `enrich_catalog_beatport` (tasks/catalog.py:136-150), TTL calé sur le time_limit (7500s) ; retour `{"skipped": "already_running"}`.
- **Dépendances** : A3-05
- **Tags optionnels** : QUICK-WIN-CANDIDAT

### [A3-12] `fetch_artist_artworks` re-cherche les mêmes artistes sans `deezer_id` à chaque run
- **ID** : A3-12
- **Type** : perf
- **Sévérité** : basse
- **Effort estimé** : S (< 1h)
- **Confiance** : haute
- **Preuve** : `server/workers/tasks/artists.py:477-510` : Pass 1 requête `Artist.deezer_id.is_(None)` puis `_link_one` fait une recherche Deezer ; en cas de non-match, seul `skipped += 1` — l'artiste reste `deezer_id IS NULL` et sera re-cherché au run suivant. Le sentinel `NOT_FOUND` existe (46 artistes en prod) mais n'est posé que manuellement via l'admin (`admin.py:161` PATCH no-deezer). Prod : 226 artistes sans deezer_id → 226 recherches Deezer répétées à chaque déclenchement.
- **Constat** : volume actuellement modeste (226), mais croissant avec le catalogue (14078 artistes) et cumulé au fan-out `asyncio.gather` non borné sur la même liste (ligne 510 — le semaphore deezer à 5 limite la concurrence effective, pas le volume).
- **Recommandation** : ajouter un timestamp `deezer_searched_at` sur Artist (pattern identique au catalog) et filtrer les re-recherches (ex. re-essai après 30 jours). Ne PAS poser `NOT_FOUND` automatiquement — le sentinel signifie « confirmé absent » (décision humaine, CLAUDE.md).
- **Dépendances** : aucune
- **Tags optionnels** : aucun

### [A3-13] Lock `crawl_single_playlist` : TTL 900s < time_limit 4500s
- **ID** : A3-13
- **Type** : bug
- **Sévérité** : basse
- **Effort estimé** : S (< 1h)
- **Confiance** : haute
- **Preuve** : `server/workers/tasks/radar.py:107` : `lock = r.lock(f"crawl:playlist:{playlist_id}", timeout=900)` vs décorateur lignes 98-99 : `soft_time_limit=3600, time_limit=4500`. Le release gère proprement l'expiration (`LockNotOwnedError`, lignes 115-118).
- **Constat** : au-delà de 15 minutes de crawl (grosse playlist + enrichissement Deezer+Beatport inline, plausible vu le soft limit à 1h), le lock expire alors que la task tourne encore : un déclenchement manuel (`watchlist.py:72` POST /{id}/crawl) ou un retry peut alors s'exécuter en parallèle sur la même playlist — double enrichissement et double diff `removed_at`. Comparer avec le lock Beatport dont le TTL couvre exactement le time_limit (catalog.py:13-15).
- **Recommandation** : aligner `timeout=4600` (> time_limit) sur le pattern documenté dans catalog.py.
- **Dépendances** : aucune
- **Tags optionnels** : QUICK-WIN-CANDIDAT

### [A3-14] Lock d'import Rekordbox : TTL 600s trop court, check-then-set non atomique, delete sans vérification de propriété
- **ID** : A3-14
- **Type** : dette
- **Sévérité** : basse
- **Effort estimé** : S (< 1h)
- **Confiance** : haute
- **Preuve** : `server/api/routers/import_rb.py:46-64` : `if await redis.exists(lock_key)` puis plus loin `redis.set(lock_key, task_id, ex=600)` (non atomique, deux requêtes simultanées passent toutes les deux) ; `server/workers/tasks/import_rb.py:205` : `r.delete(f"import:lock:{user_id}")` en `finally` sans vérifier que le lock appartient encore à cette task. La task n'a pas de time_limit propre (hérite du global 1800/3600s, celery_app.py:62-63) > TTL 600s.
- **Constat** : un import > 10 min laisse expirer le lock ; l'utilisateur peut en lancer un second, et le `finally` du premier supprimera le lock du second (delete inconditionnel). L'upsert rend le résultat DB correct, mais deux imports concurrents du même user doublent le travail et le progress Redis devient incohérent (deux task_id écrivent).
- **Recommandation** : `SET NX EX` avec TTL >= time_limit de la task, et delete conditionnel à la valeur (`if r.get(lock_key) == task_id`), comme dans catalog.py:149-150.
- **Dépendances** : aucune
- **Tags optionnels** : aucun

### [A3-15] CLAUDE.md situe `deezer_enrich.py` dans `server/api/` alors qu'il est dans `server/workers/`
- **ID** : A3-15
- **Type** : dead-doc
- **Sévérité** : basse
- **Effort estimé** : S (< 1h)
- **Confiance** : haute
- **Preuve** : CLAUDE.md, section Architecture : `│   ├── deezer_enrich.py     # Deezer search + enrichment` listé sous `server/api/`. Réalité : `server/api/deezer_enrich.py` n'existe pas (vérifié — erreur « File does not exist ») ; le module est `server/workers/deezer_enrich.py` (grep : tous les imports sont `from workers.deezer_enrich import ...`).
- **Constat** : divergence doc/code signalée conformément à la consigne de CLAUDE.md (« SAY SO explicitly »). Le brief d'audit A3 a lui-même été induit en erreur par cette ligne. Accessoirement, le docstring de `workers/deezer_enrich.py:9` référence « enrich_catalog Celery task (weekly backfill) » alors que le beat est quotidien (05:00).
- **Recommandation** : déplacer la ligne `deezer_enrich.py` sous `workers/` dans l'arbre Architecture de CLAUDE.md et corriger « weekly » → « daily » dans le docstring.
- **Dépendances** : aucune
- **Tags optionnels** : QUICK-WIN-CANDIDAT

### [A3-16] Le fallback TIDAL lit un fichier de tokens OAuth réels commité dans le repo
- **ID** : A3-16
- **Type** : securite
- **Sévérité** : haute
- **Effort estimé** : S (< 1h)
- **Confiance** : haute
- **Preuve** : `server/workers/source_clients.py:246-259` :
  ```python
  token_file = Path(__file__).parent.parent / "scripts" / ".tidal_tokens.json"
  if token_file.exists():
      tokens = json.loads(token_file.read_text())
      session.load_oauth_session(... tokens["access_token"] ...)
  ```
  Le fichier `server/scripts/.tidal_tokens.json` est versionné avec des tokens réels (inventaire §11 : « TOKENS OAUTH TIDAL RÉELS COMMITÉS, access_token JWT visible »).
- **Constat** : au-delà du fichier commité (périmètre A6/A7), le code du périmètre A3 institutionnalise ce fichier comme fallback de production (« dev fallback », mais rien n'empêche son usage en prod puisque le chemin est relatif au module). Le refresh_token commité permet de régénérer des access tokens indéfiniment tant qu'il n'est pas révoqué.
- **Recommandation** : côté A3 : restreindre le fallback fichier à un chemin hors repo (env `TIDAL_TOKEN_FILE`) ou le supprimer (Redis + env suffisent, la cascade 1-2 couvre prod ET dev). La purge git + rotation des tokens relève de A6/A7.
- **Dépendances** : aucune (signalement croisé A6/A7)
- **Tags optionnels** : hors-domaine:securite-repo

---

## Non couvert

- `server/workers/tasks/artists.py` phases internes de `sync_artists` (heuristiques comma/ampersand) : lues mais non auditées en profondeur côté qualité de matching (relève de C2/similarité, pas de la résilience workers).
- Comportement runtime réel des retries Celery (autoretry + acks_late + visibility_timeout) non testé dynamiquement — analyse statique uniquement.
- `server/api/trackid/parsing.py` : lecture rapide, rien de notable (fonctions pures, testées).
- Vérification exhaustive des 285 candidats vulture min-confidence 60 : hors budget, seuls les modules du périmètre ont été tranchés (enrichment.py, source_clients.py, db.py : vivants).
