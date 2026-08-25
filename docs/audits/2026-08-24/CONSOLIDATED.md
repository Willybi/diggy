# Audit 2026-08-24 — Consolidation (Phase 2)

> Date : 2026-08-24. Main agent, à partir des 8 rapports A1-A8 (61 findings bruts).
> HEAD audité : `52a506f` (2026-08-24). Delta vs audit 2026-08-09 (`9b305d6`) : 102 commits, 314 fichiers, +59k/−7,4k lignes.
> Après dédoublonnage : **57 findings uniques** — **0 critique, 3 hautes, 18 moyennes, 36 basses**.
> Contre-vérification main agent : les **3 hautes re-vérifiées ligne à ligne** (A3-01 : lecture du flux `sets.py:920-1131`, l'orchestrateur ne branche que sur `new_cursor is None`, `deadline_hit` n'est qu'une stat ; A4-01 : `HubSearchResults.vue:59-60,197-201`, le texte serveur est injecté brut, seule la query est regex-échappée ; A5-01 : `docker-compose.yml:11-13` cap 1G confirmé) + sondage de 8 moyennes (A6-02 [y compris levée d'un artefact d'affichage grep sur `rate_limit.py:63` — le fichier est correct, le non-match `endswith` tient], A2-01, M1/A1-05, A1-01, A5-02, A7-01, A4-02, plus l'aval d'A3-01) — toutes confirmées. **Aucun finding rejeté pour preuve insuffisante.**
> Nommage : l'audit précédent occupe `docs/audits/2026-08/` (même mois) → clés de ce cycle = `2026-08-24/Ax-nn`.

---

## 1. Synthèse chiffrée

| | Critique | Haute | Moyenne | Basse | Total brut |
|---|---|---|---|---|---|
| A1 Backend | 0 | 0 | 3 | 7 | 10 |
| A2 Database | 0 | 0 | 2 | 4 | 6 |
| A3 Workers | 0 | 1 | 2 | 5 | 8 |
| A4 Frontend | 0 | 1 | 2 | 9 | 12 |
| A5 Infra/CI | 0 | 1 | 6 | 5 | 12 |
| A6 Sécurité/tests | 0 | 0 | 3 | 2 | 5 |
| A7 Hygiène/doc | 0 | 0 | 2 | 4 | 6 |
| A8 Invariants (40 TENU / 2 VIOLÉ) | 0 | 0 | 0 | 2 | 2 |
| **Bruts** | **0** | **3** | **20** | **38** | **61** |
| **Uniques (après fusions §2)** | **0** | **3** | **18** | **36** | **57** |

**Lecture d'ensemble** : la santé continue de monter — 0 critique pour le 2e cycle consécutif, 3 hautes (vs 8 en 2026-08), 40/42 invariants tenus, la série AV vérifiée en place point par point (locks, autoretry purgé, deadlines, C3 sur TOUTES les surfaces neuves, ruff/pip-audit/npm audit à zéro). Les 3 hautes sont **toutes effort S** et deux sont nées dans le delta lui-même : une **régression du fix 3dcb68c** (A3-01), un **legacy jamais audité exhumé par le split AV5** (A4-01), et une **dette de capacité pgvector** qui devient bloquante avec l'avancement du backfill C9.a (A5-01). Les foyers moyens : (1) la surface **`content-similar`** C9.b (gate annoncé non effectif + hors rate-limiting), (2) les **Collections v2** (logique dans le router, dédup non contrainte, tests multi-user absents — un chantier livré sans son durcissement), (3) la **chaîne backup/DR qui a dérivé du schéma réel** (3 buckets sur 6, restore.md pré-pgvector, mc non pinné, crons en UTC à l'insu du crontab).

### Top 5 par impact

1. **A3-01 (haute, S)** — `backfill_trackid_sets` : la sortie deadline AV9 emprunte le chemin de complétion normale. Deadline en collecte + batch vide → `trackid_backfill_done=1` **terminal à tort** (le backfill s'auto-termine silencieusement) ; deadline en import partiel → le curseur inline est **écrasé par `batch[-1]`** (le plus vieux collecté) + `end_page` persisté → les sets collectés-non-importés sont sautés À JAMAIS (le backfill remonte le temps, ils ne seront jamais revus). Régression introduite le 2026-08-24 même (3dcb68c) — le chemin `SoftTimeLimitExceeded` voisin fait, lui, exactement ce qu'il faut.
2. **A4-01 (haute, S)** — stored injection de markup via `v-html` dans le highlight de recherche du Hub : les titres/artistes du catalog PARTAGÉ (alimentable par l'import XML de n'importe quel user et par les scrapes TrackID) sont injectés non échappés dans le DOM de tout chercheur. La CSP `script-src 'self'` bloque l'exécution de scripts inline (pas de XSS exécutable en l'état) mais liens de phishing/images beacon/casse de layout passent. Seul site `v-html` sur donnée serveur du repo.
3. **A5-01 (haute, S)** — cap mémoire postgres 1G face à pgvector : `track_embeddings` pèse déjà **940 MB à 24 % du backfill** (69k lignes mesurées en prod), extrapolation ~3,5 G à 266k. Chaque recherche « sonne comme » traversera un graphe HNSW de plusieurs Go sous un cache plafonné à 1G → thrash disque systématique. À corriger AVANT la fin du backfill (l'éval à l'échelle C9.a mesurerait des latences fausses).
4. **Famille `content-similar` — M1 (A1-05+A6-01, moyenne, S) + A6-02 (moyenne, S) + A1-06 (basse, S)** : le « gaté admin » de C9.b n'existe qu'au front (l'endpoint est public jusqu'aux invités, docstring l'assume, roadmap/CLAUDE.md disent le contraire) ; il échappe au rate limiting (`endswith("/similar")` ne matche pas `content-similar`) ; et un catalog_id inexistant produit un `200 []` caché 6h (clé Redis fabricable à volonté). Trois angles de la même surface, un seul lot.
5. **Famille backup/DR — A5-02 + M4 (A5-05+A7-06) + A5-03 (moyennes, S) + A5-04 (moyenne, S)** : le mirror MinIO ignore les buckets playlist/set/album-artworks (liste figée pré-C6/C7) ; `docs/restore.md` ne mentionne pas pgvector (un restore d'urgence sur postgres vanilla échoue à mi-chemin, dernier test 2026-07-10 = pré-0049) ; `mc` est re-téléchargé non pinné à chaque backup avec les credentials MinIO root ; et `CRON_TZ=Europe/Paris` est ignoré par le cron Ubuntu (prouvé syslog : tout tourne en UTC, le backup 01:30 « Paris » tourne en réalité à 03:30 Paris en été, chevauchant `crawl_trackid_latest`).

---

## 2. Dédoublonnage — fusions

L'ID retenu = le premier dans l'ordre de consolidation (A1→A8) ; toutes les preuves des absorbés restent valides.

| ID fusionné | Absorbe | Objet | Sévérité retenue |
|---|---|---|---|
| **M1 = A1-05** | A6-01 | `content-similar` : gate admin front-only, endpoint public. Découvertes indépendantes, preuves identiques (`routers/catalog.py:135-149`, `auth_middleware.py:12`) ; A6 ajoute l'angle divergence doc↔code (roadmap « LIVRE admin-only ») et le couplage au throttle. | moyenne (A6) |
| **M2 = A2-04** | A6-03 | Dédup `collection_items` check-then-insert sans contrainte DB. Preuves identiques (`routers/collections.py:257-267`, migration 0047) ; A6 ajoute la conséquence aggravante : doublon → `scalar_one_or_none()` → `MultipleResultsFound` → **DELETE 500 permanent** (item insupprimable par l'API), et A2 le lien « downgrade 0047 cassé par un doublon track ». | basse |
| **M3 = A3-02** | A8-01 | Garde deadline AV9 absente des drains restants. A8 la formalise comme violation d'invariant sur `precompute_recommendations` (le plus récent) ; A3 couvre en plus `crawl_trackid_latest`, `recrawl_incomplete_sets`, `sync_artists` Phase B. | moyenne (A3) |
| **M4 = A5-05** | A7-06 | `docs/restore.md` pré-pgvector : restore vanilla échoue, dernier test antérieur au schéma vectoriel. Preuves identiques (grep vector vide, date :229). | moyenne |

Recoupements NON fusionnés (complémentaires, gardés distincts) :
- **M1 vs A6-02 vs A1-06** — même surface `content-similar`, trois défauts distincts (gate, throttle, contrat 404/cache) → un seul lot, trois fixes.
- **A7-01 vs A2-02** — A7-01 retient TOUS les compteurs (dont le 31→32 aussi vu par A2) ; A2-02 reste scopé au MANUAL block du schema doc (colonnes droppées encore documentées, note NULLS LAST promise par CLAUDE.md absente, HNSW invisible).
- **A3-03 vs A3-04 vs A3-05** — dimensionnement, doc et sélection du même drain BPM : trois findings, une passe commune, couplés au diagnostic OPS « ~50 % erreurs » en cours (mémoire monitoring-backlogs-tuning).
- **A1-01 vs A6-04 vs M2** — Collections v2 : extraction service, tests multi-user, contrainte DB. Ordre imposé : tests d'abord (A6-04 verrouille le comportement), puis extraction (A1-01), la contrainte (M2) indépendante.
- **A5-06/A5-08/A5-09/A5-11** — quatre reprises du même `deploy.yml`, à mutualiser si le workflow est repris.

---

## 3. Graphe de dépendances (ordres imposés)

```
A3-01 (aiguillage deadline backfill)  ──►  M3/A3-02 (dupliquer le pattern SEULEMENT une fois l'aval corrigé)
M3 + A3-08 (CrawlLogger precompute)  ──  même fichier recommendations.py, même passe
A3-03 (retaillage batch BPM) ──► A3-04 (les chiffres doc dépendent du retaillage) ; A3-05 attend le diagnostic OPS
M1 (gate content-similar) + A6-02 (throttle) + A1-06 (contrat 404/cache)  ──  un lot, même surface
A6-04 (tests multi-user collections)  ──►  A1-01 (extraction collection_service)  ;  M2 (contrainte unique) indépendant
A5-01 (cap postgres + shared_buffers)  ──►  AVANT la fin du backfill C9.a  ──►  A2-05 (EXPLAIN KNN) APRÈS la fin du backfill
A5-02 + A5-03 + M4 (+ re-test restore) + A5-04 (crontab UTC)  ──  lot backup/DR cohérent
A5-06 + A5-08 + A5-09 (+ A5-11 si acté)  ──  même deploy.yml
A7-01 + A7-02 + A2-02 + A3-04 + A1-08 + A8-02 + A7-03 + A7-05  ──  une passe doc (CLAUDE.md + schema doc + READMEs)
A1-03 (similar_from_context)  ──  décision AVANT C9.c
A1-10 (track_position albums)  ──  décision produit ; migration + funnel si retenu
A4-01 / A4-02 / A4-03 / A4-04 / A4-06  ──  indépendants ; A4-04/A4-10 exigent une vérif RENDU (CDP)
```

Findings sans dépendance : tous les autres.

---

## 4. Delta vs audit 2026-08-09

**Corrigés depuis (vérifiés par les agents, pas sur parole)** : l'intégralité des 51 findings 2026-08 marqués CORRIGÉ au ledger tient à la re-lecture — locks 15 paires conformes, zéro `autoretry_for` actif, deadline AV9 sur les 4 drains, DLQ/CrawlLogger/routing réparés (A3/A8) ; fuite `lib_sub` fermée, rate-limits AV1 en place et testés anti-spoof, C3 appliqué sur 100 % des surfaces NEUVES avec tests 2-users albums/embeddings (A6/A8) ; table partagée AV5 et discipline D9 exemplaires — gardes `ownPath` aux deux niveaux, detach/attach, allowlist exacte (A4) ; pip-audit bloquant + piège pgvector deploy réglé STRUCTURELLEMENT (`up -d --no-deps postgres` avant migration à chaque deploy) + reload nginx câblé côté CI (A5) ; convention services sans HTTPException à 100 %, response_model partout (A1).

**Récurrences / persistants (clé d'origine conservée)** :
| Clé d'origine | État 2026-08-24 | Vu par |
|---|---|---|
| 2026-07/A7-05 (compteurs CLAUDE.md) | **3e RÉCURRENCE** → A7-01 : corrigés par AV7 le 2026-08-16, re-driftés en 8 jours (C7/C9.a/C9.b) — 106 endpoints ≠ 105, 32 tables ≠ 31, 39 defs ≠ 38, 18 services ≠ 17. La question « processus » (bump à la clôture de chantier) se pose plus que la question « chiffres » | A7, A2 |
| 2026-07/A7-11 (README triage scripts) | **3e RÉCURRENCE** → A7-03 : corrigé AV1 le 2026-08-09, puis 8 scripts ajoutés en 15 jours sans ligne d'inventaire | A7 |
| Pattern « routers ré-engraissés » (2026-07 search/watchlist → 2026-08/A1-08 sets/admin, corrigé AV6) | **3e OCCURRENCE du pattern** → A1-01 : Collections C5 v2 naît avec 529 lignes de logique en router, zéro service — le pattern se reproduit sur chaque chantier neuf, AV6 n'a corrigé que le stock | A1 |
| 2026-07/A2-11 (FK sans index, arbitré « réévaluer à la croissance ») | Nouvelle colonne de la même famille → A2-06 (`user_collections.folder_id`, volumétrie dérisoire) : à rattacher au même arbitrage, pas de chantier | A2 |
| 2026-08/A1-09 (`similar_from_context` documenté caller-less) | Toujours mort 2 audits plus tard → A1-03 : décision de suppression à acter (ou conservation explicite pour C9.c) | A1 |
| 2026-08/A1-08 (dé-engraissement routers, corrigé AV6) | Résidu non couvert par AV6 → A1-09 : router sets garde détail ~150 l., import+opinion, client TrackID | A1 |

**Nouveaux foyers propres à ce cycle** : la surface `content-similar` (née C9.b, 2026-08-24), le durcissement manquant de Collections v2 (né C5 v2), la dérive backup/DR vs schéma réel (née de l'accumulation C6/C7/C9.a sans re-passe backup), la capacité postgres vs pgvector (née du backfill C9.a), le dimensionnement BPM sous throttle (né des fixes 19d7b38/cb2c23d).

**Régressions** : **une, au sens strict** — A3-01 : l'extension AV9 au backfill TrackID (3dcb68c, 2026-08-24) a introduit un défaut d'aiguillage que le chemin soft-limit préexistant n'avait pas. C'est la première régression d'un fix d'audit constatée par un audit suivant ; elle plaide pour le réflexe « tester les DEUX chemins de sortie » sur tout fix de garde.

---

## 5. Hypothèses réfutées (ne pas re-signaler)

| # | Hypothèse | Verdict | Preuve |
|---|---|---|---|
| R1 | `search_trackid_sets` (GET /sets/search) mort (vulture) | **RÉFUTÉ** — consommé par SetsView.vue:922 (modal recherche TrackID) | A1 |
| R2 | `genres.py:422` variable `traceback` morte (vulture 100 %) | **RÉFUTÉ** — 3e argument du contrat errback Celery, même famille que les hooks actés FP | A3 |
| R3 | La garde deadline AV9 du backfill serait mal placée | **RÉFUTÉ** — bien EN TÊTE des deux boucles ; c'est l'AVAL de la sortie qui est bugué (A3-01) | A3 |
| R4 | Composants/composables front morts dans le delta | **RÉFUTÉ** — balayage systématique : chaque fichier de components/composables/utils référencé hors tests | A4 |
| R5 | Secrets réintroduits dans le delta | **RÉFUTÉ** — scan du diff 9b305d6..52a506f : seuls des fixtures de test et un placeholder commenté | A6 |
| R6 | Le cache reco/content-neighbors peut fuiter entre users | **RÉFUTÉ** — clés `reco:<uid>` et `(seed, viewer|anon)` partout, single-flight par user | A6 |
| R7 | Résidu bancal du piège deploy pgvector (one-time C9.a) | **RÉFUTÉ** — `deploy.yml:141` recrée postgres avant la migration À CHAQUE deploy, structurel | A5 |
| R8 | Le piège SAEnum aurait mordu C7 (AlbumType) | **RÉFUTÉ** — name==value minuscule des deux côtés (modèle + migration 0046) | A2, A8 |
| R9 | L'auto-heal pourrait tuer un run enrich en cours | **VRAI en théorie, compromis documenté** — même classe que le kill de deploy, locks TTL courts auto-guéris | A3 |
| R10 | `set_reliable()` ORM vs `set_reliable_sql` divergent sur NULL | **VRAI mais sans effet** — colonne NOT NULL défaut false, docstring l'assume | A3 |
| R11 | Le throttle preview ferait déborder/SIGKILL le créneau BPM | **RÉFUTÉ** — absorbé par la deadline ; le vrai problème est dimensionnement/observabilité (A3-03) | A3 |

---

## 6. Matrice de priorisation

Règle : **QUICK WIN** = impact haute × effort S. `QW-c` = candidat quick win tagué (effort S, risque faible) en sévérité moyenne/basse.

### 6.1 QUICK WINS stricts (haute × S) — 3/3 hautes

| ID | Titre | Effort | Conf. |
|---|---|---|---|
| A3-01 | Aiguiller la sortie deadline du backfill TrackID vers le chemin « interrupted » (+2 tests) | S | haute |
| A4-01 | Échapper le texte avant le `<mark>` du highlight Hub (ou rendu en segments) | S | haute |
| A5-01 | Cap postgres 1G→3G + `shared_buffers` ~768MB — AVANT la fin du backfill C9.a | S | haute |

### 6.2 Findings moyens (18)

| ID | Titre court | Type | Effort | Conf. | Tags |
|---|---|---|---|---|---|
| M1 (A1-05) | `content-similar` : gate admin front-only, endpoint public — divergence doc/code à trancher | sécu/doc | S | haute | QW-c, décision |
| A6-02 | `content-similar` hors rate limiting (suffixe non matché) | sécu | S | haute | QW-c |
| A1-01 | Collections : 529 lignes de logique métier en router, zéro service (3e occurrence du pattern) | archi | M | haute | après A6-04 |
| A1-04 | Waiter single-flight reco : connexion DB épinglée ≤48 s pendant le poll | perf | S | moyenne | |
| A2-01 | `catalog_merge` ne repointe pas `catalog_albums` (liens album perdus au merge) | bug | S | haute | QW-c |
| A2-05 | KNN « sonne comme » : recall HNSW post-filtré non garanti (à MESURER post-backfill) | perf | M | moyenne | après backfill |
| M3 (A3-02) | Deadline AV9 absente des drains restants (precompute, trackid_latest, recrawl, sync_artists) | dette | M | haute | après A3-01 |
| A3-03 | Batch BPM 2000 inatteignable sous throttle 1 req/s — `deadline_hit` neutralisé comme signal | perf | S | haute | |
| A4-02 | Bouton « Ajouter à la bib » sans handler (affordance morte, aria mensonger) | bug | S | haute | QW-c, décision |
| A4-04 | CollectionCard : suppression invisible au tactile (hover-only) | bug | S | moyenne | QW-c, vérif CDP |
| A5-02 | backup.sh mirrore 3 buckets MinIO sur 6 | bug | S | haute | QW-c |
| A5-03 | `mc` téléchargé non pinné à chaque backup (supply chain + offsite sauté si CDN down) | dette | S | haute | |
| A5-04 | `CRON_TZ` ignoré par cron Ubuntu — tous les crons VPS en UTC (backup à 03:30 Paris l'été) | bug | S | haute | geste OPS |
| M4 (A5-05) | restore.md pré-pgvector : restore vanilla échoue, re-test à dater | doc | S | haute | QW-c |
| A5-06 | Setup SSH CI : keyscan TOFU, erreurs avalées (incident déjà vécu, reproductible) | dette | S | haute | |
| A5-07 | IP amont nginx périmée sur deploy manuel — resolver 127.0.0.11 (archi, à planifier) | archi | M | haute | |
| A6-04 | Tests multi-user Collections absents (ownership + visibilité track privé) | test | S | haute | avant A1-01 |
| A7-01 | Compteurs CLAUDE.md re-driftés (3e récurrence) — poser le processus, pas juste les chiffres | doc | S | haute | QW-c, lot doc |

### 6.3 Findings basses (36) — par lot

- **Passe doc (1 commit)** : A7-02 (« C9.b not built yet » vs livré le jour même), A7-03 (8 scripts hors README triage, 3e récurrence), A2-02 (MANUAL block : colonnes droppées documentées, note NULLS LAST absente, HNSW invisible + compteur), A3-04 (fenêtre BPM 00h→04h ≠ doc 00h→03h, « 8000/nuit » sans comptabilité), A1-08 (commentaire auth_middleware cite `/radar/full` supprimé), A8-02 (logo Google = exception couleurs à consigner), A7-05 (docs/prompts/ gitignoré mais pointé comme référence — trancher), A2-06 (folder_id → rattacher à l'arbitrage FK 2026-07/A2-11).
- **Code mort / suppressions (décision simple)** : A1-03 (`similar_from_context`, 2 audits sans caller — supprimer ou consacrer C9.c), A1-02 (`total_identified` + son N+1 par candidat au funnel nocturne), A3-06 (`CrawlLogger.update_stats` + `log_id`), A7-04 (`docs/c9-benchmark;C` vide, `node_modules/` racine, `__pycache__` — nettoyage disque, pas git).
- **Collections durcissement (avec A1-01/A6-04)** : M2 (contrainte unique partielle + IntegrityError→409 ; répare aussi le DELETE 500 et le downgrade 0047), A4-03 (« N tracks » faux sur CollectionCard), A4-05 (dropdown sans click-outside ni catch), A4-09 (CollectionsView hors KeepAlive — documenter ou intégrer), A4-11 (duplication rows typées ↔ HubSearchResults — avant un 6e type d'item).
- **Frontend divers** : A1-06 (contrat 404/cache content-similar), A4-06 (volume 0 → 0.8 au reload), A4-07 (réponses recherche désordonnées), A4-08 (listener document non détaché sous KeepAlive — seule entorse D9), A4-10 (littéraux oklch hors tokens, pastille genre à vérifier en dark), A4-12 (AlbumView sans watch route.params.id).
- **Workers résiduels** : A3-05 (sélection BPM `id DESC` + échecs sans plafond — attend le diagnostic OPS), A3-07 (`link_set_artists` O(N·M) + commit/SELECT par set), A3-08 (precompute sans CrawlLogger — invisible du monitoring).
- **Backend résiduels** : A1-07 (`_MAX_SEARCH_ATTEMPTS` dupliqué main-synced — test de cohérence), A1-09 (résidu logique router sets), A1-10 (tracklist album ordonnée par id, pas par position disque — décision produit), A2-03 (downgrade 0046 : type PG `album_type` survit).
- **Infra basses** : A5-08 (health check post-deploy 1 curl), A5-09 (pas de timeout-minutes CI), A5-10 (Redis sans maxmemory sous cap 512M), A5-11 (build sur le VPS de prod — chantier GHCR, L), A5-12 (default.conf/empty.conf doublons).
- **Tests** : A6-05 (embedding_backfill sans test + constantes dupliquées sans garde de synchro).

### 6.4 Décompte quick wins

3 QUICK WINS stricts (les 3 hautes, toutes S) + **~14 QW-c** de confiance haute sans décision produit. Un lot « AW1 » réaliste : ~18-20 items S, 1-1,5 jour.

---

## 7. Proposition de regroupement en chantiers (préfiguration Phase 4, à valider en Phase 3)

| Chantier | Contenu (IDs) | Effort |
|---|---|---|
| **AW1 — Quick wins** | A3-01, A4-01, A5-01, A6-02, A2-01, A5-02, M4 (restore.md, doc seule), A4-03, A4-04, A4-06, A4-08, A1-08, A3-06, A1-02, A7-04, A1-06 + décisions simples (A4-02, M1 selon Q2) | 1-1,5 j |
| **AW2 — Workers : deadline v2 & BPM** | M3 (4 drains), A3-08 (CrawlLogger precompute), A3-03 + A3-04 (retaillage + doc BPM), A1-04 (rollback waiter), [A3-05 si le diagnostic OPS conclut] | 1-2 j |
| **AW3 — Collections durcissement** | A6-04 (tests d'abord), A1-01 (extraction service), M2 (contrainte unique), A4-05, A4-09, A4-11, A2-03 (downgrade 0046 au passage — même migration que M2) | 1-2 j |
| **AW4 — Backup/DR & CI** | A5-03 (image backup pinnée), A5-04 (crontab UTC, geste OPS), re-test restore post-pgvector (M4), A5-06 (known_hosts figé), A5-08, A5-09, A5-10 | 1 j |
| **AW5 — Doc & décisions** | A7-01 + processus de bump, A7-02, A7-03, A2-02, A7-05, A1-07, A1-03 (selon décision), A8-02, A2-06 (ledger) | 0,5-1 j |
| **Hors série** | A5-11 (build GHCR, L — à inscrire conditionnel), A5-07 (nginx resolver — à planifier avec une reprise nginx), A2-05 (EXPLAIN KNN post-backfill — action de suivi C9.a), A1-09/A1-10 (opportunistes), A4-12, A4-07, A4-10 | — |

Séquencement suggéré : **AW1 immédiat** (les 3 hautes + le gros des QW-c) → **AW2** (dépend d'A3-01) ∥ **AW3** (zone disjointe) → **AW4** → **AW5**. A2-05 se déclenche à la fin du backfill C9.a, pas avant.

---

*Fin de la Phase 2. Phase 3 : questions d'arbitrage Q1-Q7 posées à William → DECISIONS.md. Phase 4 (LEDGER + roadmap) uniquement après.*
