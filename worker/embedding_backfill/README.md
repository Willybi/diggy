# Embedding backfill local (C9.a)

Outillage **local** (pattern A7-07 : tourne sur le PC, pas sur le VPS) qui calcule
l'**embedding audio EffNet** (Discogs-EffNet, 1280-d, modèle C9 v1 figé au
benchmark C9.0-bis) depuis les previews Deezer 30 s pour les lignes `catalog`
ayant une preview mais **aucun embedding** encore stocké pour `(MODEL_NAME,
MODEL_VERSION)` — cible ~266 k titres. Jumeau de l'outil BPM
[`worker/bpm_backfill/`](../bpm_backfill/README.md) : même canal SSH/psql, même
forme dry-run/apply + checkpoint + relançable en salves, mais il **INSERT un
vecteur** dans la table pgvector `track_embeddings` au lieu d'un scalaire `bpm`.

Décisions issues du benchmark [C9.0-bis](../../docs/c9-benchmark/) :

- Modèle : Essentia **`TensorflowPredictEffnetDiscogs`**, nœud embeddings
  **`PartitionedCall:1`** (1280-d), audio **16 kHz**, moyenne des patches puis
  **L2-normalisation** → 1280 floats. Logique reprise **verbatim** de
  `docs/c9-benchmark/embed_eval.py` (`_effnet_embed`), figée dans
  [`embed.py`](embed.py). EffNet a gagné le gate (xart@10 32,4× vs MERT-L6 13,9×
  vs CLAP 2,9×), CLAP + MERT écartés.
- Identité versionnée : **`model_name='discogs-effnet'`**,
  **`model_version='bs64-1'`**, `dim=1280` — doit rester en phase avec
  `server/api/models/embedding.py` (ce script hôte est stdlib-only et ne peut pas
  importer ce module SQLAlchemy).
- **Aucune persistance audio** : la preview est résolue à la volée via l'API
  Deezer publique (`GET api.deezer.com/track/{id}` → `.preview`, URL jamais
  stockée), téléchargée en fichier temporaire, embeddée puis **supprimée**.

Essentia (+ TensorFlow) ne s'installe pas sous Windows → l'embed tourne dans un
**conteneur Docker Linux** (image construite depuis le [`Dockerfile`](Dockerfile)
du paquet : `python:3.11-slim` + ffmpeg + `essentia-tensorflow` + le graphe EffNet
`discogs-effnet-bs64-1.pb` téléchargé au build). L'orchestrateur, lui, tourne sur
l'**hôte** en **stdlib pure** et n'a besoin que de `ssh` (alias `diggy-vps`) et
`docker`.

> **Précondition (lot L1)** : la table pgvector `track_embeddings` (migration
> `0049`, extension `vector`) doit être **déployée en prod** avant tout `--apply`.

## Les 3 étapes (orchestrées par `backfill_embeddings.py`)

1. **PULL** — candidats streamés depuis la prod (lecture seule) via
   `ssh diggy-vps "... psql -q -f -"` alimenté d'un `COPY (...) TO STDOUT` :

   ```sql
   SELECT c.id, c.deezer_id
   FROM catalog c
   LEFT JOIN track_embeddings te
     ON te.catalog_id = c.id
    AND te.model_name = 'discogs-effnet'
    AND te.model_version = 'bs64-1'
   WHERE c.has_preview = true
     AND c.deezer_id IS NOT NULL
     AND c.deezer_id <> 'NOT_FOUND'
     AND te.id IS NULL          -- seulement les lignes SANS embedding encore
   ORDER BY c.id                -- (+ optionnel AND c.id > :after_id)
   ```

   → `data/candidates.csv`. Le LEFT JOIN `te.id IS NULL` + `ORDER BY c.id` rendent
   le pull **keyset-résumable** : une ligne déjà embeddée ne réapparaît jamais.
2. **EMBED** — `docker run --rm -v <workdir>:/work diggy-embedding-backfill python
   /work/embed.py ...` : throttle ~5 rps sur l'API Deezer, download transitoire,
   EffNet `PartitionedCall:1` → moyenne patches → L2-norm → `data/results.csv`
   (colonnes `id,status,dim,emb` ; `emb` = liste JSON de 1280 floats sur `ok` ;
   status = `ok | no_preview | error:*`).
3. **APPLY** (seulement avec `--apply`) — INSERT par lots via le même canal
   SSH/psql :

   ```sql
   INSERT INTO track_embeddings
       (catalog_id, model_name, model_version, embedding, created_at)
   VALUES
       (id1, 'discogs-effnet', 'bs64-1', '[f1,f2,...]'::vector, now()),
       ...
   ON CONFLICT (catalog_id, model_name, model_version) DO NOTHING;
   ```

   **`ON CONFLICT ... DO NOTHING` est le garde d'idempotence** (contrainte
   `uq_track_embeddings_catalog_model`) : un embedding déjà stocké pour ce
   `(track, model, version)` n'est **jamais** dupliqué. Le vecteur est rendu en
   littéral pgvector `'[...]'::vector` (chaque composante `float()`-coercée →
   injection-safe).

## Usage

```bash
# dry-run sur un petit échantillon (pull + embed réels, AUCUNE écriture)
python worker/embedding_backfill/backfill_embeddings.py --limit 20

# dry-run sur tout le backlog
python worker/embedding_backfill/backfill_embeddings.py

# embed + écriture en prod
python worker/embedding_backfill/backfill_embeddings.py --apply

# MARATHON : draine TOUT le backlog en fenêtres successives, sans arrêt
python worker/embedding_backfill/backfill_embeddings.py --loop --apply --workers 4

# salve keyset (fenêtre d'ids), relançable
python worker/embedding_backfill/backfill_embeddings.py --after-id 500000 --limit 20000 --apply

# ré-appliquer le dernier results.csv sans re-télécharger/re-embedder
python worker/embedding_backfill/backfill_embeddings.py --reuse-results --apply
```

Options : `--limit N` (LIMIT du pull), `--after-id N` (reprise keyset : `c.id > N`),
`--loop` (mode marathon, cf. ci-dessous), `--workers K` (threads d'embed dans le
conteneur, défaut 2 — EffNet est CPU-bound, rester modeste sur un laptop),
`--batch-size` (lignes par INSERT, défaut 200 : chaque ligne porte un vecteur de
1280 floats), `--workdir` (défaut `worker/embedding_backfill/data/`, gitignoré).

### Mode marathon (`--loop`)

Sans `--loop`, une invocation fait **un seul** PULL→EMBED→APPLY : elle embedde
TOUT le lot tiré puis n'écrit qu'à la **toute fin** — inadapté à un rattrapage de
plusieurs centaines de milliers de lignes (un crash en cours = rien d'écrit,
récupération via `--reuse-results`). `--loop` transforme ça en **rattrapage
continu** : il répète des fenêtres de `--limit` lignes (défaut 20000) en avançant
un **curseur keyset** (`c.id`), jusqu'à ce qu'une fenêtre ne tire plus rien. Chaque
fenêtre **écrit (par batches de 200) + checkpointe AVANT** la suivante → les
résultats arrivent en prod **régulièrement**, et un crash/redémarrage **reprend**
tout seul (les lignes écrites sortent du pull via `te.id IS NULL`, les lignes en
`error:*` sont retentées, les `no_preview` restent ignorés). Après un tour complet,
s'il reste des erreurs, la boucle attend `--retry-cooldown` secondes (défaut 1800)
puis refait un tour, jusqu'à `--max-rounds` tours (défaut 3, `--apply` uniquement).
La dernière ligne n'annonce `drained` que si rien n'est resté de côté ; sinon elle
donne le nombre de lignes en erreur et ignorées par le checkpoint. À lancer dans un
terminal durable (le PC ne doit pas se mettre en veille, Docker Desktop doit rester
up). Un `--limit` plus bas (ex. 2000) écrit en prod plus souvent.

### Rate-limit Deezer

Un débit soutenu déclenche des HTTP 429 sur le téléchargement des previews, sans
quota journalier fixe : ralentir suffit. `EMBED_MIN_INTERVAL` règle l'écart entre deux
appels `/track/{id}` (défaut 0.2 s, `1.0` pour un rattrapage) et cadence donc aussi
les téléchargements ; `--workers` ne parallélise que le téléchargement et EffNet. Sur
un 429 ou une erreur de quota Deezer (codes 4/700), `embed.py` met **tous** ses threads
en pause (`Retry-After` s'il est numérique, sinon 30 s → 5 min, 5 fois au maximum),
puis déclare la ligne en erreur (`error:HTTP429`) pour un tour suivant.

**Défaut = dry-run** : sans `--apply`, l'INSERT n'est pas exécuté ; le plan est
affiché (compteurs eligible/no_preview/errors + extrait du SQL).

## Séquence prod (OPS)

Le backfill EffNet 175 k+ tourne **en local** (~63 h estimées, cf. NUIT_RECAP), en
salves relançables. Séquence :

1. **Déployer L1 d'abord** (push → CI → migration `0049` appliquée en prod : table
   `track_embeddings` + extension `vector` + index HNSW). Sans elle, le PULL
   échoue (table absente) et l'`--apply` n'a nulle part où écrire.
2. **Dry-run** `--limit 20` : vérifier le pull + l'embed + le plan SQL sur un
   échantillon (aucune écriture).
3. **`--apply`** en salves (`--after-id`/`--limit` pour fenêtrer, ou tout le
   backlog d'un coup). Chaque salve est idempotente : un crash / une relance ne
   re-download que les candidats neufs (checkpoint + `te.id IS NULL`).
4. Re-dry-run pour confirmer la convergence (le backlog des candidats décroît).

> Pas de dump préalable requis (l'outil n'`INSERT` que dans une table neuve, sans
> jamais UPDATE/DELETE une donnée existante — contrairement aux scripts OPS
> `server/api/scripts/` qui mutent `catalog`). Reste prudent : c'est de la prod.

## Checkpoint & fil de l'eau

`data/processed_ids.txt` enregistre les ids **à issue finale** : les `no_preview`
toujours, les ids **écrits** après chaque lot `--apply` réussi. Les `error:*` n'y
entrent **jamais** : ce sont surtout des rate-limits, ils doivent rester retentables.
Une relance périodique re-télécharge donc les **nouveaux** candidats et les erreurs
passées, jamais les `no_preview` connus. Cas particuliers :

- Un `ok` obtenu en dry-run n'est **pas** checkpointé (il reste à écrire) —
  enchaîner avec `--reuse-results --apply` pour l'écrire sans re-embedder.
- Pour retenter aussi les `no_preview` (ou purger un checkpoint antérieur à ce
  comportement, qui contient des erreurs), le renommer : le fichier ne sert qu'aux
  lignes sans embedding, les lignes écrites sortent du pull toutes seules.
- Le pull re-filtre de toute façon `te.id IS NULL` : une ligne écrite sort
  naturellement des candidats au run suivant.

## Tests

```bash
pytest worker/embedding_backfill/test_backfill_embeddings.py worker/embedding_backfill/test_embed_rate_limit.py -q   # logique pure, sans Essentia/réseau
ruff check worker/embedding_backfill/
```

Volontairement **hors `tests/`** : le CI n'a pas Essentia et ne doit pas dépendre
de ce paquet d'outillage local.
