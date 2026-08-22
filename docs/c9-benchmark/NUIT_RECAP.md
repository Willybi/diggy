# C9.0-bis — Récap de nuit (benchmark EffNet vs CLAP vs MERT)

> Pour ton réveil. Benchmark **TERMINÉ à 10:24**. Dernière MAJ : **2026-08-22 10:26**.
> Statut global : ✅ **PIPELINE FINI, verdict franc. Aucune intervention n'a été nécessaire de la nuit.**

---

## TL;DR (à lire en premier)

- ✅ **Benchmark 3 modèles complet** (EffNet + CLAP + MERT-95M par couche + ensemble + 6 baselines), univers commun 6740 tracks, tout en CPU sur ton PC, zéro incident bloquant, zéro coût cloud.
- 🏆 **GAGNANT : EffNet, sans discussion.** xart@10 = **32,35×** [30,9–33,9] — contre **MERT-L6 13,86×** (meilleure couche MERT) et **CLAP 2,92×**. Les IC95 ne se chevauchent pas → décision statistiquement franche. EffNet est **~2,3× > meilleur MERT** et **~11× > CLAP**.
- 💰 **EffNet gagne aussi en COÛT** : MERT = 18,1 s/track (backfill 175k ≈ **~6 j/6 cœurs**), CLAP 2,48 s/track ; EffNet = vecteurs C9.0 **déjà là** + CNN CPU-friendly (~63 h mesurées pour 175k). Le gagnant qualité est aussi le moins cher.
- 📉 **CLAP écarté** (2,9×, sous les baselines métadonnées — optimisé texte↔audio, pas la similarité de mix). **MERT écarté** (meilleur cas 13,9× à L6, loin d'EffNet, et 6× plus cher). Pas de bénéfice d'ensemble (`effnet+clap` 31,6× < EffNet).
- 🎧 **Audio ≫ métadonnées** : best/gower_lite = 4,63× → trigger `gower_full` **non armé**, apport audio franc et autonome.
- ▶️ **DÉCISION : figer EffNet comme modèle v1 et lancer C9.a** (migration pgvector + backfill EffNet) **directement — pas de second tour de benchmark nécessaire**.

---

## Ce qui a été fait cette nuit

### 1. Protocole v2 finalisé + validé par tes retours (Fable)
`docs/prompts/C9_benchmark_protocol_v2.md` — A1 rempli, A2 baselines, A3 bootstrap, B1-B5 répondus,
boucle unique en pseudo-code, `gower_lite`/`gower_full`+trigger, CLAP music+3×10s+`clap_pre`, MERT couches.

### 2. Step 0 — exports enrichis (read-only VPS, sample gelé préservé)
- `sample_meta.csv` (6901 tracks : bpm, key, genres, label, date, isrc, normkey, album_id)
- `sample_pos.csv` (8754 positions, pour l'adjacence)
- `genre_map.csv` + `genre_edges.csv` (graphe C2, pour `gower_full`)

**Diagnostics mesurés :**
- **Fuite cross-artist = 0,02 %** → `xart@10` reste le chiffre décisionnel (le 32,5× n'est pas gonflé).
- Degré : médiane 14, plancher 7 → strates 3–9 (21 %) / 10+ (79 %), pas de strate 1–2 (tirage sets ≥8).

### 3. Code `embed_eval.py` reworké (protocole v2) + testé
- **Embed** : CLAP `laion/larger_clap_music` + fenêtrage 3×10 s + `clap_pre` (768-d, même forward) ;
  MERT 13 couches stockées + **chrono CPU/track** (B4) ; timing extrapolé aux 175k.
- **Eval unifié** : scorers embeddings + baselines (`popularity/bpm/bpm_camelot/gower_lite/gower_full/label_year`)
  + fusions Borda, exclusions `none/xart/xrel`, `adj@3`, **bootstrap IC95**, strates de degré, expansion
  couches MERT sans ré-inférence, ensemble `effnet+clap`. Écrit `compare_results.json`.
- **Validé en local sur EffNet** (voir tableau ci-dessous) — reproduit C9.0 au chiffre près.

### 4. EffNet réutilisé
Vecteurs C9.0 (`embeddings.npz`, 6819×1280) recopiés en `embeddings_effnet.npz` → **0 recalcul**.

---

## Tableau final (univers commun 6740 tracks — EffNet ∩ CLAP ∩ MERT)

| config | dim | all@10 | **xart@10** | IC95 | xrel@10 | adj3@10 | shuf@10 |
|---|---|---|---|---|---|---|---|
| 🏆 **effnet** | 1280 | 34.87× | **32.35×** | [30.9, 33.9] | 32.33× | 41.87× | 1.02× |
| mert_L6 | 768 | 15.77× | **13.86×** | [13.0, 14.8] | 13.84× | 16.50× | 0.97× |
| mert_L9 | 768 | 14.64× | 13.01× | [12.1, 13.9] | 13.00× | 15.90× | 0.97× |
| mert_mean_all | 768 | 13.00× | 11.24× | [10.5, 12.0] | 11.23× | 14.01× | 0.93× |
| mert_L12 | 768 | 9.26× | 8.14× | [7.6, 8.7] | 8.15× | 10.48× | 1.05× |
| clap | 512 | 3.30× | **2.92×** | [2.6, 3.2] | 2.92× | 3.16× | 1.01× |
| effnet+clap | 1792 | 34.50× | 31.60× | [30.2, 33.0] | 31.59× | 41.59× | 1.02× |
| label_year | 2 | 14.89× | 9.63× | [8.5, 10.7] | 9.60× | 10.53× | — |
| gower_lite | 5 | 8.33× | 6.99× | [6.3, 7.8] | 6.96× | 8.65× | — |
| bpm_camelot | 2 | 5.83× | 5.25× | [4.8, 5.7] | 5.25× | 7.75× | — |
| gower_full | 5 | 5.05× | 4.56× | [4.0, 5.2] | 4.54× | 5.41× | — |
| bpm | 1 | 4.41× | 4.20× | [3.8, 4.7] | 4.20× | 4.86× | — |
| popularity | 0 | 2.35× | 2.35× | [2.1, 2.6] | 2.35× | 2.50× | — |
| gower_lite+effnet | — | 25.49× | 22.13× | [20.9, 23.3] | 22.11× | 29.62× | — |
| gower_lite+mert_mean_all | — | 13.88× | 11.50× | [10.7, 12.3] | 11.48× | 15.59× | — |
| gower_lite+clap | — | 6.64× | 5.69× | [5.2, 6.2] | 5.68× | 7.20× | — |

*(clap_pre mesuré au run préliminaire = 3,19×, écarté avec clap. `compare_results.json` = données machine complètes.)*

**Lectures :**
- **EffNet écrase tout** (32,35×), IC95 sans chevauchement avec le 2ᵉ (MERT-L6 13,86×). Domination **domain-specific** : EffNet est entraîné sur la taxonomie Discogs (400 styles électroniques), parfaitement alignée sur la co-occurrence en sets DJ.
- **MERT par couche** : L6 (mid) meilleur, L12 (dernière) pire → cohérent avec la littérature (signal musical au milieu). Mais plafonne à ~14×, **2,3× sous EffNet**.
- **CLAP dernier des embeddings** (2,92×), **sous** les baselines métadonnées → optimisé texte↔audio, pas la similarité de mix.
- **Pas d'ensemble** : `effnet+clap` (31,6×) < EffNet seul. `gower_lite+mert` (11,5×) ≈ MERT seul → la fusion avec métadonnée faible n'ajoute rien.
- **Audio ≫ métadonnées** : meilleure métadonnée `label_year` 9,6× (fuite écosystème anticipée par Fable), puis `gower_lite` 7,0×. best/gower_lite = 4,63× → trigger `gower_full` **non armé**.
- **`gower_full` (4,6×) < `gower_lite` (7,0×)** : propagation taxonomique dilue ici → `gower_lite` reste la baseline métadonnées la plus forte (pas de sous-vente).
- **Nuance** : médiane `xart@10` par seed = 0 (co-occurrence rare, base-rate 0,2 %) — normal, la moyenne/lift (calibrée shuf ≈ 1×) reste l'agrégat pertinent.

## B4 — coût de backfill 175k (mesuré)

| modèle | inférence/track (CPU) | backfill 175k (1 thread) | ~6 cœurs | verdict |
|---|---|---|---|---|
| **effnet** | (CNN, réutilisé C9.0) | ~63 h mesurées | ~11 h effectives | 🟢 le moins cher, **local** |
| clap | 2,48 s | ~120 h | ~20 h | (écarté qualité) |
| mert | **18,1 s** | ~879 h | ~6 j | 🔴 lourd (écarté qualité + coût) |

EffNet = meilleure qualité **ET** coût le plus bas → aucun compromis.

## Métriques complémentaires (demandées à la revue, ajoutées sans ré-embed)

- **`xlabel@10`** (exclut même artiste ET même **label**) : EffNet 32,35× → **31,47× (−2,7 %)** ⇒ le
  signal d'EffNet **n'est PAS de la reconnaissance de label**, c'est du contenu. Contraste : `label_year`
  s'effondre (9,88 → **2,98**), `gower_lite` recule (7,03 → 4,87). Point 3 de la revue réglé.
- **hit-rate@k** (≥1 vrai setmate dans le top-k, cross-artist) — métrique produit « sonne comme » :
  EffNet **35,0 % @10 · 47,2 % @20 · 64,5 % @50** (par degré 3-9 = 27 %, 10+ = 38 %) ; MERT-L6 20 %/@10 ;
  CLAP 6 %. Point 4 réglé.

📄 **Rapport archivé complet** : [RAPPORT_C9.0-bis.md](RAPPORT_C9.0-bis.md).
📄 **Enseignements C2 + C9.c** (propagation taxonomique à revoir ; métadonnées en contrainte, pas en
score) : [docs/completed/C9.0-bis_enseignements_C2_C9c.md](../completed/C9.0-bis_enseignements_C2_C9c.md).

---

## État du pipeline & surveillance

| Composant | État |
|---|---|
| EffNet | ✅ réutilisé (C9.0, 6819×1280) |
| CLAP embed | ✅ 04:18 — 6874/6901 (npz 512-d + 1024-d) |
| MERT embed | ✅ 10:20 — 6816/6901 (npz 6816×13×768), 69 erreurs transitoires (Deezer, run 6h) |
| `compare` 3-way final | ✅ 10:24 — `compare_results.json` écrit |
| Driver + watchdog | ✅ terminés proprement |

## Prochaine étape (à ton réveil) — C9.a

Le modèle v1 est tranché (**EffNet**). On peut lancer **C9.a** sans autre benchmark :
1. Migration **pgvector** (extension + table/colonne versionnée `model_name`/`model_version`, HNSW).
2. **Backfill EffNet des ~175k previews** en local (kit déjà prêt, ~63 h mesurées → étalable sur quelques nuits), écriture prod via ssh-psql.
3. Éval voisins-vs-co-occurrence **rejouée à l'échelle réelle** (le lift absolu ne se transporte pas de l'univers dense 6740 aux 175k — re-mesure attendue).
4. Puis C9.b (« sonne comme » Track Detail) / C9.c (reco hybride, **surpondérer l'audio** vu que la fusion 50/50 sous-performe).

Dis-moi quand tu veux que je lance C9.a (via `/work_manager`).

**Deezer** : throttle global 5 rps (indépendant du nb de workers), débit réel ~1,3 rps, IP maison → zéro risque, zéro impact prod.

---

## Incidents (aucun bloquant)

- **Path Git Bash** (early) : `/work/...` mangé par MSYS → corrigé (`MSYS_NO_PATHCONV=1` + `pwd -W`). CLAP relancé proprement.
- **1 `ImportError` CLAP** (race d'import transformers au démarrage des 4 threads) : 1 track perdue / 6901, bénin, ne se reproduit pas.
- **~1-2 % d'erreurs Deezer transitoires** (quota occasionnel, auto-retry) : conforme à C9.0.

---

## Journal

- **03:00** — build image torch OK (torch 2.13 cpu, transformers 4.40.2, poids CLAP music + MERT bakés).
- **03:05** — CLAP embed lancé (après fix path), sain.
- **03:15** — step-0 exports + diagnostics (fuite 0,02 %, degré médiane 14).
- **03:40** — eval v2 reworké + **validé sur EffNet** (32,53× = C9.0).
- **03:45** — driver autonome + watchdog lancés ; ce récap créé.
- **04:18** — CLAP fini (6874/6901, ~0,16 % erreurs) ; driver enchaîne MERT auto (plein CPU).
- **04:20** — MERT démarre, sain (CPU ~595 %). Débit stabilisé ~3,1 s/track → ETA ~10:15.
- **05:00** — `compare` préliminaire EffNet+CLAP : **CLAP faible (2,96×), EffNet domine (32,5×), CLAP écarté**. Récap mis à jour.
- **05:30 → 10:00** — MERT progresse (~3,1 s/track, plein CPU), 6 checks watchdog, tous sains, 0 incident.
- **10:20** — MERT fini (6816/6901, B4 = 18,1 s/track).
- **10:24** — `compare` 3-way final : **EffNet 32,35× GAGNE**, MERT-L6 13,86×, CLAP 2,92×. Pipeline DONE.
- **10:26** — récap finalisé. Fin de la nuit, rien à relancer.
