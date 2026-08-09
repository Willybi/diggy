# Audit A2 — Base de données (2026-08)

> **Date** : 2026-08-09 · **HEAD audité** : `9b305d6` (2026-08-08)
> **Périmètre** : `server/api/models/` (12 modules, 28 tables mappées), migrations Alembic 0031→0043 (13 nouvelles), `docs/database-schema.md`, chemins de requêtes chauds (Explorer, /radar/feed, /api/sets/, backlog E1/E2.c), DB prod (SELECT lecture seule via `ssh diggy-vps`).
> **Méthode** : croisement code ↔ modèles ↔ migrations ↔ DB live. Chaque colonne suspecte vérifiée par `COUNT(*) FILTER` en prod ; chaque qualification perf appuyée par un `EXPLAIN` prod (jamais `ANALYZE`). Audit précédent : `docs/audit_2026-07/A2_database.md`.
> **Fait marquant du delta** : la volumétrie a changé d'ordre de grandeur — `catalog` 15 836 → **255 975 lignes (186 MB, dont 109 MB d'index)**, `set_tracks` → **389 006 lignes (102 MB)**, `sets` 608 → **28 869**, `radar_trends` 9 172 → **38 137**. L'inflow TrackID (~8 k tracks/j en moyenne sur le mois) rend structurantes des requêtes qui étaient anecdotiques en juillet.

## Ce qui va bien

- **`docs/database-schema.md` est à jour** (résout 2026-07/A2-03) : régénéré dans le commit E2.c `cce583a` (2026-08-08), dernier commit touchant les modèles (`git diff cce583a..HEAD -- server/api/models/ server/api/alembic/` = vide). Il reflète 0041 (`metric_snapshots`, l.616), 0042 (`rating` : **0 occurrence** dans le doc, `user_tracks.created_at` avec `server_default=now()`, l.160) et 0043 (`bpm_analyzed_at`/`bpm_analysis_attempts`, l.106-107).
- **`alembic_version` prod = `0043`**, alignée avec les 43 fichiers du repo (vérifié `SELECT version_num FROM alembic_version`).
- **Les 13 downgrades (0031→0043) sont symétriques**, à deux irréversibilités près, toutes deux **documentées dans le fichier** : 0031 ne recrée pas `watched_playlists` (données périmées, drop assumé, commentaire l.29) et 0040 est un no-op explicite (trim de whitespace non réversible, l.24-26). 0042 recrée bien colonne **et** contrainte `ck_rating_range` au downgrade ; 0033/0038 droppent les colonnes qu'ils créent (les UPDATE de backfill n'ont rien à défaire).
- **2026-07/A2-04 résolu — les index vivent désormais dans les modèles** : `CatalogEntry.__table_args__` (12 index dont les 4 partiels, `models/catalog.py:74-108`), `Artist.__table_args__` (`uq_artists_deezer_id` avec `sqlite_where` + partiel `ix_artists_deezer_searched_at`, `models/artist.py:47-63`), `SetFlag.__table_args__` (`uq_set_flag_pair` + `uq_set_flag_group_key` partiel, `models/sets.py:188-197`), `RadarTrack.__table_args__` (`models/radar.py:106-113`). L'inventaire prod `pg_indexes` (32 index sur les 7 tables sondées) colle aux déclarations — catalog : 15 index prod = 12 déclarés + pkey + 2 uniques, zéro écart.
- **Fixes AU3 en place en prod** : `ix_user_tracks_catalog_id`, `ix_user_follows_entity_id` (0031), `user_tracks.created_at` défaut DB (0 NULL sur les nouvelles lignes).
- **Invariants dedup respectés** : `catalog_normalized_key_key` et `catalog_isrc_key` uniques en prod ; `ix_catalog_deezer_id`/`ix_catalog_beatport_id` **non uniques** (absence délibérée X1/X3 préservée) ; `uq_artists_deezer_id` déclarée modèle + migration 0034 (`IF NOT EXISTS`, no-op sur l'index prod pré-existant, MANUAL block du schema doc à jour).
- **La purge `radar_trends` fonctionne** : 38 137 lignes portent toutes le même `computed_at` (`2026-08-08 05:00:34`) — `_purge_stale_trends` (`workers/tasks/trends.py:101-112`) supprime les périmées à chaque `compute_trends`. La table ne dérive pas, elle suit le catalog.
- **Les index partiels E1 servent réellement** : `EXPLAIN` prod du tier never-tried → `Index Scan using ix_catalog_deezer_searched_at` (cost 830 vs ~11 000 en seq scan). Le drain horaire Beatport et la passe Deezer s'appuient dessus.
- **`snapshot_backlogs` est fidèle à sa cadence** : 415 lignes `metric_snapshots` entre le 2026-07-22 15:50 et le 2026-08-08 21:30 = exactement 1/heure, zéro trou ; les lectures de `monitoring_service` sont fenêtrées sur `captured_at` indexé (`monitoring_service.py:52-54`).
- **`bpm_analysis_candidate_filter()` est bien la source unique du prédicat E2.c** : partagée par la tâche nocturne, le snapshot horaire (`tasks/monitoring.py:89-91`) et l'admin ; 4 116 lignes `bpm_analyzed_at` stampées en prod après la première nuit — le marqueur d'attempt fonctionne.

---

## Findings

### [A2-01] Les tris Explorer ne peuvent pas utiliser les index 0039 : Sort de ~256 k lignes à chaque page
- **Type** : perf
- **Sévérité** : moyenne
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** :
  - `services/catalog_service.py:346-349` : `query.order_by(*[dir_fn(c).nulls_last() for c in order_cols], dir_fn(CatalogEntry.id))` — tout tri est `NULLS LAST` + tie-break `id`.
  - Migration `0039_catalog_explorer_indexes.py:12-16` : 5 index b-tree simples (`bpm`, `key`, `duration_ms`, `release_date`, `created_at`), ordre par défaut `ASC NULLS LAST` → parcouru à rebours, un b-tree donne `DESC NULLS FIRST`, incompatible avec le `DESC NULLS LAST` demandé, et aucun index ne porte le tie-break `id`.
  - `EXPLAIN` prod du tri par défaut (`ORDER BY created_at DESC NULLS LAST, id DESC LIMIT 60`) :
    ```
    Limit (cost=15598.40..15605.40)
      -> Gather Merge -> Sort (Sort Key: created_at DESC NULLS LAST, id DESC)
         -> Parallel Seq Scan on catalog (rows=106600/worker)
    ```
    `ix_catalog_created_at` n'est **pas** utilisé. Les tris `title`/`artist` passent par `lower(trim(col))` (`catalog_service.py:324,328`) — aucun index fonctionnel n'existe.
  - Volumétrie : 255 975 lignes / 186 MB, +~8 k lignes/j ; chaque page recompte en plus le total via `select(func.count()).select_from(query.subquery())` (`catalog_service.py:351`) sur les 4 outer joins.
- **Constat** : les index 0039 servent les **filtres** de plage (bpm/durée/année) mais aucun **tri** — or le tri par défaut (`created_at` desc) s'exécute à chaque fetch du windowing Explorer **et** du feed Radar (qui réutilise `list_catalog`). Aujourd'hui ~15 600 unités de coût (dizaines de ms) ; la croissance de 8 k lignes/j la rend linéairement pire sur un VPS déjà tendu en ressources (cf. incident OOM /radar/feed). C'est un demi-raté de 0039 : l'intention (« created_at is the new default sort ») n'est pas servie par l'index créé.
- **Recommandation** : migration remplaçant `ix_catalog_created_at` par un index composite aligné sur la clause réelle : `CREATE INDEX ix_catalog_created_at_id ON catalog (created_at DESC NULLS LAST, id DESC)` (PG supporte l'ordre NULLS dans l'index), déclaré au modèle. Optionnel : mêmes composites pour `release_date`/`bpm` si les mesures le justifient, et index fonctionnel `lower(trim(title))` seulement si le tri A–Z devient un usage mesuré. Le `count()` par page est un sujet A1/A4 (contrat d'API), pas de fix DB.
- **Dépendances** : aucune
- **Tags** : —

### [A2-02] `radar_trends` toujours sans index sur `family`/`rank_in_family`/`rank_global` — table ×4 en un mois, nouveau consommateur /radar/feed
- **Type** : perf
- **Sévérité** : moyenne
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** :
  - **RÉCURRENCE 2026-07/A2-14** (alors « basse », seuil de réévaluation posé à ~100 k lignes).
  - Prod `pg_indexes` : `radar_trends` n'a toujours **que** `radar_trends_pkey`. Volumétrie : 9 172 lignes (juillet) → **38 137 lignes / 11 MB** (2026-08-08) — ×4 en un mois, croissance proportionnelle au catalog.
  - Nouveau chemin depuis D6 : `radar_service.py:325-328` (`list_bi_score`, page /radar) filtre `RadarTrend.rank_in_family <= TREND_PER_FAMILY` OU `rank_global <= TREND_GLOBAL_K` ; `EXPLAIN` prod → `Seq Scan on radar_trends (cost=0.00..1510.05)`.
  - L'endpoint historique `/api/radar/trends` (Hub, public, guests inclus) fait toujours son `GROUP BY family` + `ORDER BY rank_in_family`/`rank_global` sur la même table sans index (`routers/radar.py`).
- **Constat** : le seuil de réévaluation du prédécesseur sera atteint vers octobre au rythme actuel ; entre-temps le nombre de consommateurs a doublé (Hub + page Radar, les deux surfaces les plus exposées de l'app, guests compris). Chaque affichage paie un seq scan de 11 MB qui grossit chaque semaine.
- **Recommandation** : migration + déclaration modèle : `Index("ix_radar_trends_family_rank", "family", "rank_in_family")` et `Index("ix_radar_trends_rank_global", "rank_global")`. Coût d'écriture négligeable (la table est réécrite 1×/j par `compute_trends`).
- **Dépendances** : aucune
- **Tags** : —

### [A2-03] `catalog.needs_reconciliation` et `catalog.status` : mortes (0 writer, 0 reader, valeur unique en prod)
- **Type** : mort
- **Sévérité** : basse
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** :
  - Prod (255 975 lignes) : `count(*) FILTER (WHERE needs_reconciliation)` = **0**, `FILTER (WHERE needs_reconciliation IS NULL)` = **0** (100 % `false`) ; `FILTER (WHERE status <> 'official')` = **0**.
  - Grep repo `needs_reconciliation` : seuls hits = modèle (`models/catalog.py:64`) + migration 0005. Aucun writer, aucun reader, non exposée par les schemas Pydantic.
  - `catalog.status` : aucun writer (le seul flux est le default `'official'` du modèle, `models/catalog.py:51-53`), aucun reader (`CatalogEntry.status` = 0 hit hors modèle ; les champs `status` des schemas sont des statuts de tâches/flags, pas cette colonne).
  - Aggravant doc : le MANUAL block du schema doc les documente comme vivantes — `docs/database-schema.md:34` (« `catalog.status`: "official" (default), "pending", etc. ») alors qu'aucun `"pending"` n'a jamais existé.
- **Constat** : deux colonnes créées en 0005 « pour plus tard », jamais branchées en 15 mois. Même profil que `fingerprint`/`preview_url` purgées en AU3 (0031) : preuve mécanique complète (0 donnée variante, 0 référence code).
- **Recommandation** : drop des deux colonnes dans la prochaine migration utilitaire (pattern 0031), et retrait des deux lignes du MANUAL block. Si un doute produit subsiste sur `status`, la garder mais corriger le MANUAL block en « réservée, jamais alimentée » (pattern A2-05/A2-08 de 2026-07) — le duo actuel (colonne morte + doc qui la prétend vivante) est le pire des deux mondes.
- **Dépendances** : même migration que A2-05 possible
- **Tags** : —

### [A2-04] `catalog.origin` : write-only — écrite à l'import, jamais lue nulle part
- **Type** : mort
- **Sévérité** : basse
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** :
  - Writers réels : default `'deezer'` (`models/catalog.py:48-50`) + `origin="rekordbox"` à la création d'une entrée privée d'import (`workers/tasks/import_rb.py:131`).
  - Readers : **0** — grep `origin` sur `server/` : seuls hits = modèle, migration 0005, le générateur de doc, et un commentaire (`workers/tasks/artists.py:1636`). Non exposée par les schemas.
  - Prod : `deezer` = 255 933, `rekordbox` = 42. La valeur est de plus **fausse par construction** : les entrées créées par le crawl TrackID ou l'import manuel F5 (TIDAL) reçoivent aussi `'deezer'` (default), la colonne ne trace donc même pas fidèlement la provenance qu'elle prétend porter.
- **Constat** : à la différence de A2-03, un writer existe — mais une provenance jamais lue et majoritairement fausse (tout ce qui n'est pas import RB est étiqueté `deezer`) n'a pas de valeur forensique. `scope`/`owner_id` portent déjà la distinction utile (privé RB vs partagé).
- **Recommandation** : décision produit rapide : (a) dropper la colonne + retirer `docs/database-schema.md:33` (mon option par défaut), ou (b) la fiabiliser en la stampant correctement à CHAQUE point de création (trackid, F5, C6.c v2) — mais c'est un chantier sans consommateur identifié. Ne pas la laisser en l'état : sa valeur actuelle induit en erreur quiconque la requête.
- **Dépendances** : même migration que A2-03 si drop
- **Tags** : —

### [A2-05] `sets.platform` : backfillée une fois en 0029, plus jamais écrite ni lue — 99,7 % NULL
- **Type** : mort
- **Sévérité** : basse
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** :
  - Prod : `platform` = NULL sur **28 781 / 28 869** sets (99,7 %) ; les 88 non-NULL (`soundcloud` 56, `youtube` 28, `hearthis` 4) sont exactement la population du backfill `UPDATE sets SET platform = ...` de `0029_set_dedup_schema.py:98-101` (pattern-match sur `source_url`).
  - Aucun writer applicatif : grep `platform` sur `server/api` + `server/workers` → seuls hits = modèle (`models/sets.py:46`), migrations 0029/0035, et des commentaires sur les « platform ids » du catalog (autre sujet). L'importer TrackID (`api/trackid/`) ne la renseigne jamais.
  - Aucun reader : ni `set_dedup_service`, ni les routers, ni les schemas.
- **Constat** : colonne posée par le chantier dédup C6.0 (0029) pour distinguer la plateforme d'origine d'un set, utilisée une seule fois par le backfill de sa propre migration, puis abandonnée — le scoring dédup ne s'en sert pas (la refonte 2026-08-07 ne la mentionne pas). Chaque nouveau set (~1 000/j) naît avec NULL.
- **Recommandation** : drop (`sets` est en pleine croissance, autant purger avant que la colonne morte pèse) — ou si le dédup cross-plateforme futur la revendique, la stamper à l'import TrackID et le documenter. À trancher avec le même arbitrage que A2-04.
- **Dépendances** : aucune
- **Tags** : —

### [A2-06] `metric_snapshots` et `crawl_logs` : croissance non bornée, aucune rétention
- **Type** : dette
- **Sévérité** : basse
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** :
  - Prod : `metric_snapshots` = 415 lignes / 304 kB depuis le 2026-07-22, cadence 24/j (0041, tâche horaire). `crawl_logs` = 981 lignes / 568 kB depuis le 2026-06-23, ~31/j mesurés sur les 14 derniers jours (30-42/j).
  - Grep `delete`/`purge` sur `server/workers/` : la seule purge existante est `_purge_stale_trends` (radar_trends). Aucun code ne supprime jamais une ligne de `metric_snapshots`, `crawl_logs` (ni `admin_audit_log`, volontairement — audit trail).
  - Lectures : fenêtrées (`monitoring_service.py:52-54` sur `captured_at` indexé ; listing crawl_logs paginé `order_by started_at desc`, `catalog_service.py:859`) — pas de dégradation de lecture à court terme.
- **Constat** : ~9 000 lignes/an pour `metric_snapshots` (payload JSON ~750 B/ligne indexée), ~11 000/an pour `crawl_logs`. Quelques Mo/an : aucun danger opérationnel avant des années, mais c'est une dérive silencieuse sans décision actée, sur un VPS où les dumps chiffrés partent en offsite chaque nuit (le poids finit dans les backups).
- **Recommandation** : acter une politique et l'inscrire : soit une purge dans `snapshot_backlogs` même (ex. `DELETE FROM metric_snapshots WHERE captured_at < now() - interval '13 months'` — garde un an+ de comparaison saisonnière ; idem crawl_logs à 6-12 mois hors erreurs), soit une ligne explicite « croissance acceptée, réévaluer à 100 k lignes » dans le MANUAL block. Le statu quo non documenté est le seul mauvais choix.
- **Dépendances** : aucune
- **Tags** : —

### [A2-07] Le prédicat backlog BPM (E2.c) = seq scan parallèle de la plus grosse table, 28×/jour
- **Type** : perf
- **Sévérité** : basse
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** :
  - `EXPLAIN` prod du count `bpm_analysis_candidate_filter()` :
    ```
    Finalize Aggregate (cost=12234.57..12234.58)
      -> Parallel Seq Scan on catalog (rows=20341/worker)
         Filter: has_preview IS TRUE AND bpm IS NULL AND deezer_id IS NOT NULL
                 AND bpm_analyzed_at IS NULL AND deezer_id <> 'NOT_FOUND'
    ```
    Aucun index ne couvre `has_preview` ni la combinaison ; `ix_catalog_bpm` n'est pas choisi (`bpm IS NULL` = 69 919 lignes, 27 % — non sélectif).
  - Exécutions : `snapshot_backlogs` horaire (`tasks/monitoring.py:89-91`, 24/j) + tâche nocturne `analyze_bpm_previews` (4/nuit, SELECT candidats + garde) + carte admin Aperçu à la demande. Table : 186 MB, +8 k lignes/j.
- **Constat** : ~28 scans complets/jour de la plus grosse table pour un prédicat 5 conditions. Supportable aujourd'hui (scan parallèle, VPS idle la nuit), mais le coût est indépendant de la taille du backlog (qui, lui, va fondre à ~0 en ~8 nuits) : une fois le backlog drainé, on paiera pour toujours des seq scans horaires qui comptent 0.
- **Recommandation** : index partiel aligné sur le prédicat : `CREATE INDEX ix_catalog_bpm_analysis_backlog ON catalog (id) WHERE has_preview AND bpm IS NULL AND bpm_analyzed_at IS NULL AND deezer_id IS NOT NULL AND deezer_id <> 'NOT_FOUND'` (déclaré au modèle avec `postgresql_where`, précédent : `ix_catalog_deezer_searched_at`). Index minuscule (≤ backlog courant), count devient un index-only scan de quelques ms.
- **Dépendances** : cohérent à livrer avec A2-01/A2-02 (même migration d'index)
- **Tags** : —

### [A2-08] Import Rekordbox : toujours un upsert par piste dans la boucle
- **Type** : perf
- **Sévérité** : basse
- **Effort estimé** : M
- **Confiance** : haute
- **Preuve** :
  - **RÉCURRENCE 2026-07/A2-13**, inchangée : `workers/tasks/import_rb.py:143-171` — `for t in batch:` construit et exécute `conn.execute(pg_insert(ut_table).values(...).on_conflict_do_update(...))` **par piste** (commit par lot l.179, mais N round-trips DB pour N pistes).
- **Constat** : identique à juillet — task Celery avec progression, tolérable fonctionnellement, mais chaque import complet paie N allers-retours alors que `pg_insert` accepte une liste de dicts (le même fichier bulk-e déjà le catalog).
- **Recommandation** : inchangée — chunker en lots de 500-1 000 `values([...])` en conservant la progression. À faire au prochain passage sur `import_rb` (pas de chantier dédié).
- **Dépendances** : aucune
- **Tags** : —

### [A2-09] `/api/sets/` : agrégation `GROUP BY` sur 389 k `set_tracks` à chaque page, tris non indexés, tie-break non unique
- **Type** : perf
- **Sévérité** : basse
- **Effort estimé** : M
- **Confiance** : haute
- **Preuve** :
  - `routers/sets.py:222-250` : la liste calcule `total_tracks_expr` (agrégat sur le join `set_tracks`) + HAVING, trie sur `played_date`/`title`/`duration_ms` (`sort_columns`, l.231-236) et recompte le total par page via `select(func.count()).select_from(stmt.subquery())` (l.247).
  - Prod `pg_indexes` sur `sets` : uniquement `sets_pkey`, `uq_set_external_source`, `ix_sets_parent_set_id` — aucun des tris n'est indexé. Volumétrie : 28 279 roots, `set_tracks` = 389 006 lignes / 102 MB, +~8 k/j.
  - Tie-break : `stmt.order_by(primary, DJSet.created_at.desc())` (l.244) — `created_at` n'est pas unique (contrairement à la leçon A1-02 appliquée à Explorer, `catalog_service.py:345-348`, qui tie-break sur `id`).
- **Constat** : chaque page de la liste Sets refait l'agrégation complète du join + le count. À 389 k lignes c'est encore fluide ; à ~3 M (un an d'inflow) le GROUP BY par page se comptera en secondes. Le tie-break `created_at` (timestamps à la µs, collisions improbables mais possibles en batch d'import) peut dupliquer/omettre une ligne entre deux pages du windowing.
- **Recommandation** : (1) tie-break `DJSet.id.desc()` au lieu de `created_at.desc()` — one-liner sans risque ; (2) au prochain passage sur /sets : dénormaliser `track_count` sur `sets` (maintenu à l'import/recrawl, comme `completion_pct` l'est déjà) pour sortir l'agrégat de la liste, + index `(parent_set_id, played_date)` si les mesures le justifient. Pas urgent — planifier avant que set_tracks n'atteigne ~1 M.
- **Dépendances** : aucune
- **Tags** : —

---

## Hypothèses réfutées

- **`SetFlagType.part_candidate` / `part_overlap_anomaly` morts** (candidats vulture) : **vivants**. Créés par `set_dedup_service.py:454` (`flag_type = "part_overlap_anomaly" if pairwise_max > 0.30 else "part_candidate"`), lus par `:1174` (group flags) et l'admin (`AdminSets.vue:101`), explicitement épargnés par `scripts/rescore_set_flags.py:14`. Les hits vulture viennent de l'indirection enum → string.
- **`catalog.created_at` NULL = bug actif** : non — 4 503 lignes NULL mais `max(id)` = 7 496 vs `max(id)` catalog = 257 857 : population exclusivement historique (pré-`workers/db.py`, qui stampe `created_at` à chaque insert, l.120). Elles se classent en fin de tri par défaut (`nulls_last`), comportement acceptable pour des lignes anciennes. Un backfill one-off resterait cosmétique.
- **FK sans index sur `artist_activity.catalog_id`/`set_id`, `user_radar_state.catalog_id`, `collection_items.catalog_id`** (scans à chaque DELETE catalog, fréquents depuis les merges X1) : volumétrie toujours négligeable — `artist_activity` 62 lignes, `user_radar_state` ~5, `collection_items` ~0. Le report du prédécesseur (A2-11, « réévaluer quand les tables grossissent ») reste le bon arbitrage.
- **`crawl_logs` sans index sur `started_at`** (tri du listing admin) : 981 lignes — négligeable pour des années ; l'index `ix_crawl_logs_task_type` couvre l'autre filtre.
- **`admin_audit_log` / `set_flags` / `artist_activity` en croissance non bornée** : 337 / 303 / 62 lignes — rythmes insignifiants (actions admin, paires flaggées bornées par le dédup, feature follow peu utilisée). Rien à purger.
- **N+1 `match_set` (2026-07/A2-12)** : largement corrigé par la refonte scoring 2026-08-07 — la requête DF est batchée en UNE requête sur tous les mtids (`set_dedup_service.py:787`), le chargement séquentiel par candidat restant est délibéré et documenté (session partagée, jamais de gather sur une même session — commentaire l.775-776) et borné (candidats < 10). Plus rien à signaler.
- **`radar_trends` croissance non bornée** : réfuté — purge opérationnelle, preuve : les 38 137 lignes portent un unique `computed_at` (voir « Ce qui va bien »). La croissance suit le catalog, c'est le problème d'index (A2-02), pas de rétention.
- **`metric_snapshots` : lectures dégradées par la croissance** : réfuté à court terme — toutes les lectures sont fenêtrées ou `LIMIT 1` sur `captured_at` indexé (`monitoring_service.py:52-54,160-162,216-218`). Seule la croissance brute reste (A2-06).
- **Downgrade 0031 asymétrique sur `fingerprint`** : le downgrade recrée la colonne avec `unique=True` inline (contrainte `catalog_fingerprint_key`) au lieu de l'index unique historique de `create_all` — divergence de nom d'objet uniquement, sans effet fonctionnel ; pas un finding.
- **Doc « 28 tables » vs « 31 classes » (CLAUDE.md)** : cohérents — 28 classes mappées (= 28 tables du doc) + 2 enums (`SetFlagType`, `SetFlagStatus`) + `StringArray` = 31 classes annoncées.
