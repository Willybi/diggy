# C9.c — Calibration offline de `CONTENT_BONUS` (reco hybride)

**Chantier :** C9.c (lot L5) · **Statut code :** outil local read-only (`worker/embedding_backfill/eval_hybrid.py`) · **Décision figée par l'opérateur après un run réel**

La reco hybride (lot L2) classe l'univers de retrieval de la reco (`KNN ∪ co-occurrence`,
le cœur L1) avec un score de métadonnées PLUS un bonus audio ADDITIF surpondéré :

```
hybrid_score(seed, cand) = metadata_score(seed, cand)
                         + CONTENT_BONUS · (1 − cosine_distance(seed, cand))
```

`CONTENT_BONUS` (`services/recommendation_service.py::RecommendationConfig`) vaut
**1.0 par défaut et n'est PAS calibré**. Cet outil mesure la qualité de classement
du hybride à plusieurs valeurs de bonus, contre un hold-out de co-occurrence, pour
que l'opérateur **fige le poids sur des chiffres** — pas sur une intuition.

C'est le **frère** de `eval_at_scale.py` : même canal read-only `ssh diggy-vps …
psql`, même cache `npz`, même boucle de métrique importée VERBATIM de
`docs/c9-benchmark/embed_eval.py`. Aucune écriture prod, aucun changement de
comportement serveur.

---

## 1. Ce qui est comparé

Toutes les variantes classent **le même univers de retrieval par seed** (celui que
la prod construit réellement) :

| Variante | Score de classement | Rôle |
|---|---|---|
| `meta` | `gower_lite` seul (= `CONTENT_BONUS = 0`) | **baseline métadonnées** |
| `hybrid@b` | `gower_lite + b·(1 − dist)` pour chaque `b` de la grille | le hybride à tester |
| `audio` | `(1 − dist)` = cosinus des vecteurs EffNet | **référence contenu-seul** |

- **Canal métadonnées** = `gower_lite` de `embed_eval` (BPM + Camelot + genres +
  label + année) — la MÊME similarité métadonnées, sans co-occurrence, validée par
  le benchmark C9.0-bis.
- **Canal contenu** = cosinus des embeddings EffNet L2-normalisés (`emb_scorer`),
  donc `(1 − dist)` ∈ [−1, 1] (pratiquement positif).
- **Univers de retrieval par seed** = `KNN(k) ∪ co-occ(cap)`, avec les défauts de
  la reco (`RETRIEVAL_KNN_K_DEFAULT = 200`, `RETRIEVAL_COOC_CAP_DEFAULT = 500` de
  `services/similarity_service.py`, mirroités ici en `--knn-k` / `--cooc-cap`).

## 2. Hold-out & métrique

Identiques à `eval_at_scale` : la vérité-terrain est la **co-occurrence en sets DJ**
(`build_partners`). Pour chaque track-seed on classe SON univers de retrieval et on
mesure si ses co-occurrents (set-mates) ressortent dans le top-k. Reporté par
variante :

- **lift@10** (× vs hasard), en *all-positifs* et en *cross-artist* ;
- **hit-rate@10 / @20 / @50** (cross-artist) = ≥ 1 vrai set-mate dans le top-k ;
- **IC95 bootstrap** sur le lift@10 cross-artist.

Le lift cross-artist est le chiffre-phare (comme C9.0-bis) : il neutralise le signal
trivial « même artiste ».

## 3. Pas de fuite (leakage)

Le hold-out est la co-occurrence ; le canal métadonnées **ne doit donc pas** contenir
de terme de co-occurrence, sinon il mémoriserait la réponse. Deux garanties :

1. Le score serveur `_score_seed_against_pool` contient un terme de co-occurrence
   (`score_cooc` sur sets/playlists partagés) — il **fuirait**. On ne l'utilise donc
   PAS comme canal métadonnées. On utilise `gower_lite`, **sans co-occurrence**.
2. La co-occurrence n'intervient qu'au **retrieval** (construction de l'univers),
   jamais dans le score de classement. Comme la prod retrouve les set-mates, les
   positifs sont, à concurrence du `cooc_cap`, dans l'univers — la métrique mesure
   alors purement si le **classement** (méta / hybride / audio) les remonte dans le
   top-k. C'est exactement la question que `CONTENT_BONUS` règle.

## 4. Lancer le run (opérateur)

Depuis la racine du repo, sur le PC qui a l'alias SSH `diggy-vps` (canal read-only) :

```bash
# run par défaut : échantillonne ~2000 sets fiables, tire les embeddings, évalue
python worker/embedding_backfill/eval_hybrid.py

# grille de bonus personnalisée + échantillon plus large
python worker/embedding_backfill/eval_hybrid.py --sample-sets 3000 --bonus-grid 0.25,0.5,1,2,4

# ré-évaluer un run précédent SANS re-tirer la prod (offline)
python worker/embedding_backfill/eval_hybrid.py --reuse
```

Options utiles : `--knn-k` / `--cooc-cap` (largeurs de retrieval, défauts = ceux de
la reco), `--limit-tracks N` (borne l'univers scorable pour aller plus vite),
`--seed` (reproductibilité), `--workdir` (par défaut `worker/embedding_backfill/data_hybrid/`).
Le run écrit `universe.csv` + `embeddings.npz` (réutilisables via `--reuse`) et
`eval_hybrid_results.json`. **Read-only de bout en bout** — aucun flag `--apply`.

## 5. Lire les chiffres & règle de décision

Le tableau donne, par variante, `lift_xart@10` + IC95 et `hit@10/@50`. Le script
imprime aussi un **bonus recommandé** et un **choix parcimonieux** :

- **Bonus recommandé** = celui qui **maximise le lift@10 cross-artist** (tie-break
  hit@50).
- **Choix parcimonieux** = le **plus petit** bonus dont le lift@10 tombe dans l'IC95
  du meilleur — au-delà, ajouter du poids audio n'aide plus de façon mesurable.
  **Préférer le parcimonieux** quand plusieurs bonus sont statistiquement à égalité.
- La ligne `meta` (bonus 0) et la ligne `audio` bornent le débat : `audio ajoute
  +X%` dit combien le canal contenu apporte AU-DESSUS des métadonnées seules. Si
  ce gain est ~nul ou si l'IC95 de tous les hybrides recouvre celui de `meta`, la
  décision est **garder `CONTENT_BONUS` bas** (l'audio n'aide pas ici) ; s'il est
  franc et croît avec le bonus jusqu'à un plateau, figer le bonus **au début du
  plateau**.

### ⚠️ Mise en garde d'échelle (à lire avant de reporter la constante)

Le canal métadonnées de l'éval est `gower_lite` (∈ [0, 1]), **PAS** le
`score_pct` du serveur (`_score_seed_against_pool`, une autre échelle, qui fold en
plus un terme de co-occurrence). Le bonus calibré ici est donc **sur l'échelle
gower-lite**, pas transposable tel quel à la constante serveur. Concrètement :

- Lire la **FORME de la courbe** (où l'audio commence à aider / cesse d'aider /
  nuit), pas le chiffre brut.
- Le rapport `audio / meta` (canaux sur des échelles comparables [0, 1]) est le
  signal robuste : il dit *combien* surpondérer l'audio, indépendamment de
  l'échelle absolue du score métadonnées serveur.
- Après avoir figé une valeur, **valider qualitativement** la sortie reco (un petit
  A/B ou une revue à l'œil du « Pour toi ») avant de considérer le poids définitif.

## 6. Où poser la valeur

Quand l'opérateur a tranché : `CONTENT_BONUS` vit dans
`server/api/services/recommendation_service.py` (`RecommendationConfig.CONTENT_BONUS`,
défaut `1.0`). Ce lot **ne commite pas** de valeur calibrée — la constante reste à
`1.0` tant que l'opérateur n'a pas posé le nombre après un run réel.
