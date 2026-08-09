# A7 — Hygiène repo & documentation

> Audit READ-ONLY — 2026-08-09, HEAD `9b305d6` (2026-08-08)
> **Périmètre** : CLAUDE.md (compteurs + beat table + pointeurs), README, `docs/` (ROADMAP, database-schema, completed/, audits/), `.gitignore`, scripts (`scripts/`, `server/scripts/`, `server/api/scripts/`, `worker/`), fichiers égarés.
> **Méthode** : comptages mécaniques confrontés à CHAQUE affirmation chiffrée de CLAUDE.md (`ls | wc -l`, `grep -c`, `pytest --collect-only`), diff ligne à ligne du tableau beat vs `server/workers/celery_app.py`, `git log --diff-filter` sur `docs/completed/` et sur les ajouts suspects depuis 2026-07-09, vérification de la persistance des fixes AU8 (b72d994).
> **Référence** : audit précédent `docs/audit_2026-07/A7_hygiene_repo.md` (13 findings, traités par AU8).

---

## Ce qui va bien

- **Les fixes AU8 ont tenu 164 commits.** Vérifié un par un contre l'état actuel :
  - `.coverage` absent de `git ls-files`, patterns `.coverage` / `.coverage.*` dans `.gitignore` (2026-07/A7-01 : clos, pas de récurrence).
  - `.tidal_tokens.json` gitignoré et hors suivi ; le script renommé `server/scripts/bootstrap_tidal_tokens.py` est versionné (2026-07/A7-02 + A7-12 : clos).
  - `out/*.csv` déplacés vers `scripts/data/canonical_{nodes,edges}.csv` (2026-07/A7-03 : clos).
  - README réécrit (b72d994, 2026-07-11) : stack, structure et quickstart toujours exacts à HEAD (spot-check : 2 workers Celery nommés, structure `server/api`/`workers`, `.env.example` référencé et présent) (2026-07/A7-04 : clos).
  - `design-decisions.md` déplacé dans `docs/` (2026-07/A7-10 : clos).
  - `worker/import_rekordbox.py` archivé dans `docs/completed/`, `worker/` + `server/deezer/` documentés dans CLAUDE.md comme outillage local (2026-07/A7-07 : clos).
  - `server/api/scripts/README.md` de triage rejouable/one-shot créé et même maintenu depuis (dernier commit 25243d3, 2026-08-07) — voir toutefois A7-03 ci-dessous pour 3 entrées manquantes.
- **`docs/completed/` est resté FROZEN** : `git log --since=2026-07-09 --diff-filter=M -- docs/completed/` → **0 modification**. Seuls des AJOUTS (archives design AU8 + `import_rekordbox.py`), conformes à la convention.
- **`docs/database-schema.md` est à jour à la migration près** : régénéré dans le commit E2.c même (`cce583a`, 2026-08-08). Vérifié : « 28 tables » = 28 `__tablename__` réels ; colonnes 0043 présentes (`bpm_analyzed_at` l.106, `bpm_analysis_attempts` l.107) ; table 0041 `metric_snapshots` (l.616) ; `rating` (drop 0042) : **0 occurrence**. Le pattern 2026-07/A7-06 (schéma en retard d'une migration) ne récidive pas.
- **Le tableau Celery Beat de CLAUDE.md est exact à 12/12 lignes** vs `server/workers/celery_app.py:90-179` : heures (`crontab`), queues (`task_routes` l.90-100 : `analyze_bpm_previews`/`check_followed_artists`/`link_artists_deezer`/`fetch_artist_artworks`/`enrich_catalog*` → `enrich`, reste → `celery`), `batch_size` 550 (l.129) et 2000 (l.145), fenêtres 6-23 (l.128) et 0-3 (l.144, 4 créneaux × 2000 = « ≈ 8000/nuit » ✓), `snapshot_backlogs` à :30 (l.177), modules `tasks/*` conformes.
- **La majorité des compteurs CLAUDE.md sont justes** : 43 migrations (43 fichiers dans `server/api/alembic/versions/`), 15 routers, 18 views **toutes routées** (18 imports uniques dans `server/frontend/src/router.js`), 57 composants (33 racine + 12 `filters/` + 3 `charts/` + 9 `admin/` = 48 shared + 9 admin, `AdminOverview.vue` présent), 4 stores Pinia, 2 workers Celery (`docker-compose.yml:85,117`), 12 modules models (10 domaine + base + `__init__`), 16 services tous nommés, `GET /admin/backlog` présent (`routers/admin.py:698`).
- **Pointeurs de doc : 100 % résolus.** `docs/database-schema.md`, `docs/ROADMAP.md`, `docs/restore.md`, `docs/similarity_calibration.ipynb`, `docs/audits/README.md`, `docs/audits/LEDGER.md`, `docs/e2a-benchmark/`, `docs/completed/design/`, `.env.example` : tous présents. Les 7 slash commands du tableau CLAUDE.md = exactement les 7 fichiers de `.claude/commands/`.
- **Aucun artefact égaré commité en 164 commits** : `git log --since=2026-07-09 --diff-filter=A` filtré sur csv/png/sql/dump/log/db/zip → uniquement les 4 fichiers de données de `docs/e2a-benchmark/` (36-88 Ko, livrable documenté du benchmark E2.a, pointé par CLAUDE.md et la roadmap). `git status` propre (hors `docs/audits/2026-08/` en cours).
- **`.gitignore` sain** : newline finale présente (vérifié `od -c`), `docs/prompts/` avec slash (fix A7-09 partiel), `.claude/*` + exception `!.claude/commands/` cohérente avec la décision Q5.
- **ROADMAP exacte sur les chantiers récents majeurs** : E2 TERMINE (2026-08-08), D6 TERMINE (2026-08-06), X1/X3 TERMINE (2026-07-22), X2 TERMINE (2026-08-02), D9 A FAIRE (inscrit 2026-08-07) — tous cohérents avec le git log. Exceptions D4/D7/D8 → finding A7-02.

---

## Findings

### [A7-01] CLAUDE.md « Last verified 2026-08-08 » : 4 compteurs faux ou incohérents (tasks/, composables, classes models, tests)
- **Type** : doc
- **Sévérité** : moyenne
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** (comptages du 2026-08-09 sur HEAD `9b305d6`) :
  | Affirmation CLAUDE.md | Réalité | Commande / preuve |
  |---|---|---|
  | `CLAUDE.md:60` « tasks/ # 8 modules: radar, catalog, artists, genres, import_rb, sets, trends, monitoring » | **9 modules** — `bpm.py` (E2.c) manque à la liste | `ls server/workers/tasks/` → artists, **bpm**, catalog, genres, import_rb, monitoring, radar, sets, trends. Incohérence INTERNE : le tableau beat de CLAUDE.md cite lui-même `tasks/bpm.py` |
  | `CLAUDE.md:73-75` composables = 8 noms (useInfiniteScroll … useFilterState) | **10 fichiers** — `useScrollRestore.js` (ajouté X2, c9bd8c4 2026-07-31) et `useUrlSync.js` (X2, 527d613 2026-08-01) absents | `ls server/frontend/src/composables/` → 10 .js ; `git log --diff-filter=A` sur les 2 fichiers |
  | `CLAUDE.md:25` « SQLAlchemy models (31 classes, 12 modules) » | **30** classes dans les modules domaine (28 modèles Base-derived + 2 enums `SetFlagType`/`SetFlagStatus`), ou **32** en comptant les 2 helpers de `base.py` (`array_any`, `StringArray`) — 31 ne correspond à aucun décompte | `grep -c "^class " server/api/models/*.py` : admin 2, artist 5, catalog 3, collection 2, genre 3, monitoring 1, opinion 1, radar 5, sets 7, user 1 = 30 ; base 2 |
  | `CLAUDE.md:4` « 1559 tests verts » (contexte D6.0) | **1655** tests collectés | `python -m pytest tests/ --collect-only -q` → « 1655 tests collected » (E2 a ajouté ~96 tests après la rédaction) |
  | `CLAUDE.md:34` « 15 routers, 105 endpoints » | 15 routers ✓ ; **104** décorateurs `@router.<verbe>` dans `routers/` + 1 `@app.get("/api/health")` (`main.py:120`) = 105 au total app | `grep -rEoh "@router\.(get|post|put|patch|delete|head|options)" server/api/routers/*.py | wc -l` → 104. Exact si le compte inclut `/api/health` (hors `routers/`), off-by-one sinon — à préciser plutôt qu'à corriger |
- **Constat** : le fichier annonce « Last verified: 2026-08-08 » (le jour même de HEAD) mais deux listes structurantes de l'arbre Architecture (modules `tasks/`, composables) sont en retard d'un ou deux chantiers (E2.c pour `bpm.py` — pourtant décrit ailleurs dans le même fichier ; X2 pour les 2 composables — X2 n'apparaît nulle part dans CLAUDE.md alors que `useScrollRestore` est une dépendance déclarée du chantier D9 inscrit à la roadmap). Le compteur « 31 classes » est faux quel que soit le périmètre de comptage. « 1559 tests » est un instantané D6.0 devenu faux — un chiffre volatile que la propre règle du fichier (§ Maintaining This File : « Volatile state … lives in the pointed docs ») demande de ne pas figer ici. Conformément à la consigne du fichier (« If you notice a divergence … SAY SO explicitly »), je le signale.
- **Recommandation** : corriger les 4 points : « 9 modules: … bpm, … », ajouter `useScrollRestore` + `useUrlSync` (mention X2) à la liste des composables, remplacer « 31 classes » par « 30 classes (28 modèles + 2 enums) » (ou le périmètre choisi, explicité), remplacer « 1559 tests verts » par une formulation non chiffrée (« suite verte ») ou déplacer le chiffre. Optionnel : préciser « 105 endpoints (104 routers + /api/health) ».
- **Dépendances** : récurrence du pattern 2026-07/A7-05 (compteurs CLAUDE.md) — les valeurs d'alors avaient été corrigées par AU8, ce sont de NOUVEAUX drifts (E2.c/X2). La réflexion « ordres de grandeur plutôt que compteurs exacts » proposée en 2026-07 n'a pas été tranchée et reste pertinente.
- **Tags** : QW-c

### [A7-02] ROADMAP : D4 « EN COURS » et D7 « A FAIRE » alors que D4-Admin (Vague 5) + D7 sont livrés depuis 2026-08-08
- **Type** : doc
- **Sévérité** : moyenne
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** :
  - `docs/ROADMAP.md:57` (vue d'ensemble) : « D4 … EN COURS — Track + Playlist + Set + Artist Detail TERMINES (2026-07-20) ; reste Admin Vague 5 (build avance …) » ; `docs/ROADMAP.md:70` : « D7 Admin mobile Flags + Lier (design) … A FAIRE — polish mobile Flags + bloc "Lier" … ».
  - Statut détaillé de la section D4 (`docs/ROADMAP.md:1033`) encore plus daté : « EN COURS — page 1 (Track Detail) TERMINEE (2026-07-17, commit 0c47a8c …) ».
  - Or le git log montre la livraison : `12b7b87` 2026-08-07 « feat(admin): onglet Aperçu (backlog) + badges + finition responsive mobile », `d212522` 2026-08-07, `667ceed` 2026-08-08 « fix(admin): revue design Aperçu … » — soit exactement « Admin Vague 5 » + le périmètre D7 (absorbé, sous-ensemble strict, cf. mémoire projet « D4 Admin (Vague 5) + D7 ✅ TERMINÉ 2026-08-08 »).
  - Le DERNIER commit de la roadmap (`9b305d6`, 2026-08-08, clôture E2) est POSTÉRIEUR à ces livraisons mais n'a pas touché D4/D7 ; l'en-tête « Derniere mise a jour : 2026-08-07 » (`docs/ROADMAP.md:12`) n'a pas non plus été daté au 08.
  - Point connexe : `docs/ROADMAP.md:71` « D8 … A FAIRE — inscrit 2026-08-03 » alors que le sous-lot D8.b est coché livré (`docs/ROADMAP.md:1633` « [x] Genre Detail : tracklist → APERCU BORNE … », commit `3574e1d` 2026-08-04) — la ligne de la vue d'ensemble ne mentionne pas ce partiel.
- **Constat** : `/roadmap_update` n'a pas été passé après la clôture D4-Admin/D7 (seule celle d'E2 l'a été). Conséquence concrète : `/roadmap_status` recommandera « finir D4 » et considérera D7 comme un chantier disponible, alors que les deux sont livrés et en revue design soldée. C'est la doc de pilotage du projet : son exactitude conditionne le choix du prochain chantier.
- **Recommandation** : lancer `/roadmap_update` (la commande existe pour ça) en croisant avec les commits `12b7b87`/`d212522`/`667ceed` : D4 → TERMINE (2026-08-08), D7 → TERMINE-ABSORBÉ par D4 Vague 5 (garder la trace de l'absorption), ligne D8 de la vue d'ensemble → « A FAIRE (D8.b livré 2026-08-04 avec Genre Detail) », en-tête « Derniere mise a jour » redaté.
- **Dépendances** : aucune
- **Tags** : QW-c

### [A7-03] `server/api/scripts/README.md` : 3 scripts absents du triage rejouable/one-shot (dedup_catalog, reverify_platform_ids, dedup_artists_deezer)
- **Type** : doc
- **Sévérité** : basse
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** : `grep -c "dedup_catalog\|reverify_platform_ids\|dedup_artists_deezer" server/api/scripts/README.md` → **0**. Les 3 fichiers existent : `dedup_catalog.py` (ajouté `6735ef9`, 2026-07-22, X1), `reverify_platform_ids.py` (`67b2ef3`, 2026-07-22, X3), `dedup_artists_deezer.py` (`fdcc957`, 2026-07-24, dédup artistes). Le README a pourtant été maintenu APRÈS ces ajouts : dernier commit `25243d3` (2026-08-07), qui a ajouté la ligne `rescore_set_flags.py`. Inventaire README = 15 scripts, répertoire = 18.
- **Constat** : récurrence PARTIELLE de 2026-07/A7-11 — le fix AU8 (README de triage) est en place et vivant, mais la discipline « nouveau script ⇒ ligne d'inventaire » a sauté pour les 3 scripts des chantiers X1/X3/dédup-artistes. Ce sont précisément les scripts les plus sensibles du dossier (fusions destructives dry-run/`--apply`, exécutés en prod) : un futur contributeur ne peut pas savoir depuis le README lesquels sont des one-shots déjà passés (`dedup_artists_deezer` : backfill exécuté, les orphelins courants sont gérés par la tâche nightly depuis) et lesquels restent des outils OPS rejouables (`dedup_catalog`, `reverify_platform_ids` — CLAUDE.md les décrit comme « cleanups for pre-X3 rows », rejouables par construction `same_track`).
- **Recommandation** : ajouter 3 lignes à l'inventaire : `dedup_catalog.py` (rejouable — fusion des VRAIS doublons, clustering `same_track`, appliqué 2026-07-22 : 588 fusions), `reverify_platform_ids.py` (rejouable — reset des ids pré-X3 partagés, appliqué 2026-07-22, patché 5de55a1 pour `has_preview`), `dedup_artists_deezer.py` (one-shot — exécuté ~2026-07-24, backfill des orphelins accent/Unicode, le fil de l'eau est couvert par `link_artists_deezer`).
- **Dépendances** : clé d'origine 2026-07/A7-11 (récurrence partielle du même mécanisme, pas du même contenu)
- **Tags** : —

### [A7-04] CLAUDE.md référence les scripts OPS sous `scripts/…` alors qu'un AUTRE dossier `scripts/` existe à la racine du repo
- **Type** : doc
- **Sévérité** : basse
- **Effort estimé** : S
- **Confiance** : haute (sur le fait) / moyenne (sur la gêne réelle)
- **Preuve** : CLAUDE.md cite « `scripts/reverify_platform_ids.py` », « `scripts/dedup_catalog.py` », « `scripts/dedup_artists_deezer.py` » (lignes 4, 89, 182). Ces fichiers vivent dans **`server/api/scripts/`**. Or `scripts/` à la racine du repo EXISTE et contient autre chose (`import_taxonomy.py`, `data/canonical_*.csv` — créé par le fix AU8 de 2026-07/A7-03). La notation `scripts/…` correspond au chemin EN CONTENEUR (`docker compose exec api python scripts/<nom>.py`, WORKDIR = `api/`, documenté dans `server/api/scripts/README.md:7`), pas au chemin repo.
- **Constat** : depuis AU8 il y a collision de nommage : un agent (ou un humain) qui lit CLAUDE.md et cherche `scripts/dedup_catalog.py` tombe sur le mauvais dossier racine et conclut à un fichier manquant. L'ambiguïté est née de la coexistence des deux conventions (chemin conteneur dans CLAUDE.md, dossier `scripts/` racine créé après coup).
- **Recommandation** : dans CLAUDE.md, écrire les chemins repo complets (`server/api/scripts/…`) ou ajouter une note unique (« les scripts OPS cités `scripts/…` = `server/api/scripts/` vus du conteneur api »). Ne rien déplacer sur disque.
- **Dépendances** : A7-01 (même passe d'édition de CLAUDE.md)
- **Tags** : —

---

## Hypothèses réfutées

- **« Des artefacts binaires ont dû revenir en 164 commits » — NON.** `git ls-files` sur `.coverage|tokens|csv|png|sql|dump|log|sqlite|zip` → uniquement les livrables documentés (`docs/e2a-benchmark/`, `scripts/data/`). Les fixes .gitignore d'AU8 tiennent ; aucun pattern manquant révélé par l'historique récent.
- **« docs/completed/ a probablement été retouché pendant la refonte UI » — NON.** `--diff-filter=M` vide depuis 2026-07-09 ; uniquement des ajouts d'archives (AU8). La convention frozen est respectée.
- **« database-schema.md est sûrement en retard sur 0042/0043 » (pattern 2026-07/A7-06) — NON.** Régénéré dans le commit même de la migration 0043 (`cce583a`) ; `rating` absent, colonnes E2.c et `metric_snapshots` présentes, « 28 tables » exact.
- **« Le tableau beat de CLAUDE.md a dû dériver avec E2.c/MON » — NON.** 12/12 lignes conformes à `celery_app.py` (heures, queues, batch, modules), y compris la nouvelle ligne `analyze_bpm_previews`.
- **« Les vues ne sont peut-être pas toutes routées » — NON.** Les 18 fichiers de `views/` apparaissent tous dans `server/frontend/src/router.js`.
- **Observations sans finding** : (1) `node_modules/` à la racine du repo (local, non versionné, gitignoré) ne contient qu'un cache `.vite` de 8 Ko — bruit local sans enjeu, supprimable à l'occasion. (2) `docs/audits/LEDGER.md` est encore à l'état d'amorçage (« vide — amorçage au premier run ») : c'est le travail de la Phase 4 de CE cycle d'audit, pas un finding. (3) La ligne « Dernier audit complet » de `docs/audits/README.md` pointe 2026-07 : mise à jour prévue en Phase 4, hors périmètre.
