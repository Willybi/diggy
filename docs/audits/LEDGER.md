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
| 2026-07/A5-04 | Gate CI pip-audit non bloquant | haute (aggravée) | EN ROADMAP | 2026-07 | 2026-08 | AU1 a corrigé la CIBLE du job, pas son caractère non-bloquant ; 26 vulns derrière → 2026-08/A5-01, **AV2** (après upgrades A6-03, Q2) |
| 2026-07/A4-09 | HubView dans le chunk principal | moyenne | EN ROADMAP | 2026-07 | 2026-08 | Clos « non justifié » en AU6 (191,9 kB) ; cliquet vérifié : 211,6 kB après D6 → 2026-08/A4-06, **AV5** |
| 2026-07/A2-14 | Tris `radar_trends` sans index | moyenne (aggravée) | EN ROADMAP | 2026-07 | 2026-08 | Table ×4 en un mois, 2 consommateurs guests, seq scan prouvé → 2026-08/A2-02, **AV3** |
| 2026-07/A1-04 | I/O synchrone bloquante dans l'event loop | moyenne | EN ROADMAP | 2026-07 | 2026-08 | Corrigé sur watchlist/import externe ; restent 5 sites (admin search-deezer, link_to_deezer, enrich_single_beatport, boucle artworks, upload import) → **AV3** |
| 2026-07/A1-10 | attach/detach dédup sets dans `routers/admin.py` | moyenne | EN ROADMAP | 2026-07 | 2026-08 | Rattaché C6 par Q8 2026-07, jamais exécuté ; aggravé par les group-flags → **AV6** |
| 2026-07/A1-11 | `detach_set` sans garde `is_virtual` | basse | EN ROADMAP | 2026-07 | 2026-08 | Inchangé au caractère près → **AV1** |
| 2026-07/A1-07 | `GET /api/watchlist/` sans consommateur | basse | EN ROADMAP | 2026-07 | 2026-08 | 2e audit consécutif → SUPPRESSION actée (Q4 2026-08), **AV6** (tests follow réécrits sur /browse) |
| 2026-07/A2-13 | Import Rekordbox : upsert par piste | basse | OUVERT | 2026-07 | 2026-08 | Inchangé (= 2026-08/A2-08) ; arbitrage maintenu : au prochain passage sur import_rb, pas de chantier dédié |
| 2026-07/A5-11 | Tags d'images Docker flottants | basse | EN ROADMAP | 2026-07 | 2026-08 | minio/certbot pinnés (AU2) ; restent nginx/node/python → 2026-08/A5-06, **AV2** |
| 2026-07/A6-06 | Wildcards LIKE non échappés | basse | EN ROADMAP | 2026-07 | 2026-08 | `like_escape` créé (AU1) mais 6-8 sites D6/D8 repartis sur `f"%{q}%"` brut → **AV1** |
| 2026-07/A6-08 | Cœur upsert PG de l'import RB non testé | basse | EN ROADMAP | 2026-07 | 2026-08 | Lock/parsing/scope testés depuis ; upsert toujours skippé ; `tasks/*` toujours dans l'omit → **AV7** |
| 2026-07/A6-14 | Branches d'échec OAuth non testées | basse | EN ROADMAP | 2026-07 | 2026-08 | `invalid_state` testé ; google_failed/collision/verify_google_token nus → 2026-08/A6-07, **AV7** |
| 2026-07/A7-05 | Compteurs CLAUDE.md faux | basse | EN ROADMAP | 2026-07 | 2026-08 | Corrigés AU8 puis re-drift E2.c/X2 → 2026-08/A7-01, **AV7** |
| 2026-07/A7-11 | README de triage des scripts incomplet | basse | EN ROADMAP | 2026-07 | 2026-08 | Mécanisme vivant ; 3 scripts X1/X3 manquants → 2026-08/A7-03, **AV1** |
| 2026-07/A2-11 | FK sans index (artist_activity, user_radar_state, collection_items) | basse | ACCEPTÉ | 2026-07 | 2026-08 | Cœur corrigé en 0031 ; reste différé « réévaluer à la croissance » — re-vérifié 2026-08 : 62/5/0 lignes, arbitrage maintenu |
| 2026-07/A1-12 | 11 endpoints taxonomy réservés | basse | ACCEPTÉ | 2026-07 | 2026-08 | DECISIONS 2026-07 Q1b-2 ; réécrits en ORM + like_escape depuis — résidu inchangé |
| 2026-07/A2-05 | Colonnes `artists.bio/country/real_name/soundcloud_id` | basse | ACCEPTÉ | 2026-07 | 2026-08 | Q3 2026-07 : schemas purgés, colonnes conservées |
| 2026-07/A2-08 | Colonnes `sets.event/venue/description` | basse | ACCEPTÉ | 2026-07 | 2026-08 | Q3 2026-07 : schemas purgés, colonnes conservées |
| 2026-07/M3 | Tokens TIDAL dans l'historique git | critique (rotation faite) | ACCEPTÉ | 2026-07 | 2026-08 | Rotation + git rm + .gitignore faits ; purge refusée (Q4-B) avec CONDITION : `git filter-repo` obligatoire si le repo s'ouvre |
| 2026-07/A5-17 | Stack locale full-stack non fonctionnelle | basse | ACCEPTÉ | 2026-07 | 2026-08 | Q6 2026-07 : non supporté (push→CI→prod) ; la phrase CLAUDE.md contradictoire → 2026-08/A5-05, AV7 |

## Findings de l'audit 2026-08

Arbitrés le 2026-08-09 (`docs/audits/2026-08/DECISIONS.md`, Q1-Q8). Fusions : M1=A1-01 (⊂A6-01), M2=A3-02 (⊂A8-02), M3=A3-04 (⊂A8-04), M5=A1-07 (⊂A6-04), M6=A4-10 (⊂A8-06).

| Clé | Titre | Sévérité | Statut | Découvert | Dernière vue | Résolution / Référence |
|---|---|---|---|---|---|---|
| 2026-08/A1-01 | Fuite inter-users `lib_sub` Artist Detail (M1, aussi vu par A6) | haute | EN ROADMAP | 2026-08 | 2026-08 | **AV1** — fix 1 ligne + test 2 users |
| 2026-08/A1-02 | Pool similarité ~256k lignes rematérialisé par requête, /similar public sans cache | haute | EN ROADMAP | 2026-08 | 2026-08 | **AV3** — cache Redis (seed, viewer) TTL 6h (Q3a) ; pool précalculé = chantier conditionnel hors série |
| 2026-08/A1-03 | Invalidation cache reco absente du chemin d'avis principal | moyenne | EN ROADMAP | 2026-08 | 2026-08 | **AV1** |
| 2026-08/A1-04 | `fetch-artworks` playlists jamais commité | moyenne | EN ROADMAP | 2026-08 | 2026-08 | **AV1** |
| 2026-08/A1-05 | Surface Radar v1 morte (4 endpoints + 4 fonctions service) | moyenne | EN ROADMAP | 2026-08 | 2026-08 | SUPPRESSION actée (Q4) → **AV6** ; UserRadarState/opinion_sync intacts |
| 2026-08/A1-06 | Tris paginés sans tie-break id (Genre Detail ×4) | moyenne | EN ROADMAP | 2026-08 | 2026-08 | **AV1** (la part list_followed tombe avec la suppression Q4) |
| 2026-08/A1-07 | Rate limits absents : sets/search, preview-url, similar ×2 (M5) | moyenne | EN ROADMAP | 2026-08 | 2026-08 | **AV1** |
| 2026-08/A1-08 | Routers ré-engraissés (sets.list_sets, admin.get_backlog, radar.list_trends, list_set_flags) | moyenne | EN ROADMAP | 2026-08 | 2026-08 | **AV6** |
| 2026-08/A1-09 | Doc : `similar_from_context` n'est plus la primitive C4 ; reco consomme des membres privés | basse | EN ROADMAP | 2026-08 | 2026-08 | **AV7** (lot doc) |
| 2026-08/A1-10 | `TrackIDClient.get_styles` mort | basse | EN ROADMAP | 2026-08 | 2026-08 | SUPPRESSION (Q4) → **AV1** |
| 2026-08/A1-11 | Excepts muets intégrations Deezer admin | basse | EN ROADMAP | 2026-08 | 2026-08 | **AV1** (logger a minima) |
| 2026-08/A1-12 | Redis API : client sync middleware + connexion/requête get_redis | basse | OUVERT | 2026-08 | 2026-08 | Différé — à reprendre si un stall Redis est observé |
| 2026-08/A2-01 | Tris Explorer sans index composite (seq scan 256k/page) | moyenne | EN ROADMAP | 2026-08 | 2026-08 | **AV3** (migration groupée) |
| 2026-08/A2-02 | Index radar_trends manquants | moyenne | EN ROADMAP | 2026-08 | 2026-08 | **AV3** — clé d'origine 2026-07/A2-14 |
| 2026-08/A2-03 | `catalog.needs_reconciliation` + `catalog.status` mortes + MANUAL block mensonger | basse | EN ROADMAP | 2026-08 | 2026-08 | DROP acté (Q5) → **AV3** |
| 2026-08/A2-04 | `catalog.origin` write-only et fausse par construction | basse | EN ROADMAP | 2026-08 | 2026-08 | DROP acté (Q5) → **AV3** |
| 2026-08/A2-05 | `sets.platform` morte (99,7 % NULL) | basse | EN ROADMAP | 2026-08 | 2026-08 | DROP acté (Q5) → **AV3** |
| 2026-08/A2-06 | `metric_snapshots`/`crawl_logs` sans rétention | basse | EN ROADMAP | 2026-08 | 2026-08 | Purge >13 mois dans snapshot_backlogs (Q5) → **AV3** |
| 2026-08/A2-07 | Prédicat backlog BPM = seq scan 28×/j de la plus grosse table | basse | EN ROADMAP | 2026-08 | 2026-08 | Index partiel → **AV3** |
| 2026-08/A2-08 | Upsert import RB par piste | basse | OUVERT | 2026-08 | 2026-08 | Clé d'origine 2026-07/A2-13 — opportuniste, au prochain passage |
| 2026-08/A2-09 | /api/sets/ : agrégat par page + tie-break non unique | basse | EN ROADMAP | 2026-08 | 2026-08 | Tie-break id → **AV3** ; dénormalisation track_count différée (~1 M set_tracks) |
| 2026-08/A3-01 | Bouton admin auto-classify : kwarg `genre_only` inexistant → TypeError silencieux | haute | EN ROADMAP | 2026-08 | 2026-08 | **AV1** (avec A3-06 qui l'a masqué) |
| 2026-08/A3-02 | Beatport async : outage consomme une tentative E1 (M2, aussi vu par A8) | moyenne | EN ROADMAP | 2026-08 | 2026-08 | **AV4** — BeatportHTTPError typée, miroir du fix Deezer |
| 2026-08/A3-03 | Jumeau `enrich_catalog` Deezer : autoretry + soft 2h + sans lock | moyenne | EN ROADMAP | 2026-08 | 2026-08 | **AV4** — clôt la fiche mémoire `enrich-beatport-autoretry` |
| 2026-08/A3-04 | `autoretry_for=(Exception,)` résiduel ×8-11 tâches (M3, aussi vu par A8) | moyenne | EN ROADMAP | 2026-08 | 2026-08 | **AV4** |
| 2026-08/A3-05 | SoftTimeLimitExceeded avalé par les except par-item (recrawl, trackid_latest) | moyenne | EN ROADMAP | 2026-08 | 2026-08 | **AV4** — clause-guard pattern backfill |
| 2026-08/A3-06 | DLQ structurellement vide (garde retries < max_retries) | moyenne | EN ROADMAP | 2026-08 | 2026-08 | **AV1** |
| 2026-08/A3-07 | CrawlLogger : transaction ouverte ~55 min/run, run tué = 0 trace | moyenne | EN ROADMAP | 2026-08 | 2026-08 | **AV4** — commit du `running` à l'enter |
| 2026-08/A3-08 | Routing : sync_artists/backfill/reclassify sur `celery` au lieu d'`enrich` | moyenne | EN ROADMAP | 2026-08 | 2026-08 | **AV4** |
| 2026-08/A3-09 | Merge catalog ne reporte pas bpm_analyzed_at/attempts | basse | EN ROADMAP | 2026-08 | 2026-08 | **AV4** |
| 2026-08/A3-10 | `DEFAULT_ANALYSIS_BPM_BATCH_SIZE` + `workers/db.get_session` morts | basse | EN ROADMAP | 2026-08 | 2026-08 | SUPPRESSION (Q4) → **AV1** |
| 2026-08/A3-11 | Commentaires backfill 1000 / visibility_timeout périmés | basse | EN ROADMAP | 2026-08 | 2026-08 | **AV7** (lot doc) |
| 2026-08/A3-12 | backfill_multi_artists : commit mid-gather + gather non borné | basse | EN ROADMAP | 2026-08 | 2026-08 | **AV4** |
| 2026-08/A4-01 | ExplorerView ↔ RadarView jumelles à ~80 % (1238 lignes identiques) | haute | EN ROADMAP | 2026-08 | 2026-08 | **AV5** — extraction table partagée + vérif CDP (Q6) |
| 2026-08/A4-02 | fetchUpTo : salve de 12 requêtes parallèles sur /radar/feed | haute | EN ROADMAP | 2026-08 | 2026-08 | **AV1** — concurrence 2-3, les 2 composables |
| 2026-08/A4-03 | Facette liked/disliked GenresView bornée aux 24 premiers | moyenne | EN ROADMAP | 2026-08 | 2026-08 | **AV1** |
| 2026-08/A4-04 | SetsView ↔ WatchlistView jumelles (~878 lignes communes) | moyenne | EN ROADMAP | 2026-08 | 2026-08 | **AV5** |
| 2026-08/A4-05 | Branche « opinion mode » ×3, plafonds silencieux 100/200 | moyenne | EN ROADMAP | 2026-08 | 2026-08 | **AV5** |
| 2026-08/A4-06 | HubView 211 kB dans le chunk principal | moyenne | EN ROADMAP | 2026-08 | 2026-08 | **AV5** — clé d'origine 2026-07/A4-09 |
| 2026-08/A4-07 | Composants morts : PageHero, RingPct, ScorePill/InLibBadge (vitrine) | basse | EN ROADMAP | 2026-08 | 2026-08 | SUPPRESSION (Q4) → **AV6** |
| 2026-08/A4-08 | Timer de débounce useUrlSync/useFilterState fuitant sur la route suivante | basse | EN ROADMAP | 2026-08 | 2026-08 | **AV1** — onScopeDispose |
| 2026-08/A4-09 | audioPlayer : échec preview non-503 ferme la file au lieu de skipper | basse | EN ROADMAP | 2026-08 | 2026-08 | **AV1** |
| 2026-08/A4-10 | table.css : @media viewport hors exception fixed (M6, aussi vu par A8) | basse | EN ROADMAP | 2026-08 | 2026-08 | **AV5** — `@media (hover: none)` |
| 2026-08/A5-01 | Gate pip-audit doublement non-bloquant | haute | EN ROADMAP | 2026-08 | 2026-08 | **AV2** APRÈS upgrades (Q2) — clé d'origine 2026-07/A5-04 |
| 2026-08/A5-02 | Alerte fraîcheur backup = cul-de-sac (log 22 Mo, aucun canal) | moyenne | EN ROADMAP | 2026-08 | 2026-08 | **AV1** — canal push + logrotate |
| 2026-08/A5-03 | MinIO à 99,55 % de son cap 2G en 5 jours | moyenne | EN ROADMAP | 2026-08 | 2026-08 | BUMP 3G + GOMEMLIMIT 2700 (Q7) → **AV1** |
| 2026-08/A5-04 | Doc : image worker « 312 Mo » vs 852 MB réels | basse | EN ROADMAP | 2026-08 | 2026-08 | **AV7** (lot doc) |
| 2026-08/A5-05 | Doc : « full local app sur localhost:8080 » contredit Q6 | basse | EN ROADMAP | 2026-08 | 2026-08 | **AV7** (lot doc) |
| 2026-08/A5-06 | Tags flottants restants (nginx:alpine ×2, node, python) | basse | EN ROADMAP | 2026-08 | 2026-08 | **AV2** — clé d'origine 2026-07/A5-11 |
| 2026-08/A5-07 | npm : 5 vulns dev/build + 4 majeurs de retard | basse | EN ROADMAP | 2026-08 | 2026-08 | Volet 1 (audit fix) → **AV1** ; volet 2 → chantier « Majeurs frontend » (Q8, hors AV) |
| 2026-08/A6-02 | /api/radar/feed hors rate limiting malgré l'incident OOM | haute | EN ROADMAP | 2026-08 | 2026-08 | **AV1** |
| 2026-08/A6-03 | python-jose/multipart/starlette vulnérables (26 avis, exposition évaluée) | haute | EN ROADMAP | 2026-08 | 2026-08 | **AV2** — upgrades AVANT le gate (Q2) |
| 2026-08/A6-05 | External search : lookup catalog sans catalog_visible (divulgation d'existence) | basse | EN ROADMAP | 2026-08 | 2026-08 | **AV7** — + documenter l'exception d'intégrité import_external |
| 2026-08/A6-06 | LIKE wildcards ×6-8 sites refondus | basse | EN ROADMAP | 2026-08 | 2026-08 | **AV1** — clé d'origine 2026-07/A6-06 |
| 2026-08/A6-07 | Branches google_callback non testées | basse | EN ROADMAP | 2026-08 | 2026-08 | **AV7** — clé d'origine 2026-07/A6-14 |
| 2026-08/A6-08 | Upsert PG import RB non testé | basse | EN ROADMAP | 2026-08 | 2026-08 | **AV7** — clé d'origine 2026-07/A6-08 |
| 2026-08/A6-09 | crawl-status sans dépendance user | basse | EN ROADMAP | 2026-08 | 2026-08 | **AV1** — une ligne |
| 2026-08/A7-01 | CLAUDE.md : 4 compteurs faux ou incohérents | moyenne | EN ROADMAP | 2026-08 | 2026-08 | **AV7** — clé d'origine 2026-07/A7-05 (pattern) |
| 2026-08/A7-02 | ROADMAP : D4/D7 livrés non clos | moyenne | OUVERT | 2026-08 | 2026-08 | **IMMÉDIAT** hors série : passer `/roadmap_update` |
| 2026-08/A7-03 | 3 scripts X1/X3 absents du triage README | basse | EN ROADMAP | 2026-08 | 2026-08 | **AV1** — clé d'origine 2026-07/A7-11 |
| 2026-08/A7-04 | Chemins `scripts/` ambigus dans CLAUDE.md | basse | EN ROADMAP | 2026-08 | 2026-08 | **AV7** (lot doc) |
| 2026-08/A8-01 | Invariant #1 à re-scoper (relocate_tracks écrit dans Rekordbox) | basse | EN ROADMAP | 2026-08 | 2026-08 | **AV7** (lot doc) |
| 2026-08/A8-03 | Six tâches longues sans lock Redis | moyenne | EN ROADMAP | 2026-08 | 2026-08 | **AV4** |
| 2026-08/A8-05 | Doc : uq_artists_deezer_id porté par 0034, CLAUDE.md dit le contraire | basse | EN ROADMAP | 2026-08 | 2026-08 | **AV7** (lot doc) |
