---
description: Triage des issues Sentry de prod — collecte, root-cause, diffs proposés, mute auto du bruit, résolution après déploiement vérifié
allowed-tools: Read, Glob, Grep, Bash(git log:*), Bash(git diff:*), Bash(ssh diggy-vps:*), mcp__sentry__search_issues, mcp__sentry__get_sentry_resource, mcp__sentry__search_events, mcp__sentry__analyze_issue_with_seer, mcp__sentry__update_issue, mcp__sentry__find_projects
argument-hint: [périmètre : vide = non résolues 30j | 24h | 7d | une issue DIGGY-APP-XX]
---

Tu tries les issues Sentry de production de Diggy. Périmètre demandé : $ARGUMENTS (vide = toutes les non résolues, période 30j).

Constantes d'accès (ne les redécouvre pas) : organisation `diggy-music`, projet `diggy-app`, `regionUrl='https://de.sentry.io'`. Site de prod : https://diggy-music.fr. Dashboard des résultats : https://diggy-music.sentry.io/issues/?project=diggy-app

Ton rôle : collecter → comprendre → **proposer des correctifs code (jamais les appliquer)** → muter le bruit évident → me remettre un plan d'arbitrage, et ne clôturer un statut Sentry qu'une fois le fix déployé et vérifié. Sentry lui-même est ton journal (statuts `ignored`/`resolved` + commentaires d'activité) : pas de ledger doc à tenir.

## Règles non négociables

- **Zéro écriture dans le repo.** Tu ne fais AUCUN edit / commit / push / stash. Pour un vrai bug tu produis un **diff proposé** (fichier:ligne + patch) ; c'est moi qui le porte via `/work_manager` ou `/commit`.
- **Écritures Sentry SANS me demander : UNIQUEMENT le mute du bruit** (bucket D ci-dessous), en `ignored` mode `untilEscalating` (JAMAIS `forever`), avec un `reason` justificatif. Tout `resolved`, toute assignation, tout ignore permanent → STOP et validation.
- **`resolved` seulement APRÈS déploiement du fix vérifié** (`resolvedInNextRelease` de préférence — Sentry rouvre si ça récidive). Jamais avant que le correctif soit en prod et `/deploy_verify` SAIN. **Résoudre ≠ corriger** : ne clôture jamais une issue encore vivante sans fix déployé — ce serait cacher le problème.
- **Un finding sans preuve n'existe pas** : stack trace + `culprit` + fichier:ligne du repo. Pas d'« il semble que ».
- **Dédup contre l'existant** : ne re-signale pas un symptôme déjà couvert par un chantier `docs/ROADMAP.md` en cours, un pitfall de CLAUDE.md, ou une entrée de la mémoire projet (`MEMORY.md`). Marque-le `RATTACHÉ <chantier/pitfall>` au lieu de reproposer un fix.
- Respecte les invariants CLAUDE.md dans tout diff proposé (lock Redis `SET NX EX` TTL > time_limit ; jamais `autoretry_for=(Exception,)` sur une tâche à soft-limit ; `catalog_visible` sur tout read path catalog ; une panne HTTP externe ne brûle pas de tentative E1 ; etc.). Un fix qui viole un invariant est un fix raté.

## Phase 1 — Collecte

1. `search_issues(organizationSlug='diggy-music', projectSlugOrId='diggy-app', regionUrl='https://de.sentry.io', query='is:unresolved', sort='freq', period=<selon args>, limit=100)`. Si `$ARGUMENTS` désigne une issue précise (`DIGGY-APP-XX`), saute directement à son détail.
2. Pour chaque issue non classable au seul titre : `get_sentry_resource` (URL ou `resourceType='issue'` + shortId) → stack trace, `culprit`, `events`, `firstSeen`/`lastSeen`, tags, release. Priorise par volume d'events puis par récence.
3. Borne le contexte de dédup : `git log --oneline -20` (les pushes master = déploiements), et repère dans `docs/ROADMAP.md` + `MEMORY.md` les chantiers/pitfalls en cours (reclassify OOM, enrich beatport time-limits, OOM /radar/feed, DLQ crawl_trackid…).

## Phase 2 — Triage en 5 buckets

Classe CHAQUE issue dans exactement un bucket :

- **(A) Vrai bug code** — la stack trace pointe une ligne du repo, corrigeable : `TypeError`/`AttributeError`/`KeyError`/`ImportError`, signature qui ne matche pas, race (`ObjectDeletedError`), logique fautive. → Phase 3.
- **(B) Signal infra/ops** — pas un fix code : `SIGKILL`/`WorkerLostError`/OOM, `No space left on device`/`DiskFullError`, `TimeLimitExceeded`/hard time limit. → route ops (action VPS : mémoire, disque, capacité), pas de « resolve ».
- **(C) Symptôme d'un chantier connu** — matche un item ROADMAP en cours ou un pitfall CLAUDE.md/mémoire. → `RATTACHÉ <réf>`, aucune action propre.
- **(D) Bruit externe transitoire** — auto-mutable, définition STRICTE (whitelist, dans le doute → PAS bucket D). Les TROIS conditions :
  1. l'erreur vient d'un appel réseau vers un hôte **externe** (trackid.net, api.deezer.com, beatport, tidal) — `HTTPStatusError` 5xx, `ReadTimeout`, `ConnectTimeout`, `ConnectionError` — **ou** un transitoire Celery non-code (`TaskRevokedError`) ;
  2. le `culprit` est une tâche worker résiliente au re-scan (`backfill_trackid_sets`, `crawl_trackid_latest`, `recrawl_incomplete_sets`, `enrich_*`) — l'outage ne brûle pas de tentative E1 ;
  3. ce n'est **ni** un bug code (bucket A), **ni** un signal capacité (bucket B), **ni** une erreur DB (deadlock/DiskFull/Integrity).
- **(E) Déjà mort** — `lastSeen` antérieur au commit de déploiement qui l'a plausiblement corrigé (croise avec `git log`). → candidat `resolved`, **mais** via arbitrage (Phase 4), jamais auto.

## Phase 3 — Root-cause & diffs proposés (bucket A uniquement)

Pour chaque vrai bug :
1. Lis le fichier du `culprit` dans le repo, corrèle à la stack trace (ligne exacte).
2. Optionnel, pour corroborer une hypothèse difficile : `analyze_issue_with_seer` (Seer pointe fichier+ligne+fix). **Jamais en aveugle** : croise toujours sa sortie avec ta lecture du repo — Seer propose, tu vérifies.
3. Produis un **diff proposé** (fichier:ligne + patch), conforme aux invariants CLAUDE.md, **sans l'appliquer**. Formule aussi le test qui prouverait le fix.

## Phase 4 — Mute auto du bruit + STOP arbitrage

1. **Applique les mutes du bucket D** (et seulement ceux-là) : `update_issue(status='ignored', ignoreMode='untilEscalating', reason='Auto-muté par /sentry_triage : bruit réseau externe transitoire — rouvre si escalade')`. Liste ce qui a été muté.
2. Présente le **plan d'arbitrage** : tableau `Issue | Bucket | Volume (events, last seen) | Diagnostic | Action recommandée`, groupé par bucket, buckets A/B/C/E. Pour A : le diff proposé. Pour B : l'action ops précise. Pour E : « resolved après confirmation ».
3. **STOP.** Attends mes arbitrages. Ne résous rien, n'assigne rien, n'ignore rien d'autre sans mon feu vert. Signale le lien dashboard si je veux ouvrir les résultats dans Sentry.

## Phase 5 — Après arbitrage & déploiement (clôture des statuts)

- Les diffs que j'ai validés : je les porte via `/work_manager` ou `/commit` (tu ne touches pas au repo) → push → CI → deploy.
- **Résolution Sentry uniquement quand le fix est en prod et `/deploy_verify` SAIN.** Pour chaque issue concernée : `update_issue(status='resolvedInNextRelease', reason='Corrigé par <commit/chantier> — <une ligne>')` (ou `resolved` si le release tracking n'est pas câblé). Pour les buckets E arbitrés « à résoudre » : idem, après confirmation.
- Ne résous JAMAIS un bucket B (infra) ni un C (chantier en cours) : ils se ferment quand leur cause réelle est traitée, pas par ce skill.

## Rapport final

- **Bilan** : tableau `Issue | Bucket | Action prise | Statut Sentry résultant`. Verdict : combien mutés (D), combien de diffs proposés (A), combien routés ops (B), combien rattachés (C), combien candidats resolved (E).
- **Reste à faire humain** : les diffs à porter, les actions ops (ex. disque VPS plein), les issues en attente de déploiement avant clôture.
- Rappelle l'enchaînement : `/work_manager` (ou `/commit`) sur les diffs validés → `/deploy_verify` → re-run `/sentry_triage` pour clôturer les statuts des issues déployées.
