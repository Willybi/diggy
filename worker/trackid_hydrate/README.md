# Hydratation « clean » des sets TrackID (local-compute / VPS-commit)

Outillage **local** (pattern A7-07 : tourne sur le PC de l'opérateur, pas sur le
VPS) qui **hydrate proprement** un lot de sets TrackID scorés (C12) depuis l'**IP
résidentielle**, en parallèle du drain nocturne `backfill_trackid_sets` du VPS.
Jumeau de [`worker/beatport_backfill/`](../beatport_backfill/README.md) :
même canal SSH/psql, même forme dry-run/apply + checkpoint + relançable en salves,
même compute en conteneur Docker (image serveur de prod).

**Idée directrice** : le **compute** (fetch TrackID + Deezer/Beatport/BPM/EffNet)
est fait en LOCAL dans un conteneur, et l'**écriture** est un seul push
transactionnel « état final » sur le VPS — au lieu de laisser le drain VPS piocher
jour après jour au fil des UPDATE.

| Étape | Où | Quoi |
|-------|----|------|
| **L1a/L1b** driver | conteneur (image serveur + EffNet) | Deezer search/match + cover + preview→BPM/EffNet + Beatport → NDJSON par piste |
| **L2** orchestrateur | hôte (`hydrate.py`, stdlib) | worklist prod → détail TrackID → conteneur → **bundle** NDJSON par set → push VPS |
| **L3** OPS | VPS (`import_trackid_clean.py`) | **rejoue le funnel d'import/enrichissement verbatim** contre la DB LIVE, transaction par set |

## Pourquoi ce découpage

- **Transparence** : le compute lourd (EffNet ≈ 8 CPU-s/piste) tape l'IP
  résidentielle, pas le VPS Hostinger sous police *fair-use* (cf. la leçon
  [`hostinger-cpu-throttle`] : un gros rattrapage d'enrichissement = ~6-7 j de CPU
  soutenu + autovacuum sur `catalog`). L'hydratation « clean » sort ce coût du VPS.
- **Un write « état final »** : au lieu de dizaines de milliers d'UPDATE étalés sur
  des jours de drains, chaque set arrive **déjà enrichi** (Deezer + Beatport + BPM +
  embedding) et est écrit en UNE transaction atomique.
- **Sûreté = l'identité est résolue au PUSH, contre la DB LIVE.** Le bundle ne porte
  que de la **donnée pré-calculée** (les hits Deezer/Beatport, les octets de cover, le
  BPM, l'embedding) — **jamais** une décision d'identité. C'est le script OPS L3 qui,
  au moment du commit, **réutilise le funnel verbatim** (`import_audiostream`,
  `bulk_get_or_create_catalog`, `enrich_entry` + linkers artiste/album,
  `enrich_from_beatport`, `_mark_searched`) pour faire le dedup / merge-sur-collision /
  get-or-create artiste-album **contre l'état réel** de la base. Zéro
  ré-implémentation des matchers → aucune régression de la corruption d'id-plateforme
  corrigée sous X1/X3/X4 (un id plateforme n'est PAS une identité par enregistrement ;
  un mauvais merge est une corruption coûteuse, invariant #4).

## Le flux (par lot de N sets)

1. **WORKLIST** — les sets `not_hydrated` **scorés** (`trackid_id, slug, score`)
   streamés depuis la prod, lecture seule, via le canal SSH/psql documenté alimenté
   d'un `COPY (...) TO STDOUT` :

   ```sql
   COPY (
     SELECT trackid_id, slug, score
     FROM trackid_index
     WHERE hydration_state = 'not_hydrated'
       AND score IS NOT NULL          -- les sets « reste » à score NULL ne sont JAMAIS hydratés
     -- [AND score < :after_score]     -- borne grossière de salve
     ORDER BY score DESC, trackid_id DESC
     -- [LIMIT :n]
   ) TO STDOUT WITH (FORMAT csv, HEADER true);
   ```

   Même ordre que le drain nocturne C12. Les ids déjà dans le checkpoint local sont
   filtrés. Le vrai garde inter-runs = le checkpoint + le flip `hydration_state` fait
   par L3 (`--after-score` n'est qu'une borne grossière, `score` étant un float non
   unique).
2. **DÉTAIL** — pour chaque set, `GET .../audiostreams/{slug}` avec l'**échelle de
   débit adaptative** (6→3→2→1 + cooldown) recopiée fidèlement de l'outil shadow
   (`scripts/local/trackid_spider/shadow.py`, lui-même réplique de
   `trackid/{client,parsing}.py`). On garde le payload `detail` COMPLET (consommé par
   `import_audiostream(prefetched_detail=)` sur le VPS) + on construit la tracklist
   fusionnée (`merge_tracklist`/`is_id_track` prod-fidèles) + on télécharge les octets
   de la cover du set → `set_artwork_b64`. Un set dont le détail échoue (outage /
   throttle épuisé) est **DROPPÉ** (ni hydraté ni checkpointé → re-tenté plus tard).
3. **DRIVER** — CSV `set_trackid_id,position,title,artist,is_id` pour TOUTES les
   pistes du lot, build de l'image serveur de prod (`server/Dockerfile`) puis de
   l'image-paquet fine (`worker/trackid_hydrate/Dockerfile`, +EffNet), puis `docker
   run` du driver `enrich_driver.py` : Deezer search/match (matchers X3/X4 verbatim) +
   octets de cover + **une seule** preview partagée entre BPM (Essentia) et embedding
   (EffNet) + Beatport, émis en NDJSON par piste. Les knobs d'IP résidentielle passent
   par `-e` + `REDIS_URL` pointé sur un port fermé (la fenêtre de rate-limit partagée
   *fail-open* vers le bucket local).
4. **BUNDLE** — jointure du NDJSON driver sur la tracklist par `(set_trackid_id,
   position)` → un bundle par set sur le contrat de `import_trackid_clean.py` (sa
   docstring fait autorité). Le bloc `deezer` du driver est trimé à `track` +
   `cover_catalog_b64` + `cover_album_b64` (les URLs preview/cover sont retirées — L3
   ne les lit pas). Une piste sans ligne driver `found` (outage Deezer, `not_found`,
   ou piste `id`) → `deezer: null` + tout enrichissement null.
5. **PUSH** — voir la matrice de modes ci-dessous.

## Modes de push

| Flag | Comportement |
|------|--------------|
| *(aucun)* | **Dry-run LOCAL** : le bundle est écrit dans le workdir, **rien** n'est poussé (pas de ssh, pas de checkpoint). |
| `--dry-run-push` | Pipe le bundle au script OPS **SANS** `--apply` : L3 fait tourner le funnel, imprime ses compteurs et **rollback**. Aucun write, aucun checkpoint. |
| `--apply` | Pipe le bundle au script OPS **AVEC** `--apply` (commit) puis **checkpointe** les set ids poussés. |
| `--reuse-bundle` | Re-pousse un `bundle.ndjson` existant sans re-fetch ni re-run du conteneur (ex. dry-run local → inspection → `--reuse-bundle --apply`). |

## Usage

```bash
# dry-run LOCAL sur un petit échantillon (worklist + fetch + conteneur réels ; RIEN poussé)
python worker/trackid_hydrate/hydrate.py --limit 20

# + faire tourner l'import OPS sur le VPS, rollback (vérifier les compteurs)
python worker/trackid_hydrate/hydrate.py --limit 20 --dry-run-push

# hydrate + écriture en prod (DUMP PROD D'ABORD)
python worker/trackid_hydrate/hydrate.py --apply

# re-pousser un bundle déjà assemblé, sans re-calculer
python worker/trackid_hydrate/hydrate.py --reuse-bundle --apply

# fenêtre de salve (borne de score grossière) + limite
python worker/trackid_hydrate/hydrate.py --after-score 80 --limit 5000 --apply
```

### Options & knobs de cadence

| Option | Défaut | Rôle |
|--------|--------|------|
| `--limit N` | 0 (tout) | `LIMIT` de la worklist |
| `--after-score S` | — | ne tire que les sets `score < S` (borne grossière de salve) |
| `--detail-rate R` | 1.0 | req/s de départ du fetch détail TrackID (backoff adaptatif 3→2→1 sur 429/403 ; le spider a prouvé 1 req/s poli) |
| `--rate R` | 1.0 | **`DEEZER_RATE`** conteneur — plancher résidentiel Deezer. **Leçon C9** : un débit Deezer résidentiel soutenu se fait rate-limiter ; **1 rps + cooldown** le lève. **Ne JAMAIS relever le débit en prod.** |
| `--concurrency K` | 5 | `DEEZER_CONCURRENCY` (gather par ligne ; le token bucket cadence quand même) |
| `--beatport-rate R` | 4.0 | **`BEATPORT_RATE`** conteneur (le probe a prouvé 6 rps 0×403, marge à 4). **Ne JAMAIS relever le débit en prod.** |
| `--beatport-concurrency K` | 6 | `BEATPORT_CONCURRENCY` (les deux sémaphores beatport le lisent → doivent s'accorder) |
| `--executor-workers K` | 2 | **`HYDRATE_EXECUTOR_WORKERS`** — largeur du pool Essentia/EffNet (CPU-bloquant). **Cap le pic CPU résidentiel** (mettre à 1 sur une machine chargée). |
| `--workdir` | `<paquet>/data` | CSV + NDJSON + checkpoint (gitignoré) |

## Séquence prod (OPS)

> **⚠️ `--apply` MUTE des lignes en prod** via le funnel réutilisé (`catalog`,
> `catalog_artists`, `albums`, `track_embeddings`, `sets`/`set_tracks`, artwork MinIO,
> éventuel merge sur collision d'id). Le script OPS est idempotent et commit **par
> set** (un crash à mi-parcours est sûr), mais un **DUMP CHIFFRÉ PRÉALABLE reste
> OBLIGATOIRE** (cf. [`docs/restore.md`](../../docs/restore.md)) — un mauvais dump ne se
> rattrape pas.

1. **Déployer `import_trackid_clean.py` d'abord** (push → CI → image) : le script OPS
   doit être en prod dans l'image `api`.
2. **STOPPER le drain VPS** pendant le marathon local — sinon le VPS **et** le local
   hydratent les mêmes sets (`not_hydrated` scorés, même tri) :

   ```bash
   ssh diggy-vps "cd /root/diggy && docker compose exec -T redis redis-cli SET trackid_backfill_done 1"
   ```

   (le sentinel `trackid_backfill_done=1` fait no-op le drain `backfill_trackid_sets`
   au prochain beat — c'est un interrupteur manuel, il n'est jamais reposé
   automatiquement).
3. **Dry-run** (`--limit 20`, puis `--dry-run-push` pour voir tourner le funnel L3 et
   lire ses compteurs). Aucune écriture.
4. **DUMP** chiffré de la prod (`docs/restore.md`) — **avant** tout `--apply`.
5. **`--apply`** en salves (`--limit` / `--after-score`). Chaque salve est idempotente
   (checkpoint + `hydration_state='not_hydrated'` + `already_*` côté OPS).
6. **Re-vérifier la convergence** (re-dry-run : le backlog `not_hydrated` scoré
   décroît ; un re-`--apply` recompte tout en `already_*` sans rien re-stamper).
7. **Ré-armer le drain VPS** une fois le marathon fini :

   ```bash
   ssh diggy-vps "cd /root/diggy && docker compose exec -T redis redis-cli DEL trackid_backfill_done"
   ```

> **Fenêtre horaire** : le drain Beatport du VPS tourne **6h→23h** et le drain BPM
> **00h→03h**. Le conteneur local tape Beatport/Deezer via l'IP résidentielle
> (indépendante), mais lancer les salves lourdes en **heures creuses du VPS** limite
> tout recouvrement.

## Réalités

- **Marathon multi-semaines** : EffNet ≈ 8 CPU-s/piste + le plancher Deezer résidentiel
  1 rps ⇒ le débit est borné par le compute, pas par la DB. Sur le scope C12 (~297k
  sets / ~1,09M pistes) c'est un marathon en salves de plusieurs semaines — d'où le
  checkpoint + `--after-score` + `--reuse-bundle`.
- **Image = build TF ~500 Mo** : l'image-paquet est l'image serveur de prod (`FROM
  server/Dockerfile`) + `essentia-tensorflow==2.1b6.dev1389` (superset du wheel
  `essentia` déjà présent, même version → parité BPM avec le drain VPS) + le graphe
  Discogs-EffNet. Premier build = long ; ensuite en cache.
- **Surveiller le VPS au push** : même si le compute est local, chaque `--apply` génère
  de l'écriture (INSERT/UPDATE `catalog`, uploads MinIO) → un pic d'autovacuum. Étaler
  les salves et surveiller `ssh diggy-vps docker stats` / `sar` (leçon
  [`hostinger-cpu-throttle`]).

## Étape OPÉRATEUR — un vrai e2e demande Docker + prod

Un e2e **complet** (build de l'image ~500 Mo, `docker run` du driver, fetch TrackID
réel, Essentia/EffNet, push ssh vers la prod) n'est **pas** exécuté par la suite de
tests : il exige Docker, le réseau et l'accès prod. Le contrat **L2 → L3** (le seul
couplage : la forme du bundle) est prouvé **automatiquement, sans Docker/réseau/
Essentia** par `tests/worker/test_hydrate_clean_integration.py` (bundle forgé via le
vrai `hydrate.assemble_bundle` → ingéré par le vrai `import_bundles` sur aiosqlite).
Le run réel reste une action OPÉRATEUR à dérouler selon la séquence ci-dessus.

## Tests

```bash
pytest worker/trackid_hydrate/ -q                       # logique pure hôte (aucun réseau/serveur)
pytest tests/worker/test_hydrate_clean_integration.py -q # contrat L2↔L3 (sans Docker/Essentia)
ruff check worker/trackid_hydrate/
```

Les tests **de paquet** (`worker/trackid_hydrate/test_hydrate.py`,
`test_enrich_driver.py`) sont volontairement **hors `tests/`** : le CI n'a ni l'image
serveur ni le réseau et ne doit pas dépendre de ce paquet d'outillage local. Seule la
logique pure y est testée. Le **test d'intégration L2↔L3**, lui, vit sous `tests/` (il
n'importe que le contrat de bundle, pas le driver) et tourne au CI.

[`hostinger-cpu-throttle`]: ../../CLAUDE.md
