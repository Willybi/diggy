# Benchmark backfill discographie — local (C14.a Phase 2, GATE)

Outillage **local** (pattern A7-07 : tourne sur le PC de l'opérateur, pas sur le VPS)
qui **mesure** — sur un échantillon stratifié d'artistes — les deux chiffres dont
dépend la décision d'aller (ou non) au backfill de discographie Deezer de la
**Phase 2 de C14.a** :

1. **NET-NEW par artiste, par tier** — sur toute la discographie Deezer d'un artiste,
   combien de titres **ne sont PAS déjà** dans notre `catalog` (dédup sur l'identité
   d'ingestion EXACTE `normalized_key = normalize(title) + " - " + normalize(artist)`,
   + `isrc` avec `--with-isrc`). Décide **où couper la cohorte du backfill** (là où le
   net-new reste digeste).
2. **COÛT** — requêtes/artiste (`~1 + nb albums`) → temps de fetch Deezer au plancher
   résidentiel ; et l'**inflow Beatport** que le net-new créerait (capacité
   ~9 900/jour, le **risque throttle AV10**) + le CPU d'embedding EffNet impliqué.

> **C'est une GATE, pas le backfill.** Rien n'est écrit — ni en prod (lectures
> `SELECT`/`COPY` pures), ni sur Deezer (des `GET` seulement). Il n'y a
> **délibérément pas de `--apply`** : un benchmark n'a rien à appliquer. Le compute
> tourne **en local** (IP résidentielle) car le Deezer de masse est **interdit sur le
> VPS** (leçon AV10) ; le fetch réutilise l'**image serveur de prod** pour que
> `make_normalized_key` + la pile HTTP/rate-limit Deezer soient **byte-identiques à
> l'ingestion** → le net-new mesuré = ce que la prod insérerait vraiment.

Moule de [`worker/set_artist_backfill/`](../set_artist_backfill/README.md) (même canal
SSH/psql, même compute en conteneur) **moins la voie d'écriture**.

> **Leçon C9 (IP résidentielle)** : `--deezer-rate 1.0` par défaut — un plancher
> inter-requête appliqué PAR-DESSUS le `RateLimiter` réutilisé. **Ne JAMAIS relever le
> débit prod.**

## Les 4 étapes (orchestrées par `benchmark_discography.py`)

1. **SAMPLE** — `COPY ... TO STDOUT` lecture seule d'un échantillon **stratifié**
   d'artistes, strates **mutuellement exclusives** par profondeur décroissante :

   | tier | définition |
   |---|---|
   | `a_lib` | présent dans la bibliothèque d'un user (`user_tracks`) |
   | `b_sets12m` | ≥ 5 sets DJ fiables / 12 mois (roots-only, non-virtual, `unreliable IS NOT TRUE`, `coalesce(event_date, played_date)`) |
   | `c_catalog` | ≥ 10 titres catalog |
   | `d_traine` | longue traîne : a un `deezer_id` mais peu de signal (`--traine-strict` = 0 set, < 3 titres, pas en lib) |

   `--per-tier` par strate (`ORDER BY random()`, `--seed` pour reproductibilité),
   seulement les artistes à `deezer_id` réel (`<> 'NOT_FOUND'`). → `data/sample.csv`.
2. **INDEX** — `COPY` lecture seule de l'index d'**identité** du catalog
   (`normalized_key,isrc` de chaque ligne) → deux sets Python. **Mis en cache**
   (`data/catalog_index.csv`, ~700k lignes = un gros pull one-off ; `--reuse` le
   saute). C'est un dump d'identité — jamais commité (`.gitignore`).
3. **FETCH** — `docker run` du driver (`fetch_driver.py`) dans l'image serveur de
   prod : pour chaque artiste, marche `/artist/{id}/albums` (paginé) → `/album/{id}`
   (tracklist embarquée, sans isrc), calcule la clé d'ingestion par titre, dédup
   intra-artiste, écrit `data/discography.ndjson` (1 record/artiste + compteur de
   requêtes). `--with-isrc` ajoute un `GET /track/{id}` PAR TITRE (cher, cf. plus bas).
4. **REPORT** — classe chaque titre in-base vs net-new contre l'index, agrège par tier
   (médiane/moyenne par artiste : net-new, requêtes, titres ; % déjà en base), et
   projette le fetch Deezer + l'inflow Beatport + le CPU embedding pour des tailles de
   cohorte candidates. Affiche le rapport + écrit `data/benchmark_report.json`.

### `normalized_key` vs `isrc` (le compromis mesuré par cet outil)

Les tracklists d'album Deezer (`/album/{id}` → `tracks.data`) **ne portent PAS
d'isrc** — l'obtenir coûte un `GET /track/{id}` **par titre** (explosion de requêtes).
Le **chemin par défaut** dédup sur `normalized_key` SEUL (clé calculée depuis le
résumé d'album, `~1 + nb albums` requêtes) — c'est le modèle de coût de la roadmap ET
c'est **fidèle à ce qui serait inséré** : un backfill « pas cher » alimente des titres
sans isrc, donc l'ingestion dédup sur `normalized_key` seul.

`--with-isrc` (opt-in, **cher**) mesure combien de titres « net-new par clé » l'isrc
rattraperait en réalité = les **doublons que le chemin clé-seule créerait**. À lancer
sur un **échantillon RÉDUIT** (`--limit 2 --with-isrc`), c'est un sous-run de
calibration, jamais les ~40.

## Usage

```bash
# run complet ~40 artistes (10/tier), chemin clé-seule (défaut)
python worker/discography_backfill/benchmark_discography.py

# plus large + reproductible
python worker/discography_backfill/benchmark_discography.py --per-tier 15 --seed 0.42

# calibration isrc sur une poignée d'artistes (cher)
python worker/discography_backfill/benchmark_discography.py --limit 2 --with-isrc

# une fois la coupe décidée : projection TOTALE d'une cohorte exacte
python worker/discography_backfill/benchmark_discography.py --reuse \
    --cohort 'a_lib=580,b_sets12m=971,c_catalog=1500'

# ré-agréger un fetch précédent sans re-taper prod ni Deezer
python worker/discography_backfill/benchmark_discography.py --reuse
```

`--reuse` réutilise `data/catalog_index.csv` + `data/discography.ndjson` d'un run
précédent → itération instantanée sur le rapport / les projections (aucun réseau).

## Lecture du rapport (ce que la GATE tranche)

- **`new/art` (médiane net-new/artiste) par tier** : si `a_lib`/`c_catalog` ≈ 0
  (déjà en base) et `d_traine` très haut, c'est la tension attendue *net-new haut ↔
  pertinence basse* → couper la cohorte là où le net-new par artiste justifie encore
  le coût d'enrichissement.
- **`beatport d` (jours de drain)** : chaque net-new devient du backlog Beatport
  (~9 900/j) + du churn autovacuum `catalog` — un gros lot = jours de CPU soutenu
  (**risque throttle AV10**). C'est **le** garde-fou : étaler / abaisser le cap si la
  projection dépasse quelques jours.
- **`%in-base`** : sanity-check (un tier profond doit être très couvert).
- **isrc-only (`--with-isrc`)** : % de doublons que le chemin clé-seule créerait — si
  faible, le chemin pas-cher est sûr ; si élevé, le vrai backfill devra taper
  `/track/{id}` pour l'isrc (bien plus cher).

Puis **arbitrer la cohorte du backfill avec William** → PUIS le backfill réel ci-dessous.

**GATE PASSÉE 2026-09-25** (échantillon 40 artistes) : cohorte décidée = `a_lib` (573)
+ `b_sets12m` (970) ≈ **1 540 artistes → ~87k net-new**, méthode titre (dupes cosmétiques
mesurés ~5 %, éliminés OPS-side par l'ISRC des hits `/track`) ; `c_catalog` (15 149) en
tranche triée plus tard, `d_traine` (139 833) différé.

---

# Backfill réel (mode ÉCRITURE) — après la GATE

Une fois la cohorte tranchée, `backfill_discography.py` (host) + `bundle_driver.py`
(conteneur) + l'OPS `server/api/scripts/import_discography.py` **écrivent** les net-new
en base. **Tout le travail Deezer coûteux (rate-limité) reste LOCAL** ; le serveur ne
fait que le Beatport ultérieur (décision « serveur épargné », leçon AV10).

## Les 4 étapes (orchestrées par `backfill_discography.py`)

1. **COHORT** — `COPY` lecture seule des artistes de la cohorte (`--tiers`, défaut
   `a_lib,b_sets12m`), fenêtrable `--after-id`/`--limit`/`--shard` (salves).
2. **INDEX** — `COPY` de l'index d'identité (partagé avec le benchmark, `--reuse-index`).
3. **BUNDLE** — `docker run` de `bundle_driver.py` (+ son frère `fetch_driver.py`) : marche
   la discographie, **classe net-new par titre** contre l'index, et fetch `/track/{id}`
   **UNIQUEMENT pour les net-new** (borne le coût) → `data/bundle.ndjson` (1 record/artiste,
   les **hits Deezer complets** : isrc, contributors feat., album).
4. **IMPORT** — pipe le bundle à l'OPS `import_discography.py` (`--apply` propagé). L'OPS
   **rejoue le funnel VERBATIM** : `bulk_get_or_create_catalog` (dédup ISRC→normalized_key
   contre la DB LIVE — l'ISRC du hit **fond une variante de titre** dans la ligne existante,
   d'où le −5 % de dupes gratuit) + `enrich_entry` + linkers artiste/album +
   `_mark_searched(deezer)` + `enrich_priority` **BAS** (`DISCOGRAPHY_ENRICH_PRIORITY`=10,
   MAX-mergé → **jamais devant les tracks de sets** C12). Beatport laissé au drain VPS.

## Séquence OPS (dump-first, comme tout script `--apply`)

```bash
# 1. déployer l'OPS import_discography.py (push → CI → image) — il ship sous api/
# 2. dry-run échantillon → LIRE le sample de précision (artiste → +N net-new)
python worker/discography_backfill/backfill_discography.py --limit 20
# 3. dry-run pleine cohorte (la 1re fois : ~12 h de walk + fetch net-new à 1 rps)
python worker/discography_backfill/backfill_discography.py
# 4. DUMP PROD CHIFFRÉ (docs/restore.md) AVANT tout --apply
# 5. écrire PAR SALVES (lisse le churn autovacuum, leçon X4/AV10)
python worker/discography_backfill/backfill_discography.py --shard 0/4 --apply
python worker/discography_backfill/backfill_discography.py --shard 1/4 --apply   # etc.
```

> ⚠️ `--apply` **mute la prod** (crée `catalog`/`catalog_artists`/`albums`, peut fondre
> une ligne sur collision de `deezer_id`). **DUMP D'ABORD.** L'OPS est idempotent (une
> reprise compte `already_deezer`), mais un mauvais dump n'est pas récupérable.

Checkpoint local `data/processed_artist_ids.txt` (marqueur one-shot par artiste) ;
`--shard M/N` pour des salves parallèles ; `--reuse-bundle --apply` écrit un bundle déjà
fetché sans re-taper Deezer. Après l'écriture, Beatport draine bpm/key/genres au fil de
l'eau à la priorité basse (~9 j pour ~87k, derrière les sets), et l'outil d'embeddings
(`worker/embedding_backfill/`) ramassera les nouvelles lignes.

## Tests

- `pytest worker/discography_backfill/test_benchmark_discography.py -q` +
  `test_backfill_discography.py -q` — logique PURE des 2 orchestrateurs host (stdlib, hors
  CI ; requêtes SQL, classification, agrégation, projections, checkpoint, summarize).
- `pytest tests/worker/test_discography_fetch_driver.py -q` (benchmark) +
  `test_discography_bundle_driver.py -q` (backfill) — marche PURE des drivers (pagination,
  dédup, net-new vs keyset, fetch `/track` net-new, outage) avec un pool Deezer mocké — CI.
- `pytest tests/worker/test_import_discography.py -q` — ORCHESTRATION de l'OPS (routing
  already_deezer/merged, priorité, sample, dry-run vs apply) avec le funnel mocké — CI.

## Notes

- **Benchmark** : aucun dump requis (rien n'est écrit) ; seul coût prod = la passe `COPY`
  de l'index. **Backfill `--apply`** : DUMP obligatoire (il mute la prod).
- Les drivers sont **bind-montés** à `/work`, jamais bakés dans l'image (comme les autres
  outils locaux) ; `bundle_driver.py` importe `fetch_driver.py` (helpers de marche partagés),
  donc les deux sont copiés dans le workdir avant le `docker run`.
- **Mémoire** : en `--apply` l'OPS commite + libère par artiste (borné) ; un **dry-run de
  la cohorte ENTIÈRE** garde en revanche toutes les lignes en attente dans une seule
  transaction non commitée → **dry-run par salves aussi** (`--shard`/`--limit`), pas 87k
  d'un coup. `--limit` est loop-safe (appliqué après le checkpoint, pas en SQL).
- **Résidus connus (dette, non bloquants)** : le CTE de cohorte, le scaffolding host
  (ssh/docker) et la boucle de marche sont **dupliqués** entre `benchmark_*` et
  `backfill_*`/`bundle_driver` — risque de dérive si on édite un seul côté. Le benchmark
  étant figé (gate passée), non refactorisé pour l'instant ; à mutualiser si on y retouche.
