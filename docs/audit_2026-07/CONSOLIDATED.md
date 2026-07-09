# Audit 2026-07 — Consolidation (Phase 2)

> Date : 2026-07-09. Main agent, à partir des 7 rapports A1-A7 (114 findings bruts).
> Après dédoublonnage : **106 findings uniques** — **2 critiques, 9 hautes, 38 moyennes, 57 basses**.
> Vérification par sondage : les preuves des findings les plus lourds (A1-24/A4-01, A4-02, A6-02, A5-04, A6-03, A5-01) ont été re-vérifiées ligne à ligne par le main agent — toutes confirmées.
> Ce document prépare la Phase 3 (session d'arbitrage). Rien n'a été modifié dans le code.

---

## 1. Synthèse chiffrée

| | Critique | Haute | Moyenne | Basse | Total |
|---|---|---|---|---|---|
| A1 Backend | 0 | 2 | 8 | 15 | 25 |
| A2 Database | 0 | 0 | 4 | 10 | 14 |
| A3 Workers | 0 | 2 | 7 | 7 | 16 |
| A4 Frontend | 0 | 2 | 4 | 6 | 12 |
| A5 Infra/CI | 1 | 2 | 7 | 10 | 20 |
| A6 Sécurité/tests | 1 | 1 | 5 | 7 | 14 |
| A7 Hygiène/doc | 0 | 2 | 5 | 6 | 13 |
| **Bruts** | **2** | **11** | **40** | **61** | **114** |
| **Uniques (après fusion §2)** | **2** | **9** | **38** | **57** | **106** |

### Top 5 par impact

1. **A5-01 (critique)** — Aucun backup planifié : script + clé GPG en place, rien ne les exécute ; unique dump manuel du 2026-07-01, que la rétention 7j supprimera au prochain run (A5-02).
2. **A6-01 (critique, fusion)** — Tokens OAuth TIDAL réels commités (refresh_token sans expiration encore exploitable), fichier institutionnalisé comme fallback par le code.
3. **A3-01 (haute)** — La promotion `private→shared` n'existe que dans un chemin legacy jamais appelé par Celery : 235 entrées enrichies restées privées en prod ; l'invariant `scope` est violé avant même C3.
4. **A4-02 (haute)** — Les avis posés depuis TrackDetailView ne sont JAMAIS persistés (POST vers un endpoint inexistant, 404 avalé) — corroboré par `user_tracks.avis` 100 % NULL en prod.
5. **A6-02 (haute)** — Le rate limiting est contournable trivialement par spoof de `X-Forwarded-For` (le code lit la première valeur, contrôlée par le client).

Mentions : M1 `in_lib` cross-user (vu indépendamment par A1 et A2), M2 badge radar mobile mort depuis sa création (vu par A1 et A4), A5-04 pip-audit CI no-op, A7-04 README 13 mois en retard (bloquant C3).

---

## 2. Dédoublonnage — findings fusionnés

Chaque fusion conserve TOUTES les preuves (voir les rapports sources). L'ID retenu est le premier ; les absorbés ne sont plus comptés.

| ID fusionné | Absorbe | Objet | Sévérité retenue |
|---|---|---|---|
| **M1 = A1-03** | A2-10 | `GET /sets/{id}` : `in_lib` sans filtre `user_id` (union des bibliothèques de tous les users). Deux preuves indépendantes : `sets.py:264-267` (A1) + absence de dépendance user `sets.py:234` (A2). | haute (A1) — A2 disait moyenne ; retenu haute : fuite inter-users + violation invariant multi-user |
| **M2 = A1-24** | A4-01 | Badge radar « new-count » mort : `api.get('/radar/new-count')` sans `/api` (`BottomNav.vue:58`, `api.js:7`). A4 ajoute : requête index.html inutile à chaque navigation + l'endpoint exige un user (fetch à conditionner à `isAuthenticated`). | haute |
| **M3 = A6-01** | A3-16, A7-02 | Tokens TIDAL commités. Trois facettes complémentaires à traiter ensemble : (1) A6 : rotation + `git rm --cached` + purge historique ; (2) A3 : `source_clients.py:246-259` institutionnalise le fichier comme fallback → le sortir du repo (env `TIDAL_TOKEN_FILE`) ; (3) A7 : pattern `.tidal_tokens.json` absent du `.gitignore`, et le fichier reste nécessaire SUR DISQUE (bootstrap device-auth via `test_sources.py:87`). | critique |
| **M4 = A2-03** | A7-06 | `docs/database-schema.md` non régénéré après 0030 (`part_total`, `group_key`, `member_set_ids`, `set_id_b` nullable absents). Fix : `/schema_doc` + commit. NB : à faire APRÈS A2-04 pour que les index déclarés dans les modèles apparaissent. | moyenne |
| **M5 = A1-22** | A3-15 | CLAUDE.md situe `deezer_enrich.py` sous `server/api/` alors qu'il est sous `server/workers/` (le brief d'audit lui-même a été induit en erreur) + docstring `image_service.py:4` pointant un `storage.py` disparu + « weekly » → « daily » dans `deezer_enrich.py:9`. À traiter dans le même commit que A7-05 (compteurs CLAUDE.md). | basse |
| **M6 = A6-09** | A7-08 | `tests/worker/test_check_sync.py` : 6 tests qui valident une copie locale de la logique d'un module supprimé (`worker/check_sync.py` n'existe plus) — fausse couverture + helper mort `_run_duplicate_check`. | basse |
| **M7 = A4-03 + A4-04** | A7-13 | Fichiers frontend morts confirmés par trois greps indépendants : `AppearRow.vue` (0 réf) et `TagsView.vue` (0 réf, route redirigée). Inclut les retombées doc : CLAUDE.md (« 1 dead TagsView ») et `detail-pages-audit.md` (ligne AppearRow fausse). | basse |

Recoupements NON fusionnés (complémentaires, gardés distincts) :
- A5-16 (`.env.example` : `SECRET_KEY` au lieu de `JWT_SECRET`) et A7-04 (README obsolète qui documente aussi `SECRET_KEY`) — deux fichiers, deux fixes.
- A1-08 (router `tracks` mort sauf legacy) et A7-07 (sort de `worker/import_rekordbox.py`) — même décision amont, deux périmètres (voir Q2).
- A6-13 (rate limiter fail-open) complète A6-02 (spoof XFF) — même fichier, deux problèmes.
- A2-11 (FK sans index) recoupe M1 : l'index `user_tracks.catalog_id` sert notamment la requête corrigée par M1.
- A5-15 (Sentry actif, croyance obsolète) et A3 « Ce qui va bien » (DLQ, hook Sentry workers) — cohérents entre eux.

---

## 3. Graphe de dépendances (ordres de résolution requis)

```
DÉCISION Q2 (sort de worker/import_rekordbox.py)  ──►  A1-08 (router tracks)  ──►  A1-09 (dédup artwork, sans objet si suppression)
DÉCISION Q3 (colonnes mortes)                     ──►  migration 0031 groupée : A2-01 (DROP watched_playlists)
                                                        + A2-06 (fingerprint) + A2-07 (preview_url) + A2-09 (created_at)
                                                        + A2-11 (2 index FK) — 1 seule migration
A2-04 (index dans les modèles)  ──►  M4/A2-03 (régénérer schema doc APRÈS)  ──►  A7-05 (compteurs CLAUDE.md, même passe doc)
A2-02 (create_all dev)          ──►  contexte/cause de A2-01 et A2-04 (à traiter pour ne pas reproduire l'orpheline)
A5-01 (cron backup)  ──►  A5-02 (offsite, sinon la rétention 7j détruit l'unique dump)  ──►  A5-03 (test de restauration)
A5-01              ──►  A5-14 (nettoyage crontab dans la même passe)
A5-06 (--force-recreate)  ──►  A5-07 (ordre migrations/déploiement, même bloc de script)
A5-08 (bind mounts workers)  ◄──►  A5-09 (.dockerignore par contexte) — même refonte de build
A1-01 (search service)  ──►  A1-02 (pagination /search, à corriger dans le même mouvement)
A1-10 (attach/detach → service)  ──►  A1-11 (garde is_virtual, même zone)
A1-15 (opinion_sync → services/)  ──►  A1-25 (sets/import réutilise opinion_sync)
A1-12 (8 endpoints taxonomy : brancher ou supprimer)  ──►  A1-18 (SQL brut/camelCase : ne migrer que ce qui survit)
A4-07 (composable useTaskPoll)  ──►  résout A4-06 par construction (sinon fixer A4-06 seul)
A4-05 (usePaginatedList)  ──►  A4-08 (loading mort de useInfiniteScroll, à trancher ensemble)
A6-02 (lecture X-Real-IP)  ──►  A6-13 (logger le fail-open, même fichier)
M3/A6-01 (tokens TIDAL)  : ordre interne = rotation TIDAL  ►  git rm + .gitignore  ►  purge historique (Q4)  ►  fallback code (A3)
A3-06 (erreurs Deezer typées)  ──►  A3-07 (PlaylistGoneError, même zone)
```

Findings sans dépendance : tous les autres (exécutables isolément).

---

## 4. Rejets et corrections motivés

Aucun finding d'agent n'a été rejeté pour preuve insuffisante : le format imposé a été respecté (fichier:ligne ou SQL/commande + sortie partout), et les sondages du main agent ont confirmé les preuves testées. En revanche, **7 hypothèses du brief ou de l'inventaire Phase 0 ont été réfutées ou corrigées** par les agents — elles ne doivent PAS ressortir comme findings :

| # | Hypothèse initiale | Verdict | Preuve |
|---|---|---|---|
| R1 | « `workers/enrichment.py` (0 % coverage) = dead code potentiel » (inventaire §4) | **RÉFUTÉ** — vivant, importé par 4 modules de tasks actifs | A3, « Ce qui va bien » : `tasks/catalog.py:55,175`, `tasks/radar.py:248`, `tasks/sets.py:121,248`, `tasks/genres.py:41`. Le 0 % est un trou de tests (devenu A6-04) |
| R2 | « `radar_tracks.removed_at` ~100 % NULL → lifecycle C0.1 ne tourne pas ? » (inventaire §9) | **RÉFUTÉ** — artefact d'échantillonnage `pg_stats` | A2 : `COUNT(*) FILTER` en prod → 13 removals réels ; logique mark/clear branchée (`workers/db.py:212-231`) |
| R3 | « Vite dev server en prod » (brief §A5) | **OBSOLÈTE** — build statique Nginx en prod depuis le chantier frontend | A5 : `server/frontend/Dockerfile` target production, image 81.9 MB, cache immutable |
| R4 | « AdminView 1725 LOC, suspect principal de duplication » (brief §A4) | **OBSOLÈTE** — refactor déjà fait | A4 : AdminView.vue = 89 LOC, logique dans 6 composants `components/admin/*` |
| R5 | « Sentry DSN non configuré (connu) » (brief §A5) | **OBSOLÈTE** — DSN posé en prod, SDK initialisé API + workers | A5-15 : `main.py:38-46`, `celery_app.py:10-22`, `SENTRY_DSN` longueur 95 dans le `.env` VPS. Reste à vérifier la réception dans l'UI Sentry |
| R6 | « L'enrichissement skip `scope=private` (~259 tracks à 0 % d'enrichissement) » (brief §A3) | **CORRIGÉ** — le diagnostic était faux, le bug est réel mais ailleurs : les privées SONT enrichies (aucun filtre scope dans les queries), c'est la PROMOTION private→shared qui a été perdue au passage au pipeline async | A3-01 : promotion uniquement dans `deezer_enrich.py:334-337` (chemin jamais appelé par Celery) ; 235 privées avec `deezer_id` en prod |
| R7 | « `user_tracks.avis` 100 % NULL = colonne morte ? » (inventaire §9) | **CORRIGÉ** — la colonne est vivante côté backend (writers réels) ; le 100 % NULL vient d'un bug frontend | A2 (writers : `opinion_sync.py:70`, `catalog_service.py:580`) + A4-02 (le POST du frontend part vers un endpoint inexistant) |

Faux positifs outillés écartés en cours d'audit (non comptés) : vulture sur `health` (healthcheck Docker), `GenreNode` (utilisé via SQL brut), colonnes SQLAlchemy et endpoints FastAPI (faux positifs structurels) ; deptry DEP001 sur les packages locaux et DEP002 sur `asyncpg`/`uvicorn` (chargés hors import).

---

## 5. Matrice de priorisation

Règle du brief : **QUICK WIN** = impact haute|critique × effort S. Les `QW-c` sont les QUICK-WIN-CANDIDAT tagués par les agents (effort S, risque faible) proposés pour le même lot AU1 — à valider en bloc (voir Q1).

### 5.1 QUICK WINS (impact haute/critique × effort S) — 8

| ID | Titre | Sév. | Effort | Conf. |
|---|---|---|---|---|
| A5-01 | Planifier le backup (cron/timer) — la tuyauterie existe déjà | critique | S | haute |
| M1 (A1-03) | Filtrer `in_lib` par user sur `GET /sets/{id}` | haute | S | haute |
| M2 (A1-24) | Corriger `/radar/new-count` → `/api/radar/new-count` | haute | S | haute |
| A4-02 | Rebrancher les avis TrackDetailView sur le chemin de persistance canonique | haute | S | haute |
| A3-01 | Porter la promotion `private→shared` dans le pipeline async + rattrapage 235 lignes | haute | S | haute |
| A6-02 | Rate limiting : lire `X-Real-IP` (posé par nginx) au lieu du premier XFF | haute | S | haute |
| A5-04 | `pip-audit -r server/api/requirements.txt` (le job actuel scanne le runner) | haute | S | haute |
| A7-01 | Sortir `.coverage` du suivi git + patterns `.gitignore` | haute | S | haute |

Critiques/hautes restants NON quick-win (effort > S) : M3/A6-01 tokens TIDAL (M — rotation + purge historique, cf. Q4), A5-02 offsite (M), A7-04 README (M).

### 5.2 Findings moyens (38)

| ID | Titre court | Type | Effort | Conf. | Tags |
|---|---|---|---|---|---|
| A1-01 | search.py = service déguisé (365 LOC) | archi | M | haute | avec A1-02 |
| A1-02 | Pagination /search cassée (offset mémoire post-LIMIT sans ORDER BY) | bug | S | haute | QW-c de fait |
| A1-04 | I/O sync bloquante (requests/MinIO) dans endpoints async | perf | M | haute | |
| A1-05 | watchlist.py : 435 LOC sans couche service | archi | M | haute | |
| A1-08 | Router tracks : seuls appelants = legacy worker/ + tests | dette | M | moyenne | Q2 |
| A1-10 | Logique dedup attach/detach dans admin.py au lieu du service | archi | M | haute | C6 |
| A1-12 | 8 endpoints taxonomy sans appelant | dead-code | S | moyenne | Q1b |
| A1-17 | Worker radar → API HTTP via endpoint public `_OPEN_PREFIXES` | archi | M | haute | avec A6-10 |
| A2-01 | DROP `watched_playlists` (orpheline, preuve mécanique) | dette | S | haute | QW-c, migration 0031 |
| A2-02 | `create_all` dev coexiste avec Alembic (cause racine A2-01) | archi | M | haute | |
| M4 (A2-03) | Régénérer database-schema.md (0030 absent) | dead-doc | S | haute | QW-c, après A2-04 |
| A2-04 | ~10 index/contraintes uniquement en migration, absents des modèles | convention | M | haute | risque autogenerate |
| A3-02 | `radar_trends` jamais purgée : 28 % de lignes périmées servies, rangs en collision | bug | S | haute | QW-c |
| A3-03 | reclassify vide les genres AVANT la recherche (perte sur erreur réseau) | bug | S | haute | QW-c |
| A3-04 | Échec HTTP Deezer = « not found » définitif (`deezer_searched_at`) | bug | M | haute | |
| A3-05 | Rate limiting en mémoire par process : limites ×3 (prefork) | archi | M | haute | |
| A3-06 | Clients Deezer sync sans check statut/erreur → tracklist partielle → faux `removed_at` | bug | S | moyenne | QW-c |
| A3-07 | Suppression de playlist sur matching de chaîne « 404 » dans str(e) | bug | S | moyenne | avec A3-06 |
| A3-08 | 6 `except: pass` muets dans import/dedup/enrichissement | dette | S | haute | QW-c, C6 |
| A4-05 | Duplication fetch+pagination ArtistsView/GenresView | dette | M | haute | |
| A4-06 | 5 intervals de polling admin jamais nettoyés (onUnmounted absent) | bug | M | haute | résolu par A4-07 |
| A4-07 | Pattern poll Celery réimplémenté 7 fois → composable | dette | M | haute | |
| A4-09 | HubView (1511 LOC) dans le bundle principal | perf | M | haute | |
| A5-03 | Restauration jamais testée ni documentée (clé GPG = SPOF) | dette | M | haute | après A5-01/02 |
| A5-05 | Image frontend prod construite sans lockfile (`npm install`) | bug | S | haute | QW-c |
| A5-06 | `--force-recreate` : coupure DB/Redis à chaque push | perf | S | haute | QW-c |
| A5-08 | Workers/beat exécutent le code du repo hôte (bind mounts en prod) | archi | M | haute | avec A5-09 |
| A5-09 | Aucun `.dockerignore` dans les contextes de build réels | dette | S | haute | QW-c |
| A5-10 | Workflow deploy sans `concurrency:` | bug | S | haute | QW-c |
| A5-11 | `minio:latest`, `certbot:latest` non pinnés | dette | S | haute | QW-c |
| A6-03 | XML Rekordbox : ElementTree vulnérable au billion laughs → defusedxml | securite | S | haute | QW-c |
| A6-04 | Pipeline d'enrichissement 0 % testé ET exclu du gate coverage (`omit`) | dette | L | haute | Q7 |
| A6-05 | Payloads non bornés (radar/state/batch, image_base64 ×5000…) | securite | S | haute | QW-c |
| A6-07 | LoginCallbackView (cœur auth mobile) : 0 test | dette | M | haute | Q7 |
| A6-08 | Task import Rekordbox non testée (upsert PG, progress, lock) | dette | M | haute | Q7 |
| A7-05 | CLAUDE.md : 5 compteurs faux (+ M5 : arborescence deezer_enrich) | dead-doc | S | haute | QW-c |
| A7-07 | `worker/` + `server/deezer/` : outillage local vivant non documenté ; `import_rekordbox.py` supersédé | archi | M | moyenne | Q2 |
| A7-09 | `_design/`, `.claude/`, `docs/prompts` gitignorés mais traités comme doc de référence | convention | S | moyenne | Q5 |

### 5.3 Findings basses (57) — synthèse par lot

Détail complet dans les rapports sources ; regroupés ici par nature pour l'arbitrage :

- **Dead code backend à trancher (Q1b)** : A1-06 (PATCH /crawled, preuve mécanique complète — QW-c), A1-07 (GET /watchlist/), A1-13 (refresh-pillars + cache par process), A1-14 (reset-beatport, backfill-multi-artists — confiance basse), A1-23 (GET /auth/me — recommandation : GARDER).
- **Colonnes DB mortes (Q3)** : A2-05 (artists.bio/country/real_name/soundcloud_id), A2-06 (catalog.fingerprint + index unique — QW-c), A2-07 (catalog.preview_url exposée partout mais 100 % NULL), A2-08 (sets.event/venue/description), A2-09 (user_tracks.created_at jamais renseignée — QW-c).
- **Perf DB différée (C3)** : A2-11 (2 index FK justifiés : user_tracks.catalog_id, user_follows.entity_id — le reste différé), A2-12 (N+1 match_set borné), A2-13 (upsert par piste import RB), A2-14 (tris radar_trends sans index).
- **Workers robustesse** : A3-09 (2 tasks sans crawl_logs — QW-c), A3-10 (result.get() bloque un slot 7h), A3-11 (resolve_set_tracks sans lock — QW-c), A3-12 (re-recherche artistes sans deezer_searched_at), A3-13 (lock TTL 900s < time_limit 4500s — QW-c), A3-14 (lock import non atomique).
- **Frontend** : M7 (AppearRow + TagsView à supprimer — QW-c), A4-08 (loading mort du composable — QW-c), A4-10 (307 sur /api/genres/ au Hub — QW-c), A4-11 (3 appels mappings + stats sans catch — QW-c), A4-12 (.state ×10, keyframes spin ×4).
- **Infra basses** : A5-07 (migrations après bascule), A5-12 (port 8080 public — QW-c), A5-13 (certbot fantôme + 12 volumes orphelins — QW-c), A5-14 (cron reload redondant), A5-15 (doc Sentry à corriger), A5-16 (.env.example JWT_SECRET — QW-c), A5-17 (stack locale incohérente, Q6), A5-18 (HTTP/2 absent — QW-c), A5-19 (cache npm CI + Node 20 vs 22 — QW-c), A5-20 (workers sans healthcheck).
- **Sécurité basses** : A6-06 (wildcards LIKE non échappés), A6-10 (watchlist/active public + OpenAPI exposé en prod — QW-c), A6-11 (log du body token Google — QW-c), A6-12 (contrôle taille upload après bufferisation — QW-c), A6-13 (fail-open Redis muet), A6-14 (branches d'échec OAuth + lifecycle radar skippé en CI SQLite).
- **Backend basses** : A1-09 (bloc artwork dupliqué — dépend Q2), A1-11 (garde is_virtual — QW-c), A1-15 (catalog.py/opinion_sync.py → services/ — QW-c), A1-16 (membres privés du service importés), A1-18 (taxonomy SQL brut/camelCase — dépend A1-12), A1-19/A1-20 (opinions : response_model + int() non protégé — QW-c), A1-21 (bucket en dur ×3 — QW-c), M5 (doc deezer_enrich — QW-c), A1-25 (sets/import contourne opinion_sync — QW-c).
- **Hygiène** : A7-03 (CSV taxonomy = seed à déplacer, PAS supprimer), A7-10 (design-decisions.md → docs/ — QW-c), A7-11 (README de triage scripts), A7-12 (test_sources.py à renommer), M6 (test_check_sync fausse couverture — QW-c).

### 5.4 Décompte des QUICK-WIN-CANDIDAT

8 QUICK WINS stricts (§5.1) + **~35 QW-c** tagués par les agents (effort S, confiance majoritairement haute). Le lot AU1 réaliste après arbitrage : entre 25 et 40 items selon les réponses aux questions Q1-Q3.

---

## 6. Questions d'arbitrage pour William (Phase 3)

Formulées avec options et trade-offs. Ce qui n'est pas listé ici est considéré comme validable en bloc (fixes objectifs, sans choix de design).

### Q1 — Valider le lot AU1 Quick Wins
**Verrouillé** : les 8 QUICK WINS stricts (§5.1) sont des bugs/risques avérés avec fix borné — recommandation : GO en bloc.
**Ouvert** : inclure aussi les ~35 QW-c basses/moyennes (§5.2-5.3) dans AU1 ?
- Option A (recommandée) : AU1 = les 8 stricts + les QW-c de confiance haute SANS décision produit (≈30 items, 1-2 jours de travail). Les QW-c dépendant d'une décision (dead code, colonnes) attendent Q1b/Q3.
- Option B : AU1 = uniquement les 8 stricts ; le reste part dans des chantiers thématiques. Plus lent, moins de risque de fatigue de revue.

### Q1b — Dead code backend : supprimer, brancher ou documenter ?
Cinq groupes d'endpoints sans appelant, du plus sûr au moins sûr :
1. `PATCH /watchlist/{id}/crawled` (A1-06) — preuve mécanique complète. Reco : **supprimer**.
2. 8 endpoints taxonomy (A1-12) — construits pour le brief design Genres, jamais branchés. Options : supprimer (reco si aucune exploration de graphe prévue) / garder pour un futur « explorateur de genres » (alors les tester et les documenter). Leur sort conditionne A1-18.
3. `POST /genres/refresh-pillars` (A1-13) — cassé en multi-process de toute façon. Reco : supprimer, invalidation via redémarrage ou Redis si besoin réel.
4. `GET /watchlist/` (A1-07) + `reset-beatport`/`backfill-multi-artists` (A1-14) — usage curl admin plausible. Options : documenter comme outillage curl / supprimer. Reco : documenter (coût nul, usage plausible).
5. `GET /auth/me` (A1-23) — reco : **garder** (marqué GARDER dans l'archive F3) ; optionnellement l'appeler au boot frontend pour rafraîchir `is_admin`.

### Q2 — Sort du flux d'import legacy (`worker/import_rekordbox.py` + router `tracks`)
Le flux XML (upload → Celery) est le chemin officiel. `worker/import_rekordbox.py` (script desktop, 0 import par le code) semble supersédé ; le router `tracks` (350 LOC, 5 endpoints, 28 % coverage) n'a plus que lui et les tests comme appelants (A1-08, A7-07).
- Option A (recommandée) : confirmer que le script desktop n'est plus utilisé → l'archiver dans `docs/completed/` (pas de suppression), déprécier puis supprimer le router `tracks` (garder `GET /{track_id}` s'il sert TrackDetailView — à re-vérifier : A4 n'a pas trouvé d'appel).
- Option B : le script sert encore ponctuellement depuis le PC Rekordbox → le documenter dans CLAUDE.md (A7-07) et extraire `bulk_import` vers un service (A1-08 minimal).
- Trade-off : A supprime ~500 LOC et 5 endpoints publics de la surface d'attaque ; B conserve un chemin d'import de secours.

### Q3 — Colonnes DB mortes : quoi dropper dans la migration 0031 ?
Tout est prouvé 0 non-NULL en prod + 0 writer. Par lot :
- `watched_playlists` (table, A2-01) : reco **DROP** (preuve mécanique irréfutable, dump de précaution avant).
- `catalog.fingerprint` + index unique (A2-06) : reco **DROP** sauf si le fingerprinting audio est envisagé pour C2 (re-créer coûtera une migration triviale).
- `catalog.preview_url` (A2-07) : reco **DROP + retirer des schemas API** (le flux réel est live-only via `/preview-url` ; le champ ment à tous les consommateurs). Alternative : peupler avec TTL = chantier, pas un fix.
- `artists.bio/country/real_name/soundcloud_id` (A2-05) et `sets.event/venue/description` (A2-08) : colonnes « pour plus tard ». Options : retirer seulement des schemas Pydantic (S, réversible, reco) / dropper aussi les colonnes / garder si un chantier d'enrichissement bio/événements est envisagé.
- `user_tracks.created_at` (A2-09) : morte par accident. Options : `server_default=now()` (reco, elle servira à C3) / dropper si `date_added` suffit.

### Q4 — Tokens TIDAL : purge de l'historique git ou pas ? (M3)
La rotation (révoquer côté TIDAL) + `git rm --cached` + `.gitignore` sont non négociables (reco : immédiat). La question : réécrire l'historique ?
- Option A : `git filter-repo`/BFG + force-push — le token disparaît de tous les futurs clones. Coût : réécriture d'historique (invalide les clones existants, y compris celui du VPS → re-clone à prévoir dans le deploy), à faire une seule fois proprement.
- Option B (suffisante si la rotation est faite) : rotation seule ; le token révoqué dans l'historique devient inerte. Coût nul, mais un secret mort reste visible publiquement si le repo devient public un jour.
- Reco : B immédiatement (rotation = urgence), A à planifier si une ouverture du repo (C3 contributeurs) est envisagée.

### Q5 — Versionner `_design/`, `.claude/commands/`, `docs/prompts/` ? (A7-09)
CLAUDE.md les traite comme doc de référence ; ils n'existent que sur cette machine.
- Option A (reco) : versionner `_design/` et `.claude/commands/` (doc projet, pas user-local) ; garder `docs/prompts/` ignoré (contenu jetable, les prompts finis vont dans `docs/completed/`).
- Option B : statu quo + backup hors-git documenté + corriger CLAUDE.md pour dire que ces ressources sont locales.
- Trade-off : A protège la base des chantiers design contre une perte disque ; B évite de versionner des maquettes lourdes (à vérifier : taille de `_design/`).

### Q6 — Stack locale : trancher le flux de dev (A5-17)
Le chemin documenté (compose local + `npm run dev` hôte) semble non fonctionnel tel que versionné (nginx local vide + unhealthy, proxy Vite vers `api:8000` non résolvable depuis l'hôte). Deux options dans le rapport A5 ; à trancher selon ton usage réel (comment lances-tu le dev aujourd'hui ?). Si un contournement local non versionné existe, le versionner est le fix.

### Q7 — Dette de tests : quel niveau d'investissement ?
Trois findings de fond (A6-04 enrichissement 0 % + `omit` qui aveugle le gate, A6-07 LoginCallbackView, A6-08 import RB) + A6-14 (branches OAuth, lifecycle radar skippé en SQLite). C'est du L cumulé.
- Option A : chantier dédié « AU-tests » (1-2 jours) ciblant exactement ces 4 zones, et retrait progressif des modules du `omit`.
- Option B : opportuniste — chaque chantier AU qui touche une zone y ajoute ses tests ; pas de chantier dédié.
- Reco : A pour l'enrichissement et l'auth (code le plus critique, zéro filet aujourd'hui) ; B pour le reste.

### Q8 — Architecture backend : lancer un chantier « couche service » ?
A1-01 (search), A1-05 (watchlist), A1-10 (dedup admin), A1-15 (catalog.py/opinion_sync.py), A1-16 (membres privés) dessinent un chantier cohérent « finir la couche service » (~2-3 jours, zéro changement de comportement, à protéger par les tests existants).
- Option A : chantier dédié AU-archi après AU1.
- Option B : différer — c'est de la dette, pas des bugs ; la payer quand on retouche ces zones.
- Reco : A pour search+watchlist (les deux seuls domaines sans service, et search porte un bug lié A1-02) ; B pour le reste.

### Q9 — Infra Docker : refonte du contexte de build workers (A5-08 + A5-09)
Les workers exécutent le code du repo hôte via bind mounts en prod (rollback d'image impossible). Fix = remonter le contexte de build à `./server` + Dockerfile copiant api/ + workers/ + `.dockerignore` dédiés.
- Option A (reco) : chantier M dédié, testé en local avant push (risque : build cassé = deploy cassé).
- Option B : statu quo documenté (les bind mounts sont un choix assumé) + seulement A5-09 (.dockerignore).

---

## 7. Proposition de regroupement en chantiers (préfiguration Phase 4, à valider en Phase 3)

| Chantier | Contenu (IDs) | Effort estimé |
|---|---|---|
| **AU1 — Quick Wins** | Les 8 stricts (§5.1) + QW-c validés via Q1 (+ M3 volet rotation/gitignore) | 1-2 j |
| **AU2 — Sauvegardes & déploiement** | A5-01→03, A5-06, A5-07, A5-10, A5-11, A5-14 (+ Q9 : A5-08/09) | 1-2 j |
| **AU3 — Intégrité données** | Migration 0031 (Q3 : A2-01/06/07/09 + A2-11), A2-02, A2-04, M4, A3-02, A3-04 | 1-2 j |
| **AU4 — Robustesse workers** | A3-03, A3-05→14 (locks, erreurs typées, observabilité) | 2 j |
| **AU5 — Couche service backend** (Q8) | A1-01/02, A1-05, A1-10/11, A1-15/16, A1-17, A1-25 | 2-3 j |
| **AU6 — Dette frontend** | A4-05→08, A4-12 (+ A4-09 si validé) | 1-2 j |
| **AU7 — Dette de tests** (Q7) | A6-04, A6-07, A6-08, A6-14, M6 | 2 j |
| **AU8 — Hygiène & doc** | A7-03→05, A7-07, A7-09→12, Q1b/Q2 (suppressions actées), README (A7-04) | 1 j |

Les findings tagués `lié-chantier:C3` non urgents (A2-11 partiel, A2-14, A6-14 partiel) sont à reporter dans le brief C3 plutôt que dans la série AU.

---

*Fin de la Phase 2. Phase 3 (arbitrage) : session dédiée avec William — parcourir §1, §5.1, puis Q1→Q9, enregistrer les décisions dans `DECISIONS.md`. Phase 4 (roadmap) uniquement après.*
