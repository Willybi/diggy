# Audit 2026-07 — Décisions d'arbitrage (Phase 3)

> Date : 2026-07-09
> Décisions prises par William, pré-arbitrées hors session puis remises à Claude Code.
> Instruction au main agent : valider la cohérence de chaque décision contre CONSOLIDATED.md,
> signaler toute contradiction ou conséquence non anticipée AVANT d'enchaîner sur la Phase 4.
> En cas de doute d'interprétation : demander, ne pas interpréter.

---

## Actions déjà réalisées hors audit (2026-07-09, par William)

- **A5-01/A5-02 (mitigation temporaire)** : dump manuel frais `dump_20260709.dump` réalisé et copié hors VPS (PC local). Le fix pérenne (cron + offsite) reste dû dans AU1/AU2.
- **M3 volet rotation (fait)** : session TIDAL révoquée côté compte, token compromis inerte. Fichier session régénéré hors repo. Restent dus : `git rm --cached` + `.gitignore` + fallback env `TIDAL_TOKEN_FILE` (AU1). Purge historique : voir Q4.

---

## Q1 — Lot AU1 Quick Wins : **Option A**

AU1 = les 8 QUICK WINS stricts (§5.1) + les QW-c de confiance haute SANS décision produit (~30 items).
Les QW-c dépendant d'une décision (dead code, colonnes) suivent Q1b/Q3 ci-dessous.

Modalités :
- A3-01 : le rattrapage des 235 lignes privées enrichies = script séparé, exécuté après validation du fix de promotion, PAS fusionné dans le même commit.
- Revue de la PR AU1 par lots thématiques (workers ensemble, infra ensemble, frontend ensemble).
- A1-02 (pagination /search cassée) intègre AU1 (bug utilisateur visible), indépendamment du refactor service (Q8).

## Q1b — Dead code backend

| Groupe | Décision |
|---|---|
| 1. `PATCH /watchlist/{id}/crawled` (A1-06) | **SUPPRIMER** |
| 2. 8 endpoints taxonomy (A1-12) | **GARDER — feature long terme planifiée** (explorateur de genres). Conditions : (a) documenter dans CLAUDE.md comme "réservés, non branchés, futur chantier explorateur de genres" ; (b) test smoke minimal par endpoint (réponse 200) pour éviter la pourriture silencieuse ; (c) A1-18 reste ACTIF sur ce périmètre (SQL brut/camelCase à nettoyer puisque le code survit). |
| 3. `POST /genres/refresh-pillars` (A1-13) | **SUPPRIMER** (cassé en multi-process) |
| 4. `GET /watchlist/` (A1-07) + `reset-beatport`/`backfill-multi-artists` (A1-14) | **DOCUMENTER** comme outillage curl admin |
| 5. `GET /auth/me` (A1-23) | **GARDER** + l'appeler au boot frontend pour rafraîchir `is_admin` |

## Q2 — Import legacy : **Option A (clean)**

Le script desktop `worker/import_rekordbox.py` n'est plus utilisé (flux officiel = drag-and-drop XML web depuis F4).
- Archiver le script dans `docs/completed/` (pas de suppression sèche).
- Déprécier puis supprimer le router `tracks` (~500 LOC, 5 endpoints).
- **Garde-fou obligatoire avant suppression** : grep ciblé confirmant que `GET /tracks/{track_id}` n'est appelé par aucun composant frontend (A4 n'a rien trouvé, re-vérifier en session).
- A1-09 (dédup artwork) devient sans objet. A7-07 : documenter le reste de l'outillage `worker/` + `server/deezer/` encore vivant.

## Q3 — Migration 0031 (colonnes mortes)

| Élément | Décision |
|---|---|
| Table `watched_playlists` (A2-01) | **DROP** (dump de précaution déjà en place) |
| `catalog.fingerprint` + index unique (A2-06) | **DROP** (C2 v2 = scores sémantiques, pas de fingerprinting audio ; pgvector différé) |
| `catalog.preview_url` (A2-07) | **DROP + retirer des schemas API**. Vérifier qu'aucun composant frontend ne lit ce champ avant merge. |
| `artists.bio/country/real_name/soundcloud_id` (A2-05) | **Retrait des schemas Pydantic seulement**, colonnes conservées |
| `sets.event/venue/description` (A2-08) | **Retrait des schemas Pydantic seulement**, colonnes conservées |
| `user_tracks.created_at` (A2-09) | **`server_default=now()`** (servira à C3) |
| A2-11 (index `user_tracks.catalog_id`, `user_follows.entity_id`) | Inclus dans la même migration 0031 |

Ordre : migration 0031 → A2-04 (index dans les modèles) → M4 (régénérer `database-schema.md` via `/schema_doc`) → A7-05/M5 (passe doc CLAUDE.md).

## Q4 — Purge historique git : **Option B**

Rotation faite, token inerte. Pas de purge maintenant.
**Condition inscrite** : si le repo est un jour ouvert (public ou contributeurs), la purge `git filter-repo` devient un prérequis bloquant de ce chantier. À noter dans la roadmap comme condition, pas comme tâche.

## Q5 — `_design/`, `.claude/`, `docs/prompts/` : **repartir clean (variante de l'option A)**

Contexte : le flux design migre vers un projet Claude Design dédié. Les handoffs `_design/` historiques deviennent des archives, plus de la doc de référence.
- `.claude/commands/` : **VERSIONNER** (slash commands = infrastructure projet).
- `_design/` : archiver les .md à valeur de référence dans `docs/completed/design/` ; le reste peut être supprimé localement ; `_design/` cesse d'être référencé par CLAUDE.md comme doc de référence.
- `docs/prompts/` : reste gitignoré (convention existante : prompts finis → `docs/completed/`).
- Corriger CLAUDE.md en conséquence (les futurs handoffs design proviennent du projet Claude Design).

## Q6 — Stack locale : **fix minimal, pas de réparation full-stack**

Usage réel : dev local rare, `npm run dev` occasionnel pour visualiser une page design.
- Documenter dans CLAUDE.md que le dev local full-stack n'est PAS supporté (le flux = push → CI → prod).
- S'assurer que `npm run dev` seul fonctionne pour la visualisation frontend (les appels API peuvent échouer, mais proprement : pas de crash de page).
- Ne PAS investir dans la réparation du compose local complet.

## Q7 — Dette de tests : **reco suivie (A pour enrichissement + auth, B pour le reste)**

- Chantier AU7 réduit à : A6-04 (pipeline enrichissement + retrait du `omit` du gate coverage), A6-07 (LoginCallbackView), et M6 (supprimer la fausse couverture test_check_sync).
- **Séquencement impératif** : le volet enrichissement de AU7 s'exécute AVANT ou AVEC AU4 (robustesse workers), pour servir de filet pendant les modifications — pas après.
- A6-08 (import RB) et A6-14 : opportuniste, au fil des chantiers qui touchent ces zones.
- Le retrait du `omit` est prioritaire dans le lot (un gate aveugle est pire que pas de gate).

## Q8 — Couche service : **Option A pour search + watchlist, B pour le reste**

- AU5 réduit à : A1-01 + A1-02 (si pas déjà fixé en AU1, sinon vérifier la non-régression), A1-05, A1-15/A1-16, A1-17, A1-25.
- A1-10/A1-11 (dedup attach/detach) : **rattachés au chantier C6 existant**, retirés de la série AU.
- Contrainte : zéro changement de comportement, protégé par les tests existants.

## Q9 — Contexte de build workers : **Option A, intégré à AU2**

- Refonte contexte de build `./server` + Dockerfile api/workers + `.dockerignore` dédiés (A5-08 + A5-09).
- **Condition d'exécution** : test local complet du build avant push (build cassé = deploy cassé).
- Pas de chantier séparé : ça rejoint AU2 (sauvegardes & déploiement).

---

## Impacts sur la proposition de chantiers (§7 du CONSOLIDATED)

| Chantier | Ajustements actés |
|---|---|
| AU1 | Option A Q1 + A1-02 + M3 volet gitignore/env + suppressions Q1b-1/3 si triviales |
| AU2 | + Q9 (A5-08/09) confirmé |
| AU3 | Migration 0031 selon Q3 (périmètre exact ci-dessus) |
| AU4 | Inchangé, mais séquencé APRÈS ou AVEC le volet enrichissement de AU7 |
| AU5 | Réduit (Q8) : search + watchlist + rangements S ; A1-10/11 → C6 |
| AU6 | Inchangé |
| AU7 | Réduit (Q7) : A6-04 + A6-07 + M6 ; positionné avant/avec AU4 |
| AU8 | + Q2 (archivage script, suppression router tracks) + Q5 (design clean) + Q6 (doc stack locale) + Q1b-2 (doc taxonomy) et Q1b-4 (doc curl admin) |

Séquencement global suggéré pour la Phase 4 : **AU1 → AU2 → AU3 → AU7(enrichissement) → AU4 → AU5 → AU6 → AU8**, la série AU s'insérant avant la reprise des chantiers C (à l'exception des findings tagués lié-chantier:C3/C6, reportés dans leurs briefs respectifs).

---

*Phase 4 : GO après validation de cohérence par le main agent. Mettre à jour `docs/ROADMAP.md` selon la convention `/roadmap_update`, sans modifier les chantiers C-series/R1 existants autrement que par l'ajout des renvois lié-chantier.*
