# C9.0 — Compte rendu : les embeddings audio prédisent-ils la co-occurrence en sets DJ ?

**Date :** 2026-08-21 · **Chantier :** C9 (gate d'entrée) · **Verdict : GO franc** · **Statut code :** aucun (outillage local uniquement)

---

## 1. Résumé

Avant d'engager le chantier C9 (embeddings audio + reco par contenu), on a isolé **une** question quantitative, testable sur échantillon, à la manière du benchmark E2.a : *un embedding de contenu audio capte-t-il ce qui fait qu'un DJ place deux morceaux dans le même set ?* Réponse mesurée : **oui, très nettement** — les voisins d'embedding co-occurrent en sets **~33× plus** que le hasard, et ce signal **n'est pas** un simple effet « même artiste ». Le gate est franchi ; C9.a/b/c sont justifiés, C9.d (fine-tuning) devient optionnel.

## 2. Contexte & question

La reco actuelle (C2/C4) repose sur la **co-occurrence** : deux titres sont proches s'ils apparaissent ensemble dans des sets / des likes. Sa faiblesse structurelle est le **cold-start** : un titre sans historique est invisible. C9 propose d'ajouter un signal **acoustique** (embedding du contenu de la preview) pour recommander un titre dès son arrivée.

Le pré-requis à valider avant tout investissement (migration pgvector, backfill de ~175k titres) : **l'embedding de contenu corrèle-t-il avec le jugement implicite des DJs** (la co-occurrence en set) ? Si non, l'embedding brut n'est pas exploitable en v1.

## 3. Hypothèse

> H1 — Les plus proches voisins d'un titre dans l'espace d'embedding EffNet co-occurrent dans les sets DJ significativement plus que des titres tirés au hasard.
>
> H0 (nulle) — Aucune relation : la précision des voisins d'embedding ≈ taux de base aléatoire.

## 4. Méthode

**Modèle.** Essentia **Discogs-EffNet** (`discogs-effnet-bs64-1.pb`), embedding **1280-d**, CPU, cohérent avec la brique Essentia d'E2. Preview Deezer 30 s → 16 kHz mono → embeddings par patch → **moyenne** → **normalisation L2**. Analyse transiente, **aucun audio persisté** (posture CGU identique à E2).

**Vérité terrain = co-occurrence.** Deux titres « co-occurrent » s'ils apparaissent dans le même **set fiable racine** (`parent_set_id IS NULL`, `unreliable IS NOT TRUE`). C'est le seul signal de compatibilité disponible à l'échelle — des jugements implicites de DJs.

**Échantillonnage par sets (et non par titres).** Tirer 500 titres au hasard dans ~270k n'en fait quasi jamais co-occurrer (signal trop épars). On tire **500 sets** et on prend tous leurs titres prévisualisables → univers **dense** en co-occurrence, borné, self-contained (voisins ET positifs vivent dans le même univers embarqué). Échantillon **gelé** (`sample.csv`, read-only prod via `COPY`).

**Métrique.** Pour chaque titre-seed ayant ≥1 partenaire dans l'univers : classer tous les autres titres par cosinus (= produit scalaire, vecteurs normalisés), puis **precision@k**, **recall@k** et surtout le **lift@k = precision@k ÷ taux de base aléatoire**. Le lift ramène les précisions absolues (faibles, car la co-occurrence est rare : base-rate ~0,2 %) à une échelle interprétable : *combien de fois mieux que le hasard*.

**Trois contrôles — le cœur de la rigueur :**

| Contrôle | Ce qu'il neutralise | Attendu si H1 vraie |
|---|---|---|
| **All positives** | — (signal brut) | lift ≫ 1 |
| **Cross-artist** (positifs du même artiste **exclus**) | la fuite « même artiste » (deux titres d'un même artiste co-occurrent beaucoup ; un embedding qui ne ferait que ré-identifier l'artiste serait un faux ami) | lift ≫ 1 **et** proche du brut |
| **Shuffled** (embeddings mélangés aléatoirement) | calibration de la métrique elle-même | lift ≈ 1 |

**Score déterministe.** Le score de similarité est un produit scalaire sur vecteurs stockés — pas un LLM (invariant #5 respecté).

## 5. Résultats

Univers : **6819 / 6901 titres embeddés** (98,8 % ; 66 erreurs Deezer transitoires, 16 sans preview). 6819 seeds évalués.

| Passe | lift@1 | **lift@10** | lift@20 | precision@10 | recall@20 | rang médian du 1ᵉʳ setmate |
|---|---|---|---|---|---|---|
| **All positives** | 52.99× | **34.97×** | 29.39× | 7.86 % | 8.62 % | 21 |
| **Cross-artist** | 42.48× | **32.53×** | 27.71× | 7.14 % | 8.13 % | 24 |
| **Shuffled (contrôle)** | 1.13× | **1.15×** | 1.09× | 0.25 % | 0.32 % | 314 |

## 6. Interprétation — pourquoi « GO franc »

Trois lectures convergent :

1. **Ampleur.** lift@10 = **32.5× cross-artist**, très au-dessus du seuil de GO franc fixé *a priori* (≥ 3×). Le 1ᵉʳ setmate remonte au **rang médian ~24** sur 6818 candidats, contre 314 pour un classement aléatoire.
2. **Métrique calibrée.** Le contrôle **shuffled retombe à ~1,1×** : le lift observé n'est pas un artefact de construction (base-rate, taille d'univers) — il mesure bien une structure réelle.
3. **Point décisif — ce n'est pas la fuite d'artiste.** Retirer les positifs du même artiste ne fait chuter le lift que de 35,0× à **32,5×** (−7 %). Le signal **survit** à l'exclusion : EffNet capte une **vraie proximité acoustique** qui prédit la mise-en-set, pas seulement l'identité de l'artiste. C'est le confondeur qu'on redoutait, et il ne tient pas.

**On rejette H0.** Le contenu acoustique est un prédicteur fort et autonome de la co-occurrence DJ.

## 7. Limites & menaces à la validité (honnête)

- **Univers borné et dense.** Le lift est mesuré sur 500 sets co-occurrence-denses. En prod sur 175k titres, le voisinage absolu sera plus bruité (near-duplicates / même release en tête de liste) — donc `precision@k` **ne se transporte pas telle quelle**. Le gate valide l'**existence et la force du signal**, pas la précision opérationnelle finale (qui sera re-mesurée à l'échelle en C9.a).
- **Proxy imparfait.** La co-occurrence en set ≠ mixabilité parfaite (un set a des intros/outros, des virages de genre). C'est néanmoins le meilleur signal implicite disponible.
- **Un seul modèle.** EffNet uniquement. CLAP / MERT n'ont pas été comparés ici — le harnais est prêt à les benchmarker (échange du modèle + nœud de sortie) si on veut départager avant de figer.
- **Base-rate faible → precision absolue basse** (~7 %) : normal et attendu vu la rareté de la co-occurrence ; c'est précisément pourquoi on raisonne en lift.

## 8. Conclusion & recommandation

Gate **franchi**. Conséquences pour C9 :

1. **GO C9.a** — migration pgvector + backfill embeddings des ~175k previews (schéma versionné `model_name`/`model_version`), avec l'éval voisins-vs-co-occurrence **rejouée à l'échelle réelle**.
2. Le signal brut EffNet suffit à démarrer **C9.b** (« sonne comme ») / **C9.c** (reco hybride) **sans** exiger d'abord **C9.d** — le fine-tuning contrastif « mixabilité » devient un **stretch** pour pousser le signal plus loin, pas un prérequis.
3. **Arbitrage ouvert (William)** avant C9.a : figer EffNet v1 tout de suite (vu la marge de 32×), ou benchmarker **CLAP/MERT** avec le même harnais (CLAP ouvrirait en prime la recherche texte→audio).

## Annexe — reproduction

Kit complet dans ce dossier (`query.sql`, `Dockerfile`, `embed_eval.py`, `README.md`). Tourne en conteneur Linux, aucune persistance audio :

```bash
ssh diggy-vps "... psql --csv -f -" < query.sql > sample.csv     # échantillon gelé (read-only)
docker build -t c9-bench .                                        # essentia-tensorflow + modèle EffNet
docker run --rm -v "$PWD:/work" c9-bench python /work/embed_eval.py both --workers 6
```
