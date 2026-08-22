# C9.0 — Benchmark embeddings audio vs co-occurrence en sets — GO/NO-GO

> Chantier **C9** (roadmap). Gate d'entrée isolé (calqué sur E2.a) : **avant** toute migration
> pgvector ou backfill des ~175k, on répond à UNE question quantitative sur un échantillon —
> *les voisins d'un embedding de contenu prédisent-ils la co-occurrence en sets DJ ?* Si oui, le
> signal contenu vaut le chantier (feature « sonne comme » + reco hybride + cold-start). Si non,
> l'embedding brut ne capte pas la structure « mixable » → il faudrait C9.d (fine-tuning contrastif)
> avant toute feature v1, donc NO-GO en l'état.

## Ce que ça mesure (et pourquoi)

- **Modèle v1** : Essentia **Discogs-EffNet** (`discogs-effnet-bs64-1.pb`), embedding 1280-d, CPU,
  cohérent avec la brique Essentia d'E2. C'est le candidat que la roadmap veut valider en premier
  (CLAP / MERT se benchmarkent ensuite avec le même harnais si GO).
- **Vérité terrain** : la **co-occurrence** — deux titres co-occurrent s'ils apparaissent dans le
  même set *fiable racine* (`parent_set_id IS NULL`, `unreliable IS NOT TRUE`). C'est le seul signal
  de « compatibilité » qu'on possède à l'échelle (~jugements implicites de DJs).
- **Échantillonnage par SETS, pas par tracks** : tirer 500 tracks au hasard dans 270k ne produit
  quasi aucune co-occurrence (signal trop épars). On tire **500 sets** et on prend leurs titres
  prévisualisables → univers **dense** en co-occurrence, borné (~quelques milliers de titres),
  self-contained (voisins ET positifs vivent dans le même univers embarqué).
- **Métrique** : pour chaque seed ayant ≥1 partenaire dans l'univers, on classe tous les autres
  titres par cosinus et on mesure **precision@k**, **recall@k** et surtout le **lift@k**
  (precision ÷ taux de base aléatoire). Trois lectures :
  1. **all positives** — le signal brut ;
  2. **cross-artist** (positifs du même artiste **exclus**) — *le chiffre porteur* : isole la vraie
     proximité acoustique de la simple fuite « même artiste » (deux titres d'un même artiste
     co-occurrent beaucoup, un embedding qui ne ferait que ré-identifier l'artiste serait un faux ami) ;
  3. **contrôle embeddings mélangés** — doit retomber à ~1.00x (calibre la métrique).

Seuils indicatifs (William arbitre) : **lift@10 cross-artist ≥ 3x** = GO franc ; **≥ 1.8x** = GO
modéré ; **< 1.3x** = NO-GO / renvoi à C9.d.

## Garde-fous (invariants)

- Score de similarité = **produit scalaire déterministe** sur vecteurs stockés → l'invariant #5
  (les LLMs ne calculent jamais de similarité) n'est PAS violé (un encodeur audio n'est pas un LLM).
- **Aucune persistance audio** : la preview est analysée transitoirement puis supprimée ; on ne
  garderait (plus tard) que le vecteur. Posture CGU identique à E2.
- **Read-only prod** : l'extraction est un `COPY … TO STDOUT`, aucune écriture.

## Reproduction

Tourne en conteneur Linux (Windows n'héberge pas Essentia). Aucune persistance audio.

| Fichier | Rôle |
|---|---|
| [`query.sql`](query.sql) | Échantillon gelé : 500 sets fiables → membership (set_id, track) prévisualisable |
| `sample.csv` | L'échantillon gelé (généré par l'étape 1, à committer) |
| [`Dockerfile`](Dockerfile) | Image (essentia-tensorflow + modèle EffNet) |
| [`embed_eval.py`](embed_eval.py) | `embed` (download Deezer → EffNet → vecteurs) puis `eval` (métrique co-occurrence) |
| `embeddings.npz` / `status.csv` | Sorties de la phase embed (vecteurs L2 + statut par track) |

```bash
# 1. geler l'échantillon depuis la prod (read-only)
ssh diggy-vps "cd /root/diggy && docker compose exec -T postgres sh -c 'psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -q -f -'" < query.sql > sample.csv

# 2. construire l'image (télécharge le modèle EffNet + essentia-tensorflow, ~2 Go)
docker build -t c9-bench .

# 3. embed (télécharge les previews, ~1 Mo/track ; supprimées après analyse) puis eval
docker run --rm -v "$PWD:/work" c9-bench python /work/embed_eval.py both --workers 4

# re-lancer seulement le rapport sans ré-embedder :
docker run --rm -v "$PWD:/work" c9-bench python /work/embed_eval.py eval
```

## C9.0-bis — comparaison des 3 modèles (EffNet vs CLAP vs MERT, tout CPU)

Avant de figer le modèle v1, on rejoue le MÊME échantillon gelé (`sample.csv`) avec les 3 candidats
et on compare le **lift@10 cross-artist** sur l'**univers commun** (les tracks que les 3 ont
embeddées avec succès → comparaison apples-to-apples, seule la représentation varie). Contexte
matériel : **CPU obligatoire** (le GPU de la machine est AMD → hors écosystème CUDA/ML) ; MERT est
donc limité à sa variante **95M** (330M trop lente en CPU).

**Deux images** — essentia-tensorflow (EffNet) et torch (CLAP/MERT) ne cohabitent pas (conflit
numpy/protobuf) :

```bash
# EffNet (image essentia existante — déjà mesuré en C9.0, ré-embed optionnel)
docker build -t c9-bench .
docker run --rm -v "$PWD:/work" c9-bench python /work/embed_eval.py embed --model effnet --workers 6

# CLAP + MERT (nouvelle image torch, CPU-only ; build ~plusieurs Go, télécharge les poids HF)
docker build -f Dockerfile.torch -t c9-bench-torch .
docker run --rm -v "$PWD:/work" c9-bench-torch python /work/embed_eval.py embed --model clap --workers 4
docker run --rm -v "$PWD:/work" c9-bench-torch python /work/embed_eval.py embed --model mert --workers 4

# comparaison finale sur l'univers commun (pur numpy, tourne dans n'importe quelle image)
docker run --rm -v "$PWD:/work" c9-bench-torch python /work/embed_eval.py compare --models effnet,clap,mert
```

Chaque `embed --model X` écrit `embeddings_<X>.npz` + `status_<X>.csv` (gitignorés). `compare`
imprime, par modèle : dim, lift@1/10/20 (all-positives), lift@1/10/20 (cross-artist), et le contrôle
mélangé shuf@10 (doit rester ~1× → métrique calibrée). **Le gagnant = plus haut lift@10 cross-artist.**

> ⚠️ **À surveiller au 1ᵉʳ run** (parties non rejouées ici, l'environnement Docker/HF/Deezer n'étant
> pas testable en amont) : (1) compat `transformers`↔code distant MERT (pin `>=4.30,<4.41`, à ajuster
> si le `trust_remote_code` casse) ; (2) MERT peut réclamer `nnAudio`/`torchaudio` selon la version du
> frontend (déjà dans l'image) ; (3) l'agrégation MERT retenue = **moyenne temps puis moyenne des
> couches** → 768-d (choix standard ; une couche unique donnerait un autre point) ; (4) débit CPU
> MERT bien plus lent qu'EffNet (transformer vs CNN) — normal, on benchmarke la QUALITÉ, pas la
> vitesse. **Enjeu coût** : si MERT gagne, le backfill 175k en CPU (carte AMD non exploitable)
> imposerait du **GPU cloud** ; EffNet/CLAP (CNN) gardent le backfill 100 % local (~63 h mesurées).

## Verdict — GO (2026-08-21)

**Décision : GO.** Les embeddings Discogs-EffNet prédisent la co-occurrence en sets DJ **très
au-dessus du hasard**, et le signal n'est PAS de la fuite « même artiste ».

Échantillon : 500 sets fiables → **6819 / 6901 titres embeddés** (98,8 % ; 66 erreurs Deezer
transitoires + 16 sans preview). Univers dense, base-rate co-occurrence ~0,2 %.

| Passe | lift@1 | lift@10 | lift@20 | precision@10 | recall@20 | rang médian 1ᵉʳ setmate |
|---|---|---|---|---|---|---|
| **All positives** | 52.99x | **34.97x** | 29.39x | 7.86 % | 8.62 % | 21 |
| **Cross-artist** (même artiste exclu) | 42.48x | **32.53x** | 27.71x | 7.14 % | 8.13 % | 24 |
| **Contrôle mélangé** (doit ≈1x) | 1.13x | 1.15x | 1.09x | 0.25 % | 0.32 % | 314 |

Lectures :

- **lift@10 cross-artist = 32.53x** (seuil GO franc ≥ 3x) → GO net. Le contrôle mélangé retombe à
  ~1.1x : la métrique est calibrée, le lift n'est pas un artefact.
- **Cross-artist (32.5x) ≈ all-positives (35.0x)** : retirer les positifs du même artiste n'écroule
  PAS le signal → EffNet capte une **vraie proximité acoustique** qui prédit la mise-en-set, pas juste
  l'identité de l'artiste. C'est le point décisif.
- Le 1ᵉʳ setmate remonte au **rang médian ~21-24** sur 6818 candidats (vs 314 au hasard).

Portée (honnête) : le lift mesure la prédiction des setmates dans un univers **borné et dense**
en co-occurrence (500 sets). En prod sur ~175k titres, le voisinage absolu sera plus bruité
(near-duplicates / même release en tête) — donc `precision@k` ne se transporte pas telle quelle ;
mais la question du gate (« le contenu corrèle-t-il avec la co-occurrence DJ ? ») reçoit un **oui
franc**. La co-occurrence en set n'est pas une vérité de mixabilité parfaite (intros/outros, virages
de genre), mais c'est le meilleur signal implicite disponible.

**Conséquences pour C9 :**

1. **GO C9.a** : migration pgvector + backfill embeddings des ~175k previews (schéma versionné
   `model_name`/`model_version`), avec l'éval voisins-vs-co-occurrence rejouée à l'échelle réelle.
2. Le signal brut EffNet suffit à démarrer C9.b (« sonne comme ») / C9.c (reco hybride) **sans**
   exiger d'abord C9.d — le fine-tuning contrastif « mixabilité » (C9.d) devient un **stretch** pour
   pousser le signal plus loin, pas un prérequis.
3. Prochain arbitrage possible avant C9.a : benchmarker **CLAP / MERT** avec ce même harnais (échange
   du modèle dans le Dockerfile + le nœud de sortie) si on veut comparer avant de figer EffNet — ou
   figer EffNet v1 tout de suite vu la marge.
