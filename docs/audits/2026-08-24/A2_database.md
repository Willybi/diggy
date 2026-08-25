# A2 — Database (audit global 2026-08-24)

Périmètre : `server/api/models/`, `server/api/alembic/versions/` (delta 0045→0049 prioritaire), `docs/database-schema.md`. Lecture seule, aucune connexion prod.

## Ce qui va bien

- **Piège SAEnum réellement corrigé (C7)** : `AlbumType` a bien des membres `name == value` en minuscule (`models/album.py:21-25`) et la migration 0046 crée le type PG avec les mêmes labels (`sa.Enum("album", "single", "ep", "compile", name="album_type")`, `0046_albums.py:22`). Le pitfall documenté dans CLAUDE.md est appliqué des deux côtés.
- **Invariant identité album respecté** : `_resolve_or_create_album` (`server/workers/deezer_enrich.py`) retourne `None` sans `deezer_album_id` — aucun album créé sans id fiable (invariant #4) ; `uq_albums_deezer_id` partiel est déclaré au modèle AVEC `sqlite_where` (harnais de test) ET dans la migration (`postgresql_where`), calqué sur `uq_artists_deezer_id`.
- **`track_embeddings` propre** : FK `catalog_id` couverte par la colonne de tête de `uq_track_embeddings_catalog_model` (pas d'index redondant, documenté dans le modèle) ; index HNSW migration-only bien exclu de l'autogenerate (`alembic/env.py:26-32`, `_AUTOGEN_SKIP_INDEXES`) ; `event.listen(before_create, CREATE EXTENSION …).execute_if(dialect="postgresql")` couvre TOUS les chemins `create_all` PG (`models/embedding.py:61-65`) ; extension jamais droppée au downgrade (délibéré, commenté).
- **Leçon `StringArray` appliquée à `EmbeddingVector`** : comparator explicite `cosine_distance` (`models/base.py:102-113`) au lieu de compter sur l'héritage du `TypeDecorator` — exactement le piège qui avait mordu sur `.any()`.
- **0047 sans perte + index** : backfill `item_type='track', item_id=catalog_id` avant le NOT NULL, PK surrogate via `sa.Identity` (peuple les lignes existantes), et `ix_collection_items_collection_id` recrée la couverture perdue avec l'ancienne PK composite — le résidu accepté « FK sans index `collection_items` » est de fait partiellement résorbé.
- **Nouveaux FK indexés** : `albums.artist_id` (`ix_albums_artist_id`), `catalog_albums.album_id` (`ix_catalog_albums_album_id`), `collection_folders.user_id` (`ix_collection_folders_user_id`).
- **`sets.unreliable` (0045)** : `NOT NULL` + `server_default="false"` identique modèle↔migration ; pas d'index sur le flag et c'est correct — le prédicat `unreliable IS NOT TRUE` est non sélectif (la grande majorité des sets sont fiables), un index serait ignoré.
- **Downgrades 0045, 0048, 0049 symétriques** (0049 : l'extension `vector` reste en place, documenté délibéré).
- **Schema doc à jour côté auto-généré** : `albums`, `catalog_albums`, `track_embeddings`, `collection_folders`, `folder_id`, `item_type/item_id/item_name`, `unreliable` tous présents dans `docs/database-schema.md` — la régénération C9.a a bien eu lieu.
- **Endpoint « sonne comme » borné** : `limit: int = Query(10, ge=1, le=24)` (`routers/catalog.py:138`) aligné sur `CONTENT_NEIGHBORS_MAX_CACHED = 24`, cache Redis 6h fail-open par (seed, viewer).

---

### [A2-01] `catalog_merge` ne repointe pas `catalog_albums` — liens album du perdant perdus au merge
- **Type** : bug
- **Sévérité** : moyenne
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** : `server/workers/catalog_merge.py` repointe `catalog_artists` (l.266), `user_tracks` (l.282), `user_radar_state` (l.316), `set_tracks`/`radar_tracks`/`artist_activity` (l.320-321), `user_opinions` (l.332+), `collection_items` track (l.284-287) — `grep -n "catalog_albums\|CatalogAlbum" server/workers/catalog_merge.py` ne retourne **rien**. Or `catalog_albums.catalog_id` est FK `ON DELETE CASCADE` (`models/album.py:71-73`) : le `delete` du perdant emporte ses liens album.
- **Constat** : quand `merge_catalog_entries` fusionne deux lignes catalog, les appartenances album du perdant disparaissent en CASCADE et la canonical n'est PAS reliée. Contrairement à l'embedding (drop documenté « re-embedded on the next sweep » dans CLAUDE.md/modèle), cette perte n'est documentée nulle part — ni dans le module, ni dans CLAUDE.md (qui ne mentionne que le repoint `collection_items` track). Conséquence concrète : la dé-dup reco/similarité « ≤1 titre/album » (`_load_album_map`) et l'`album_id` exposé sur `CatalogEntryOut` perdent de la couverture à chaque merge, et la canonical déjà enrichie ne sera pas re-liée par le funnel (elle ne repasse plus par la recherche Deezer).
- **Recommandation** : ajouter dans `merge_catalog_entries` un `_repoint_composite(session, CatalogAlbum, CatalogAlbum.album_id, canonical_id, loser_id)` (conflict-aware, jumeau exact du bloc `catalog_artists` — PK composite `catalog_id`+`album_id`, jamais de doublon de lien). À défaut, documenter la perte comme délibérée dans le module ET CLAUDE.md.
- **Dépendances** : aucune.
- **Tags** : —

### [A2-02] Doc schéma : MANUAL block périmé (colonnes droppées en 0044 encore documentées, note NULLS LAST promise absente, HNSW invisible) + compteur CLAUDE.md 31→32
- **Type** : doc
- **Sévérité** : basse
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** : `docs/database-schema.md:33-34` documente encore `catalog.origin` (« how the entry entered the catalog ») et `catalog.status` — colonnes **droppées par la migration 0044** (`0044_av3_perf_indexes_drop_dead_cols.py`, DROP de `origin`/`status`/`needs_reconciliation` + `sets.platform`). `grep -n "NULLS LAST\|hnsw" docs/database-schema.md` → **0 résultat** alors que CLAUDE.md (section AV3) affirme que la divergence modèle↔migration `NULLS LAST` de `ix_catalog_created_at_id` est « consignée dans le MANUAL block du schema doc ». L'index HNSW `ix_track_embeddings_hnsw` (migration-only, exclu de l'autogenerate) n'apparaît nulle part dans le doc. Enfin, CLAUDE.md (bloc Architecture) annonce « 31 mapped table classes » ; `grep -c __tablename__ server/api/models/*.py` = **32** (le doc généré dit correctement « 32 tables »).
- **Constat** : le MANUAL block est la seule partie maintenue à la main et il a dérivé sur 3 points : (1) il décrit des colonnes qui n'existent plus (un dev qui le lit avant une requête 3+ tables croit `origin`/`status` disponibles) ; (2) la note `NULLS LAST` que CLAUDE.md prétend y trouver n'y est pas — **divergence CLAUDE.md ↔ code signalée explicitement**, conformément à la consigne du fichier ; (3) les index migration-only (HNSW) sont invisibles du doc alors que c'est le document de référence pré-migration. Le compteur « 31 » de CLAUDE.md est en retard d'une table depuis C9.a.
- **Recommandation** : dans le MANUAL block — retirer les puces `catalog.origin`/`catalog.status`, ajouter une sous-section « Migration-only objects » consignant (a) la variante `NULLS LAST` prod de `ix_catalog_created_at_id` (0044) et (b) `ix_track_embeddings_hnsw` (0049, exclu autogenerate). Corriger « 31 » → « 32 » dans CLAUDE.md.
- **Dépendances** : aucune.
- **Tags** : —

### [A2-03] Downgrade 0046 asymétrique : le type PG `album_type` survit, re-upgrade cassé
- **Type** : dette
- **Sévérité** : basse
- **Effort estimé** : S
- **Confiance** : moyenne
- **Preuve** : `0046_albums.py:66-71` — le downgrade fait `op.drop_index` ×2 + `op.drop_table` ×2, aucun `DROP TYPE`. `op.drop_table("albums")` n'a pas connaissance de l'enum (appel par nom seul) → le type `album_type` créé par `sa.Enum(..., name="album_type")` à l'upgrade reste en base.
- **Constat** : après un `downgrade 0045` puis `upgrade 0046`, le `CREATE TYPE album_type` ré-émis par SQLAlchemy échoue en `DuplicateObject` sur PostgreSQL (le create inline de `op.create_table` n'est pas checkfirst). Le downgrade n'est donc pas rejouable — mineur (les downgrades ne tournent jamais en prod ici) mais c'est la seule des 5 nouvelles migrations dont l'aller-retour est cassé, et la chaîne est déjà fragile (non bootstrappable, connu).
- **Recommandation** : dans `downgrade()`, après `op.drop_table("albums")` : `sa.Enum(name="album_type").drop(op.get_bind(), checkfirst=True)`.
- **Dépendances** : aucune.
- **Tags** : —

### [A2-04] `collection_items` : dédup check-then-insert sans contrainte DB — doublons possibles sous concurrence, downgrade 0047 alors cassé
- **Type** : dette
- **Sévérité** : basse
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** : `routers/collections.py:257-267` — SELECT de dédup puis INSERT, aucune contrainte unique sur `collection_items` (`models/collection.py:49-71` : seul l'index `collection_id`, migration 0047 idem). Deux POST concurrents identiques passent tous deux le SELECT → 2 lignes. Le downgrade 0047 (`0047_collection_items_polymorphic.py:83-85`) recrée la PK composite `(collection_id, catalog_id)` : elle échouerait sur un doublon track.
- **Constat** : l'intégrité applicative « sans FK native » est délibérée (documentée, miroir `user_opinions`) — mais la **dédup** app-only, elle, n'est pas protégée par la base alors qu'elle pourrait l'être sans FK. Risque faible au volume actuel (curation mono-user, double-clic/re-submit = le scénario réel), conséquence bénigne (item affiché deux fois) sauf pour le downgrade qui devient non rejouable. Signalé comme dette S, pas comme bug.
- **Recommandation** : deux index uniques partiels (dialecte-safe, même pattern que `uq_albums_deezer_id`) : `UNIQUE (collection_id, item_type, item_id) WHERE item_id IS NOT NULL` et `UNIQUE (collection_id, item_type, item_name) WHERE item_id IS NULL` ; le router attrape `IntegrityError` → 409 (le check applicatif actuel reste comme fast-path). Nota : les résidus acceptés couvrent « FK sans index collection_items », PAS l'absence d'unicité — pas de re-signalement d'un point arbitré.
- **Dépendances** : à faire avant tout usage réel du downgrade 0047 ; indépendant du reste.
- **Tags** : —

### [A2-05] KNN « sonne comme » : recall du HNSW post-filtré non garanti (ef_search 40 vs filtres `catalog_visible` + model, et bascule seq-scan possible)
- **Type** : perf
- **Sévérité** : moyenne
- **Effort estimé** : M
- **Confiance** : moyenne
- **Preuve** : `services/similarity_service.py:1376-1389` — `ORDER BY embedding <=> seed LIMIT 24` avec JOIN `catalog` + `WHERE model_name/model_version + catalog_id != seed + catalog_visible(user_id)` (qui contient un EXISTS `user_tracks` pour un viewer authentifié). Index : HNSW pur sur `embedding` seul (0049). `CONTENT_NEIGHBORS_MAX_CACHED = 24` (l.1278) ; `hnsw.ef_search` PG par défaut = 40, `hnsw.iterative_scan` = off en pgvector 0.8.
- **Constat** : deux effets classiques du KNN filtré, aucun observé/mesuré ici (pas d'EXPLAIN prod dans cet audit, d'où confiance moyenne) : (1) **recall tronqué** — l'index scan HNSW remonte ~ef_search (40) candidats *avant* post-filtre ; chaque voisin non `catalog_visible` (ligne privée d'autrui) ou le seed consomme un slot → possiblement <24 résultats alors que des voisins visibles existent au-delà, et le manque est silencieux (le front cache juste des cartes). Aujourd'hui bénin (une seule version de modèle → filtre non sélectif ; catalogue très majoritairement `shared`) mais il se dégradera mécaniquement le jour où une **v2 du modèle coexiste** (le filtre `model_name/version` élimine ~50 % des lignes de l'index) ; (2) **choix de plan** — avec le JOIN + EXISTS, le planner peut préférer un seq-scan des embeddings (à terme ~266k × 1280 float4 ≈ 1,3 Go lus par cache-miss). Le cache 6h par (seed, viewer) amortit, mais chaque miss reste coûteux ou incomplet.
- **Recommandation** : (a) une fois le backfill avancé, `EXPLAIN (ANALYZE, BUFFERS)` de la requête réelle en prod (viewer NULL et authentifié) ; (b) si recall court : `SET LOCAL hnsw.ef_search` (p.ex. 100) ou `hnsw.iterative_scan = relaxed_order` (dispo en pgvector 0.8.0, celle du `postgres/Dockerfile`) sur cette session ; (c) consigner dans le modèle/CLAUDE.md que l'ajout d'un 2ᵉ `(model_name, model_version)` impose de re-regarder ce plan (index HNSW partiel par modèle = option). Rien à changer tant que la mesure ne le justifie pas.
- **Dépendances** : à mesurer après la fin du backfill local C9.a (couverture ~24 % au 2026-08-24, un EXPLAIN maintenant ne serait pas représentatif).
- **Tags** : —

### [A2-06] `user_collections.folder_id` : FK sans index (nouvelle, hors liste des résidus acceptés)
- **Type** : perf
- **Sévérité** : basse
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** : `models/collection.py:35-37` — `folder_id = Column(Integer, ForeignKey("collection_folders.id", ondelete="SET NULL"), nullable=True)` sans `index=True` ; migration 0048 n'en crée pas non plus (`0048_collection_folders.py:31-41`). Le `ON DELETE SET NULL` et le `delete_folder` (null explicite des membres) scannent `user_collections` par `folder_id`.
- **Constat** : même famille que les FK sans index déjà arbitrées (`artist_activity`/`user_radar_state`/`collection_items`), mais `folder_id` est postérieure à l'arbitrage donc signalée une fois pour le ledger. Volumétrie dérisoire (collections privées par user, dizaines de lignes) : aucun impact mesurable aujourd'hui.
- **Recommandation** : rien à faire maintenant ; ajouter `folder_id` à la liste « FK sans index — réévaluer à la croissance » du ledger pour qu'elle soit couverte par le même arbitrage.
- **Dépendances** : aucune.
- **Tags** : —
