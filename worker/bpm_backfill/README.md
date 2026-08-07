# BPM backfill local (E2.b)

Outillage **local** (pattern A7-07 : tourne sur le PC, pas sur le VPS) qui dérive un
**BPM estimé** depuis les previews Deezer 30 s pour les lignes `catalog` ayant une
preview mais aucun `bpm` (~48 872 au lancement du chantier). Décisions issues du
benchmark [E2.a](../../docs/e2a-benchmark/README.md) :

- Moteur : Essentia **`RhythmExtractor2013(method="multifeature")`** (léger, pas de
  TensorFlow) sur le MP3 30 s à 44,1 kHz.
- **Gate de confiance : on n'écrit le BPM que si `confidence >= 2.0`** (~84 % de
  précision, ~82 % de couverture). En dessous → `low_conf`, la ligne reste `NULL`
  (mieux vaut pas de BPM qu'un mauvais BPM).
- Provenance : **`bpm_source = 'analysis'`** — la plus basse autorité, jamais
  prioritaire sur `beatport` (invariant #3) ni `rekordbox` (invariant #2).
- **Aucune persistance audio** : la preview est résolue à la volée via l'API Deezer
  publique (`GET api.deezer.com/track/{id}` → `.preview`, URL jamais stockée),
  téléchargée en fichier temporaire, analysée puis **supprimée**.

Essentia ne s'installe pas sous Windows → l'analyse tourne dans un **conteneur Docker
Linux** (image construite depuis le [`Dockerfile`](Dockerfile) du paquet :
`python:3.11-slim` + ffmpeg + `essentia`/`requests`). L'orchestrateur, lui, tourne sur
l'**hôte** en **stdlib pure** (Python 3.13 Windows, aucune dépendance) et n'a besoin
que de `ssh` (alias `diggy-vps`) et `docker`.

## Les 3 étapes (orchestrées par `backfill_bpm.py`)

1. **PULL** — candidats streamés depuis la prod (lecture seule) via
   `ssh diggy-vps "... psql -q -f -"` alimenté d'un
   `COPY (SELECT id, deezer_id FROM catalog WHERE has_preview = true AND bpm IS NULL
   AND deezer_id IS NOT NULL AND deezer_id <> 'NOT_FOUND' ...) TO STDOUT WITH (FORMAT
   csv, HEADER true)` → `data/candidates.csv`. `beatport_id` **volontairement non
   filtré** (décision produit : une ligne déjà liée Beatport mais sans bpm est incluse).
2. **ANALYZE** — `docker run --rm -v <workdir>:/work diggy-bpm-backfill python
   /work/analyze_bpm.py ...` : throttle ~5 rps sur l'API Deezer, download transitoire,
   RhythmExtractor2013, gate conf ≥ 2.0 → `data/results.csv`
   (colonnes `id,bpm,conf,status` ; status = `ok | low_conf | no_preview | error:*`).
3. **APPLY** (seulement avec `--apply`) — UPDATE par lots via le même canal SSH/psql :

   ```sql
   UPDATE catalog AS c
   SET bpm = v.bpm, bpm_source = 'analysis'
   FROM (VALUES (id1, bpm1), (id2, bpm2), ...) AS v(id, bpm)
   WHERE c.id = v.id AND c.bpm IS NULL;
   ```

   **`AND c.bpm IS NULL` est le garde d'idempotence + course** : un bpm existant
   (beatport / rekordbox / legacy, ou posé entre-temps par un run d'enrichissement)
   n'est **jamais** écrasé. C'est `bpm IS NULL` (pas `bpm_source IS NULL`) — protège
   aussi le legacy sans provenance (garde-fous mesurés du README E2.a).

## Usage

```bash
# dry-run sur un petit échantillon (pull + analyse réelles, AUCUNE écriture)
python worker/bpm_backfill/backfill_bpm.py --limit 20

# dry-run sur tout le backlog
python worker/bpm_backfill/backfill_bpm.py

# analyse + écriture en prod
python worker/bpm_backfill/backfill_bpm.py --apply

# ré-appliquer le dernier results.csv sans re-télécharger/re-analyser
python worker/bpm_backfill/backfill_bpm.py --reuse-results --apply
```

Options : `--limit N` (LIMIT du pull), `--workers K` (threads d'analyse, défaut 4),
`--min-conf` (défaut 2.0), `--batch-size` (lignes par UPDATE, défaut 500),
`--workdir` (défaut `worker/bpm_backfill/data/`, gitignoré).

**Défaut = dry-run** : sans `--apply`, l'UPDATE n'est pas exécuté ; le plan est
affiché (compteurs eligible/low_conf/no_preview/errors + extrait du SQL).

## Checkpoint & fil de l'eau

`data/processed_ids.txt` enregistre les ids **tentés à issue finale** : les rejets
(`low_conf` / `no_preview` / `error:*`) toujours, les ids **écrits** après chaque lot
`--apply` réussi. Une relance périodique ne re-télécharge donc que les **nouveaux**
candidats, jamais les rejets connus. Cas particuliers :

- Un `ok` obtenu en dry-run n'est **pas** checkpointé (il reste à écrire) — enchaîner
  avec `--reuse-results --apply` pour l'écrire sans re-analyser.
- Pour forcer un retry des `error:*` (pannes réseau), supprimer leurs ids du fichier.
- Le pull re-filtre de toute façon `bpm IS NULL` : une ligne écrite sort naturellement
  des candidats au run suivant.

## Garde-fous provenance (rappel E2.a)

- `'analysis'` est écrasable sans code par un run Beatport ultérieur
  (`enrich_from_beatport` écrit si `bpm_source != 'beatport'`) — c'est voulu :
  Beatport reste l'autorité du catalogue partagé (invariant #3).
- Jamais de KEY en v1 (NO-GO triple-confirmé E2.a). Pas de TempoCNN/librosa.
- Aucune migration, aucun modèle touché : l'outil n'écrit que `bpm` + `bpm_source`
  via SQL, uniquement là où `bpm IS NULL`.

## Tests

```bash
pytest worker/bpm_backfill/test_backfill_bpm.py -q   # logique pure, sans Essentia/réseau
ruff check worker/bpm_backfill/
```

Volontairement **hors `tests/`** : le CI n'a pas Essentia et ne doit pas dépendre de
ce paquet d'outillage local.
