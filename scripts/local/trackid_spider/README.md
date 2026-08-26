# TrackID spider local (C11 — Index TrackID, lot L2)

Outil **local autonome** (pattern A7-07 : tourne sur le PC, jamais sur le VPS) qui
énumère **exhaustivement** le listing public
`GET https://trackid.net/api/public/audiostreams` (~381 k sets) dans un **staging
SQLite local**, à **1 requête/seconde STRICT, sans parallélisme**. Il ne se
connecte **jamais** à la prod, n'importe **jamais** le paquet `server`, et n'écrit
que dans un fichier SQLite local. Un lot ultérieur (**L3**) importera le CSV/NDJSON
exporté dans la table prod `trackid_index` — hors périmètre de cet outil.

> **Autonome** : `stdlib` + `httpx` uniquement. Aucune dépendance au runtime
> serveur. Se lance depuis la racine du repo par chemin de script.

## Faits API confirmés (sonde manuelle réelle, 2026-08-26)

Le listing expose, **sans appel détail**, tout ce dont L1/L3 ont besoin :

| Fait | Valeur mesurée |
|------|----------------|
| `rowCount` global | **~381 486** (croît dans le temps ; le 381 314 du brief est un instantané) |
| Plafond `pageSize` | **100** en dur (200/500/1000 renvoient tous 100 items) — 100 = le plafond efficace |
| Fenêtrage `minAddedOn`/`maxAddedOn` | fonctionne ; **`[min, max)` (max EXCLUSIF)** confirmé |
| `rowCount` fenêtré | renvoyé dès la page 0 **sans consommer les pages** → pré-scan quasi gratuit (ex. janv. 2024 = 11 100) |
| Tri par défaut | `addedOn` **décroissant** (plus récent d'abord) |
| `status`, `audioStreamType` | **entiers** (pas des chaînes) |

**Champs du payload HORS du contrat de colonnes** (préservés intégralement dans
`raw_json`, à remonter à L1) : `order`, `duration`, `favouriteDate`, `isPrivate`,
`detectionProcesses` (lourd — présent dans le listing), `amendments`,
`audioStreamReprocesses`, `accountAudiostream`, `canReprocess`.

> Les validations formelles V1-V6 sont **codées** (`probe.py`) et se lancent contre
> l'API réelle par `spider.py probe` ; les tests, eux, restent **mockés** (aucun
> réseau). Voir « Mode probe » ci-dessous.

## Architecture (modulaire)

| Module | Rôle |
|--------|------|
| `mapping.py` | payload camelCase → contrat de colonnes snake_case (+ `raw_json` zéro-perte) |
| `client.py` | client HTTP sync, **1 req/s strict**, backoff exponentiel, plafond pageSize=100 |
| `store.py` | staging SQLite (miroir brut) + checkpoint par fenêtre + export + requêtes volumétrie |
| `windows.py` | plan de fenêtres **statique** + construction adaptative (bisection temporelle) |
| `probe.py` | mode probe (A.0 / V1-V6 + pré-scan mensuel) → `report.md` / `plan.json` / `payload_sample.json` / `prescan.json` |
| `crawl.py` | mode crawl (consomme le plan, reprise idempotente, upsert, passe finale) |
| `reports.py` | rapports **complétude** (réconciliation 3 voies) + **volumétrie** |
| `logs.py` | logs JSON structurés (progression / débit / ETA) + ligne console |
| `spider.py` | CLI argparse (`probe` / `crawl` / `export` / `report` / `status`) |

## Contrat de colonnes de l'export (partagé L1 ↔ L3 — ordre EXACT)

```
trackid_id, slug, title, channel, styles, status, is_deleted, track_count,
time_hit_rate, track_hit_rate, processing_priority, artwork_url, added_on,
created_on, added_by, added_by_id, audio_stream_type, external_id, url,
favourite_count, like_count, average_rating, raw_json, window_id
```

`styles` et `raw_json` sont sérialisés en **JSON compact** (CSV comme NDJSON, pour
garder les colonnes identiques). `is_deleted` = 0/1 dans le staging (le booléen réel
survit dans `raw_json`). `window_id` = label de la fenêtre statique d'origine.
**Aucun champ du payload n'est perdu** : même un champ hors contrat survit dans
`raw_json`.

## Les 4 étapes

### 1. Mode probe — `spider.py probe`

Sonde et **documente** l'API (réseau réel, toujours 1 req/s), puis écrit dans le
workdir :

- `report.md` — verdicts **V1** (fenêtrage adjacent sans chevauchement ni perte),
  **V2** (plafond pageSize), **V3** (stabilité pagination sur fenêtre figée),
  **V4** (filtre `styles=`, bonus), **V5** (isDeleted inclus dans rowCount ?),
  **V6** (pré-scan volumétrie mensuelle) + **politique d'erreurs HTTP**.
- `plan.json` — le **plan de fenêtres statique** (seuil ~10 000 items/fenêtre,
  auditable, contiguïté auto-vérifiée).
- `payload_sample.json` — un item de listing brut réel (schéma de référence).
- `prescan.json` — carte de distribution rowCount par mois (~85 sondes, 1/mois).

```bash
python scripts/local/trackid_spider/probe.py --help   # (via spider.py)
python scripts/local/trackid_spider/spider.py probe --since 2016-01
```

**Pourquoi fenêtrer par `addedOn`** : une fenêtre dont `max <= run_start` ne peut
**jamais** gagner d'item pendant le crawl (un nouvel item a `addedOn = now > max`)
→ les offsets de pagination ne bougent pas sous nos pieds. La bisection temporelle
découpe les mois « chauds » (imports massifs : une discographie ajoutée en minutes)
en fenêtres denses et courtes, bornant la profondeur de pagination.

### 2. Mode crawl — `spider.py crawl`

Consomme `plan.json`, crawle **chaque fenêtre** dans `staging.db` :

- **1 req/s strict**, backoff exponentiel sur erreur.
- **checkpoint par fenêtre** (`pending`/`in_progress`/`done`/`failed`/`overflow`) +
  `pages_done` → reprise **idempotente** (une interruption reprend sans perte ni
  doublon ; l'upsert par `trackid_id` rend tout re-fetch inoffensif).
- fenêtre `overflow` si le `rowCount` observé au run dépasse le plan (pages en trop
  crawlées quand même → aucune perte, juste un signal).
- **passe finale** `[run_start, now)` pour capter les ajouts survenus pendant le
  crawl.
- erreur HTTP persistante (après N retries) → fenêtre `failed` (reprise au run
  suivant, sinon traitement manuel).

```bash
python scripts/local/trackid_spider/spider.py crawl
python scripts/local/trackid_spider/spider.py status   # résumé des états de fenêtres
```

### 3. Export — `spider.py export`

Exporte le staging vers CSV (défaut) ou NDJSON avec l'**ordre de colonnes exact**
du contrat — c'est ce fichier que L3 importera.

```bash
python scripts/local/trackid_spider/spider.py export --format csv
python scripts/local/trackid_spider/spider.py export --format ndjson
```

### 4. Rapports — `spider.py report`

Écrit deux livrables analytiques autonomes (JSON + texte) :

- **Complétude** : réconciliation 3 voies `Σ(rowCount fenêtres)` vs `total_known`
  (381 486) vs `max(trackid_id) − min(trackid_id) + 1`, interprétée selon la
  réponse **V5**.
- **Volumétrie** : top channels, distribution des hitRate, volumétrie par année,
  pics d'imports massifs (un user important une discographie en minutes).

```bash
python scripts/local/trackid_spider/spider.py report \
    --total-known 381486 --v5-deleted-in-rowcount true
```

## Séquence recommandée (OPS)

```bash
# 1) sonder + produire le plan (réseau réel, 1 req/s ; ~85 sondes + V1-V6)
python scripts/local/trackid_spider/spider.py probe --since 2016-01
#    -> lire report.md, auditer plan.json

# 2) crawl exhaustif (relançable : Ctrl-C puis relancer reprend où ça s'est arrêté)
python scripts/local/trackid_spider/spider.py crawl

# 3) exporter pour L3
python scripts/local/trackid_spider/spider.py export --format csv

# 4) rapports de complétude + volumétrie
python scripts/local/trackid_spider/spider.py report --total-known 381486 \
    --v5-deleted-in-rowcount true
```

À `pageSize=100` et 1 req/s, ~381 k items ≈ **~3 815 pages ≈ ~65-75 min** de crawl
(+ overhead de fenêtrage). Une interruption est sans coût : la relance reprend au
checkpoint.

Les artefacts de run (`staging.db`, `plan.json`, exports, rapports, logs) vivent
dans `data/` (gitignoré). Utiliser `--workdir` pour un autre emplacement.

## Tests & lint

```bash
pytest scripts/local/trackid_spider/ -q          # 33 tests, sans réseau (HTTP mocké)
ruff check scripts/local/trackid_spider/
```

Volontairement **hors `tests/`** : le CI ne doit pas dépendre de cet outillage
local. Les tests couvrent le fenêtrage (adjacence sans chevauchement), la reprise
idempotente, l'upsert par `trackid_id`, le mapping payload→contrat (y compris
`raw_json` capturant un champ inconnu), la sérialisation CSV/NDJSON, le backoff
HTTP, et les cas limites (fenêtre vide, page instable, erreur → `failed`,
overflow). **Aucun crawl réel** contre trackid.net n'est lancé dans les tests.
