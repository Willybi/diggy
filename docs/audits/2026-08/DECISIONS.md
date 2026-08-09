# Audit 2026-08 — Décisions d'arbitrage (Phase 3)

> Date : 2026-08-09. Décisions prises par William en session, sur la base de `CONSOLIDATED.md` (68 findings uniques).
> Cohérence vérifiée par le main agent contre le CONSOLIDATED : aucune contradiction ; un ajustement de
> forme signalé (A5-01 déplacé d'AV1 vers AV2 — son ordre imposé « après les upgrades » l'y mettait déjà de fait).

---

## Q1 — Lot AV1 Quick Wins : **GO en bloc**

AV1 = les 5 QUICK WINS stricts (M1, A3-01+A3-06, A6-02, A4-02 — A5-01 déplacé en AV2, cf. ci-dessous) + les ~20 QW-c
de confiance haute sans décision produit : A1-03, A1-04, A1-06, M5 (buckets sets/search + preview-url + similar),
A4-03, A5-02 (canal d'alerte backup + logrotate), A5-03 (bump MinIO, cf. Q7), A6-09, A4-08, A4-09,
2026-07/A1-11 (garde is_virtual), A1-10 (get_styles), A3-10 (2 symboles morts workers), A6-06 (like_escape ×8 sites),
A7-03 (3 lignes README scripts), A5-07 volet 1 (npm audit fix).
Modalités : revue par lots thématiques (backend / workers / frontend / infra), tests jumeaux pour M1
(pattern test_scope_visibility à deux users) et A3-01 (contrat routeur↔tâche).

## Q2 — Dépendances backend & gate CI (AV2) : **GO complet**

Ordre impératif : (1) python-jose 3.3.0→3.4.0 + python-multipart 0.0.9→≥0.0.18 (drop-in) ;
(2) lot fastapi+starlette (filet = suite API complète, 1655 tests) + requests/curl-cffi/python-dotenv ;
(3) **ensuite seulement** A5-01 : gate pip-audit bloquant (`needs:` + retrait `continue-on-error`),
les avis sans fix (PYSEC-2025-185) maintenus via `--ignore-vuln` explicites et commentés.
A5-06 (pins nginx:1.29-alpine, node/python acceptables) dans le même lot.

## Q3 — Famille OOM/similarité : **option (a) — palliatifs maintenant**

- AV1 : bucket `/api/radar/feed` (A6-02), buckets M5, lissage `fetchUpTo` 12→2-3 (A4-02).
- AV3 : cache Redis résultat sur `get_similar_tracks` par (seed, viewer) TTL 6h — pattern similar_sets existant (A1-02),
  migration d'index groupée (A2-01 composite created_at/id + A2-02 radar_trends + A2-07 partiel backlog BPM),
  tie-break A2-09, I/O sync restante (2026-07/A1-04).
- Le **pool précalculé nightly** (« fix durable » noté dans `RecommendationConfig`) N'EST PAS lancé :
  inscrit à la roadmap comme chantier CONDITIONNEL, déclenché si les mesures post-AV3 (RSS par requête,
  latence /similar) restent insuffisantes. Ne PAS toucher au barème C2.

## Q4 — Code mort : **tout supprimer**

| Élément | Décision |
|---|---|
| Surface Radar v1 : `GET /radar/full`, `PATCH /{id}/state`, `PATCH /state/batch`, `DELETE /{id}` + `list_full`/`update_state`/`batch_update_state`/`add_track` + leurs tests (A1-05) | **SUPPRIMER** — `UserRadarState` et `opinion_sync` restent intacts (vivants) |
| `GET /api/watchlist/` (2026-07/A1-07, 2e audit sans consommateur) | **SUPPRIMER** — réécrire les tests follow sur `/browse` ; sa part d'A1-06 (ORDER BY `list_followed`) tombe |
| `TrackIDClient.get_styles` (A1-10) | **SUPPRIMER** |
| `DEFAULT_ANALYSIS_BPM_BATCH_SIZE` + `workers/db.get_session` (A3-10) | **SUPPRIMER** (ou référencer la constante depuis le beat — au choix de l'exécutant, source unique) |
| `PageHero.vue`, `RingPct.vue` (0 réf) ; `ScorePill.vue`/`InLibBadge.vue` + leurs sections DesignSystemView (A4-07) | **SUPPRIMER** — mettre à jour le compteur composants de CLAUDE.md dans la passe doc AV7 |

Exécution : suppressions simples (get_styles, symboles workers, composants) dans AV1 ; suppressions d'API
(Radar v1, GET /watchlist/) dans AV6 avec le dé-engraissement des routers (même zone, même revue).

## Q5 — DB : colonnes mortes & rétention : **reco suivie**

- **DROP** dans la migration AV3 (même migration que les index) : `catalog.needs_reconciliation`,
  `catalog.status`, `catalog.origin`, `sets.platform`. Retirer les lignes correspondantes du MANUAL block
  de `docs/database-schema.md`, régénérer via `/schema_doc` APRÈS la migration.
- **Rétention** : purge >13 mois sur `metric_snapshots` ET `crawl_logs`, implémentée dans `snapshot_backlogs`
  (DELETE fenêtré à chaque run horaire — idempotent, pas de nouvelle tâche). Documentée dans le schema doc.

## Q6 — Extraction table partagée frontend : **chantier dédié (AV5)**

A4-01 (Explorer↔Radar) → A4-04 (Sets↔Watchlist) → A4-05 (helper opinion one-shot + traitement du plafond
silencieux 100/200) + A4-06 (split HubView : sections lazy sous le fold, mesure vite build avant/après)
+ M6 (table.css → `@media (hover: none)` en passant). Positionné APRÈS AV2. Garde-fou impératif :
vérification RENDU (pipeline CDP, mémoire `verif-visuelle-headless`) sur les 4 vues après extraction —
zéro changement visuel attendu. Gel implicite : aucune évolution fonctionnelle des tables avant AV5.

## Q7 — MinIO : **bump**

Cap 2G→3G + `GOMEMLIMIT` 1800→2700MiB (`docker-compose.yml`), commentaire compose corrigé (retirer
« this keeps it bounded », démenti par l'observation 99,55 %). Restart hebdo conservé. Surveillance :
`RestartCount`/`OOMKilled` entre deux lundis. Intégré à AV1 (une ligne compose + un commentaire).

## Q8 — Majeurs frontend : **inscrire**

Nouveau chantier roadmap dédié « Majeurs frontend » (vite 5→8 + vitest 3→4 ensemble, puis pinia 2→4,
vue-router 4→5), positionné APRÈS AV5 (l'extraction réduit la surface à re-valider), hors série AV.
Re-validation des 18 vues + vérif CDP au menu.

---

## Impacts sur la proposition de chantiers (§7 du CONSOLIDATED)

| Chantier | Ajustements actés |
|---|---|
| AV1 | + A5-03 (bump MinIO, Q7) + suppressions simples Q4 ; **− A5-01** (déplacé AV2) |
| AV2 | + A5-01 (après upgrades, ordre impératif) + A5-06 |
| AV3 | Périmètre Q3(a) + migration Q5 (drops + rétention) dans la même migration que les index |
| AV4 | Inchangé (M2, A3-03, M3, A3-05, A3-07, A3-08, A8-03, A3-09, A3-12) |
| AV5 | Inchangé + garde-fou CDP obligatoire (Q6) |
| AV6 | + suppressions d'API Q4 (Radar v1, GET /watchlist/) avec A1-08 + 2026-07/A1-10 + A4-07 vitrine |
| AV7 | Lot doc CLAUDE.md (9 divergences) + `/schema_doc` post-migration + tests A6-07/A6-08 + A6-05 ; A7-02 (`/roadmap_update`) exécuté IMMÉDIATEMENT, hors série |
| Hors série | « Majeurs frontend » (Q8) + « Pool similarité précalculé » (Q3b, conditionnel) inscrits à la roadmap |

Séquencement : **A7-02 immédiat** → AV1 → AV2 → AV3 ∥ AV4 (zones disjointes) → AV5 → AV6 → AV7.

---

*Phase 4 : LEDGER mis à jour (findings 2026-08 insérés avec leur affectation AV), bloc roadmap proposé,
message de commit proposé. La suite naturelle est `/work_manager` sur AV1.*
