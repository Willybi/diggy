# Audit 2026-08 — Consolidation (Phase 2)

> Date : 2026-08-09. Main agent, à partir des 8 rapports A1-A8 (73 findings bruts, dimension A8 Invariants inaugurée).
> HEAD audité : `9b305d6` (2026-08-08). Delta vs audit 2026-07 : 164 commits, 532 fichiers.
> Après dédoublonnage : **68 findings uniques** — **0 critique, 8 hautes, 26 moyennes, 34 basses**.
> Contre-vérification : les **8 findings « haute » ont TOUS été re-vérifiés ligne à ligne par le main agent** (lecture directe du code cité, re-exécution des mesures pour A4-01 : diff/comm re-produits à l'identique — 555/1238) + sondage de 6 moyennes (A2-01, A3-02, A3-06, A7-02, A8-05, A4-02) — toutes confirmées. Aucun finding rejeté pour preuve insuffisante.
> Ce document prépare la Phase 3 (arbitrage). Rien n'a été modifié dans le code.

---

## 1. Synthèse chiffrée

| | Critique | Haute | Moyenne | Basse | Total |
|---|---|---|---|---|---|
| A1 Backend (dont 4 récurrences) | 0 | 2 | 8 | 6 | 16 |
| A2 Database | 0 | 0 | 2 | 7 | 9 |
| A3 Workers | 0 | 1 | 7 | 4 | 12 |
| A4 Frontend | 0 | 2 | 4 | 4 | 10 |
| A5 Infra/CI | 0 | 1 | 2 | 4 | 7 |
| A6 Sécurité/tests | 0 | 3 | 1 | 5 | 9 |
| A7 Hygiène/doc | 0 | 0 | 2 | 2 | 4 |
| A8 Invariants (45 TENU / 5 VIOLÉ) | 0 | 0 | 3 | 3 | 6 |
| **Bruts** | **0** | **9** | **29** | **35** | **73** |
| **Uniques (après fusion §2)** | **0** | **8** | **26** | **34** | **68** |

**Lecture d'ensemble** : santé nettement meilleure qu'en 2026-07 (0 critique vs 2 ; les backups tournent, l'infra est propre, 45/50 invariants tenus, la série AU a tenu 164 commits). Les 8 hautes se concentrent sur **3 foyers** : (1) une fuite multi-user pré-C3 jamais couverte (Artist Detail), (2) la famille « coût par requête » autour de la similarité/du feed (racine de l'incident OOM), (3) la chaîne dépendances-vulnérables × gate CI aveugle. S'y ajoute un foyer d'**observabilité workers** (DLQ structurellement vide + bouton admin mort + crawl_logs perdus sur SIGKILL) découvert par recoupement A3.

### Top 5 par impact

1. **M1 (A1-01, haute, S)** — `artist_service.get_detail` : `lib_sub` sans filtre `user_id`. La page Artist Detail (PUBLIQUE) sert à tout viewer le `rb_bpm`/`rb_key`/`rb_mytags` Rekordbox de n'importe quel utilisateur (étiqueté `bpm_source='rekordbox'`), `in_lib`/`nb_lib` = union des bibliothèques, lignes dupliquées si 2 détenteurs. Découvert INDÉPENDAMMENT par A1 et A6. Fix 1 ligne.
2. **A6-03 (haute, M) × A5-01 (haute, S)** — python-jose 3.3.0 (la lib JWT de l'auth, 2 majors de retard, 1 avis sans fix sur sa branche), python-multipart 0.0.9 (upload XML, 7 avis), starlette 0.38.6 (9 avis) — 26 vulnérabilités que le job CI pip-audit détecte à CHAQUE push mais que `continue-on-error: true` + absence du `needs:` de deploy rendent invisibles. Récurrence aggravée de 2026-07/A5-04 : AU1 a corrigé la cible du job, pas son caractère non-bloquant.
3. **A1-02 (haute, M) + A6-02 (haute, S) + A4-02 (haute, S)** — la famille OOM : le pool de similarité (~256k lignes catalog) est rematérialisé en mémoire À CHAQUE requête sur `/api/catalog/{id}/similar` (public, non caché, non throttlé) et `/api/radar/feed` (hors RATE_LIMITS malgré l'incident ~550 Mo/req du 2026-08-01) ; côté front, `fetchUpTo` tire jusqu'à 12 requêtes parallèles sur ce même feed à chaque restauration de scroll. Trois angles du même incident prod documenté.
4. **A3-01 (haute, S) + A3-06 (moyenne, S)** — le bouton admin « auto-classifier » dispatche un kwarg inexistant → `TypeError` à CHAQUE déclenchement depuis sa création, ET la DLQ ne capture structurellement plus les échecs (le garde `retries < max_retries` exclut les tâches sans autoretry, c'est-à-dire toutes les modernes) — la carte admin DLQ observe une file vide par construction, ce qui a masqué le premier bug.
5. **A4-01 (haute, L) + A4-04 (moyenne, L)** — deux paires de vues jumelles copiées-collées (Explorer↔Radar ~80 % identiques : 1238 lignes strictement communes ; Sets↔Watchlist ~50 % : 878 lignes) + la branche « opinion mode » ×3 (A4-05). ~2100 lignes dupliquées en dérive silencieuse : toute évolution de table doit être répliquée à la main.

---

## 2. Dédoublonnage — fusions

L'ID retenu = le premier dans l'ordre de consolidation (A1→A8) ; toutes les preuves des absorbés restent valides (voir rapports sources).

| ID fusionné | Absorbe | Objet | Sévérité retenue |
|---|---|---|---|
| **M1 = A1-01** | A6-01 | Fuite `lib_sub` Artist Detail. Deux découvertes indépendantes, preuves identiques (`artist_service.py:319-324`) ; A6 ajoute l'angle invariant (« Rekordbox BPM = donnée perso ») et le caractère PUBLIC de l'endpoint. | haute |
| **M2 = A3-02** | A8-02 | Beatport async : non-200 → `[]` → `not_found` → `_mark_searched` (outage consomme une tentative E1). Preuves identiques (`enrichment.py:507-508,676-678`, `async_http.py:146-165`) ; A8 le rattache formellement à l'invariant E1 de CLAUDE.md. | moyenne |
| **M3 = A3-04** | A8-04 | `autoretry_for=(Exception,)` résiduel sur 8-11 tâches à soft-limit (le footgun de l'incident 2026-07-13). Périmètres quasi identiques ; A3-03 (jumeau `enrich_catalog` Deezer, cas le plus exposé, suivi mémoire `enrich-beatport-autoretry`) reste un finding distinct rattaché. | moyenne |
| **M5 = A1-07** | A6-04 | Endpoints publics coûteux hors `RATE_LIMITS` : `GET /api/sets/search` (proxy TrackID), `GET /api/catalog/{id}/preview-url` (quota Deezer partagé), `GET /api/catalog/{id}/similar` + `/api/sets/{id}/similar` (CPU/mémoire, cf. A1-02). Union des deux périmètres ; même fichier, même fix. | moyenne |
| **M6 = A4-10** | A8-06 | `assets/table.css:122-131` : `@media (max-width: 640px)` sur éléments non-fixed (unique écart container-queries). Preuves identiques ; A4 propose le fix le plus juste (`@media (hover: none)`). | basse |

Recoupements NON fusionnés (complémentaires, gardés distincts) :
- **A6-02** (radar/feed hors rate-limit) vs **A4-02** (salve fetchUpTo côté front) vs **A1-02** (pool par requête côté service) — trois couches du même incident OOM, trois fixes différents (bucket, lissage, cache). Traiter ENSEMBLE (lié : mémoire projet `api-oom-radar-feed`).
- **A8-03** (6 tâches longues sans lock) vs **A3-03** (jumeau Deezer : autoretry + pas de lock) vs **M3** (autoretry) — même passe de code workers, objets distincts.
- **A5-01** (gate CI) vs **A6-03** (exposition des vulns) — départage explicite entre agents, ordre imposé : upgrades d'abord, gate bloquant ensuite.
- **A7-01/A7-04** (compteurs/chemins CLAUDE.md) vs **A5-04/A5-05** (image 852 Mo, localhost:8080) vs **A8-01/A8-05** (invariant #1, uq_artists_deezer_id) vs **A1-09** (similar_from_context) vs **A3-11** (commentaires backfill) — 9 divergences doc distinctes, UN seul lot de correction CLAUDE.md.
- **A2-08** (récurrence 2026-07/A2-13, upsert import RB) et **A6-08** (upsert non testé) — même zone, un fix + son test.

---

## 3. Graphe de dépendances (ordres imposés)

```
A6-03 (upgrade python-jose/multipart, puis fastapi+starlette)  ──►  A5-01 (gate pip-audit bloquant — AVANT les upgrades il bloquerait tout deploy)
A1-02 (cache /similar + pool)  ◄─ensemble─►  A6-02 (bucket radar/feed)  ◄─ensemble─►  A4-02 (lissage fetchUpTo)   [famille OOM]
M5 (buckets preview-url/sets-search/similar)  ──  même fichier/même passe que A6-02
A3-06 (DLQ)  ──►  A3-01 (le TypeError devient VISIBLE une fois la DLQ réparée — fixer les deux ensemble)
M3 (autoretry) + A8-03 (locks) + A3-03 (jumeau Deezer) + A3-05 (SoftTimeLimit avalé) + A3-08 (routing)  ──  une seule passe workers cohérente
A3-07 (CrawlLogger commit running)  ──  même passe (rend le SIGKILL d'A3-05 observable)
A4-01 (table partagée Explorer/Radar)  ──►  A4-04 (Sets/Watchlist, même extraction)  ──►  A4-05 (helper opinion one-shot)  ; M6 bouge avec
A2-01 + A2-02 + A2-07 (+ tie-break A2-09)  ──  une seule migration d'index groupée
DÉCISION colonnes (Q5)  ──►  A2-03 + A2-04 + A2-05 (même migration que ci-dessus si drop acté)
DÉCISION Radar v1 (Q4)  ──►  A1-05 (suppression 4 endpoints + 4 fonctions service + tests)
DÉCISION GET /watchlist/ (Q4)  ──►  2026-07/A1-07 (+ sa part d'A1-06 tombe)
A7-02 (/roadmap_update)  ──  indépendant, à faire tout de suite
Lot doc CLAUDE.md (9 divergences §2)  ──  après les décisions (les textes dépendent de Q4/Q5)
A1-08 + 2026-07/A1-10 (dé-engraissement routers)  ──  même lot admin.py/sets.py ; APRÈS la passe workers (A3-01 touche admin.py)
```

Findings sans dépendance : tous les autres.

---

## 4. Delta vs audit 2026-07

**Corrigés depuis (vérifiés par les agents, pas sur parole)** : l'essentiel des ~100 findings de juillet. Notamment : 17/20 A5 (backups quotidiens + offsite + restore testé 2026-07-10 + deploy conforme + zéro bind-mount prod + healthchecks 10/10 + pins minio/certbot), 11/12 A4 (avis persistés, composables adoptés, badge new-count, .state global), le gros d'A3 (promotion private→shared async, purge radar_trends, locks ×10 conformes, chord+errback, PlaylistGoneError, backoff artistes E1), A1 (search/watchlist en services, pagination search, response_model 100 %, taxonomy en ORM), A2 (schema doc à jour, index dans les modèles, downgrades symétriques), A6 (X-Real-IP + spoof testé, defusedxml, omit RÉDUIT, fausse couverture supprimée, LoginCallbackView testé).

**Récurrences / persistants (clé d'origine conservée)** :
| Clé 2026-07 | État 2026-08 | Vu par |
|---|---|---|
| A5-04 (pip-audit no-op) | **RÉCURRENCE AGGRAVÉE** → A5-01 : la cible du job a été corrigée (AU1) mais le job reste doublement non-bloquant, et 26 vulns réelles s'accumulent derrière | A5 |
| A4-09 (HubView bundle) | **RÉCURRENCE** → A4-06 : clos « mesuré, non justifié » en AU6 à 191,9 kB — le cliquet anticipé s'est vérifié : 211,6 kB (+20 kB) après D6, toujours import statique | A4 |
| A2-14 (index radar_trends) | **RÉCURRENCE AGGRAVÉE** → A2-02 : table ×4 (38 137 lignes), 2 consommateurs guests (Hub + /radar), seq scan prouvé | A2 |
| A2-13 (upsert par piste import RB) | inchangé → A2-08 | A2 |
| A1-04 (I/O sync event loop) | **partiellement corrigé** (watchlist/import externe OK) — 5 sites restants dont `enrich_single_beatport` (~3 s à ~1 min de loop gelé) | A1 |
| A1-07 (GET /watchlist/ sans consommateur) | inchangé — 2e audit consécutif | A1 |
| A1-10 / A1-11 (attach/detach dans admin.py, garde is_virtual) | inchangés, A1-10 AGGRAVÉ par les group-flags du chantier scoring | A1 |
| A6-06 (wildcards LIKE) | **fix à moitié appliqué** : `like_escape` créé (AU1) mais 6-8 sites du delta D6/D8 repartis sur `f"%{q}%"` brut | A6 |
| A6-14 (branches auth) | partiel : invalid_state testé, google_failed/collisions/verify_google_token toujours nus → A6-07 | A6 |
| A6-08 (upsert import RB non testé) | partiel : lock/parsing/scope testés, le cœur upsert PG toujours skippé | A6 |
| A5-11 (tags flottants) | partiel : minio/certbot pinnés, reste nginx:alpine ×2 / node:22-alpine / python:3.13-slim → A5-06 | A5 |
| A7-11 (README scripts) | **récurrence partielle** → A7-03 : le mécanisme vit mais 3 scripts X1/X3 (les plus destructifs) manquent au triage | A7 |
| A7-05 (compteurs CLAUDE.md) | pattern récurrent → A7-01 : les valeurs AU8 ont re-drifté (E2.c/X2) — la question « ordres de grandeur plutôt que compteurs » se repose | A7 |
| Suivi mémoire `enrich-beatport-autoretry` (jumeau Deezer) | formalisé → A3-03 (autoretry + soft-limit 2h + PAS de lock, dormant mais armé) | A3, A8 |

**Nouveaux foyers propres à ce cycle** : la fuite M1 (pré-C3, jamais audité), la famille OOM/similarité (née de C4+D6), l'observabilité workers (DLQ/CrawlLogger/genre_only — nés de MON), la duplication des vues jumelles (née de D6), les colonnes mortes 0005/0029 (A2-03/04/05), la croissance non bornée metric_snapshots/crawl_logs (née de MON), le trou E1 Beatport async (M2 — le fix Deezer d'AU4 n'a jamais été porté sur le jumeau).

**Régressions** : aucune au sens strict (aucun fix AU re-cassé). En revanche le **pattern « routers ré-engraissés » recommence** (A1-08 : `sets.list_sets` ~190 LOC, `admin.get_backlog` ~140 LOC — le mécanisme qui avait produit search.py/watchlist.py version 2026-07), et la duplication frontend (A4-01/04) est née APRÈS l'AU6 qui factorisait les patterns précédents.

---

## 5. Hypothèses réfutées (ne pas re-signaler)

| # | Hypothèse | Verdict | Preuve |
|---|---|---|---|
| R1 | `sim_bpm`/`sim_key`/`sim_cooc` + `reset_similarity_context_cache` + `pillar_map` morts (vulture) | **RÉFUTÉ** — API de calibration/tests délibérée (brief C2.d : « Ne pas les supprimer ») ; fixture xdist | A1 |
| R2 | `SetFlagType.part_candidate`/`part_overlap_anomaly` morts | **RÉFUTÉ** — vivants (set_dedup_service:454, admin, épargnés par rescore) ; l'indirection enum→string trompe vulture | A2 |
| R3 | `radar_trends` sans purge | **RÉFUTÉ** — purge opérationnelle (38 137 lignes, un seul `computed_at`) ; le problème est l'INDEX (A2-02) | A2 |
| R4 | `catalog.created_at` NULL = bug actif | **RÉFUTÉ** — 4 503 lignes exclusivement historiques (max id 7 496 vs 257 857) | A2 |
| R5 | Un répertoire runtime manquerait au `.dockerignore` (bpm/scripts OPS) | **RÉFUTÉ** — `scripts/` n'y matche que `server/scripts/` ; les scripts OPS vivent dans `server/api/scripts/` et shippent via `COPY api/` | A5 |
| R6 | Le tableau beat CLAUDE.md divergerait du code | **RÉFUTÉ** — 12/12 lignes exactes (heures, queues, batch, modules) | A3, A7 |
| R7 | DesignSystemView (1253 LOC) ship en prod | **RÉFUTÉ** — route `import.meta.env.DEV`, aucun chunk émis | A4 |
| R8 | Les shelves de GenreDetailView violent les patterns paginés | **RÉFUTÉ** — « voir plus » borné sans sentinel, hors périmètre de la règle ; la tracklist passe par usePaginatedList | A4 |
| R9 | Des secrets réintroduits dans le delta | **RÉFUTÉ** — aucun fichier sensible ajouté depuis 67162e3, arbre propre | A6 |
| R10 | Le cache reco/similar-sets peut fuiter entre users | **RÉFUTÉ** — clés par user/viewer partout | A6 |
| R11 | Surallocation mémoire des caps Docker vs RAM VPS | **RÉFUTÉ** — 9,4G de limits pour 15,6G de RAM, usage réel 3,6G | A5 |
| R12 | `batch 2000` BPM ne tiendrait pas dans le créneau nocturne | **VRAI mais ABSORBÉ par design** — soft-limit catché, partiel commité, lock libéré, reprise à h+1 | A3 |
| R13 | deptry DEP003 boto3/botocore transitifs | **FAUX POSITIF** — boto3 est pinné dans requirements.txt (deptry exécuté hors contexte conteneur) | Phase 0/A5 |
| R14 | `crawl_logs`/`admin_audit_log`/FK sans index → perf | **RÉFUTÉ à court terme** — volumétries négligeables (981/337/62 lignes) ; seule la POLITIQUE de rétention manque (A2-06) | A2 |

---

## 6. Matrice de priorisation

Règle : **QUICK WIN** = impact haute × effort S. `QW-c` = candidat quick win tagué par les agents (effort S, risque faible).

### 6.1 QUICK WINS stricts (haute × S) — 5

| ID | Titre | Effort | Conf. |
|---|---|---|---|
| M1 (A1-01) | Filtrer `lib_sub` par `user_id` sur Artist Detail (fuite inter-users) | S | haute |
| A3-01 | Réparer le dispatch `genre_only` du bouton admin auto-classify | S | haute |
| A6-02 | Bucket `RATE_LIMITS` pour `/api/radar/feed` | S | haute |
| A4-02 | Limiter la concurrence de `fetchUpTo` (12 → 2-3) dans les 2 composables | S | haute |
| A5-01 | Gate pip-audit bloquant (`needs:` + retrait `continue-on-error`) — **APRÈS A6-03** | S | haute |

Hautes restantes NON quick-win : A6-03 (upgrades deps, M — le prérequis d'A5-01), A1-02 (cache+pool similarité, M), A4-01 (extraction table partagée, L).

### 6.2 Findings moyens (26)

| ID | Titre court | Type | Effort | Conf. | Tags |
|---|---|---|---|---|---|
| A1-03 | Invalidation cache reco absente du chemin d'avis principal | bug | S | haute | QW-c de fait |
| A1-04 | `fetch-artworks` playlists jamais commité (has_artwork perdu) | bug | S | haute | QW-c |
| A1-05 | Surface Radar v1 morte (4 endpoints + 4 fonctions) | mort | S | haute | Q4 |
| A1-06 | Tris paginés sans tie-break id (Genre Detail ×4, list_followed) | bug | S | haute | QW-c |
| M5 (A1-07) | Rate limits absents : sets/search, preview-url, similar ×2 | sécu | S | haute | QW-c |
| A1-08 | Routers ré-engraissés (sets.list_sets, admin.get_backlog…) | archi | M | haute | avec 2026-07/A1-10 |
| 2026-07/A1-04 | I/O sync restante ×5 (enrich_single_beatport ~1 min de loop gelé) | perf | M | haute | |
| 2026-07/A1-10 | attach/detach dédup sets dans admin.py (aggravé group-flags) | archi | M | haute | |
| A2-01 | Tris Explorer sans index composite (seq scan 256k/page) | perf | S | haute | migration groupée |
| A2-02 | Index radar_trends manquants (récurrence aggravée ×4) | perf | S | haute | migration groupée |
| M2 (A3-02) | Beatport async : outage consomme une tentative E1 | bug | M | haute | |
| A3-03 | Jumeau `enrich_catalog` Deezer : autoretry + soft 2h + sans lock | dette | S | haute | suivi mémoire |
| M3 (A3-04) | autoretry_for=(Exception,) résiduel ×8-11 tâches | dette | M | haute | |
| A3-05 | SoftTimeLimitExceeded avalé par les except par-item (recrawl, trackid_latest) | bug | S | haute | |
| A3-06 | DLQ structurellement vide (garde retries < max_retries) | bug | S | haute | avec A3-01 |
| A3-07 | CrawlLogger : transaction idle-in-transaction ~55 min/run, run tué = 0 trace | perf | S | haute | |
| A3-08 | Routing queue : sync_artists/backfill/reclassify sur `celery` au lieu d'`enrich` | archi | S | haute | |
| A4-03 | Facette liked/disliked GenresView bornée aux 24 premiers | bug | S | haute | QW-c |
| A4-04 | Sets↔Watchlist jumelles (~878 lignes communes) | dette | L | haute | avec A4-01 |
| A4-05 | Branche « opinion mode » ×3, plafonds silencieux 100/200 | dette | M | haute | avec A4-04 |
| A4-06 | HubView 211 kB dans le chunk principal (récurrence, cliquet vérifié) | perf | M | haute | |
| A5-02 | Alerte fraîcheur backup = cul-de-sac (log 22 Mo, aucun canal) | bug | S | haute | QW-c |
| A5-03 | MinIO à 99,55 % de son cap 2G en 5 jours | perf | S | haute | QW-c, Q7 |
| A6-03 | Upgrade python-jose/multipart puis fastapi+starlette | sécu | M | haute | AVANT A5-01 |
| A7-01 | CLAUDE.md : 4 compteurs faux (tasks/ 9, composables 10, classes, tests) | doc | S | haute | QW-c, lot doc |
| A7-02 | ROADMAP : D4/D7 livrés non clos (`/roadmap_update` non passé) | doc | S | haute | QW-c, immédiat |

### 6.3 Findings basses (34) — par lot

- **Passe doc CLAUDE.md (9 items, 1 commit)** : A7-01 (ci-dessus), A5-04 (image 852 Mo ≠ « 312 Mo »), A5-05 (localhost:8080 contredit Q6), A8-01 (invariant #1 vs relocate_tracks — re-scoper), A8-05 (uq_artists_deezer_id porté par 0034), A1-09 (similar_from_context n'est plus la primitive C4), A3-11 (commentaires backfill 1000/visibility_timeout périmés), A7-04 (chemins `scripts/` ambigus), A7-03 (3 scripts hors triage README).
- **Code mort à supprimer (décision simple)** : A1-05 (Q4), 2026-07/A1-07 (GET /watchlist/, 2e audit — Q4), A1-10 (TrackIDClient.get_styles), A3-10 (DEFAULT_ANALYSIS_BPM_BATCH_SIZE + workers/db.get_session), A4-07 (PageHero, RingPct, ScorePill/InLibBadge vitrine).
- **Colonnes DB mortes (Q5)** : A2-03 (needs_reconciliation + status, 0 writer/reader, MANUAL block mensonger), A2-04 (origin write-only et fausse par construction), A2-05 (sets.platform 99,7 % NULL).
- **DB perf/hygiène différables** : A2-06 (politique rétention metric_snapshots/crawl_logs à ACTER), A2-07 (index partiel backlog BPM — 28 seq scans/j de la plus grosse table), A2-08 (upsert import RB, récurrence), A2-09 (tie-break sets + agrégat par page).
- **Workers résiduels** : A3-09 (merge ne reporte pas bpm_analyzed_at), A3-12 (commit mid-gather backfill_multi_artists).
- **Sécu basses** : A6-05 (external search : lookup catalog sans catalog_visible — divulgation d'existence), A6-06 (récurrence LIKE wildcards, 6-8 sites), A6-09 (crawl-status sans dépendance user), A6-07/A6-08 (tests auth callback + upsert RB).
- **Frontend basses** : A4-08 (timer débounce fuitant sur la route suivante), A4-09 (échec preview non-503 ferme la file au lieu de skipper), M6 (table.css @media→hover:none).
- **Infra basses** : A5-06 (pins nginx/node/python), A5-07 (npm audit fix volet 1 ; majeurs vite 8/pinia 4 → Q8).

### 6.4 Décompte quick wins

5 QUICK WINS stricts (§6.1) + **~20 QW-c** de confiance haute sans décision produit. Un lot « AV1 » réaliste : ~22-25 items S, 1-2 jours.

---

## 7. Proposition de regroupement en chantiers (préfiguration Phase 4, à valider en Phase 3)

| Chantier | Contenu (IDs) | Effort |
|---|---|---|
| **AV1 — Quick wins** | M1, A3-01+A3-06, A6-02, A4-02, A1-03, A1-04, A1-06, M5, A4-03, A5-02, A5-03 (si Q7=bump), A6-09, A4-08, A4-09, 2026-07/A1-11, A1-10, A3-10, A6-06, A7-03, npm audit fix (A5-07 v1) | 1-2 j |
| **AV2 — Dépendances & gate** | A6-03 (jose/multipart → fastapi+starlette) PUIS A5-01 ; A5-06 (pins) | 1-2 j |
| **AV3 — Perf data & OOM** | A1-02 (cache similar + stratégie pool), A2-01+A2-02+A2-07 (une migration d'index), A2-09 (tie-break), 2026-07/A1-04 (I/O sync ×5) | 2 j |
| **AV4 — Workers robustesse v2** | M2 (BeatportHTTPError), A3-03, M3, A3-05, A3-07, A3-08, A8-03, A3-09, A3-12 | 2 j |
| **AV5 — Dette frontend (extraction)** | A4-01 → A4-04 → A4-05, A4-06 (Hub), M6 | 2-3 j |
| **AV6 — Backend archi** | A1-08, 2026-07/A1-10, suppressions Q4 (A1-05, GET /watchlist/), A4-07 | 1-2 j |
| **AV7 — Doc & décisions** | Lot doc CLAUDE.md (9 items), A7-02 (immédiat), migration colonnes Q5 (A2-03/04/05), politique A2-06, A6-05, tests A6-07/A6-08 | 1 j |

Séquencement suggéré : **A7-02 immédiat** (roadmap fausse) → **AV1** → **AV2** → **AV3/AV4** (parallélisables, zones disjointes) → **AV5** → **AV6** → **AV7**. Les majeurs frontend (vite 8, pinia 4…) = chantier séparé à arbitrer (Q8), hors série AV.

---

*Fin de la Phase 2. Phase 3 : questions d'arbitrage Q1-Q8 posées à William (voir session) → DECISIONS.md. Phase 4 (LEDGER + roadmap) uniquement après.*
