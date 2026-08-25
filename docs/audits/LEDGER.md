# Ledger des findings d'audit

> Une ligne par finding unique, tous audits confondus. Clé = `<AAAA-MM>/Ax-nn` (audit découvreur + ID local).
> Statuts et taxonomie : voir `README.md`. Mis à jour en Phase 4 de chaque `/audit_global`.
>
> **Amorçage effectué le 2026-08-09** (audit 2026-08) depuis `docs/audit_2026-07/` : seuls les findings
> de 2026-07 encore ouverts, acceptés ou partiels ont été reportés — les ~90 corrigés par la série AU1-AU8
> (commits `ebca46b`→`b72d994`, 2026-07-09 → 2026-07-11) ne sont pas listés individuellement.
> Chaque ligne a été re-vérifiée contre le code à HEAD `9b305d6`. Les affectations « EN ROADMAP » réfèrent
> à la série AV arbitrée dans `docs/audits/2026-08/DECISIONS.md`.

## Reports de l'audit 2026-07

| Clé | Titre | Sévérité | Statut | Découvert | Dernière vue | Résolution / Référence |
|---|---|---|---|---|---|---|
| 2026-07/A5-04 | Gate CI pip-audit non bloquant | haute (aggravée) | CORRIGÉ | 2026-07 | 2026-08 | AU1 a corrigé la CIBLE du job, pas son caractère non-bloquant ; 26 vulns derrière → 2026-08/A5-01, **AV2** (après upgrades A6-03, Q2) (commit 50a1e39 + hotfix jinja2 3c0c8b6, 2026-08-10) |
| 2026-07/A4-09 | HubView dans le chunk principal | moyenne | CORRIGÉ | 2026-07 | 2026-08 | Clos « non justifié » en AU6 (191,9 kB) ; cliquet vérifié : 211,6 kB après D6 → 2026-08/A4-06, **AV5** (commit 43e0302, 2026-08-15) |
| 2026-07/A2-14 | Tris `radar_trends` sans index | moyenne (aggravée) | CORRIGÉ | 2026-07 | 2026-08 | Table ×4 en un mois, 2 consommateurs guests, seq scan prouvé → 2026-08/A2-02, **AV3** (commit 593ab47, 2026-08-10) |
| 2026-07/A1-04 | I/O synchrone bloquante dans l'event loop | moyenne | CORRIGÉ | 2026-07 | 2026-08 | Corrigé sur watchlist/import externe ; restent 5 sites (admin search-deezer, link_to_deezer, enrich_single_beatport, boucle artworks, upload import) → **AV3** (commit 593ab47, 2026-08-10) |
| 2026-07/A1-10 | attach/detach dédup sets dans `routers/admin.py` | moyenne | CORRIGÉ | 2026-07 | 2026-08 | Rattaché C6 par Q8 2026-07, jamais exécuté ; aggravé par les group-flags → **AV6** (commit f15b52c, 2026-08-15) |
| 2026-07/A1-11 | `detach_set` sans garde `is_virtual` | basse | CORRIGÉ | 2026-07 | 2026-08 | Inchangé au caractère près → **AV1** (commit a09fafd, 2026-08-09) |
| 2026-07/A1-07 | `GET /api/watchlist/` sans consommateur | basse | CORRIGÉ | 2026-07 | 2026-08 | 2e audit consécutif → SUPPRESSION actée (Q4 2026-08), **AV6** (tests follow réécrits sur /browse) (commit f15b52c, 2026-08-15) |
| 2026-07/A2-13 | Import Rekordbox : upsert par piste | basse | OUVERT | 2026-07 | 2026-08 | Inchangé (= 2026-08/A2-08) ; arbitrage maintenu : au prochain passage sur import_rb, pas de chantier dédié |
| 2026-07/A5-11 | Tags d'images Docker flottants | basse | CORRIGÉ | 2026-07 | 2026-08 | minio/certbot pinnés (AU2) ; restent nginx/node/python → 2026-08/A5-06, **AV2** (commit 50a1e39 + hotfix jinja2 3c0c8b6, 2026-08-10) |
| 2026-07/A6-06 | Wildcards LIKE non échappés | basse | CORRIGÉ | 2026-07 | 2026-08 | `like_escape` créé (AU1) mais 6-8 sites D6/D8 repartis sur `f"%{q}%"` brut → **AV1** (commit a09fafd, 2026-08-09) |
| 2026-07/A6-08 | Cœur upsert PG de l'import RB non testé | basse | CORRIGÉ | 2026-07 | 2026-08 | Lock/parsing/scope testés depuis ; upsert toujours skippé ; `tasks/*` toujours dans l'omit → **AV7** (AV7, 2026-08-16) |
| 2026-07/A6-14 | Branches d'échec OAuth non testées | basse | CORRIGÉ | 2026-07 | 2026-08 | `invalid_state` testé ; google_failed/collision/verify_google_token nus → 2026-08/A6-07, **AV7** (AV7, 2026-08-16) |
| 2026-07/A7-05 | Compteurs CLAUDE.md faux | basse | CORRIGÉ | 2026-07 | 2026-08-24 | Corrigés AU8, re-drift → AV7 (2026-08-16), re-drift C7/C9 en 8 jours → **3e récurrence** 2026-08-24/A7-01, **AW5** (+ processus de bump en clôture de chantier) |
| 2026-07/A7-11 | README de triage des scripts incomplet | basse | CORRIGÉ | 2026-07 | 2026-08-24 | Corrigé AV1 (a09fafd), puis 8 scripts ajoutés en 15 jours sans inventaire → **3e récurrence** 2026-08-24/A7-03, **AW5** |
| 2026-07/A2-11 | FK sans index (artist_activity, user_radar_state, collection_items) | basse | ACCEPTÉ | 2026-07 | 2026-08-24 | Cœur corrigé en 0031 ; différé « réévaluer à la croissance » ; 2026-08-24 : `user_collections.folder_id` (2026-08-24/A2-06) rattaché au même arbitrage (volumétrie dérisoire) |
| 2026-07/A1-12 | 11 endpoints taxonomy réservés | basse | ACCEPTÉ | 2026-07 | 2026-08 | DECISIONS 2026-07 Q1b-2 ; réécrits en ORM + like_escape depuis — résidu inchangé |
| 2026-07/A2-05 | Colonnes `artists.bio/country/real_name/soundcloud_id` | basse | ACCEPTÉ | 2026-07 | 2026-08 | Q3 2026-07 : schemas purgés, colonnes conservées |
| 2026-07/A2-08 | Colonnes `sets.event/venue/description` | basse | ACCEPTÉ | 2026-07 | 2026-08 | Q3 2026-07 : schemas purgés, colonnes conservées |
| 2026-07/M3 | Tokens TIDAL dans l'historique git | critique (rotation faite) | ACCEPTÉ | 2026-07 | 2026-08 | Rotation + git rm + .gitignore faits ; purge refusée (Q4-B) avec CONDITION : `git filter-repo` obligatoire si le repo s'ouvre |
| 2026-07/A5-17 | Stack locale full-stack non fonctionnelle | basse | ACCEPTÉ | 2026-07 | 2026-08 | Q6 2026-07 : non supporté (push→CI→prod) ; la phrase CLAUDE.md contradictoire → 2026-08/A5-05, AV7 |

## Findings de l'audit 2026-08

Arbitrés le 2026-08-09 (`docs/audits/2026-08/DECISIONS.md`, Q1-Q8). Fusions : M1=A1-01 (⊂A6-01), M2=A3-02 (⊂A8-02), M3=A3-04 (⊂A8-04), M5=A1-07 (⊂A6-04), M6=A4-10 (⊂A8-06).

| Clé | Titre | Sévérité | Statut | Découvert | Dernière vue | Résolution / Référence |
|---|---|---|---|---|---|---|
| 2026-08/A1-01 | Fuite inter-users `lib_sub` Artist Detail (M1, aussi vu par A6) | haute | CORRIGÉ | 2026-08 | 2026-08 | **AV1** — fix 1 ligne + test 2 users (commit a09fafd, 2026-08-09) |
| 2026-08/A1-02 | Pool similarité ~256k lignes rematérialisé par requête, /similar public sans cache | haute | CORRIGÉ | 2026-08 | 2026-08 | **AV3** — cache Redis (seed, viewer) TTL 6h (Q3a) ; pool précalculé = chantier conditionnel hors série (commit 593ab47, 2026-08-10) |
| 2026-08/A1-03 | Invalidation cache reco absente du chemin d'avis principal | moyenne | CORRIGÉ | 2026-08 | 2026-08 | **AV1** (commit a09fafd, 2026-08-09) |
| 2026-08/A1-04 | `fetch-artworks` playlists jamais commité | moyenne | CORRIGÉ | 2026-08 | 2026-08 | **AV1** (commit a09fafd, 2026-08-09) |
| 2026-08/A1-05 | Surface Radar v1 morte (4 endpoints + 4 fonctions service) | moyenne | CORRIGÉ | 2026-08 | 2026-08 | SUPPRESSION actée (Q4) → **AV6** ; UserRadarState/opinion_sync intacts (commit f15b52c, 2026-08-15) |
| 2026-08/A1-06 | Tris paginés sans tie-break id (Genre Detail ×4) | moyenne | CORRIGÉ | 2026-08 | 2026-08 | **AV1** (la part list_followed tombe avec la suppression Q4) (commit a09fafd, 2026-08-09) |
| 2026-08/A1-07 | Rate limits absents : sets/search, preview-url, similar ×2 (M5) | moyenne | CORRIGÉ | 2026-08 | 2026-08 | **AV1** (commit a09fafd, 2026-08-09) |
| 2026-08/A1-08 | Routers ré-engraissés (sets.list_sets, admin.get_backlog, radar.list_trends, list_set_flags) | moyenne | CORRIGÉ | 2026-08 | 2026-08 | **AV6** (commit f15b52c, 2026-08-15) |
| 2026-08/A1-09 | Doc : `similar_from_context` n'est plus la primitive C4 ; reco consomme des membres privés | basse | CORRIGÉ | 2026-08 | 2026-08 | **AV7** (lot doc) (AV7, 2026-08-16) |
| 2026-08/A1-10 | `TrackIDClient.get_styles` mort | basse | CORRIGÉ | 2026-08 | 2026-08 | SUPPRESSION (Q4) → **AV1** (commit a09fafd, 2026-08-09) |
| 2026-08/A1-11 | Excepts muets intégrations Deezer admin | basse | CORRIGÉ | 2026-08 | 2026-08 | **AV1** (logger a minima) (commit a09fafd, 2026-08-09) |
| 2026-08/A1-12 | Redis API : client sync middleware + connexion/requête get_redis | basse | OUVERT | 2026-08 | 2026-08 | Différé — à reprendre si un stall Redis est observé |
| 2026-08/A2-01 | Tris Explorer sans index composite (seq scan 256k/page) | moyenne | CORRIGÉ | 2026-08 | 2026-08 | **AV3** (migration groupée) (commit 593ab47, 2026-08-10) |
| 2026-08/A2-02 | Index radar_trends manquants | moyenne | CORRIGÉ | 2026-08 | 2026-08 | **AV3** — clé d'origine 2026-07/A2-14 (commit 593ab47, 2026-08-10) |
| 2026-08/A2-03 | `catalog.needs_reconciliation` + `catalog.status` mortes + MANUAL block mensonger | basse | CORRIGÉ | 2026-08 | 2026-08 | DROP acté (Q5) → **AV3** (commit 593ab47, 2026-08-10) |
| 2026-08/A2-04 | `catalog.origin` write-only et fausse par construction | basse | CORRIGÉ | 2026-08 | 2026-08 | DROP acté (Q5) → **AV3** (commit 593ab47, 2026-08-10) |
| 2026-08/A2-05 | `sets.platform` morte (99,7 % NULL) | basse | CORRIGÉ | 2026-08 | 2026-08 | DROP acté (Q5) → **AV3** (commit 593ab47, 2026-08-10) |
| 2026-08/A2-06 | `metric_snapshots`/`crawl_logs` sans rétention | basse | CORRIGÉ | 2026-08 | 2026-08 | Purge >13 mois dans snapshot_backlogs (Q5) → **AV3** (commit 593ab47, 2026-08-10) |
| 2026-08/A2-07 | Prédicat backlog BPM = seq scan 28×/j de la plus grosse table | basse | CORRIGÉ | 2026-08 | 2026-08 | Index partiel → **AV3** (commit 593ab47, 2026-08-10) |
| 2026-08/A2-08 | Upsert import RB par piste | basse | OUVERT | 2026-08 | 2026-08 | Clé d'origine 2026-07/A2-13 — opportuniste, au prochain passage |
| 2026-08/A2-09 | /api/sets/ : agrégat par page + tie-break non unique | basse | CORRIGÉ | 2026-08 | 2026-08 | Tie-break id → **AV3** ; dénormalisation track_count différée (~1 M set_tracks) (commit 593ab47, 2026-08-10) |
| 2026-08/A3-01 | Bouton admin auto-classify : kwarg `genre_only` inexistant → TypeError silencieux | haute | CORRIGÉ | 2026-08 | 2026-08 | **AV1** (avec A3-06 qui l'a masqué) (commit a09fafd, 2026-08-09) |
| 2026-08/A3-02 | Beatport async : outage consomme une tentative E1 (M2, aussi vu par A8) | moyenne | CORRIGÉ | 2026-08 | 2026-08 | **AV4** — BeatportHTTPError typée, miroir du fix Deezer (commit aad0a07, 2026-08-12) |
| 2026-08/A3-03 | Jumeau `enrich_catalog` Deezer : autoretry + soft 2h + sans lock | moyenne | CORRIGÉ | 2026-08 | 2026-08 | **AV4** — clôt la fiche mémoire `enrich-beatport-autoretry` (commit aad0a07, 2026-08-12) |
| 2026-08/A3-04 | `autoretry_for=(Exception,)` résiduel ×8-11 tâches (M3, aussi vu par A8) | moyenne | CORRIGÉ | 2026-08 | 2026-08 | **AV4** (commit aad0a07, 2026-08-12) |
| 2026-08/A3-05 | SoftTimeLimitExceeded avalé par les except par-item (recrawl, trackid_latest) | moyenne | CORRIGÉ | 2026-08 | 2026-08 | **AV4** — clause-guard pattern backfill (commit aad0a07, 2026-08-12) |
| 2026-08/A3-06 | DLQ structurellement vide (garde retries < max_retries) | moyenne | CORRIGÉ | 2026-08 | 2026-08 | **AV1** (commit a09fafd, 2026-08-09) |
| 2026-08/A3-07 | CrawlLogger : transaction ouverte ~55 min/run, run tué = 0 trace | moyenne | CORRIGÉ | 2026-08 | 2026-08 | **AV4** — commit du `running` à l'enter (commit aad0a07, 2026-08-12) |
| 2026-08/A3-08 | Routing : sync_artists/backfill/reclassify sur `celery` au lieu d'`enrich` | moyenne | CORRIGÉ | 2026-08 | 2026-08 | **AV4** (commit aad0a07, 2026-08-12) |
| 2026-08/A3-09 | Merge catalog ne reporte pas bpm_analyzed_at/attempts | basse | CORRIGÉ | 2026-08 | 2026-08 | **AV4** (commit aad0a07, 2026-08-12) |
| 2026-08/A3-10 | `DEFAULT_ANALYSIS_BPM_BATCH_SIZE` + `workers/db.get_session` morts | basse | CORRIGÉ | 2026-08 | 2026-08 | SUPPRESSION (Q4) → **AV1** (commit a09fafd, 2026-08-09) |
| 2026-08/A3-11 | Commentaires backfill 1000 / visibility_timeout périmés | basse | CORRIGÉ | 2026-08 | 2026-08 | **AV7** (lot doc) (AV7, 2026-08-16) |
| 2026-08/A3-12 | backfill_multi_artists : commit mid-gather + gather non borné | basse | CORRIGÉ | 2026-08 | 2026-08 | **AV4** (commit aad0a07, 2026-08-12) |
| 2026-08/A4-01 | ExplorerView ↔ RadarView jumelles à ~80 % (1238 lignes identiques) | haute | CORRIGÉ | 2026-08 | 2026-08 | **AV5** — extraction table partagée + vérif CDP (Q6) (commit 43e0302, 2026-08-15) |
| 2026-08/A4-02 | fetchUpTo : salve de 12 requêtes parallèles sur /radar/feed | haute | CORRIGÉ | 2026-08 | 2026-08 | **AV1** — concurrence 2-3, les 2 composables (commit a09fafd, 2026-08-09) |
| 2026-08/A4-03 | Facette liked/disliked GenresView bornée aux 24 premiers | moyenne | CORRIGÉ | 2026-08 | 2026-08 | **AV1** (commit a09fafd, 2026-08-09) |
| 2026-08/A4-04 | SetsView ↔ WatchlistView jumelles (~878 lignes communes) | moyenne | CORRIGÉ | 2026-08 | 2026-08 | **AV5** (commit 43e0302, 2026-08-15) |
| 2026-08/A4-05 | Branche « opinion mode » ×3, plafonds silencieux 100/200 | moyenne | CORRIGÉ | 2026-08 | 2026-08 | **AV5** (commit 43e0302, 2026-08-15) |
| 2026-08/A4-06 | HubView 211 kB dans le chunk principal | moyenne | CORRIGÉ | 2026-08 | 2026-08 | **AV5** — clé d'origine 2026-07/A4-09 (commit 43e0302, 2026-08-15) |
| 2026-08/A4-07 | Composants morts : PageHero, RingPct, ScorePill/InLibBadge (vitrine) | basse | CORRIGÉ | 2026-08 | 2026-08 | SUPPRESSION (Q4) → **AV6** (commit f15b52c, 2026-08-15) |
| 2026-08/A4-08 | Timer de débounce useUrlSync/useFilterState fuitant sur la route suivante | basse | CORRIGÉ | 2026-08 | 2026-08 | **AV1** — onScopeDispose (commit a09fafd, 2026-08-09) |
| 2026-08/A4-09 | audioPlayer : échec preview non-503 ferme la file au lieu de skipper | basse | CORRIGÉ | 2026-08 | 2026-08 | **AV1** (commit a09fafd, 2026-08-09) |
| 2026-08/A4-10 | table.css : @media viewport hors exception fixed (M6, aussi vu par A8) | basse | CORRIGÉ | 2026-08 | 2026-08 | **AV5** — `@media (hover: none)` (commit 43e0302, 2026-08-15) |
| 2026-08/A5-01 | Gate pip-audit doublement non-bloquant | haute | CORRIGÉ | 2026-08 | 2026-08 | **AV2** APRÈS upgrades (Q2) — clé d'origine 2026-07/A5-04 (commit 50a1e39 + hotfix jinja2 3c0c8b6, 2026-08-10) |
| 2026-08/A5-02 | Alerte fraîcheur backup = cul-de-sac (log 22 Mo, aucun canal) | moyenne | CORRIGÉ | 2026-08 | 2026-08 | **AV1** — canal push + logrotate (commit a09fafd, 2026-08-09) |
| 2026-08/A5-03 | MinIO à 99,55 % de son cap 2G en 5 jours | moyenne | CORRIGÉ | 2026-08 | 2026-08 | BUMP 3G + GOMEMLIMIT 2700 (Q7) → **AV1** (commit a09fafd, 2026-08-09) |
| 2026-08/A5-04 | Doc : image worker « 312 Mo » vs 852 MB réels | basse | CORRIGÉ | 2026-08 | 2026-08 | **AV7** (lot doc) (AV7, 2026-08-16) |
| 2026-08/A5-05 | Doc : « full local app sur localhost:8080 » contredit Q6 | basse | CORRIGÉ | 2026-08 | 2026-08 | **AV7** (lot doc) (AV7, 2026-08-16) |
| 2026-08/A5-06 | Tags flottants restants (nginx:alpine ×2, node, python) | basse | CORRIGÉ | 2026-08 | 2026-08 | **AV2** — clé d'origine 2026-07/A5-11 (commit 50a1e39 + hotfix jinja2 3c0c8b6, 2026-08-10) |
| 2026-08/A5-07 | npm : 5 vulns dev/build + 4 majeurs de retard | basse | CORRIGÉ | 2026-08 | 2026-08 | Volet 1 (audit fix) → **AV1** (commit a09fafd, 2026-08-09) ; volet 2 → chantier « Majeurs frontend » (Q8, hors AV) |
| 2026-08/A6-02 | /api/radar/feed hors rate limiting malgré l'incident OOM | haute | CORRIGÉ | 2026-08 | 2026-08 | **AV1** (commit a09fafd, 2026-08-09) |
| 2026-08/A6-03 | python-jose/multipart/starlette vulnérables (26 avis, exposition évaluée) | haute | CORRIGÉ | 2026-08 | 2026-08 | **AV2** — upgrades AVANT le gate (Q2) (commit 50a1e39 + hotfix jinja2 3c0c8b6, 2026-08-10) |
| 2026-08/A6-05 | External search : lookup catalog sans catalog_visible (divulgation d'existence) | basse | CORRIGÉ | 2026-08 | 2026-08 | **AV7** — + documenter l'exception d'intégrité import_external (AV7, 2026-08-16) |
| 2026-08/A6-06 | LIKE wildcards ×6-8 sites refondus | basse | CORRIGÉ | 2026-08 | 2026-08 | **AV1** — clé d'origine 2026-07/A6-06 (commit a09fafd, 2026-08-09) |
| 2026-08/A6-07 | Branches google_callback non testées | basse | CORRIGÉ | 2026-08 | 2026-08 | **AV7** — clé d'origine 2026-07/A6-14 (AV7, 2026-08-16) |
| 2026-08/A6-08 | Upsert PG import RB non testé | basse | CORRIGÉ | 2026-08 | 2026-08 | **AV7** — clé d'origine 2026-07/A6-08 (AV7, 2026-08-16) |
| 2026-08/A6-09 | crawl-status sans dépendance user | basse | CORRIGÉ | 2026-08 | 2026-08 | **AV1** — une ligne (commit a09fafd, 2026-08-09) |
| 2026-08/A7-01 | CLAUDE.md : 4 compteurs faux ou incohérents | moyenne | CORRIGÉ | 2026-08 | 2026-08 | **AV7** — clé d'origine 2026-07/A7-05 (pattern) (AV7, 2026-08-16) |
| 2026-08/A7-02 | ROADMAP : D4/D7 livrés non clos | moyenne | CORRIGÉ | 2026-08 | 2026-08 | **IMMÉDIAT** hors série : passer `/roadmap_update` (commit d0bbc11, 2026-08-09) |
| 2026-08/A7-03 | 3 scripts X1/X3 absents du triage README | basse | CORRIGÉ | 2026-08 | 2026-08 | **AV1** — clé d'origine 2026-07/A7-11 (commit a09fafd, 2026-08-09) |
| 2026-08/A7-04 | Chemins `scripts/` ambigus dans CLAUDE.md | basse | CORRIGÉ | 2026-08 | 2026-08 | **AV7** (lot doc) (AV7, 2026-08-16) |
| 2026-08/A8-01 | Invariant #1 à re-scoper (relocate_tracks écrit dans Rekordbox) | basse | CORRIGÉ | 2026-08 | 2026-08 | **AV7** (lot doc) (AV7, 2026-08-16) |
| 2026-08/A8-03 | Six tâches longues sans lock Redis | moyenne | CORRIGÉ | 2026-08 | 2026-08 | **AV4** (commit aad0a07, 2026-08-12) |
| 2026-08/A8-05 | Doc : uq_artists_deezer_id porté par 0034, CLAUDE.md dit le contraire | basse | CORRIGÉ | 2026-08 | 2026-08 | **AV7** (lot doc) (AV7, 2026-08-16) |

## Findings de l'audit 2026-08-24

Arbitrés le 2026-08-24 (`docs/audits/2026-08-24/DECISIONS.md`, Q1-Q7). Fusions : M1=A1-05 (⊂A6-01), M2=A2-04 (⊂A6-03), M3=A3-02 (⊂A8-01), M4=A5-05 (⊂A7-06).

| Clé | Titre | Sévérité | Statut | Découvert | Dernière vue | Résolution / Référence |
|---|---|---|---|---|---|---|
| 2026-08-24/A3-01 | Sortie deadline backfill TrackID → chemin de complétion normale (faux done terminal + curseur clobbé) — régression 3dcb68c | haute | EN ROADMAP | 2026-08-24 | 2026-08-24 | **AW1** |
| 2026-08-24/A4-01 | Injection HTML via v-html dans le highlight de recherche du Hub | haute | EN ROADMAP | 2026-08-24 | 2026-08-24 | **AW1** |
| 2026-08-24/A5-01 | Cap postgres 1G vs pgvector ~3,5G à terme (940 MB à 24 % du backfill) | haute | EN ROADMAP | 2026-08-24 | 2026-08-24 | **AW1** — geste OPS fenêtre calme (Q5), avant la fin du backfill C9.a |
| 2026-08-24/A1-05 | content-similar : gate admin front-only, endpoint public (M1, aussi vu par A6) | moyenne | EN ROADMAP | 2026-08-24 | 2026-08-24 | **AW1** — require_admin serveur le temps du ramp-up (Q2a) |
| 2026-08-24/A6-02 | content-similar hors rate limiting (suffixe /similar non matché) | moyenne | EN ROADMAP | 2026-08-24 | 2026-08-24 | **AW1** |
| 2026-08-24/A1-06 | content-similar : 200 [] caché 6h pour un id inexistant (vs 404 sur /similar) | basse | EN ROADMAP | 2026-08-24 | 2026-08-24 | **AW1** |
| 2026-08-24/A2-01 | catalog_merge ne repointe pas catalog_albums (liens album perdus au merge) | moyenne | EN ROADMAP | 2026-08-24 | 2026-08-24 | **AW1** |
| 2026-08-24/A5-02 | backup.sh mirrore 3 buckets MinIO sur 6 | moyenne | EN ROADMAP | 2026-08-24 | 2026-08-24 | **AW1** |
| 2026-08-24/A4-02 | Bouton « Ajouter à la bib » sans handler | moyenne | EN ROADMAP | 2026-08-24 | 2026-08-24 | SUPPRESSION du bouton (Q3) → **AW1** |
| 2026-08-24/A4-03 | CollectionCard : « N tracks » faux depuis les items polymorphes | basse | EN ROADMAP | 2026-08-24 | 2026-08-24 | **AW1** |
| 2026-08-24/A4-04 | CollectionCard : suppression invisible au tactile (hover-only) | moyenne | EN ROADMAP | 2026-08-24 | 2026-08-24 | **AW1** (vérif CDP) |
| 2026-08-24/A4-06 | audioPlayer : volume sauvegardé à 0 revient à 0.8 | basse | EN ROADMAP | 2026-08-24 | 2026-08-24 | **AW1** |
| 2026-08-24/A4-08 | Listener document click ExplorerView non détaché sous KeepAlive | basse | EN ROADMAP | 2026-08-24 | 2026-08-24 | **AW1** |
| 2026-08-24/A1-08 | Commentaire auth_middleware cite /radar/full supprimé AV6 | basse | EN ROADMAP | 2026-08-24 | 2026-08-24 | **AW1** |
| 2026-08-24/A1-02 | total_identified : N+1 par candidat, champ sans consommateur | basse | EN ROADMAP | 2026-08-24 | 2026-08-24 | SUPPRESSION (Q3) → **AW1** |
| 2026-08-24/A1-03 | similar_from_context sans caller (2 audits) | basse | EN ROADMAP | 2026-08-24 | 2026-08-24 | SUPPRESSION (Q3) → **AW1** |
| 2026-08-24/A3-06 | CrawlLogger.update_stats + log_id morts | basse | EN ROADMAP | 2026-08-24 | 2026-08-24 | SUPPRESSION (Q3) → **AW1** |
| 2026-08-24/A7-04 | Fichiers égarés non trackés (docs/c9-benchmark;C, node_modules racine, __pycache__) | basse | EN ROADMAP | 2026-08-24 | 2026-08-24 | **AW1** (nettoyage disque, pas de commit) |
| 2026-08-24/A3-02 | Deadline AV9 absente des drains restants (precompute/trackid_latest/recrawl/sync_artists) (M3, aussi vu par A8) | moyenne | EN ROADMAP | 2026-08-24 | 2026-08-24 | **AW2** — après A3-01 |
| 2026-08-24/A3-03 | Batch BPM 2000 inatteignable sous throttle — deadline_hit neutralisé comme signal | moyenne | EN ROADMAP | 2026-08-24 | 2026-08-24 | **AW2** |
| 2026-08-24/A3-04 | Doc fenêtre BPM : 00h→04h/5 créneaux vs doc 00h→03h/~8000 par nuit | basse | EN ROADMAP | 2026-08-24 | 2026-08-24 | **AW2** (avec A3-03) |
| 2026-08-24/A3-08 | precompute_recommendations sans CrawlLogger (invisible du monitoring) | basse | EN ROADMAP | 2026-08-24 | 2026-08-24 | **AW2** |
| 2026-08-24/A1-04 | Waiter single-flight reco : connexion DB épinglée ≤48s pendant le poll | moyenne | EN ROADMAP | 2026-08-24 | 2026-08-24 | **AW2** — rollback avant la boucle d'attente |
| 2026-08-24/A3-05 | Sélection BPM id DESC + échecs download sans plafond (tête de file re-consommée) | basse | OUVERT | 2026-08-24 | 2026-08-24 | Attend le diagnostic OPS « ~50 % erreurs BPM » (mémoire monitoring-backlogs-tuning) ; instrumenter d'abord |
| 2026-08-24/A6-04 | Tests multi-user Collections absents (ownership + track privé) | moyenne | EN ROADMAP | 2026-08-24 | 2026-08-24 | **AW3** — tests AVANT l'extraction A1-01 |
| 2026-08-24/A1-01 | Collections : 529 lignes de logique en router, zéro service (3e occurrence du pattern) | moyenne | EN ROADMAP | 2026-08-24 | 2026-08-24 | **AW3** — extraction collection_service façon AV6 |
| 2026-08-24/A2-04 | Dédup collection_items sans contrainte DB → doublon possible, DELETE 500, downgrade 0047 cassé (M2, aussi vu par A6) | basse | EN ROADMAP | 2026-08-24 | 2026-08-24 | **AW3** — 2 index uniques partiels + IntegrityError→409 (Q4) |
| 2026-08-24/A2-03 | Downgrade 0046 asymétrique (type PG album_type survit) | basse | EN ROADMAP | 2026-08-24 | 2026-08-24 | **AW3** — même migration que M2 |
| 2026-08-24/A4-05 | AddToCollectionButton : dropdown sans click-outside ni catch | basse | EN ROADMAP | 2026-08-24 | 2026-08-24 | **AW3** |
| 2026-08-24/A4-09 | CollectionsView hors allowlist KeepAlive (décision non documentée) | basse | EN ROADMAP | 2026-08-24 | 2026-08-24 | **AW3** — documenter ou intégrer |
| 2026-08-24/A4-11 | Duplication rows typées CollectionDetailView ↔ HubSearchResults | basse | EN ROADMAP | 2026-08-24 | 2026-08-24 | **AW3** — extraction helpers avant un 6e type d'item |
| 2026-08-24/A5-03 | mc téléchargé non pinné à chaque backup (supply chain + offsite sauté si CDN down) | moyenne | EN ROADMAP | 2026-08-24 | 2026-08-24 | **AW4** — image backup dédiée pinnée |
| 2026-08-24/A5-04 | CRON_TZ ignoré par cron Ubuntu — tous les crons VPS en UTC | moyenne | EN ROADMAP | 2026-08-24 | 2026-08-24 | **AW4** — crontab réécrit en UTC (geste OPS) |
| 2026-08-24/A5-05 | restore.md pré-pgvector : restore vanilla échoue, test 2026-07-10 antérieur au schéma (M4, aussi vu par A7) | moyenne | EN ROADMAP | 2026-08-24 | 2026-08-24 | Doc → **AW1** ; re-test restore complet + re-stamp → **AW4** |
| 2026-08-24/A5-06 | Setup SSH CI : keyscan TOFU, erreurs avalées (incident déjà vécu) | moyenne | EN ROADMAP | 2026-08-24 | 2026-08-24 | **AW4** — secret VPS_KNOWN_HOSTS figé |
| 2026-08-24/A5-08 | Health check post-deploy : 1 curl après sleep 15s | basse | EN ROADMAP | 2026-08-24 | 2026-08-24 | **AW4** |
| 2026-08-24/A5-09 | Aucun timeout-minutes sur les jobs CI | basse | EN ROADMAP | 2026-08-24 | 2026-08-24 | **AW4** |
| 2026-08-24/A5-10 | Redis sans maxmemory sous cap cgroup 512M | basse | EN ROADMAP | 2026-08-24 | 2026-08-24 | **AW4** — maxmemory 400mb, noeviction conservé |
| 2026-08-24/A7-01 | Compteurs CLAUDE.md re-driftés (106 endpoints, 32 tables, 39 defs, 18 services) | moyenne | EN ROADMAP | 2026-08-24 | 2026-08-24 | **AW5** — clé d'origine 2026-07/A7-05 (3e récurrence) ; + processus de bump en clôture |
| 2026-08-24/A7-02 | CLAUDE.md « C9.b not built yet » vs C9.b livré le jour même | basse | EN ROADMAP | 2026-08-24 | 2026-08-24 | **AW5** |
| 2026-08-24/A7-03 | README triage scripts : 8 scripts absents | basse | EN ROADMAP | 2026-08-24 | 2026-08-24 | **AW5** — clé d'origine 2026-07/A7-11 (3e récurrence) |
| 2026-08-24/A2-02 | MANUAL block schema doc périmé (colonnes droppées, note NULLS LAST absente, HNSW invisible) | basse | EN ROADMAP | 2026-08-24 | 2026-08-24 | **AW5** |
| 2026-08-24/A7-05 | docs/prompts/ gitignoré mais pointé comme doc de référence | basse | EN ROADMAP | 2026-08-24 | 2026-08-24 | **AW5** — trancher versionner vs annoter |
| 2026-08-24/A1-07 | _MAX_SEARCH_ATTEMPTS dupliqué main-synced worker→API | basse | EN ROADMAP | 2026-08-24 | 2026-08-24 | **AW5** — test de cohérence anti-drift |
| 2026-08-24/A8-02 | Couleurs logo Google LoginView : exception de marque non documentée | basse | EN ROADMAP | 2026-08-24 | 2026-08-24 | **AW5** — documenter l'exception, ne pas tokeniser |
| 2026-08-24/A2-06 | user_collections.folder_id : FK sans index | basse | ACCEPTÉ | 2026-08-24 | 2026-08-24 | Rattaché à l'arbitrage 2026-07/A2-11 (« réévaluer à la croissance ») |
| 2026-08-24/A1-10 | Tracklist album ordonnée par id, pas par position disque | basse | EN ROADMAP | 2026-08-24 | 2026-08-24 | **C7.c** (Q4) — colonne track_position + funnel + backfill, hors série AW |
| 2026-08-24/A5-07 | IP amont nginx périmée sur deploy manuel — resolver 127.0.0.11 | moyenne | EN ROADMAP | 2026-08-24 | 2026-08-24 | Chantier « nginx resolver » hors série (Q7) ; absorbe A5-12 |
| 2026-08-24/A5-11 | Build des images sur le VPS de prod à chaque deploy | basse | EN ROADMAP | 2026-08-24 | 2026-08-24 | Chantier « Build GHCR » hors série, planifié priorité basse (Q7) |
| 2026-08-24/A5-12 | default.conf/empty.conf : doublons vides montés sur la même cible | basse | EN ROADMAP | 2026-08-24 | 2026-08-24 | Absorbé par le chantier nginx resolver (A5-07) |
| 2026-08-24/A2-05 | Recall KNN HNSW post-filtré non garanti (ef_search 40 vs filtres) | moyenne | OUVERT | 2026-08-24 | 2026-08-24 | À MESURER (EXPLAIN ANALYZE) après la fin du backfill C9.a ; consigne v2-modèle à documenter |
| 2026-08-24/A3-07 | link_set_artists : scan O(N·M) + SELECT/commit par set | basse | OUVERT | 2026-08-24 | 2026-08-24 | Opportuniste — au prochain passage sur la tâche |
| 2026-08-24/A6-05 | embedding_backfill sans test + constantes modèle dupliquées sans garde | basse | OUVERT | 2026-08-24 | 2026-08-24 | Opportuniste — test constants-in-sync + helpers purs |
| 2026-08-24/A1-09 | Router sets : résidu logique métier (détail, import+opinion, client TrackID) | basse | OUVERT | 2026-08-24 | 2026-08-24 | Opportuniste — après AW3, même patron d'extraction |
| 2026-08-24/A4-07 | Recherche Hub non gardée contre les réponses désordonnées | basse | OUVERT | 2026-08-24 | 2026-08-24 | Opportuniste |
| 2026-08-24/A4-10 | Littéraux oklch hors tokens (pastille genre à vérifier en dark) | basse | OUVERT | 2026-08-24 | 2026-08-24 | Opportuniste — vérif CDP |
| 2026-08-24/A4-12 | AlbumView sans watch route.params.id | basse | OUVERT | 2026-08-24 | 2026-08-24 | Opportuniste — 3 lignes, à prendre avec C7.c |
