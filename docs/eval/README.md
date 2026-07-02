# Golden Set — Similarity Evaluation

## Format

`golden_similar.json` contient une liste d'annotations :

```json
[
  {
    "query_id": 123,
    "similar_ids": [456, 789, 101, 202, 303]
  }
]
```

- `query_id` : catalog_id de la track de reference
- `similar_ids` : 5 catalog_ids consideres comme similaires (ordre = pertinence)

## Workflow

1. Lancer le script de suggestion :
   ```bash
   python server/scripts/eval_similarity.py suggest --track-ids 123,456,789
   ```
2. Pour chaque track, le script affiche les top-10 candidats. Accepter/rejeter chaque paire.
3. Les paires acceptees sont ecrites dans `golden_similar.json`.

## Evaluation

```bash
python server/scripts/eval_similarity.py eval
python server/scripts/eval_similarity.py compare --w1 '{"bpm":0.4}' --w2 '{"bpm":0.2}'
```

Metriques : recall@5, recall@10, MRR (par track et moyenne).
