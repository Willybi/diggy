---
description: Audit global de santé du code — dette, sécurité, perfs, code mort — rapport daté, ledger inter-audits, proposition roadmap
allowed-tools: Read, Glob, Grep, Write, Task, Agent, Bash(git log:*), Bash(git diff:*), Bash(git shortlog:*), Bash(ruff check:*), Bash(vulture:*), Bash(deptry:*), Bash(pip-audit:*), Bash(npm audit:*), Bash(npm outdated:*)
argument-hint: [périmètre : vide = complet | incremental | dimension(s) ciblée(s), ex. securite frontend]
---

Tu pilotes un audit global de santé du code Diggy. Périmètre demandé : $ARGUMENTS (vide = audit complet).

Modèle éprouvé : `docs/audit_2026-07/` (Phase 0 inventaire outillé → agents par dimension → CONSOLIDATED → DECISIONS → série AU roadmap). Tu reproduis ce pipeline en y ajoutant le suivi inter-audits. Le fonctionnement du système (taxonomie, statuts, cadence) est documenté dans `docs/audits/README.md` — lis-le d'abord.

## Règles non négociables

- **AUCUNE modification de code.** Tu n'écris QUE sous `docs/audits/<AAAA-MM>/`, `docs/audits/LEDGER.md`, et la ligne « Dernier audit complet » de `docs/audits/README.md` (en Phase 4). Aucun commit (tu proposes le message à la fin, c'est moi qui committe). **Collision de mois** : si `docs/audits/<AAAA-MM>/` existe déjà (2ᵉ audit le même mois), suffixe le jour — dossier `docs/audits/<AAAA-MM-JJ>/` et clés de finding `<AAAA-MM-JJ>/Ax-nn` (précédent : `2026-08-24/`).
- **Un finding sans preuve n'existe pas** : fichier:ligne, ou commande + sortie. Pas d'« il semble que ».
- **Ne re-signale JAMAIS un résidu accepté** : décisions des DECISIONS.md précédents, statuts ACCEPTÉ du ledger, résidus documentés dans CLAUDE.md (ex. `/storage` non authentifié, endpoints taxonomy réservés, absence délibérée d'index unique sur les ids plateforme, chaîne Alembic non bootstrappable, dev local full-stack non supporté). Si le contexte a matériellement changé, tu peux le remonter, mais explicitement marqué **RÉÉVALUATION** avec ce qui a changé.
- **Les sorties d'outils sont des CANDIDATS, pas des findings.** Faux positifs structurels connus : vulture sur colonnes SQLAlchemy, endpoints FastAPI, `health` (healthcheck Docker), `GenreNode` (SQL brut) ; deptry DEP001 sur packages locaux, DEP002 sur `asyncpg`/`uvicorn`. Chaque candidat se vérifie par lecture du code avant d'être retenu.
- Respecte les invariants Data Authority et les pièges connus de CLAUDE.md : un audit qui recommande de les violer est un audit raté.

## Phase 0 — Cadrage & inventaire outillé

1. Lis `docs/audits/README.md`, `docs/audits/LEDGER.md`, puis le CONSOLIDATED.md et le DECISIONS.md de l'audit précédent (chemin indiqué dans le README ; premier audit historique : `docs/audit_2026-07/`).
2. Borne le delta : le rapport précédent note le commit HEAD audité → `git log --oneline <commit>..HEAD` + `git diff --stat <commit>..HEAD`. C'est la carte des zones neuves (à auditer en priorité) et le périmètre exact du mode `incremental`.
3. Inventaire mécanique (signaux pas chers, consignés bruts) :
   - `ruff check server/ --statistics`
   - `vulture server/ --min-confidence 60` (hors alembic)
   - `deptry` si installé ; pip-audit : sur cette machine Windows le binaire est absent et le pin `essentia` (wheel Linux-only) casse la résolution → `python -m pip_audit -r <copie de requirements.txt SANS la ligne essentia> --no-deps --ignore-vuln PYSEC-2025-185 --ignore-vuln PYSEC-2026-1325` (le gate CI reste la référence ; le run local est un signal)
   - depuis `server/frontend` (cd dans son PROPRE appel Bash, jamais inline) : `npm audit`, `npm outdated`
   - grep `TODO|FIXME|XXX|HACK` sur `server/`
   - top fichiers par LOC et par churn (`git log --since="6 months ago" --name-only`)
4. Crée `docs/audits/<AAAA-MM>/` (ou `<AAAA-MM-JJ>/` en cas de collision de mois, cf. règles) et écris `_inventory.md` avec l'avertissement CANDIDATS en tête (modèle : `docs/audit_2026-07/_inventory.md`).

En mode `incremental`, le périmètre des phases suivantes = fichiers touchés depuis le dernier audit + leurs consommateurs directs (imports/appels, via Grep) ; les dimensions non concernées sont sautées et le rapport le dit explicitement.

## Phase 1 — Fan-out agents (parallèle, lecture seule)

Lance EN PARALLÈLE (un seul message, plusieurs appels) un agent par dimension retenue :

| ID | Dimension | Périmètre & angles spécifiques Diggy |
|---|---|---|
| A1 | Backend | `server/api/` hors alembic : routers minces (logique en service), pagination/tri déterministes, gestion d'erreurs homogène, endpoints morts (croiser frontend + workers + scripts + tests), response_model, N+1 |
| A2 | Database | modèles, migrations, `docs/database-schema.md` : colonnes/tables mortes, index manquants (FK, requêtes chaudes), doc vs modèles, downgrades symétriques, invariants dedup |
| A3 | Workers | `server/workers/` : pattern lock Redis (SET NX EX, TTL > time_limit), pièges autoretry, budgets/caps, idempotence, chord vs result.get, cadence slack, routing queues |
| A4 | Frontend | `server/frontend/src/` : composants/exports morts, zéro couleur hardcodée (tokens), composables sanctionnés (pas de fetch offset maison ni setInterval), duplication entre vues, container queries |
| A5 | Infra/CI | Dockerfiles, compose, nginx, `.github/` : dockerignore par contexte, pièges nginx (add_header), gates CI réels (pas de no-op), backups (cron vivant, offsite, date du dernier test de restore honnête dans `docs/restore.md`) |
| A6 | Sécurité & tests | auth/authz (`catalog_visible` sur TOUT read path catalog), injection, secrets repo/historique, rate limiting, deps vulnérables ; trous de couverture sur chemins critiques, fausse couverture (tests qui testent une copie) |
| A7 | Hygiène repo/doc | CLAUDE.md vs code (compteurs, chemins, conventions), docs pointées existantes, fichiers égarés, .gitignore, scripts morts |
| A8 | Invariants projet | passe mécanique greppable : chaque invariant/pitfall listé dans CLAUDE.md → vérifié un par un, verdict TENU / VIOLÉ (preuve) / INVÉRIFIABLE |

Chaque prompt d'agent est AUTONOME et contient :
1. le périmètre exact (chemins) et les angles de sa ligne du tableau ;
2. les extraits pertinents de `_inventory.md` (ses candidats à vérifier) ;
3. la liste des résidus acceptés à ne PAS re-signaler (extraite du ledger + CLAUDE.md) ;
4. l'obligation d'ouvrir son rapport par une section **« Ce qui va bien »** (points vérifiés conformes, pour éviter les faux findings des audits suivants) ;
5. le format de finding OBLIGATOIRE :

   ```
   ### [Ax-nn] Titre court
   - **Type** : bug | archi | dette | perf | sécu | mort | doc | test
   - **Sévérité** : critique | haute | moyenne | basse
   - **Effort estimé** : S | M | L
   - **Confiance** : haute | moyenne | basse
   - **Preuve** : fichier:ligne + extrait, ou commande + sortie
   - **Constat** : ce qui est cassé/risqué et pourquoi c'est un problème ICI
   - **Recommandation** : le fix proposé, sans l'exécuter
   - **Dépendances** : autres findings liés, ordre imposé
   - **Tags** : QW-c si impact haute|critique × effort S × risque faible
   ```
6. l'instruction d'ÉCRIRE lui-même son rapport à `docs/audits/<AAAA-MM>/Ax_<dimension>.md` (seul fichier qu'il a le droit d'écrire, aucune autre modification), et de ne retourner en réponse QUE le tableau récapitulatif `ID | Titre | Sévérité | Effort | Confiance`.

## Phase 2 — Consolidation

1. Lis les rapports A*.md. Dédoublonne et fusionne (l'ID retenu = le premier, conserver TOUTES les preuves).
2. **Contre-vérifie toi-même, ligne à ligne, la preuve de TOUS les findings critique/haute** et un sondage des moyennes. Ce qui ne tient pas est rejeté et documenté (section « Rejets motivés » — même discipline que le work_manager : jamais sur parole).
3. Croise avec `docs/audits/LEDGER.md` : un finding déjà connu garde sa clé d'origine (`<AAAA-MM>/Ax-nn` du premier audit qui l'a vu) — une récurrence est un signal AGGRAVANT à dire ; les nouveaux prennent la clé de cet audit.
4. Écris `CONSOLIDATED.md` (modèle : `docs/audit_2026-07/CONSOLIDATED.md`) : synthèse chiffrée par dimension × sévérité, top 5 par impact, **delta vs audit précédent** (corrigés depuis / persistants / nouveaux / régressions), hypothèses réfutées, graphe de dépendances, matrice de priorisation — règle QUICK WIN = impact haute|critique × effort S.

## Phase 3 — Arbitrage (STOP)

Formule les questions de décision Q1..Qn (suppressions de code mort, drops de colonnes, options structurantes) avec pour chacune : options, conséquences, ta recommandation. **Formule chaque question pour un non-ops** : vulgarise le jargon infra/DB, énonce le bénéfice produit/utilisateur et le coût en clair — une question qui exige un 2ᵉ tour d'explication est une question ratée. Présente la synthèse du CONSOLIDATED + les questions, puis **ARRÊTE-TOI et attends mes arbitrages**. Consigne-les ensuite dans `DECISIONS.md` (modèle : `docs/audit_2026-07/DECISIONS.md`), en vérifiant la cohérence de chaque décision contre le CONSOLIDATED et en signalant toute contradiction AVANT d'enchaîner.

## Phase 4 — Ledger & roadmap

1. Mets à jour `docs/audits/LEDGER.md` : nouveaux findings → OUVERT ; constatés corrigés depuis l'audit précédent → CORRIGÉ (commit/date si retrouvable via `git log`) ; arbitrés « on ne corrige pas » → ACCEPTÉ (réf. décision Qn) ; disparus car le code a changé → OBSOLÈTE. Mets à jour « Dernière vue » pour tout finding re-rencontré. Pointe la ligne « Dernier audit complet » de `docs/audits/README.md` sur le dossier de cet audit.
2. Propose un bloc roadmap prêt à coller (série type AU : un lot quick wins d'abord, puis lots thématiques, avec Definition of Done) — ne modifie PAS `docs/ROADMAP.md` sans mon accord explicite.
3. Propose le message de commit (docs uniquement, format conventionnel). Rappelle que la suite naturelle est `/work_manager` sur le premier lot arbitré.
