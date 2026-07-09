# Audit A2 — Base de données

> **Date** : 2026-07-09
> **Périmètre** : modèles SQLAlchemy (`server/api/models/`), 30 migrations Alembic (`server/api/alembic/versions/`), `docs/database-schema.md`, requêtes des services (`server/api/services/`), routers et workers (`server/workers/`), DB prod (SELECT lecture seule via SSH).
> **Méthode** : croisement inventaire Phase 0 (§9) ↔ code ↔ DB live. Chaque colonne suspecte vérifiée par `COUNT(*) FILTER (WHERE ... IS NOT NULL)` en prod (et non par `pg_stats.null_frac`, sujet à échantillonnage). Chaque recommandation de suppression appuyée par : 0 ligne non-NULL en prod + 0 writer dans le code + 0 reader hors modèle.
> **Note** : les deux sous-agents d'exploration (FK sans index, N+1) ont été perdus en cours de route ; ces deux angles ont été refaits en direct de façon ciblée (voir "Non couvert" pour les limites).

## Ce qui va bien

- **Conventions temps/durées respectées** : aucun `DateTime` naïf dans les modèles (grep `DateTime\((?!timezone=True)` = 0 hit sur `server/api/models/`), toutes les durées en ms (`duration_ms`, `timecode_ms`).
- **Politiques FK conformes à la doc** (vérifié en prod via `pg_constraint`) : `user_tracks.catalog_id` → `ON DELETE RESTRICT`, `radar_tracks.catalog_id` / `set_tracks.catalog_id` → `SET NULL`, `catalog_artists` → `CASCADE`, `radar_tracks.watched_entity_id` → `CASCADE` (fix 0021 appliqué).
- **Le lifecycle radar C0.1 fonctionne** : la suspicion de l'inventaire (§9, `removed_at` ~100% NULL) est un artefact de sampling `pg_stats`. Réalité prod : `SELECT count(*) FILTER (WHERE removed_at IS NOT NULL) FROM radar_tracks` → **13** removals sur 6806, et la logique mark/clear est bien branchée (`server/workers/db.py:212-231`).
- **`user_tracks.avis` est vivante** : writers réels (`server/api/opinion_sync.py:70`, `server/api/services/catalog_service.py:580`) ; les 100% NULL reflètent l'usage, pas du code mort.
- **Patterns de chargement majoritairement propres** : préchargement agrégé en une requête + boucle mémoire dans `artist_service.py:118-152`, batch-fetch des titres membres dans `admin.py:342-354`, `selectinload` imbriqué dans `GET /sets/{id}` (`routers/sets.py:238-241`), `bulk_get_or_create_catalog` dans les workers (`workers/db.py:36`).
- **`alembic_version` prod = 0030**, alignée avec le repo ; 0030 (part_total, group_key) bien appliquée en prod (vérifié via `information_schema` / `pg_indexes`).
- **Dedup et sentinels conformes** : `normalized_key`/`isrc`, sentinel `deezer_id='NOT_FOUND'` utilisés comme documenté.

---

## Findings

### [A2-01] Table orpheline `watched_playlists` en prod (rename 0006 sauté)
- **ID** : A2-01
- **Type** : dette
- **Sévérité** : moyenne
- **Effort estimé** : S (< 1h)
- **Confiance** : haute
- **Preuve** :
  - `server/api/alembic/versions/0006_watched_entities.py:24-25` : `if "watched_playlists" in tables and "watched_entities" not in tables: op.rename_table(...)` — rename **conditionnel**.
  - Prod, `information_schema.columns` sur `watched_playlists` : schéma **pré-0006** (10 colonnes : id, external_id, source, title, description, created_at, last_crawled_at, has_artwork, track_count, owner — pas de `type`, `current_task_id`, `crawl_started_at`).
  - Prod : `SELECT count(*), count(*) [ids présents dans watched_entities], max(created_at), max(last_crawled_at)` → `24 | 24 | 2026-06-08 | 2026-06-09`. Les 24 ids sont **tous** recouverts par `watched_entities` (56 lignes), table figée depuis un mois.
  - Grep `watched_playlists` sur tout le repo : aucune référence code hors migrations 0001/0002/0006 et docs.
- **Constat** : au moment où 0006 a tourné, `watched_entities` existait déjà (créée par le `create_all` de `main.py`, cf. A2-02), donc le rename a été sauté et l'app a reparti de zéro sur la nouvelle table. L'ancienne `watched_playlists` est restée en prod avec 24 lignes périmées, invisible des modèles et du schema doc.
- **Recommandation** : migration `0031` avec `DROP TABLE IF EXISTS watched_playlists` (précédée d'un `pg_dump -t watched_playlists` de précaution sur le VPS). Preuve mécanique irréfutable : schéma obsolète, données recouvertes, zéro référence code, figée.
- **Dépendances** : aucune
- **Tags optionnels** : QUICK-WIN-CANDIDAT

### [A2-02] `Base.metadata.create_all` au démarrage coexiste avec Alembic
- **ID** : A2-02
- **Type** : archi
- **Sévérité** : moyenne
- **Effort estimé** : M (1h-1j)
- **Confiance** : haute
- **Preuve** :
  - `server/api/main.py:54-56` : `if os.getenv("ENV") != "production": await conn.run_sync(Base.metadata.create_all)`.
  - Migrations écrites défensivement à cause de ça : `0001_add_sets_artists_genres.py:23` (« idempotent: skip if create_all already ran »), `0005_catalog_scope_user_tracks.py:39` (`if "fingerprint" not in catalog_cols`), `0006:24` (rename conditionnel).
  - Conséquence historique concrète : A2-01 (la table orpheline existe parce que `create_all` a créé `watched_entities` avant que 0006 ne tourne).
- **Constat** : deux sources de vérité du schéma. Aujourd'hui gaté hors production, mais toujours actif en dev : une table/colonne déclarée dans un modèle apparaît en dev sans migration, puis la migration écrite ensuite se court-circuite elle-même (pattern 0001/0005/0006). Les index créés uniquement en migration (A2-04) n'existent pas dans les DB dev issues de `create_all`.
- **Recommandation** : réserver `create_all` au harnais de test (SQLite in-memory) ; en dev Docker, exécuter `alembic upgrade head` au démarrage du container API (comme en prod). Supprimer le bloc de `lifespan` ou le conditionner à un flag explicite `USE_CREATE_ALL=1` réservé aux tests.
- **Dépendances** : aucune (mais explique A2-01, A2-04)

### [A2-03] `docs/database-schema.md` périmé (C6.1 / migration 0030 non reflétée)
- **ID** : A2-03
- **Type** : dead-doc
- **Sévérité** : basse
- **Effort estimé** : S (< 1h)
- **Confiance** : haute
- **Preuve** : `server/api/models/sets.py:47` (`part_total`), `:155-156` (`set_id_b` **nullable**), `:172-173` (`group_key`, `member_set_ids`) — vs `docs/database-schema.md:343` (pas de `part_total`), `:397` (`set_id_b` | Integer | **no**), aucune mention de `group_key`/`member_set_ids`.
- **Constat** : le doc n'a pas été régénéré après le chantier C6.1 (0030). CLAUDE.md impose pourtant « run `/schema_doc` after any model/migration change ». Tout agent qui lit ce doc pour une requête 3+ tables travaille sur un schéma faux pour `sets`/`set_flags`.
- **Recommandation** : exécuter `/schema_doc` et committer le diff.
- **Dépendances** : aucune
- **Tags optionnels** : QUICK-WIN-CANDIDAT | lié-chantier:C6

### [A2-04] Index et contraintes uniques définis uniquement en migration, absents des modèles
- **ID** : A2-04
- **Type** : convention
- **Sévérité** : moyenne
- **Effort estimé** : M (1h-1j)
- **Confiance** : haute
- **Preuve** :
  - `0020_add_missing_indexes.py:9-20` : `ix_radar_tracks_watched_entity`, `ix_radar_tracks_catalog`, `ix_catalog_deezer_id` (partiel), `ix_catalog_beatport_id` (partiel), `ix_watched_entities_source`, `ix_catalog_genres` (GIN).
  - `0028_compound_indexes.py:11-20` : `ix_radar_tracks_source_detected`, `ix_user_opinions_user_opinion`.
  - `0029_set_dedup_schema.py:95` : `uq_set_flag_pair` ; `0030_set_parts.py:30` : `uq_set_flag_group_key` (unique partiel).
  - Grep `Index\(` sur `server/api/models/` : **0** déclaration composite ; le modèle `SetFlag` (`models/sets.py:148-173`) n'a **aucun** `__table_args__` (ni `uq_set_flag_pair` ni `uq_set_flag_group_key`), alors que ces contraintes existent en prod (vérifié `pg_indexes`).
- **Constat** : ~10 index/contraintes vivent uniquement dans les migrations. Trois conséquences : (1) le schema doc généré depuis les modèles ne les liste pas (il montre encore `uq_set_flag_pair` d'une version antérieure du modèle, mais pas les autres) ; (2) un `alembic revision --autogenerate` proposera de les **dropper** ; (3) les DB dev issues de `create_all` (A2-02) tournent sans ces index — comportements de perfs divergents dev/prod.
- **Recommandation** : déclarer ces index/contraintes dans les modèles (`__table_args__` avec `Index(...)`, `postgresql_where` pour les partiels), vérifier par un autogenerate à blanc que le diff est vide, puis régénérer le schema doc.
- **Dépendances** : A2-03 (régénération doc après), A2-02 (contexte)

### [A2-05] Colonnes `artists.bio/country/real_name/soundcloud_id` jamais alimentées mais exposées dans l'API
- **ID** : A2-05
- **Type** : dead-code
- **Sévérité** : basse
- **Effort estimé** : S (< 1h)
- **Confiance** : haute (colonnes mortes) / basse (pour leur suppression)
- **Preuve** :
  - Prod : `SELECT count(*) FROM artists WHERE bio IS NOT NULL OR country IS NOT NULL OR real_name IS NOT NULL OR soundcloud_id IS NOT NULL` → **0** (sur 9997).
  - Grep repo : aucun writer ; seuls hits = modèle (`models/artist.py:21-26`), migration 0001, exposition lecture (`schemas/artist.py:25-30`, `services/artist_service.py:89,216-217,391-396`).
  - Contre-exemple : `trackid_id` est vivante (writer `api/trackid/importer.py:26-27,42`) — ne pas la toucher.
- **Constat** : quatre colonnes créées en 0001 « pour plus tard », jamais peuplées depuis, mais sérialisées dans `ArtistDetail` (toujours `null` côté frontend). Bruit dans le schéma et l'API.
- **Recommandation** : décision produit à trancher : soit un chantier d'enrichissement les peuplera (auquel cas documenter dans le schema doc MANUAL block), soit les retirer des schemas Pydantic dès maintenant (S, sans migration). Le drop des colonnes elles-mêmes reste optionnel (asymétrie : coût de stockage nul, risque de suppression prématurée > gain).
- **Dépendances** : aucune

### [A2-06] `catalog.fingerprint` : colonne morte avec index unique sur 15 836 lignes
- **ID** : A2-06
- **Type** : dead-code
- **Sévérité** : basse
- **Effort estimé** : S (< 1h)
- **Confiance** : haute
- **Preuve** :
  - Prod : `SELECT count(*) FROM catalog WHERE fingerprint IS NOT NULL` → **0** (sur 15836).
  - Grep `fingerprint` sur `server/` : seuls hits = `models/catalog.py:54` (`unique=True`) et `0005_catalog_scope_user_tracks.py:39-40`. **Aucun** read, **aucun** write, nulle part.
- **Constat** : colonne ajoutée en 0005 (probablement pour un futur audio-fingerprinting), jamais branchée. Elle maintient un index unique inutile sur la plus grosse table (18 MB).
- **Recommandation** : drop colonne + index dans la même migration 0031 que A2-01. Preuve mécanique complète (0 donnée, 0 référence code) — si le fingerprinting revient (C2 ?), la re-créer coûtera une migration triviale.
- **Dépendances** : A2-01 (même migration), hors-domaine:{produit} pour confirmer qu'aucun chantier imminent ne la vise
- **Tags optionnels** : QUICK-WIN-CANDIDAT | lié-chantier:C2

### [A2-07] `catalog.preview_url` jamais persistée mais lue et exposée partout
- **ID** : A2-07
- **Type** : dette
- **Sévérité** : basse
- **Effort estimé** : S (< 1h)
- **Confiance** : haute
- **Preuve** :
  - Prod : `SELECT count(*) FROM catalog WHERE preview_url IS NOT NULL` → **0** (sur 15836).
  - Seul point d'écriture théorique : `api/catalog.py:17,47` (`get_or_create_catalog(preview_url=...)`) — mais **aucun caller ne passe l'argument** (`services/radar_service.py:312-314` appelle sans ; `workers/db.py:36 bulk_get_or_create_catalog` ne gère pas le champ).
  - Pourtant lue/sérialisée : `routers/radar.py:52,73` (TrendItem.preview_url, endpoint public), `services/similarity_service.py:479`, `services/catalog_service.py:302,507`.
  - Le vrai flux preview est **live** : `GET /catalog/{id}/preview-url` → `catalog_service.get_preview_url:526-556` interroge l'API Deezer à chaque appel ; `has_preview` est lui correctement maintenu (`workers/deezer_enrich.py:318-320`).
- **Constat** : architecture asymétrique : `has_preview` (booléen) est persisté, l'URL est récupérée en direct (les URLs preview Deezer expirent — ne pas les stocker est probablement le bon choix). Mais la colonne et les champs API `preview_url` subsistent et renvoient toujours `null`, ce qui est trompeur pour tout consommateur.
- **Recommandation** : acter la décision « preview = live only » : retirer `preview_url` des SELECT/schemas (radar, similarity, catalog detail), puis dropper la colonne (même lot que A2-01/A2-06). Alternative si un cache est souhaité : la peupler avec TTL — mais c'est un chantier, pas un fix.
- **Dépendances** : A2-06 (même migration si drop)

### [A2-08] `sets.event/venue/description` : jamais écrites, renvoyées `null` dans l'API
- **ID** : A2-08
- **Type** : dead-code
- **Sévérité** : basse
- **Effort estimé** : S (< 1h)
- **Confiance** : haute (mortes) / basse (suppression)
- **Preuve** :
  - Prod : `SELECT count(*) FROM sets WHERE event IS NOT NULL OR venue IS NOT NULL OR description IS NOT NULL` → **0** (sur 608).
  - Les deux seuls sites de création de `DJSet` n'alimentent aucune des trois : `api/trackid/importer.py:101-111`, `services/set_dedup_service.py:861-869`.
  - Lues uniquement pour la réponse API : `routers/sets.py:329-333`.
- **Constat** : colonnes créées en 0001 pour des métadonnées de set (événement, lieu) qu'aucune source actuelle (TrackID.net) ne fournit.
- **Recommandation** : les retirer du schéma de réponse `DJSetDetailOut` (S, sans migration) et documenter leur statut « réservé » dans le MANUAL block du schema doc — ou les dropper si aucune source future ne les fournira (décision produit).
- **Dépendances** : aucune

### [A2-09] `user_tracks.created_at` jamais renseignée aux trois points d'écriture
- **ID** : A2-09
- **Type** : bug
- **Sévérité** : basse
- **Effort estimé** : S (< 1h)
- **Confiance** : haute
- **Preuve** :
  - Prod : `SELECT count(*) FROM user_tracks WHERE created_at IS NOT NULL` → **0** (sur 631).
  - `routers/tracks.py:166-178` : `UserTrack(...)` sans `created_at`.
  - `workers/tasks/import_rb.py:136-159` : `pg_insert(ut_table).values(...)` sans `created_at` (ni dans le `set_` de l'upsert).
  - Le modèle (`models/catalog.py`) n'a ni `default` ni `server_default` sur cette colonne.
- **Constat** : la colonne existe pour tracer la date d'entrée dans Diggy (distincte de `date_added` Rekordbox), mais aucun chemin d'écriture ne la remplit et aucun default ne la sauve. Elle est morte par accident, pas par design.
- **Recommandation** : ajouter `server_default=func.now()` via micro-migration (les 631 lignes existantes resteront NULL — acceptable), ou la dropper si `date_added` suffit. Choix à trancher en 15 min.
- **Dépendances** : aucune
- **Tags optionnels** : QUICK-WIN-CANDIDAT

### [A2-10] `GET /sets/{id}` calcule le statut « in lib » sur les bibliothèques de TOUS les utilisateurs
- **ID** : A2-10
- **Type** : bug
- **Sévérité** : moyenne
- **Effort estimé** : S (< 1h)
- **Confiance** : haute
- **Preuve** :
  - `routers/sets.py:234` : `async def get_set_detail(set_id: int, db=Depends(get_db))` — **aucune dépendance user**.
  - `routers/sets.py:264-267` : `select(UserTrack.catalog_id).where(UserTrack.catalog_id.in_(catalog_ids))` — pas de filtre `user_id`.
- **Constat** : le flag `in_lib` de chaque piste d'un set reflète « présent dans la bibliothèque de n'importe qui ». Invisible aujourd'hui (une seule vraie bibliothèque importée), faux dès qu'un deuxième utilisateur importe la sienne — et fuite mineure d'information inter-utilisateurs.
- **Recommandation** : ajouter `user: User | None = Depends(get_current_user)` et filtrer `UserTrack.user_id == uid` (avec `lib_set = set()` si guest, `uid()` pouvant être None). Vérifier au passage les autres calculs « in lib » du même style (`routers/search.py:51` filtre bien par user — OK).
- **Dépendances** : aucune
- **Tags optionnels** : QUICK-WIN-CANDIDAT | lié-chantier:C3

### [A2-11] 6 FK sans index : 2 justifient un index, 4 sont différables
- **ID** : A2-11
- **Type** : perf
- **Sévérité** : basse
- **Effort estimé** : S (< 1h)
- **Confiance** : haute
- **Preuve** :
  - Prod `pg_indexes` : `user_tracks`, `user_follows`, `user_radar_state`, `user_set_follows`, `collection_items` n'ont **que** leur PK composite (leading = `user_id`/`collection_id`) ; `set_flags` n'a rien sur `resolved_by`.
  - Requêtes filtrant **sans** la leading column :
    - `user_tracks.catalog_id` : `routers/sets.py:265` (`catalog_id.in_(...)` sans user_id — cf. A2-10), `routers/search.py:137` (join `UserTrack.catalog_id == CatalogArtist.catalog_id`), + **check RESTRICT** exécuté par PG à chaque `DELETE FROM catalog` (seq scan de user_tracks par catalog_id).
    - `user_follows.entity_id` : `routers/watchlist.py:109-110` (sous-requête corrélée par entity_id seul), `workers/tasks/radar.py:173` (`DELETE ... WHERE entity_id == playlist_id`).
    - `user_set_follows.set_id` : `workers/tasks/sets.py:339` (`select(set_id).distinct()` — full scan de toute façon) ; `opinion_sync.py:105` filtre avec user_id → PK OK.
    - `user_radar_state.catalog_id` : `opinion_sync.py:77` et `radar_service.py:221,264` filtrent avec user_id → PK OK ; seule la cascade `DELETE catalog` scanne.
    - `collection_items.catalog_id` : `routers/collections.py:126,181` filtrent avec collection_id → PK OK ; cascade catalog seule concernée (0 ligne).
    - `set_flags.resolved_by` : écrit (`admin.py:453,476`), jamais filtré → index inutile.
  - Volumétrie prod : user_tracks 376 kB / 631 lignes, user_follows 12, user_set_follows 11, user_radar_state 5, collection_items 0 — **aucun impact mesurable aujourd'hui**.
- **Constat** : le seul index structurellement justifié est `user_tracks.catalog_id` (RESTRICT scanné à chaque suppression catalog + deux requêtes applicatives sans leading) ; `user_follows.entity_id` est le second candidat (delete par entité + sous-requête corrélée). Le reste est du confort prématuré.
- **Recommandation** : dans la prochaine migration utilitaire : `CREATE INDEX ix_user_tracks_catalog_id` et `ix_user_follows_entity_id`. Ne pas indexer les 4 autres tant que C3 n'a pas fait grossir les tables (réévaluer alors `user_radar_state.catalog_id` et `collection_items.catalog_id` pour les cascades).
- **Dépendances** : aucune
- **Tags optionnels** : lié-chantier:C3

### [A2-12] N+1 dans le matching de dédup sets (`match_set`)
- **ID** : A2-12
- **Type** : perf
- **Sévérité** : basse
- **Effort estimé** : M (1h-1j)
- **Confiance** : haute
- **Preuve** :
  - `services/set_dedup_service.py:610-626` : `for candidate in candidates:` → **2 requêtes par candidat** (`select(DJSet)` puis `select(SetTrack)` par set candidat).
  - `services/set_dedup_service.py:418-429` : `for mid in member_ids:` → 1 requête `SetTrack` par membre du groupe de parts.
  - Contexte d'appel : `api/trackid/importer.py:174` (import de sets, exécuté par les tasks Celery `crawl_trackid_latest`/`backfill_trackid_sets` et `POST /sets/import`) et `api/scripts/audit_set_dedup.py`.
- **Constat** : N est borné (candidats = sets partageant des mtids, typiquement < 10 ; le commit a311e5e a de plus posé des limites sur resolve_set_tracks) et le contexte est batch nocturne — l'impact réel est faible. C'est du N+1 « propre » à corriger opportunistiquement, pas une urgence.
- **Recommandation** : lors du prochain passage sur `set_dedup_service` : précharger `DJSet` des candidats en un `WHERE id IN (...)` et les `SetTrack` en un `WHERE set_id IN (...)` groupé par set_id (même pattern que `materialize_parent` qui le fait déjà correctement, cf. `child_tracks` préchargé ligne ~727).
- **Dépendances** : aucune
- **Tags optionnels** : lié-chantier:C6

### [A2-13] Import Rekordbox : un upsert par piste dans une boucle
- **ID** : A2-13
- **Type** : perf
- **Sévérité** : basse
- **Effort estimé** : M (1h-1j)
- **Confiance** : haute
- **Preuve** : `workers/tasks/import_rb.py:136-160` : boucle sur toutes les pistes de la bibliothèque avec `conn.execute(pg_insert(ut_table).values(...).on_conflict_do_update(...))` **par piste** (N = taille de la bibliothèque, potentiellement plusieurs milliers de round-trips).
- **Constat** : task Celery avec progression, donc tolérable fonctionnellement, mais chaque import complet paie N allers-retours DB alors que `pg_insert` accepte une liste de dicts (le même fichier fait déjà du bulk pour le catalog via `bulk_get_or_create_catalog`).
- **Recommandation** : chunker en lots de 500-1000 avec `pg_insert(ut_table).values([...batch...]).on_conflict_do_update(...)`, en conservant la mise à jour de progression entre les lots.
- **Dépendances** : aucune

### [A2-14] `radar_trends` : tris de l'endpoint public `/api/radar/trends` sans index
- **ID** : A2-14
- **Type** : perf
- **Sévérité** : basse
- **Effort estimé** : S (< 1h)
- **Confiance** : haute
- **Preuve** :
  - Prod `pg_indexes` sur `radar_trends` : **uniquement** `radar_trends_pkey (catalog_id)`.
  - `routers/radar.py:32-38` : `GROUP BY family` sur toute la table à chaque appel ; `:58-62` : `ORDER BY rank_in_family` (si filtre family) ou `ORDER BY rank_global` — aucun des deux indexé. Endpoint ouvert aux guests (allowlist middleware) et affiché sur le Hub.
- **Constat** : 9172 lignes / 2152 kB aujourd'hui → seq scan + sort en quelques ms, non mesurable. Mais la table croît avec le catalog (1 ligne par track tendance) et l'endpoint est le plus exposé de l'app (page d'accueil, non authentifié, appelé par tous les visiteurs).
- **Recommandation** : au moment du chantier C3 (ou si `radar_trends` dépasse ~100k lignes) : index `(family, rank_in_family)` et `(rank_global)`. Optionnel aujourd'hui ; le noter dans le brief C3 suffit.
- **Dépendances** : A2-04 (les déclarer dans le modèle, pas seulement en migration)
- **Tags optionnels** : lié-chantier:C3

---

## Non couvert

- **Plans d'exécution réels** : aucun `EXPLAIN ANALYZE` n'a été exécuté sur la prod ; les qualifications d'impact perf (A2-11, A2-14) reposent sur la volumétrie et la structure des requêtes, pas sur des mesures.
- **Balayage N+1 exhaustif** : les 17 tasks Celery et les 16 routers n'ont pas tous été inspectés ligne à ligne ; l'analyse a ciblé les plus gros services (set_dedup, artist, genre, catalog, admin) après la perte des sous-agents. Un N+1 résiduel dans `workers/tasks/artists.py` (404 stmts, 3% coverage) ou `genres.py` n'est pas exclu.
- **Diff modèles ↔ DB colonne par colonne** : vérifié mécaniquement sur `sets`, `set_flags`, `watched_playlists` et les index de `radar_tracks`/`radar_trends`/`user_opinions` + politiques FK des 4 tables clés ; les ~20 autres tables n'ont été comparées que via le schema doc (lui-même périmé, cf. A2-03). Un autogenerate à blanc après A2-04 donnerait la réponse complète.
- **`is_initial_detection`** : 150 lignes `true` sur 6806 en prod — ratio non expertisé (dépend de l'historique des crawls initiaux), à survoler lors d'un audit radar fonctionnel.
