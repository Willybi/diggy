# Audit 2026-08 — Phase 0 : Inventaire outillé

> Généré le 2026-08-08. Sorties brutes des outils mécaniques, fournies en contexte aux agents d'audit.
> **AVERTISSEMENT : ces sorties sont des CANDIDATS, pas des findings.** Chaque agent doit vérifier
> par lecture du code avant de retenir quoi que ce soit. Faux positifs structurels connus : vulture
> sur colonnes SQLAlchemy / endpoints FastAPI / `health` (healthcheck Docker) / `GenreNode` (SQL brut) ;
> deptry DEP001 sur packages locaux (`models`, `services`, `utils`, `trackid`), DEP002 sur `asyncpg`/`uvicorn`.

## 0. Bornage du delta

- **Audit précédent** : `docs/audit_2026-07/` (2026-07-09), commit audité = `67162e3` (commit des docs d'audit).
- **HEAD audité (cet audit)** : `9b305d6` (2026-08-08, clôture E2). Working tree PROPRE (0 fichier modifié/untracked).
- **Delta** : `git log --oneline 67162e3..HEAD` = **164 commits** ; `git diff --stat` = **532 fichiers, +81 684 / −11 254**.
- Chantiers livrés dans le delta : série AU1-AU8 complète (les fixes de l'audit 2026-07), E1 (re-scan enrichissement), C3 (visibilité multi-user), C4 (reco perso + similarité), C6.b/c/e (re-crawl, follow artistes, playlists auto-crawl), F5 (import manuel), N1/N2/P2, X1/X3 (dédup catalog + validation platform-id), MON (monitoring + drain Beatport horaire), dédup artistes Deezer/NFC, D4 p.1-4 + Vague 5 Admin (refonte détails), D6 p.1-8 (refonte listes + Radar + D6.0 Rating), D8.b, X2 (scroll/URL), E2.a/b/c (BPM analysis + task VPS), Prettier repo-wide (0dec964), xdist CI (bf141ed), file de lecture audioPlayer (9e1abdd).
- **Audit complet** (périmètre vide) : le delta couvre pratiquement tout le codebase — pas de dimension sautée.

### Top churn `server/` sur le delta (extrait `git diff --stat`, tri par lignes)

```
SetsView.vue 2003 · tasks/artists.py 1732 · WatchlistView.vue 1660 · GenreDetailView.vue 1554
RadarView.vue 1495 (nouveau) · ExplorerView.vue 1440 (nouveau) · TrackDetailView.vue 1197
CatalogView.vue -1193 (supprimé) · ArtistDetailView.vue 1024 · PlaylistDetailView.vue 975
SetDetailView.vue 927 · tasks/sets.py 877 · catalog_service.py 868 · similarity_service.py 777
HubView.vue 749 · AdminOverview.vue 658 (nouveau) · AdminMonitoring.vue 613 (nouveau)
watchlist_service.py 559 (nouveau) · charts/TimeSeriesChart.vue 455 (nouveau)
reverify_platform_ids.py 404 (nouveau) · search_service.py 403 (nouveau) · catalog_merge.py 399 (nouveau)
routers/tracks.py -350 (supprimé) · TrackCard.vue 386 (nouveau) · DiscoveryCard.vue 381 (nouveau)
```

### Top LOC actuels

Backend (hors alembic) : `tasks/artists.py` **2042** · `set_dedup_service.py` 1240 · `catalog_service.py` 1207 · `similarity_service.py` 1043 · `tasks/sets.py` 969 · `artist_service.py` 839 · `routers/admin.py` 836 · `genre_service.py` 787.
Frontend (hors tests) : `HubView.vue` **1730** · `SetsView.vue` 1669 · `GenreDetailView.vue` 1527 · `RadarView.vue` 1495 · `ExplorerView.vue` 1440 · `WatchlistView.vue` 1344 · `DesignSystemView.vue` 1253 · `TrackDetailView.vue` 1211 · `AdminArtists.vue` 798.

Churn 6 mois (commits touchant le fichier) : CatalogView 61 (mort), tasks.py legacy 60, schemas.py legacy 49, routers/catalog.py 46, models.py legacy 46, routers/admin.py 42, TrackDetailView 39, ArtistDetailView 38, main.py 36.

## 1. Ruff

`ruff check server/ --statistics` → **0 violation**. Lint propre.

## 2. Vulture (dead code candidats, min-confidence 60, hors alembic)

~165 hits. L'écrasante majorité = faux positifs structurels (colonnes SQLAlchemy, endpoints FastAPI, dunder Pydantic, `exc_tb`). **Candidats réels à vérifier par lecture** :

```
server\api\models\artist.py:26-38: real_name, country, soundcloud_id, bio        # colonnes « pour plus tard » (Q3 2026-07 : gardées, schemas purgés — vérifier statu quo)
server\api\models\catalog.py:48: origin ; :64: needs_reconciliation              # colonnes à vérifier (writers ?)
server\api\models\sets.py:33-34: event, venue ; :46: platform                    # idem Q3 2026-07
server\api\models\sets.py:151-152: part_candidate, part_overlap_anomaly          # C6.0 — lus quelque part ?
server\api\services\genre_service.py:83: pillar_map                              # appelants ?
server\api\services\radar_service.py:514: add_track                              # appelants ?
server\api\services\similarity_service.py:80,90,138: sim_bpm, sim_key, sim_cooc  # probablement appelés dynamiquement (registry ?) — vérifier
server\api\services\similarity_service.py:314: reset_similarity_context_cache    # test-only ?
server\api\services\similarity_service.py:731: similar_from_context              # consommé par reco/radar ?
server\api\trackid\client.py:98: get_styles                                      # appelants ?
server\workers\db.py:32: get_session                                             # appelants ?
server\workers\tasks\bpm.py:36: DEFAULT_ANALYSIS_BPM_BATCH_SIZE                  # neuf (E2.c) — mort-né ?
server\deezer\extractor.py + sync_checker.py                                     # outillage local documenté (A7-07) — NE PAS re-signaler comme mort
server\frontend\node_modules\flatted\...                                         # à exclure (node_modules scanné par erreur — bruit)
```

## 3. Deptry

`python -m deptry server/` → 463 issues, quasi tout = faux positifs connus (DEP001 packages locaux). Signal potentiellement utile :

```
server\workers\tasks\import_rb.py:8,10: DEP003 'boto3'/'botocore' transitive     # boto3 EST pinné dans requirements.txt — faux positif d'exécution deptry hors contexte, à confirmer
```

## 4. pip-audit (backend)

Local (Windows) : `pip-audit -r requirements.txt` échoue sur `essentia==2.1b6.dev1389` (wheel cp313 **Linux-only** — pas de distribution Windows ; comportement attendu, l'image worker est Linux).
Relancé sur requirements **moins essentia** → **26 vulnérabilités connues dans 7 packages** :

```
python-dotenv    1.0.1   PYSEC-2026-2270  fix 1.2.2
requests         2.32.3  PYSEC-2026-1872/2275  fix 2.32.4 / 2.33.0
curl-cffi        0.7.4   PYSEC-2026-2431  fix 0.15.0
python-jose      3.3.0   PYSEC-2024-232/233 (algorithm confusion / DoS), PYSEC-2025-185 (sans fix)  fix 3.4.0
python-multipart 0.0.9   PYSEC-2026-1851/1852/3036-3040 (7 avis)  fix jusqu'à 0.0.31
starlette        0.38.6  PYSEC-2026-161/248/249/1941/1943/2280/2281 (9 avis)  fix jusqu'à 1.3.1
ecdsa            0.19.2  PYSEC-2026-1325 (transitive via python-jose)
```

**⚠ Candidat majeur (A5/A6)** : le job CI `audit` (deploy.yml:80-90) est en `continue-on-error: true` ET absent du `needs:` du job `deploy` (deploy.yml:108) → le gate pip-audit posé par AU1 (A5-04) est **doublement non-bloquant**. Les 26 vulns passent en prod silencieusement. python-jose = la lib JWT de l'auth ; python-multipart = l'upload XML Rekordbox ; starlette = FastAPI lui-même.

## 5. npm audit / npm outdated (frontend)

`npm audit` → **5 vulnérabilités (4 high, 1 moderate)**, toutes dans la chaîne dev/build (pas le runtime navigateur) :

```
esbuild ≤0.24.2 (moderate, GHSA-67mh-4wv8-2f99, dev server) ← vite ≤6.4.2
nanoid ≤3.3.16 (high ×2, boucle infinie)                     fix simple `npm audit fix`
postcss ≤8.5.22 (high ×2, path traversal sourcemap)          fix simple `npm audit fix`
vite 5.4.21 → fix = vite 8.2.1 (breaking)
```

`npm outdated` (majeurs en retard) : vite 5→8, pinia 2→4, vue-router 4→5, vitest 3→4, @vitejs/plugin-vue 5→6, jsdom 26→29. Mineurs : axios 1.18.1→1.19.0, vue 3.5.38→3.5.41, eslint, prettier.

## 6. TODO / FIXME / XXX / HACK

**1 seul** dans le code réel : `PlatformLink.vue:38` (TODO logos officiels — placeholder assumé). Les 2 autres hits = hashes base64 dans package-lock.json (bruit).

## 7. Comptages mécaniques (à croiser avec CLAUDE.md — dimension A7)

- Migrations : **43 fichiers** `.py` dans `alembic/versions/` (CLAUDE.md dit 43 ✓).
- Vues frontend : **18** (CLAUDE.md ✓). Composants : 33 racine + 12 filters + 3 charts + 9 admin = **57** (CLAUDE.md ✓ : 48 shared + 9 admin).
- Routers : 15 annoncés, 105 endpoints annoncés — à recompter (A7).
- Modèles : 31 classes / 12 modules annoncés — à recompter (A7).

## 8. Environnement d'audit — limites

- `gh` CLI absent de la machine → statut des runs CI non vérifiable localement (les smoke tests deploy passent, dernier deploy 2026-08-08 OK d'après le git log).
- pip-audit local tourne sur Windows/py313 SANS essentia (voir §4) — la référence exacte reste le job CI ubuntu.
- Aucune commande d'écriture exécutée : audit lecture seule, working tree propre avant/après.

## 9. Rappels de périmètre pour les agents

- **Résidus ACCEPTÉS à ne pas re-signaler** (audit 2026-07 + CLAUDE.md) : `/storage/*` non authentifié (C3 différé assumé), 11 endpoints taxonomy réservés non branchés (Q1b-2), absence délibérée d'index unique sur `deezer_id`/`beatport_id` catalog (X1/X3), chaîne Alembic non bootstrappable (connu, baseline à faire), dev local full-stack non supporté (Q6), colonnes `artists.bio/country/real_name/soundcloud_id` + `sets.event/venue/description` gardées avec schemas purgés (Q3), pas de purge historique git des tokens TIDAL (Q4 option B, token révoqué), endpoints curl admin documentés sans UI (Q1b-4), `uq_artists_deezer_id` créé hors migrations (documenté MANUAL), tests harnesses gardent leur `create_all` (AU3), aggregate-only counts et set tracklists non filtrés par `catalog_visible` (résidu C3 accepté), badge « estimé » et autorité basse de `bpm_source='analysis'` (E2.b acté).
- Un finding déjà vu en 2026-07 et toujours présent garde sa clé d'origine (`2026-07/Ax-nn`) — le signaler comme RÉCURRENCE.
