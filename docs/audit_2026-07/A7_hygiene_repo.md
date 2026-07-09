# A7 — Hygiène repo & documentation

> Audit READ-ONLY — 2026-07-09
> **Périmètre** : racine du repo, `docs/`, `_design/` (local non versionné), `scripts/`, `server/scripts/`, `server/api/scripts/`, `worker/`, `.gitignore`, README, CLAUDE.md, tout le non-code.
> **Méthode** : croisement `git ls-files` / `git log -1 --format=%as` par fichier, grep exhaustif des imports et références (tests inclus), comptages mécaniques (migrations, routers, endpoints, vues, composants) confrontés aux affirmations de CLAUDE.md, lecture des en-têtes de chaque document suspect. Base : `_inventory.md` §11.
> **Rappel d'asymétrie appliqué** : aucune suppression recommandée sans preuve d'inutilité ; le défaut est l'archivage vers `docs/completed/` ou le déplacement.

---

## Ce qui va bien

- **`docs/ROADMAP.md` est à jour** (dernier commit 2026-07-08, en-tête "Derniere mise a jour : 2026-07-07", C6.0 + C6.1 + C6.a marqués TERMINÉS dans la vue d'ensemble — cohérent avec le git log et CLAUDE.md). Les roadmaps périmées sont correctement archivées dans `docs/completed/`.
- **`docs/completed/` est bien tenu** : 30 fichiers (roadmaps archivées, prompts de chantiers terminés `PROMPT-*.md` / `*_agent_prompt.md`, notebooks d'exploration, briefs). La convention "archive FROZEN" fonctionne.
- **`tests/TESTING.md`** (2026-06-19) est un document de *standards* (patterns, fixtures, naming), pas un instantané volatile : son contenu correspond toujours aux conftest actuels (SQLite in-memory, `auth_client`/`admin_client`, mocks `sys.modules`). Rien à corriger.
- **`docs/design-audit.md`** (2026-07-08) et **`docs/detail-pages-audit.md`** (2026-07-01) ne sont PAS obsolètes : le premier alimente le chantier design-system en cours (commits 24dc6f2, 338a338e du 2026-07-08), le second est le document de référence du chantier D4, marqué "BLOQUÉ (briefs)" dans la roadmap donc toujours à venir. À archiver dans `docs/completed/` seulement à la clôture de leurs chantiers respectifs.
- **Lint propre** (ruff 0 violation) et `docs/audit_2026-07/` correctement isolé (non versionné à ce stade, visible en `??` dans git status).

---

## Findings

### [A7-01] Artefact binaire `.coverage` commité et recommité au fil des mois
- **ID** : A7-01
- **Type** : dette
- **Sévérité** : haute
- **Effort estimé** : S (< 1h)
- **Confiance** : haute
- **Preuve** : `git log -1 --format=%as -- .coverage` → **2026-07-09** (HEAD, a311e5e). `git log --oneline --follow -- .coverage` → 4 commits le modifient (dbef5d9, fa803fa, ab99c6e, a311e5e). Taille ~77 Ko (binaire SQLite). Par ailleurs `git status` montre `?? server/.coverage` (un second artefact non suivi apparaît à chaque run local). `.gitignore` ne contient aucun pattern `.coverage`.
- **Constat** : un artefact de test binaire est versionné à la racine et régénéré/recommité involontairement à chaque session de tests (4 commits, dont le HEAD du jour). Il pollue les diffs, gonfle l'historique et n'a aucune valeur versionnée. Un second `.coverage` non suivi traîne dans `server/`.
- **Recommandation** : `git rm --cached .coverage` + ajouter `.coverage` et `.coverage.*` au `.gitignore` (couvre racine et `server/`). Un seul commit, zéro risque.
- **Dépendances** : aucune
- **Tags optionnels** : QUICK-WIN-CANDIDAT

### [A7-02] `.gitignore` sans pattern pour `.tidal_tokens.json` (le fichier de tokens a été commité)
- **ID** : A7-02
- **Type** : convention
- **Sévérité** : moyenne (l'aspect sécurité — tokens réels dans l'historique — est instruit par A6)
- **Effort estimé** : S (< 1h)
- **Confiance** : haute
- **Preuve** : `server/scripts/.tidal_tokens.json` versionné, dernier commit 2026-06-19. `.gitignore` ne contient aucun pattern correspondant. Le fichier est fonctionnellement utilisé : écrit par `server/scripts/test_sources.py:87` (`TIDAL_TOKEN_FILE = Path(__file__).parent / ".tidal_tokens.json"`) et lu en fallback par `server/workers/source_clients.py:247` (`token_file = Path(__file__).parent.parent / "scripts" / ".tidal_tokens.json"`).
- **Constat** : le fichier de tokens OAuth TIDAL n'a jamais été gitignoré, ce qui explique qu'il ait fini dans l'historique. Il reste nécessaire *sur disque* (bootstrap du flow TIDAL device-auth, fallback avant Redis), donc il ne faut pas le supprimer localement — seulement le sortir du suivi git.
- **Recommandation** : ajouter `.tidal_tokens.json` (pattern global) au `.gitignore` + `git rm --cached server/scripts/.tidal_tokens.json`. La rotation des tokens et la purge d'historique relèvent de A6.
- **Dépendances** : finding A6 correspondant (rotation des tokens)
- **Tags optionnels** : QUICK-WIN-CANDIDAT | hors-domaine:securite

### [A7-03] `out/canonical_*.csv` : exports de travail commités à la racine, sans statut clair
- **ID** : A7-03
- **Type** : convention
- **Sévérité** : basse
- **Effort estimé** : S (< 1h)
- **Confiance** : moyenne (haute sur le constat, basse sur toute suppression — voir recommandation)
- **Preuve** : `out/canonical_edges.csv` et `out/canonical_nodes.csv`, dernier commit 2026-06-28. `scripts/import_taxonomy.py:4` (même date) les référence uniquement dans sa docstring d'usage : `python scripts/import_taxonomy.py out/canonical_nodes.csv out/canonical_edges.csv` — ce sont des arguments CLI, pas des chemins codés en dur. La taxonomie est déjà en base (540 `genre_nodes`, 729 `genre_edges` — inventaire §9).
- **Constat** : ces CSV sont les *données d'entrée* du one-shot d'import de la taxonomie Wikidata. L'import est fait, mais ces fichiers sont les seules données de seed permettant de reconstruire le graphe de genres sur une base vierge — ce qui aura de la valeur pour C3 (nouveaux environnements) ou un disaster recovery.
- **Recommandation** : NE PAS supprimer. Déplacer `out/*.csv` vers `scripts/data/` (à côté du script qui les consomme) et ajouter 2 lignes de docstring dans `import_taxonomy.py` expliquant leur rôle de seed. Supprimer ensuite le dossier `out/` vide et éventuellement ajouter `out/` au `.gitignore` pour les futurs exports de travail.
- **Dépendances** : aucune
- **Tags optionnels** : lié-chantier:C3

### [A7-04] README.md décrit un projet qui n'existe plus (13 mois de retard fonctionnel)
- **ID** : A7-04
- **Type** : dead-doc
- **Sévérité** : haute
- **Effort estimé** : M (1h-1j)
- **Confiance** : haute
- **Preuve** : `git log -1 --format=%as -- README.md` → **2026-06-04**. Contenu vérifié contre le disque : il documente `main.py` à la racine (**n'existe pas** : `ls main.py` → No such file) et `worker/rekordbox/extractor.py` (**n'existe pas** : `ls worker/rekordbox` → No such file) ; la section "Routes API" liste 7 endpoints (tracks/tags/health) alors que le backend en expose 99 sur 14 routers ; les secrets CI cités sont `VPS_HOST/VPS_USER/VPS_PASSWORD` alors que le deploy passe par clé SSH ; le `.env` d'exemple utilise `SECRET_KEY` alors que la stack exige `JWT_SECRET` (CLAUDE.md) ; aucune mention de Google OAuth, HTTPS, MinIO buckets, ou du flow d'import XML actuel.
- **Constat** : le README est resté figé à l'état "script d'import local" du projet. Un tiers qui clone le repo aujourd'hui suivrait des instructions cassées (`python main.py`) et des variables d'env erronées. C'est le point d'entrée du repo et le seul document "onboarding" ; à l'approche de C3 (ouverture à d'autres utilisateurs/contributeurs), c'est le document le plus rentable à réécrire.
- **Recommandation** : réécrire le README (structure actuelle, quickstart local `docker compose up` + `.env.example`, lien vers CLAUDE.md et `docs/database-schema.md`). Finding informatif : à planifier comme tâche courte dans N1 ou en préambule de C3, pas comme chantier autonome.
- **Dépendances** : aucune
- **Tags optionnels** : lié-chantier:C3

### [A7-05] CLAUDE.md : 5 compteurs faux dans la section Architecture (drift depuis "Last verified 2026-07-07")
- **ID** : A7-05
- **Type** : dead-doc
- **Sévérité** : moyenne
- **Effort estimé** : S (< 1h)
- **Confiance** : haute
- **Preuve** (comptages du 2026-07-09) :
  | Affirmation CLAUDE.md | Réalité | Commande |
  |---|---|---|
  | "Alembic (29 migrations)" | **30** (dernière `0030_set_parts.py`, 2026-07-07) | `ls server/api/alembic/versions/*.py \| wc -l` |
  | "16 routers, 93 endpoints" | **14 routers, 99 endpoints** | `ls server/api/routers/` (14 .py hors `__init__`) ; `grep -rE "@router\.(get\|post\|put\|patch\|delete)" \| wc -l` → 99 |
  | "27 classes, 10 modules" (models) | **28 classes, 11 modules** | `grep -rh "^class " server/api/models/*.py \| wc -l` |
  | "17 views (16 routed + 1 dead TagsView)" | **18 vues** (`DesignSystemView.vue` ajoutée, commit 42da943 du 2026-07-08) | `ls server/frontend/src/views/` |
  | "25 shared components" | **34 fichiers .vue** (28 top-level + 6 dans `components/admin/`) | `find server/frontend/src/components -name '*.vue' \| wc -l` |
- **Constat** : CLAUDE.md a été audité le 2026-07-07 (C6.a) mais les commits du 2026-07-08 (vitrine design-system, migration 0030 la veille) ont invalidé 5 compteurs. Conformément à la consigne du fichier lui-même ("SAY SO explicitly"), je le signale : le fichier diverge du code.
- **Recommandation** : mettre à jour les 5 compteurs + la date "Last verified". Réflexion optionnelle : remplacer les compteurs exacts par des ordres de grandeur ("~30 migrations") pour réduire la fréquence de drift.
- **Dépendances** : aucune
- **Tags optionnels** : QUICK-WIN-CANDIDAT

### [A7-06] `docs/database-schema.md` non régénéré après la migration 0030 (C6.1)
- **ID** : A7-06
- **Type** : dead-doc
- **Sévérité** : moyenne
- **Effort estimé** : S (< 1h)
- **Confiance** : haute
- **Preuve** : le doc (dernier commit 2026-07-07) annonce "25 tables" et `grep -c "part_total\|group_key" docs/database-schema.md` → **0**. Or les modèles contiennent ces colonnes : `server/api/models/sets.py:47` (`part_total = Column(Integer, nullable=True)`), `:172` (`group_key`), `:173` (`member_set_ids`) — ajoutées par `0030_set_parts.py` (commité le 2026-07-07, après la dernière génération du doc).
- **Constat** : le document auto-généré est en retard d'une migration. CLAUDE.md impose de le lire avant tout changement de modèle ou requête 3+ tables : un agent qui s'y fie ignorera les colonnes C6.1 (`part_total`, `group_key`, `member_set_ids`, `set_id_b` nullable).
- **Recommandation** : lancer `/schema_doc` (le skill existe précisément pour ça) et commiter le diff. Ajouter si possible un rappel dans le workflow de fin de chantier (`/roadmap_update`) : "migration ajoutée ⇒ `/schema_doc`".
- **Dépendances** : aucune
- **Tags optionnels** : QUICK-WIN-CANDIDAT

### [A7-07] Dossier `worker/` (singulier) + `server/deezer/` : outillage local vivant mais non documenté, avec un script probablement supersédé
- **ID** : A7-07
- **Type** : archi
- **Sévérité** : moyenne
- **Effort estimé** : M (1h-1j)
- **Confiance** : moyenne
- **Preuve** : `worker/__init__.py` et `worker/import_rekordbox.py` (dernier commit 2026-06-01), `worker/relocate_tracks.py` (2026-06-05). Grep exhaustif des imports (tests inclus) : `tests/worker/test_relocate_tracks.py:4` importe `from worker.relocate_tracks import (...)` — **tests actifs et passants**. `worker/import_rekordbox.py` n'est importé par RIEN (seule référence : sa propre docstring `python import_rekordbox.py`). `server/deezer/` (extractor.py, sync_checker.py) est importé par `tests/worker/test_check_sync.py:13` et couvert à 93% (inventaire §4). Ni `worker/` ni `server/deezer/` n'apparaissent dans l'arbre Architecture de CLAUDE.md ; le README les décrit sous une forme qui n'existe plus (`worker/rekordbox/`, cf. A7-04).
- **Constat** : ce n'est PAS du dead code à supprimer — `relocate_tracks.py` est testé et documenté dans le notebook archivé `docs/completed/rekordbox_relocate.ipynb`, et c'est de l'outillage côté PC local (cohérent avec l'invariant "Rekordbox is read-only", ces scripts tournent là où Rekordbox est installé). En revanche : (1) `import_rekordbox.py` semble supersédé par le flow d'upload XML (`routers/import_rb.py` + task Celery `import_rekordbox_xml`) ; (2) l'ensemble est invisible dans la doc d'architecture, ce qui le fait passer pour du legacy.
- **Recommandation** : (1) confirmer avec le mainteneur que `worker/import_rekordbox.py` n'est plus le chemin d'import actif ; si confirmé, le déplacer vers `docs/completed/` (valeur d'archive) plutôt que supprimer. (2) Ajouter 2 lignes dans CLAUDE.md § Architecture : "`worker/` + `server/deezer/` = outillage local côté PC Rekordbox (relocate, sync-check), hors runtime serveur". Ne PAS toucher `relocate_tracks.py` ni `server/deezer/` (tests actifs).
- **Dépendances** : A7-04 (le README réécrit devra décrire ce dossier correctement)
- **Tags optionnels** : aucun

### [A7-08] `tests/worker/test_check_sync.py` : helper mort référençant un module supprimé
- **ID** : A7-08
- **Type** : dead-code
- **Sévérité** : basse
- **Effort estimé** : S (< 1h)
- **Confiance** : haute
- **Preuve** : `worker/check_sync.py` a été supprimé du repo (commit de suppression `fcf50c8`, absent de `git ls-files worker/`). Pourtant `tests/worker/test_check_sync.py` (dernier commit 2026-06-08) définit `_run_duplicate_check()` (ligne 10) qui fait `import worker.check_sync as cs` et `patch("worker.check_sync.DeezerExtractor", ...)`. Grep dans le fichier : `_run_duplicate_check` n'est **appelé nulle part** — les 6 tests (tous passants, vérifié : `pytest tests/worker/test_check_sync.py -q` → 6 passed) n'utilisent que `_detect_duplicates()`, une réimplémentation locale (ligne 51).
- **Constat** : le test survit à la suppression du module qu'il testait uniquement parce que le helper qui l'importe n'est jamais exécuté. C'est un piège dormant : quiconque appelle `_run_duplicate_check` obtiendra un `ModuleNotFoundError`, et les tests actuels ne valident plus le vrai code (supprimé) mais une copie locale de sa logique.
- **Recommandation** : supprimer le helper mort `_run_duplicate_check` (lignes ~10-49). Décider si la logique de détection de doublons testée vit encore quelque part (dans `server/deezer/sync_checker.py` ?) — si oui, pointer les tests dessus ; si non, archiver le fichier de test avec mention dans le commit.
- **Dépendances** : A7-07 (même zone : outillage local)
- **Tags optionnels** : QUICK-WIN-CANDIDAT | hors-domaine:tests

### [A7-09] `docs/prompts`, `_design/` et `.claude/` gitignorés alors que CLAUDE.md les présente comme documentation de référence du projet
- **ID** : A7-09
- **Type** : convention
- **Sévérité** : moyenne
- **Effort estimé** : S (< 1h)
- **Confiance** : moyenne (l'intention du mainteneur peut être délibérée — machine unique)
- **Preuve** : `.gitignore` contient `_design/`, `docs/prompts` (dernière ligne, sans slash final ni newline terminale — vérifié via `od -c`) et `.claude/`. Or CLAUDE.md § Documentation Pointers exige de lire "son agent prompt dans `docs/prompts/`" avant un chantier et `_design/PAGES_REFERENCE.md` avant toute modif UI ; § Slash Commands documente `.claude/commands/` comme outillage central. `docs/prompts/` est **vide sur disque** (ls → 0 fichier) ; `_design/` contient 9 dossiers de handoff bien vivants (PAGES_REFERENCE.md, handoff-mobile, handoff-hub...).
- **Constat** : trois artefacts que CLAUDE.md traite comme documentation de référence n'existent que sur cette machine, sans versionnement ni backup. Les prompts des chantiers passés ont survécu uniquement parce qu'ils ont été copiés dans `docs/completed/` (PROMPT-A1..., C0_agent_prompt.md...). Une perte du disque local emporterait `_design/` (base des chantiers D4/R1) et les slash commands. Le pattern `docs/prompts` sans newline finale est en outre fragile (tout ajout naïf en fin de fichier fusionnerait avec la ligne).
- **Recommandation** : trancher explicitement : soit versionner `_design/` et `.claude/commands/` (recommandé — c'est de la doc projet, pas du user-local), soit corriger CLAUDE.md pour dire que ces ressources sont locales et assurer un backup hors-git. A minima : ajouter la newline finale au `.gitignore` et le slash (`docs/prompts/`).
- **Dépendances** : aucune
- **Tags optionnels** : aucun

### [A7-10] `design-decisions.md` à la racine du repo au lieu de `docs/`
- **ID** : A7-10
- **Type** : convention
- **Sévérité** : basse
- **Effort estimé** : S (< 1h)
- **Confiance** : haute
- **Preuve** : `design-decisions.md` à la racine, dernier commit 2026-07-08, 8.5 Ko. En-tête : "Ce fichier fait autorité pour la migration des échelles (commit 3). En cas de conflit avec design-audit.md, ce fichier gagne." — il est donc le compagnon direct de `docs/design-audit.md`, qui lui est dans `docs/`.
- **Constat** : document actif et utile (chantier design-system en cours), simplement mal placé : c'est le seul document de travail à la racine, et son autorité déclarée sur `docs/design-audit.md` rend la séparation des deux fichiers dans deux dossiers différents incohérente.
- **Recommandation** : déplacer vers `docs/design-decisions.md` (à côté de design-audit.md) en mettant à jour les références croisées. À la clôture du chantier design-system, archiver les deux ensemble dans `docs/completed/`.
- **Dépendances** : aucune
- **Tags optionnels** : QUICK-WIN-CANDIDAT

### [A7-11] `server/api/scripts/` : 13 scripts ops sans triage rejouable / one-shot terminé
- **ID** : A7-11
- **Type** : dette
- **Sévérité** : basse
- **Effort estimé** : S (< 1h)
- **Confiance** : moyenne
- **Preuve** : 13 scripts, aucun référencé par le code runtime, la CI ou les tâches Celery (grep sur `server/workers/`, `server/api/routers/`, `.github/` → 0 résultat). Dates de dernier commit : 9 scripts au 2026-07-01 (backfill_aliases, backfill_deezer_id, backfill_set_artworks, backfill_set_slugs, discover_trackid_sets, fetch_catalog_artworks, fix_artist_names, populate_artists, populate_has_preview), enrich_catalog_deezer et import_trackid_sets au 2026-07-06, audit_set_dedup et backfill_set_parts au 2026-07-07 (C6.1).
- **Constat** : le dossier mélange des one-shots dont la mission est accomplie (ex. `populate_has_preview.py`, `backfill_set_slugs.py`, `fix_artist_names.py` — leurs colonnes/données sont en place en prod) et des outils vraisemblablement rejouables (ex. `audit_set_dedup.py`, `discover_trackid_sets.py`, `import_trackid_sets.py`). Rien ne distingue les deux catégories ; un futur contributeur ne peut pas savoir ce qui est sûr à relancer.
- **Recommandation** : NE rien supprimer (un backfill est la seule trace exécutable de comment une donnée a été construite — valeur d'archive et de disaster-recovery). Ajouter un `server/api/scripts/README.md` de 15 lignes classant chaque script : `rejouable` / `one-shot exécuté le X (garder pour référence)`. Optionnel : sous-dossier `archive/` pour les one-shots terminés.
- **Dépendances** : aucune
- **Tags optionnels** : aucun

### [A7-12] `server/scripts/test_sources.py` : nom trompeur pour un script qui est devenu le bootstrap des tokens TIDAL
- **ID** : A7-12
- **Type** : convention
- **Sévérité** : basse
- **Effort estimé** : S (< 1h)
- **Confiance** : moyenne
- **Preuve** : docstring : "Feasibility test script for TIDAL and Spotify playlist sources. Run locally". Dernier commit 2026-06-19. Il écrit `.tidal_tokens.json` (`TIDAL_TOKEN_FILE`, ligne 87), fichier que `server/workers/source_clients.py:247` lit en fallback pour initialiser les tokens TIDAL en prod.
- **Constat** : la mission "feasibility" est terminée depuis longtemps (les sources TIDAL/Spotify sont implémentées dans `source_clients.py`), mais le script reste le seul moyen documenté de générer le fichier de tokens initial du flow OAuth device TIDAL. Son préfixe `test_` le fait passer pour un test manuel jetable et risque une suppression accidentelle ; il pourrait aussi être collecté par pytest si le dossier entrait un jour dans le rootdir de collecte.
- **Recommandation** : renommer en `bootstrap_tidal_tokens.py` (ou extraire la partie génération de tokens dans un script dédié et archiver le reste), mettre à jour la docstring pour décrire son rôle réel dans le flow TIDAL.
- **Dépendances** : A7-02 (même fichier de tokens)
- **Tags optionnels** : aucun

### [A7-13] `TagsView.vue` et `AppearRow.vue` : deux fichiers frontend à zéro référence
- **ID** : A7-13
- **Type** : dead-code
- **Sévérité** : basse
- **Effort estimé** : S (< 1h)
- **Confiance** : haute
- **Preuve** : `grep -rn "TagsView" server/frontend/src/` → **0 résultat** (même pas dans le router) ; `grep -rln "AppearRow" server/frontend/src/` → **0 résultat**. Confirmé indépendamment par l'inventaire §7. Note de cohérence documentaire : `docs/detail-pages-audit.md` liste encore `AppearRow.vue` comme composant partagé "utilisé dans toutes les pages détail" — affirmation désormais fausse.
- **Constat** : TagsView est documentée comme morte dans CLAUDE.md depuis au moins C6.a — le constat est connu mais l'action jamais faite. AppearRow est un mort plus récent (probablement orphelin depuis un refactor des pages détail) et n'est recensé nulle part. Le chantier N1 "Nettoyage résidus" existe précisément pour ça dans la roadmap.
- **Recommandation** : supprimer les deux fichiers dans le cadre de N1 (du code UI mort n'a pas de valeur d'archive : git garde l'historique). Mettre à jour CLAUDE.md ("1 dead TagsView" disparaît, cf. A7-05) et la ligne AppearRow de `detail-pages-audit.md`.
- **Dépendances** : A7-05
- **Tags optionnels** : QUICK-WIN-CANDIDAT | hors-domaine:frontend | lié-chantier:N1

---

## Non couvert

- **Contenu détaillé des 9 handoffs `_design/`** (lesquels sont périmés individuellement) : non versionnés, sans dates git exploitables ; nécessiterait une lecture exhaustive dossier par dossier avec le mainteneur. Traité globalement via A7-09.
- **`docs/similarity_calibration.ipynb`** : pointé par CLAUDE.md pour C2 ; C2 est marqué TERMINÉ (graphe D3 reporté) — un archivage vers `docs/completed/` sera pertinent à la clôture définitive, non instruit faute de certitude sur le reliquat D3.
- **`poetry.lock` vs `requirements-test.txt`** (double gestion de dépendances) : effleuré, relève de A5/CI.
- **`watched_playlists` orpheline en DB** : signalée par l'inventaire §9, du ressort de A2 (schéma).
