# C9.0-bis — Rapport : quel encodeur audio pour la reco par contenu ? (EffNet vs CLAP vs MERT)

**Date :** 2026-08-22 · **Chantier :** C9 (choix du modèle v1) · **Verdict : EffNet, franc** · **Statut code :** outillage local (`docs/c9-benchmark/`)

Suite du gate C9.0 (GO franc). On départage 3 encodeurs candidats sur la MÊME question — leurs voisins
prédisent-ils la co-occurrence en sets DJ ? — avec le protocole v2 (revue Fable) : baselines
non-embedding, bootstrap IC95, exclusions artiste/release/**label**, adjacence, hit-rate. Tout CPU
(Ryzen 5 5600 ; GPU AMD inexploitable pour ML). Univers commun **6740** tracks (EffNet ∩ CLAP ∩ MERT).

## 1. Verdict

**EffNet gagne sans ambiguïté** et sur les deux axes (qualité + coût) :

| | EffNet | MERT-L6 (best MERT) | CLAP |
|---|---|---|---|
| **xart@10** (lift@10 cross-artist) | **32,35×** [30,9–33,9] | 13,86× [13,0–14,8] | 2,92× [2,6–3,2] |
| IC95 disjoints du 2ᵉ ? | oui | — | — |
| coût backfill 175k (CPU) | ~63 h (vecteurs C9.0 déjà là) | ~879 h (~6 j/6 cœurs) | ~120 h |

**Décision : EffNet figé comme modèle v1. CLAP + MERT écartés. Pas de second tour.**

## 2. Tableau complet (univers commun 6740)

| config | dim | all@10 | **xart@10** | IC95 | xrel@10 | **xlabel@10** | adj3@10 | shuf@10 |
|---|---|---|---|---|---|---|---|---|
| 🏆 **effnet** | 1280 | 34.87× | **32.35×** | [30.9,33.9] | 32.33× | 31.47× | 41.87× | 1.02× |
| mert_L6 | 768 | 15.77× | 13.86× | [13.0,14.8] | 13.84× | 13.36× | 16.50× | 0.97× |
| mert_L9 | 768 | 14.64× | 13.01× | [12.1,13.9] | 13.00× | 12.53× | 15.90× | 0.97× |
| mert_mean_all | 768 | 13.00× | 11.24× | [10.5,12.0] | 11.23× | 10.87× | 14.01× | 0.93× |
| mert_L12 | 768 | 9.26× | 8.14× | [7.6,8.7] | 8.15× | 7.74× | 10.48× | 1.05× |
| clap | 512 | 3.30× | 2.92× | [2.6,3.2] | 2.92× | 2.79× | 3.16× | 1.01× |
| effnet+clap | 1792 | 34.50× | 31.60× | [30.2,33.0] | 31.59× | 30.78× | 41.59× | 1.02× |
| label_year | 2 | 15.14× | 9.88× | [8.8,11.0] | 9.86× | **2.98×** | 10.82× | — |
| gower_lite | 5 | 8.37× | 7.03× | [6.3,7.8] | 7.01× | 4.87× | 8.66× | — |
| bpm_camelot | 2 | 5.83× | 5.25× | [4.8,5.7] | 5.25× | 5.06× | 7.75× | — |
| gower_full | 5 | 5.13× | 4.63× | [4.1,5.3] | 4.61× | 2.64× | 5.44× | — |
| bpm | 1 | 4.49× | 4.28× | [3.8,4.8] | 4.28× | 4.00× | 4.95× | — |
| popularity | 0 | 2.35× | 2.35× | [2.1,2.6] | 2.35× | 2.51× | 2.50× | — |
| gower_lite+effnet | — | 25.48× | 22.13× | [20.9,23.3] | 22.11× | 18.31× | 29.63× | — |
| gower_lite+mert_mean_all | — | 13.87× | 11.49× | [10.7,12.3] | 11.47× | 9.61× | 15.61× | — |
| gower_lite+clap | — | 6.64× | 5.69× | [5.2,6.2] | 5.68× | 4.86× | 7.20× | — |

### hit-rate@k (≥1 vrai setmate dans le top-k, cross-artist) — métrique produit « sonne comme »

| config | hit@10 | hit@20 | hit@50 | hit@10 par degré (3-9 / 10+) |
|---|---|---|---|---|
| **effnet** | **35,0 %** | 47,2 % | **64,5 %** | 27 % / 38 % |
| effnet+clap | 35,1 % | 47,3 % | 64,5 % | 28 % / 38 % |
| mert_L6 | 19,9 % | 29,2 % | 44,4 % | 12 % / 23 % |
| mert_L9 | 19,0 % | 27,8 % | 44,0 % | 11 % / 22 % |
| mert_mean_all | 17,4 % | 25,5 % | 41,0 % | 10 % / 20 % |
| mert_L12 | 14,5 % | 21,8 % | 35,4 % | 8 % / 17 % |
| clap | 6,0 % | 10,9 % | 22,2 % | 3 % / 7 % |

## 3. Lectures

1. **EffNet écrase** (32,35×), IC95 sans chevauchement avec le 2ᵉ. Domination **domain-specific** :
   entraîné sur la taxonomie Discogs (400 styles électroniques), aligné sur la co-occurrence DJ.
2. **Ce n'est PAS de la fuite de label** : `xlabel@10` (exclut même artiste ET même label) ne fait
   chuter EffNet que de 32,35× → **31,47× (−2,7 %)**, alors que `label_year` s'effondre (9,88 → 2,98)
   et `gower_lite` recule (7,03 → 4,87). Le signal d'EffNet est du **contenu**, pas de l'esthétique de
   label. (Répond au point 3 de la revue.)
3. **hit-rate produit** : pour **35 % des seeds** un vrai setmate est dans le top-10, **64,5 %** dans
   le top-50 (cross-artist) ; meilleur sur les tracks à fort degré (38 %) que faible (27 %). C'est la
   métrique à suivre pour « sonne comme »/C9.b, pas la médiane du lift (=0, artefact du base-rate 0,2 %).
   (Répond au point 4.)
4. **MERT** : couches intermédiaires meilleures (L6 > L9 > mean_all > L12), conforme à la littérature ;
   plafonne ~14×, **2,3× sous EffNet**, et 6× plus cher au backfill.
5. **CLAP** dernier des embeddings (2,92×), **sous** les baselines métadonnées → optimisé texte↔audio.
6. **Pas d'ensemble** : `effnet+clap` (31,6×) < EffNet ; `gower_lite+mert` ≈ MERT.
7. **adj3 > all** partout (EffNet 41,9× vs 34,9×) : le signal est plus fort sur les paires **enchaînées**
   (≤3 positions) que sur la simple co-présence → exactement ce qu'on veut pour un moteur de mix.
8. **xrel ≈ xart** (fuite release 0,02 %) → cross-artist est bien le chiffre décisionnel.

## 4. Conséquences

- **C9.a** : figer EffNet (`model_name`/`model_version` versionnés), migration pgvector + backfill
  local ~63 h + éval **rejouée à l'échelle 175k** (le lift absolu ne se transporte pas de l'univers
  dense 6740 ; suivre le **hit-rate@k**). Stocker les vecteurs **déjà L2-normalisés** (HNSW = produit
  scalaire). Traiter les **near-duplicates** (même release/edit/remaster) qui satureront les top-k à
  175k → jonction avec les parent-sets virtuels C6.
- **C9.c** : la fusion de rangs 50/50 **dilue** (`gower_lite+effnet` 22× < EffNet 32×) → les
  métadonnées valent mieux comme **contrainte** (fenêtre BPM, compat Camelot, filtre genre) que comme
  score additif. Voir [enseignements C2/C9.c](../completed/C9.0-bis_enseignements_C2_C9c.md).

## Annexe — reproduction

Kit `docs/c9-benchmark/` : `embed_eval.py` (multi-modèles + boucle eval unifiée), `Dockerfile`
(EffNet essentia-tensorflow) + `Dockerfile.torch` (CLAP/MERT), `sample.csv` gelé, `sample_meta.csv` /
`sample_pos.csv` / `genre_map.csv` / `genre_edges.csv` (exports read-only), `compare_results.json`
(données machine complètes). `NUIT_RECAP.md` = déroulé de la nuit.
