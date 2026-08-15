# Skill Reviews — Ledger inter-sessions

> Trace persistante des rétrospectives d'usage des skills (`/skill_review`).
> Un finding qui revient d'une session à l'autre est le signal qui justifie d'éditer un skill (ou d'en créer un).
> Ce fichier est versionné ; les rétros elles-mêmes se font **en conversation** — pas de rapport par session, seul l'agrégat vit ici.

## Statuts
- **OUVERT** — repéré, pas encore corrigé.
- **EN COURS** — fix décidé, application partielle.
- **CORRIGÉ** — fix appliqué (skill + date/commit en *Résolution*).
- **ACCEPTÉ** — on a décidé de NE PAS corriger (raison en *Résolution*). Ne plus jamais le re-signaler.
- **OBSOLÈTE** — n'a plus lieu d'être (le contexte a changé).

## Catégories
**DÉRIVE** (skill ≠ code/repo) · **FRICTION** (skill juste mais coûteux) · **NON-UTILISÉ / MAL-UTILISÉ** · **GAP** (nouveau skill à créer) · **BONNE PRATIQUE** (à conserver).

## Findings

| ID | Titre | Catégorie | Skill concerné | 1ʳᵉ vue | Dernière vue | Récurrences | Statut | Résolution |
|----|-------|-----------|----------------|---------|--------------|-------------|--------|------------|
| SR-01 | Smoke tests sans slash final → 307 au lieu du JSON | DÉRIVE | deploy_verify | 2026-08-13 | 2026-08-13 | 1 | CORRIGÉ | `deploy_verify.md` : slash final sur `/api/catalog/` + `/api/artists/` + note 307 (2026-08-13) |
| SR-02 | « parallèle » sans garde « un seul working tree = série » | FRICTION | work_manager | 2026-08-13 | 2026-08-13 | 1 | CORRIGÉ | `work_manager.md` Phase 2 : garde parallélisme (série par défaut, worktree pour du vrai parallèle) (2026-08-13) |
| SR-03 | Vérif RENDU (CDP) absente du gate pré-commit | FRICTION | work_manager | 2026-08-13 | 2026-08-13 | 1 | CORRIGÉ | `work_manager.md` Phase 5 : point de gate 4 (vérif RENDU pour chantier visuel) (2026-08-13) |
| SR-04 | Recette CDP « instance locale pré-commit » non capitalisée | GAP | verif-visuelle-headless (mémoire) | 2026-08-13 | 2026-08-13 | 1 | CORRIGÉ | Nouveau doc versionné `docs/verif-visuelle-locale.md` + pointeurs CLAUDE.md (Doc Pointers) & mémoire (2026-08-13) |
| SR-05 | Traitement du journal de tête sous-spécifié | FRICTION | roadmap_update | 2026-08-13 | 2026-08-13 | 1 | CORRIGÉ | `roadmap_update.md` Étape 2 : journal de tête EN périmètre (entrée concise + bump date) (2026-08-13) |
| SR-06 | CRLF fait échouer `format:check` local (blob LF propre) | habitude/gotcha | — (CLAUDE.md) | 2026-08-13 | 2026-08-13 | 1 | CORRIGÉ | Note CLAUDE.md Dev Commands (vérif LF-normalisée avant de « corriger ») (2026-08-13) |
| SR-07 | Livrables d'un lot amont non garantis dans le tree du lot suivant → faux BLOQUÉ | FRICTION | work_manager | 2026-08-15 | 2026-08-15 | 1 | CORRIGÉ | `work_manager.md` Phase 3 (item 9 : bloc PRÉCONDITION dans les prompts dépendants) + Phase 4 (vérif Glob/Read des livrables amont avant d'émettre le lot suivant) (2026-08-15) |
| SR-08 | `allowed-tools` sans test/lint backend (`pytest`/`ruff`) ni `npx vitest` (avait `npm test`) | DÉRIVE | work_manager | 2026-08-15 | 2026-08-15 | 1 | CORRIGÉ | `work_manager.md:3` : ajout `python -m pytest`/`pytest`/`ruff check`/`npx vitest`, retrait `npm test` (2026-08-15) |
| SR-09 | Séquence OPS prod dry-run→dump→--apply→re-vérif non capitalisée | GAP | — (CLAUDE.md) | 2026-08-15 | 2026-08-15 | 1 | CORRIGÉ | Checklist « OPS data scripts » ajoutée à la section Deploy de CLAUDE.md (2026-08-15) |
| SR-10 | Décomposer un gisement par date/source avant de le dimensionner (GO/NO-GO) | BONNE PRATIQUE | — (mémoire) | 2026-08-15 | 2026-08-15 | 1 | CORRIGÉ | Mémo feedback `gisement-decompose-before-sizing` + ligne MEMORY.md (2026-08-15) |
