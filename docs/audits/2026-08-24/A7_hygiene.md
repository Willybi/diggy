# A7 — Hygiène repo/doc (audit 2026-08-24)

> Agent A7, lecture seule. HEAD au moment de l'audit : `52a506f` (C9.b LIVRÉ en roadmap).
> Méthode : recomptage mécanique (Glob/grep) de chaque compteur de CLAUDE.md + vérification d'existence
> des docs pointées + inspection des deux répertoires scripts + fraîcheur schema doc + cohérence LEDGER.

## Ce qui va bien

- **La majorité des compteurs CLAUDE.md sont justes** : 16 routers (`ls server/api/routers/*.py` hors `__init__` = 16), 19 vues (`ls server/frontend/src/views/*.vue` = 19), 63 composants dont 9 admin → 54 partagés (find `components/**/*.vue` = 63, `admin/` = 9), 11 composables (liste exacte, `useOpinionOneShot` inclus), 10 modules `tasks/` (hors `__init__`), 49 migrations (`ls server/api/alembic/versions/*.py` = 49), 4 helpers array/type dans `base.py` (`array_any`/`array_is_empty`/`StringArray`/`EmbeddingVector`), 3 str-enums. Seuls 3 compteurs ont drifté (A7-01).
- **`docs/database-schema.md` est frais** : dernière régénération `ba7aabb` (2026-08-22, C9.a) ; l'unique modification de `models/` depuis (`d3dad75`, comparator `cosine_distance` sur `EmbeddingVector` dans `base.py`) est un opérateur de requête sans impact schéma. `track_embeddings` y est présent (ligne 174) et groupé « Catalog hub » (ligne 69) comme annoncé.
- **`docs/audits/LEDGER.md` est cohérent** : amorçage documenté en tête, chaque ligne 2026-07/2026-08 porte statut + commit de résolution + « Dernière vue » ; les fusions M1-M6 sont explicitées. Rien d'incohérent relevé ligne à ligne sur les statuts CORRIGÉ/OUVERT/ACCEPTÉ.
- **`docs/c9-benchmark/` est bien tenu malgré 1,4 Go local** : un `.gitignore` local fait que seuls ~1,2 Mo de rapports/CSV/scripts sont trackés (`git ls-files docs/c9-benchmark/` : 15 fichiers, max 652 Ko) — les `.npz`/`build.log`/images Docker restent hors git.
- **Les docs pointées par « Documentation Pointers » existent** : `docs/database-schema.md`, `docs/ROADMAP.md`, `docs/similarity_calibration.ipynb`, `docs/verif-visuelle-locale.md`, `docs/restore.md`, `docs/completed/design/`, `docs/audits/README.md` + `LEDGER.md`, `docs/audit_2026-07/` (chemin historique assumé).
- **`.gitignore` couvre les vrais risques** : `.env`, `.tidal_tokens.json` (avec commentaire de contexte), `dist/`, coverage, `.claude/*` avec exception `!.claude/commands/` — et `git ls-files .claude` confirme que seules les 11 commandes sont versionnées, conforme à CLAUDE.md.
- **Le README de triage des scripts a un bon squelette** : statuts « rejouable » / « one-shot — exécuté » définis, convention de datation explicite — le mécanisme est sain, c'est son remplissage qui a redrifté (A7-03).

## Findings

### [A7-01] Compteurs CLAUDE.md driftés : 106 endpoints (pas 105), 32 tables mappées (pas 31), 39 class defs (pas 38), 18 services (pas 17)
- **Type** : doc
- **Sévérité** : moyenne
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** :
  - Endpoints : `grep -rEc "@router\.(get|post|patch|delete|put)" server/api/routers/*.py` → somme = **106** ; CLAUDE.md:39 dit « 16 routers, 105 endpoints ». Le +1 = `GET /{catalog_id}/content-similar` (`server/api/routers/catalog.py:135`, commit `d3dad75` du 2026-08-24).
  - Tables : `grep -c "__tablename__" server/api/models/*.py` → **32** ; CLAUDE.md:25 dit « 31 mapped table classes ». Le +1 = `track_embeddings` (`models/embedding.py:29`) — le module embedding EST cité dans le même bloc mais le compteur n'a pas été bumpé.
  - Class defs : `grep -c "^class " server/api/models/*.py` → **39** (32 tables + 3 enums + 4 helpers) ; CLAUDE.md:26 dit « = 38 class defs ».
  - Services : `ls server/api/services/*.py` hors `__init__` = **18** (dont `album_service.py`, C7) ; la ligne 4 de CLAUDE.md (narratif AV7) dit « services **17** (liste complète) ». La liste du bloc Architecture est à jour (18 noms, `album_service` inclus) — seul le compteur narratif est daté.
- **Constat** : 3e récurrence du pattern « compteurs qui driftent » (2026-07/A7-05 → 2026-08/A7-01, corrigé AV7 le 2026-08-16, redrifté par C7/C9.a/C9.b en 8 jours). Les compteurs de la section Architecture sont l'entrée de navigation des agents ; un chiffre faux fait perdre du temps de vérification à chaque session.
- **Recommandation** : bumper les 3 compteurs du bloc Architecture (105→106, 31→32, 38→39) ; ne pas toucher le narratif « Prior AV7 » (instantané historique exact à sa date). Envisager d'ajouter aux checklists de clôture de chantier (`/roadmap_update` ou `/commit`) un rappel « un fichier routers/models/services/views ajouté → bumper le compteur CLAUDE.md ».
- **Dépendances** : lié à A7-02 (même cause : C9.b livré après la mise à jour CLAUDE.md du jour).
- **Tags** : QW-c

### [A7-02] CLAUDE.md dit « C9.b/c, not built yet » alors que C9.b est LIVRÉ le même jour que le « Last verified »
- **Type** : doc
- **Sévérité** : basse
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** : CLAUDE.md:120 : « stores per-track content embeddings for the "sonne comme"/hybrid reco (**C9.b/c, not built yet**) ». Or `git log` : `d3dad75` (2026-08-24 19:03, endpoint back), `45e4559` (19:35, shelf front admin-gated), `52a506f` (« docs(roadmap): C9.b A FAIRE → LIVRE admin-only »). Le « Last verified: 2026-08-24 » de l'en-tête (ligne 3) couvre C9.a mais pas ces 3 commits postérieurs du même jour.
- **Constat** : la ligne « Audio embeddings » du bloc Database et le paragraphe d'en-tête décrivent un état pré-C9.b : l'endpoint `GET /api/catalog/{id}/content-similar` (voisins par contenu, `similarity_service.get_content_neighbors`) et la shelf « sonne comme » de Track Detail (gatée admin) existent et contredisent « not built yet ». La roadmap dit LIVRÉ ; CLAUDE.md dit pas construit — divergence doc↔code que CLAUDE.md lui-même demande de signaler.
- **Recommandation** : remplacer « C9.b/c, not built yet » par l'état réel (C9.b livré admin-only : endpoint `content-similar` + shelf Track Detail ; C9.c hybrid reco pas construit) et compléter le paragraphe d'en-tête C9.a d'une phrase C9.b, ou re-stamper « Last verified » après l'avoir fait.
- **Dépendances** : à faire en même temps que A7-01 (même passe d'édition CLAUDE.md).
- **Tags** : QW-c

### [A7-03] README de triage des scripts OPS : 8 scripts absents de l'inventaire (3e récurrence)
- **Type** : doc
- **Sévérité** : basse
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** : `server/api/scripts/` contient 26 scripts ; le tableau « Inventaire » de `server/api/scripts/README.md` (18 lignes, dernier commit `a09fafd` 2026-08-09) omet : `resync_catalog_artist.py` + `backfill_catalog_artists.py` (X4, `fedfee5` 2026-08-12), `cleanup_artists.py` (N3, `52544b6` 2026-08-15), `backfill_set_reliability.py` (C8, `3491d68` 2026-08-18), `backfill_albums.py` (C7, `5e6262c` 2026-08-20), `cleanup_orphan_artists.py` (`0174825` 2026-08-23), `backfill_artist_flags.py` (`e2fd75d` 2026-08-24), `cleanup_placeholder_artists.py` (`ef3afd2` 2026-08-24).
- **Constat** : 3e audit consécutif où le README de triage est en retard sur le répertoire (2026-07/A7-11 → 2026-08/A7-03, corrigé AV1 le 2026-08-09 — puis 8 scripts ajoutés en 15 jours sans ligne d'inventaire). Ce README est ce qui distingue un script rejouable d'un one-shot exécuté : un opérateur qui ne l'y trouve pas doit relire la docstring et l'historique git pour savoir s'il peut relancer.
- **Recommandation** : ajouter les 8 lignes (statut : tous rejouables dry-run/`--apply` d'après CLAUDE.md, sauf à vérifier `backfill_artist_flags`/`cleanup_placeholder_artists`, non documentés ailleurs) ; comme pour A7-01, accrocher la mise à jour du README au moment où un chantier crée un script (le `/work_manager` pourrait le porter en checklist de clôture).
- **Dépendances** : aucune.
- **Tags** : QW-c

### [A7-04] Fichiers/répertoires égarés non trackés : `docs/c9-benchmark;C` (vide), `node_modules/` à la racine, `__pycache__` racine et docs/
- **Type** : mort
- **Sévérité** : basse
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** :
  - `ls -la "docs/c9-benchmark;C"` → répertoire **vide**, créé le 2026-08-22 02:52 (nuit du benchmark C9) ; `git ls-files "docs/c9-benchmark;C*"` → rien (non tracké). Nom = artefact d'une commande mal échappée (suffixe `;C`).
  - `node_modules/` à la racine du repo : 8 Ko, 0 entrée visible, **aucun `package.json` racine** (le front vit dans `server/frontend/`) — résidu d'un `npm install` lancé du mauvais cwd ; couvert par `.gitignore` mais prête à confusion.
  - `__pycache__/` à la racine et dans `docs/` (exécutions locales de scripts) — ignorés par `.gitignore`, cosmétique.
- **Constat** : rien n'est tracké (le `.gitignore` fait son travail), mais `docs/c9-benchmark;C` en particulier est un piège : il apparaît dans tout listing de `docs/` et peut être pris pour un vrai répertoire de benchmark par un agent ou un glob.
- **Recommandation** : supprimer `docs/c9-benchmark;C`, `node_modules/` racine et les `__pycache__` hors packages (`rmdir "docs/c9-benchmark;C"` ; `Remove-Item -Recurse node_modules` à la racine). Aucune écriture git nécessaire.
- **Dépendances** : aucune.
- **Tags** : QW-c

### [A7-05] `docs/prompts/` est gitignoré mais pointé comme doc de référence par CLAUDE.md
- **Type** : doc
- **Sévérité** : basse
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** : `.gitignore` racine contient la ligne `docs/prompts/` ; la table « Documentation Pointers » de CLAUDE.md dit « Starting work on a chantier → Its agent prompt in `docs/prompts/` … If none exist yet for the target chantier, create them via `/work_manager` ». Le répertoire existe localement (7 fichiers : `C9_benchmark_protocol_v2.md`, `explorer-lot*.md`) mais `git ls-files docs/prompts/` est vide.
- **Constat** : les prompts de chantier sont désignés comme artefact à lire en début de chantier, mais ne survivent ni à un clone ni à une perte de la machine — alors que les prompts HISTORIQUES, eux, sont archivés versionnés dans `docs/completed/` (ex. `C0_agent_prompt.md`). L'intention (volatile vs archivé) n'est écrite nulle part ; un agent sur un checkout frais suivra un pointeur vers un répertoire absent.
- **Recommandation** : trancher et documenter — soit retirer `docs/prompts/` du `.gitignore` (les prompts actifs se committent, comme les commandes `.claude/commands/`), soit annoter la ligne de la table Documentation Pointers (« local, non versionné — archivé dans `docs/completed/` en clôture ») et le `.gitignore` d'un commentaire.
- **Dépendances** : aucune.
- **Tags** : —

### [A7-06] `docs/restore.md` antérieur à pgvector : un restore sur un postgres vanilla échoue, rien ne le dit
- **Type** : doc
- **Sévérité** : moyenne
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** : `grep -n postgres docs/restore.md` → la procédure installe `postgresql16-client` et restaure vers le conteneur `postgres` courant ; **aucune occurrence de `pgvector`, `vector` ou de l'image custom** `postgres/Dockerfile` (`diggy-postgres:16-pgvector`, C9.a, `ba7aabb` 2026-08-22). « Dernier test réussi : **2026-07-10** » (restore.md:229) — antérieur de 6 semaines au changement d'image.
- **Constat** : depuis la migration 0049, tout dump prod contient `CREATE EXTENSION vector` + des colonnes de type `vector(1280)`. La procédure telle qu'écrite marche tant qu'on restaure DANS le conteneur prod actuel (l'extension y est), mais le scénario que ce doc couvre — reconstruire ailleurs après un incident — échouera sur une image `postgres:16-alpine` stock, et le doc ne mentionne pas la dépendance. Le « last tested » honore la consigne d'honnêteté mais valide un chemin qui n'existe plus tel quel.
- **Recommandation** : ajouter à restore.md un prérequis explicite « la cible doit être l'image custom `postgres/Dockerfile` (pgvector) — un `postgres:16` stock rejettera le dump » + re-jouer le test de restore post-C9.a et re-stamper la date.
- **Dépendances** : aucune (indépendant du deploy C9.a restant).
- **Tags** : QW-c

## Observations (hors findings)

- **Action de clôture d'audit (pas un finding)** : `docs/audits/README.md:21` dit « Dernier audit complet : `docs/audits/2026-08/` » — à pointer vers `2026-08-24/` en Phase 4 de cet audit, comme le README le prescrit lui-même.
- **Fiche mémoire périmée** : `~/.claude/.../memory/av9-suivi-post-deploy.md` dit « reste seulement à cocher AV9-03 dans ROADMAP via /roadmap_update » et « une fois coché, SUPPRIMER cette mémoire » — or `84ae4f6` (2026-08-18) a fait ce passage AV9-03 A FAIRE → TERMINE. La fiche demande sa propre suppression ; à faire au prochain passage mémoire.
- **Troisième répertoire `scripts/`** : la désambiguïsation AV7 de CLAUDE.md couvre `server/api/scripts/` (OPS data) vs `server/scripts/` (build/ops), mais il existe aussi `scripts/` à la RACINE (tracké : `import_taxonomy.py` + `data/canonical_{nodes,edges}.csv`). Légitime (import taxonomy), mais absent de la phrase de désambiguïsation — une ligne à y ajouter éviterait la même confusion que celle qui a motivé 2026-08/A7-04.
- **Narratifs historiques** : les « 17 services », « endpoints 99 », « composants 61 » de la ligne 4 de CLAUDE.md sont des instantanés datés (AV7) exacts à leur date — non comptés comme drift (seuls les compteurs du bloc Architecture, vivants, le sont ; cf. A7-01).
