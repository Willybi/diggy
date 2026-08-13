---
description: Rétrospective de fin de chantier — confronte l'usage réel des skills à leur design, repère dérives/frictions/gaps, propose des fixes de skills et de nouveaux skills, tient un ledger inter-sessions
allowed-tools: Read, Glob, Grep, Write, Edit, Bash(git status:*), Bash(git diff:*), Bash(git log:*), Bash(git show:*), Bash(git rev-parse:*), PowerShell(git status:*), PowerShell(git diff:*), PowerShell(git log:*)
argument-hint: [nom d'un skill à cibler, ex. work_manager | vide = rétro complète de la session]
---

Tu fais la **rétrospective d'usage des skills** de la session/chantier qu'on vient de terminer. Cible : $ARGUMENTS (vide = rétro complète de tout ce qu'on a fait cette session).

Objectif : voir si on utilise nos skills **comme ils sont conçus**, repérer où les **améliorer / fine-tuner**, et détecter les **tâches répétitives sans skill** pour en proposer de nouveaux. Périmètre LARGE : skills projet (`.claude/commands/`) ET skills built-in (`code-review`, `verify`, `run`, `commit`, `schema_doc`…) ET habitudes de travail (mémoire à jour, permissions qui promptent, choix d'outils).

## Règles non négociables
- **Un finding sans preuve n'existe pas** : cite le MOMENT de la session (ce qui s'est réellement passé) + la ligne du skill que ça confirme/contredit. Pas d'« il me semble ». Tu ne « corriges » jamais un skill sur une impression.
- **Tu ne modifies AUCUN fichier avant mon accord** (Phase 5 = STOP). Après accord seulement : édition de skills, nouveau skill, CLAUDE.md/mémoire, et LEDGER.
- **Ne re-signale jamais un point déjà ACCEPTÉ** dans `docs/skill-reviews/LEDGER.md`. Une RÉCURRENCE (finding encore OUVERT vu une session de plus) est au contraire un signal AGGRAVANT à souligner : c'est ce qui fait basculer « à surveiller » → « à corriger maintenant ».
- **Fidélité au réel** : si un skill a bien tourné, dis-le (section « Ce qui a bien tourné ») — pour ne pas « corriger » par erreur un truc sain à la prochaine rétro.
- **Reste dans les conventions du repo** quand tu proposes un skill neuf ou une édition : frontmatter `description` / `allowed-tools` / `argument-hint`, français, « tu » qui s'adresse à l'agent, phases numérotées, points STOP, jamais de push ni de deploy.
- **Proportionne le remède au signal** : un skill n'a de valeur que sur du répétitif à étapes ; ne propose pas de skill pour une tâche rare ou triviale, et n'alourdis pas un skill existant pour un incident isolé (note-le au LEDGER, attends la récurrence).

## Phase 0 — Cadrage
1. Lis `docs/skill-reviews/LEDGER.md` (s'il n'existe pas encore, tu le créeras en Phase 6 — note-le). Retiens les findings **OUVERT** (à re-vérifier ce coup-ci) et **ACCEPTÉ** (à ignorer).
2. Inventorie les skills projet : `.claude/commands/*.md` (le nom du skill = le nom du fichier ; lis chaque frontmatter `description`). Garde en tête la liste des skills built-in disponibles cette session (visibles dans le contexte).
3. Mode : `$ARGUMENTS` nomme un skill → rétro **CIBLÉE** sur lui (usage cette session + confrontation ligne à ligne à son `.md`) ; vide → rétro **COMPLÈTE** de la session.

## Phase 1 — Reconstituer ce qu'on a fait
Reconstruis une frise compacte de la session à partir de :
- **le fil de conversation en contexte** : quelles tâches, quels skills invoqués (appels `Skill` / balises `<command-name>`), quels sous-agents lancés, et surtout les moments de **friction / re-travail / allers-retours / mauvaise piste** ;
- **les preuves git** de la session, pour recouper ce qui a réellement changé : `!git status --short`, `!git diff --stat`, `!git log --oneline -15` (commits faits pendant la session) ;
- **fallback si le contexte a été résumé ou est mince** : les transcripts JSONL de session sous `C:\Users\willi\.claude\projects\c--Users-willi-Desktop-diggy\*.jsonl` (grep les invocations de skill / noms de commande) — optionnel, seulement si le fil en contexte ne suffit pas.

Sors trois listes : **(a)** skills utilisés + comment ils l'ont été, **(b)** tâches multi-étapes faites À LA MAIN sans skill, **(c)** points de friction observés.

## Phase 2 — Audit d'usage (conçu vs réel)
Pour CHAQUE skill utilisé : lis son `.md`, confronte ses étapes prescrites à ce qui s'est réellement passé. Classe chaque finding dans une catégorie :
- **DÉRIVE** — le skill dit X, le repo/code est maintenant Y (chemin, compteur, convention, étape qui ne correspond plus). Fix probable : éditer le skill, ou CLAUDE.md si c'est un invariant transverse.
- **FRICTION** — le skill est juste mais a coûté des tours / de l'ambiguïté / du re-travail (étape floue, ordre sous-optimal, garde manquante, sortie mal cadrée, STOP absent). Fix : préciser / réordonner / ajouter une garde ou un exemple.
- **NON-UTILISÉ ou MAL-UTILISÉ** — un skill existant aurait dû servir mais on a fait à la main, OU il a été suivi de travers. Fix : trigger plus clair (dans le skill ou CLAUDE.md), ou simple rappel si le skill est bon.
- **GAP** — séquence multi-étapes répétée sans skill (→ Phase 3).
- **BONNE PRATIQUE** — ce qui a bien marché (à conserver explicitement).

Couvre aussi les skills **BUILT-IN** pertinents (a-t-on lancé `code-review` / `verify` / `commit` / `run` / `schema_doc` quand il fallait, et bien ?) et les **HABITUDES** de travail (mémoire mise à jour quand un fait durable est apparu ? permissions qui ont promptté inutilement ? bon choix d'outil vs shell brut ?).

## Phase 3 — Gaps → nouveaux skills
Repère les tâches **répétitives ET multi-étapes** faites à la main (cette session, recoupées avec les récurrences du LEDGER). Pour chaque candidat sérieux, fournis un **draft de skill prêt à coller** : frontmatter complet + corps en phases, dans le style du repo. Pour chaque candidat écarté, dis en une ligne POURQUOI (trop rare, trop simple, déjà couvert par un skill existant).

## Phase 4 — Croisement LEDGER
Pour chaque finding, croise avec `docs/skill-reviews/LEDGER.md` : déjà présent → garde son ID et marque la **récurrence** (aggravant, incrémente le compteur) ; nouveau → attribue un ID `SR-nn` (prochain libre). Un point vu ≥ 2 sessions passe de « à surveiller » à « à corriger maintenant ».

## Phase 5 — Rapport + arbitrage (STOP)
Présente **en conversation** (aucun fichier écrit à ce stade) :
1. **Frise de session** (2-4 lignes) : ce qu'on a fait, skills mobilisés.
2. **« Ce qui a bien tourné »** — les bonnes pratiques à garder.
3. **Findings**, les plus actionnables d'abord, chacun au format :
   - **[SR-nn] Titre** — Catégorie · Skill concerné · Récurrence (Nᵉ session) le cas échéant.
   - **Preuve** : le moment de la session + la ligne du skill visée.
   - **Fix proposé** : la modif EXACTE — un extrait *avant → après* pour une édition de skill, un draft complet pour un nouveau skill, ou le texte à ajouter pour « → CLAUDE.md » / « → mémoire feedback ».
   - **Destination** : édition skill `<fichier>` | nouveau skill `<nom>` | CLAUDE.md | mémoire feedback | rien (juste un rappel + entrée LEDGER).
4. Les **questions d'arbitrage** s'il y en a.

**ARRÊTE-TOI ici et attends mes décisions. N'écris aucun fichier avant mon accord.**

## Phase 6 — Application (après mon accord seulement)
Pour chaque fix que j'ai validé :
- édition de skill → `Edit` sur le `.md` concerné ; nouveau skill → `Write` `.claude/commands/<nom>.md` (+ ligne dans la table Slash Commands de CLAUDE.md) ; convention durable → CLAUDE.md ; préférence de travail → un mémo `feedback` dans le dossier mémoire + ligne dans `MEMORY.md`.
- Mets à jour `docs/skill-reviews/LEDGER.md` : nouveaux findings → **OUVERT** ; validés et appliqués → **CORRIGÉ** (+ date, + skill/commit) ; « on ne touche pas » → **ACCEPTÉ** (avec la raison, ne plus jamais le re-signaler) ; disparus car le contexte a changé → **OBSOLÈTE** ; mets à jour « Dernière vue » et le compteur de récurrences pour tout finding re-rencontré. Crée le fichier avec son en-tête s'il est absent.
- **Ne committe pas, ne push pas.** Liste les fichiers touchés et propose un message de commit — c'est moi qui committe (via `/commit`).
