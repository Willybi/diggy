---
description: Génère un nom de commit dans le style du repo (stage + contexte session) et committe
allowed-tools: Read, Bash(git status:*), Bash(git diff:*), Bash(git log:*), Bash(git show:*), Bash(git rev-parse:*), Bash(git commit:*), PowerShell(git status:*), PowerShell(git diff:*), PowerShell(git log:*), PowerShell(git commit:*)
argument-hint: [indice type/scope optionnel | --dry pour ne proposer que le nom]
---

Génère un nom de commit (subject Conventional Commits en français) **fidèle à la construction de tous nos commits passés**, à partir de ce qui est **dans le stage** + le contexte de notre session en cours, puis committe. Indice optionnel : $ARGUMENTS

## Étape 0 — Mode
- Si `$ARGUMENTS` contient `--dry` ou `--name-only` : proposer le nom **sans committer** (juste afficher). Sinon : proposer **puis committer**.
- Tout autre texte dans `$ARGUMENTS` est un **indice** de steering (type, scope, ou reformulation à privilégier).

## Étape 1 — Lire ce qui est dans le stage
- `!git status --short` et `!git diff --cached --stat`
- Si **rien n'est stagé** (`git diff --cached --quiet` renvoie 0) : **STOP**. Ne committe rien, ne stage rien. Dis à l'utilisateur qu'il n'y a rien dans le stage et liste (si utile) les modifs non stagées via `git status --short`. Ne jamais faire `git add` toi-même — on committe **uniquement ce qui est dans le stage**.
- Sinon, lire le détail utile : `!git diff --cached` (résume ce qui change réellement : fichiers, zones, sens du changement).

## Étape 2 — Réapprendre le style à chaque fois (ne pas se fier à une liste figée)
Échantillonne l'historique pour caler la construction sur l'état ACTUEL du repo :
- `!git log -n 120 --pretty=format:"%s"` → inventaire vivant des **types**, **scopes** et **codes chantier** réellement en usage.
- `!git log -n 8 --pretty=format:"%s%n%b%n---"` → calibrer le **corps** (structure, densité, lignes tests/docs).

## Étape 3 — Anatomie d'un nom (la « construction » à reproduire)

`type(scope): description`  — en **français**, initiale **minuscule**, concis.

- **type** ∈ `feat` `fix` `docs` `perf` `refactor` `chore` `style` `test` `ci`. Choisir selon la nature dominante du diff (nouvelle capacité → `feat` ; correctif → `fix` ; doc/roadmap/CLAUDE.md → `docs` ; perf/mémoire → `perf` ; refonte sans changement de comportement → `refactor` ; formatage seul → `style` ; deps/infra/outillage → `chore` ; CI → `ci`). Un micro-changement peut n'avoir **aucun type** (ex. `roadmap update`) — à réserver aux cas triviaux.
- **scope** = zone fonctionnelle en minuscules, tirée du diff et **confirmée dans le `git log`** (router / service / vue / chantier). Peut être composé (`sets-list`, `genre-detail`, `track-detail`). Peut être **omis** (`ci: …`). Doc de la roadmap → `docs(roadmap)` ; doc de CLAUDE.md → `docs(claude)`.
- **description** : impérative ou nominale, va droit au but. Décrit le QUOI (et le pourquoi si court).
- **référence chantier** entre parenthèses en fin quand le travail se rattache à un chantier : `(X1)`, `(X3.c)`, `(suite X4.f/g)`, `(D6 p.1)`, `(MON)`, `(E2.c)`, `(D4 p.3)`. Récupère le code exact dans le `git log` récent ou le contexte de session.
- **em-dash `—`** pour élaborer : `type(scope): CODE — précision`. **`+`** pour agréger plusieurs éléments.
- Motif roadmap : `docs(roadmap): clôture <CODE> (TERMINE <AAAA-MM-JJ>) — <résumé>` ou `docs(roadmap): <verbe> <CODE> — …`.

Exemples réels du repo (pour calibrer la construction, pas à recopier) :
- `fix(search): recherche insensible aux espaces sur toutes les surfaces (suite X4.f/g)`
- `feat(radar): page /radar bi-score (Tendance × Pour toi)`
- `perf(av3): cache /similar, migration 0044 (index+drops), rétention & I/O async`
- `docs(roadmap): clôture AV2 (TERMINE 2026-08-10) — upgrades deps + gate pip-audit bloquant`
- `chore(av2): upgrade deps vulnérables + gate pip-audit bloquant + pins nginx`

## Étape 4 — Corps (proportionnel au changement)
- Changement **trivial** (1 fichier, effet évident) → **subject seul**, pas de corps.
- Changement **substantiel** → ajouter un corps dans le style observé à l'étape 2 : 1-2 phrases what/why, puis puces par lot si plusieurs volets, et si pertinent une ligne `Tests : …` et/ou `Docs : …`. Mentionner « aucune migration » quand c'est vrai et notable.
- Priorité absolue au **subject** : c'est le « nom » demandé ; le corps est un bonus fidèle à l'usage du repo.

## Étape 5 — Committer (sauf `--dry`)
- Committer **uniquement le stage** (ne jamais `git add`, ne jamais `git push` — un push sur master = déploiement prod).
- Terminer le message par le trailer (cohérent avec nos commits faits via Claude) :
  `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`
- Utiliser un heredoc pour le message multi-lignes :
  ```
  git commit -m "$(cat <<'EOF'
  <subject>

  <corps éventuel>

  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
  EOF
  )"
  ```

## Étape 6 — Rapport
- Afficher le **nom retenu** et, si tu en as, **1-2 alternatives** de construction équivalente.
- Rappeler que rien n'a été poussé (pas de deploy) et comment ajuster si besoin : `git commit --amend -m "…"`.
- En mode `--dry`, afficher le nom (+ corps proposé) sans committer.
