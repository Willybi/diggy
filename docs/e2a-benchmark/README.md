# E2.a — Benchmark analyse audio des previews (BPM + Key) — GO/NO-GO

> Date : 2026-08-06. Chantier **E2** (roadmap). Livrable du DoD E2.a : « Benchmark documenté, précision
> BPM et key mesurées sur ~500 refs Beatport, décision GO/NO-GO tracée ».
> Deux rounds : **R1** = stack roadmap (Essentia `RhythmExtractor2013` + `KeyExtractor` edma ; librosa).
> **R2** (demandé par William) = alternatives **TempoCNN** (BPM) + **shaath** & **real libkeyfinder** (KEY).

## TL;DR — verdict

| Axe | Verdict | Meilleur | Précision déployable |
|-----|---------|----------|----------------------|
| **BPM** | **GO** (estimé, gaté, labellisé) | RhythmExtractor2013 (léger) ou TempoCNN | ~76 % brut / **~84 % à conf≥2.0** (82 % des tracks), médiane 0,00 (TempoCNN) |
| **KEY** | **NO-GO v1** (triple-confirmé) | edma ≈ shaath | ~62 % voisin (tous) ; exact ≤66 %. **libkeyfinder = le PIRE (55 % voisin).** |

Les seuils *proposés* roadmap (BPM ≥95 %, key ≥75 %) étaient à calibrer : **95 % est irréaliste** pour 30 s
de preview ; ~84 % (gaté) est le plafond réaliste et reste utile pour remplir 48 872 tracks aujourd'hui muettes.

**Décision (William, 2026-08-06)** : GO E2.b **BPM seul**, moteur **léger RhythmExtractor2013** (évite
d'embarquer TensorFlow dans le worker pour +2-3 pts), **backfill local** (pattern A7-07, VPS CPU/mémoire
contraints) ; **KEY non écrite** en v1.

## Méthode

- **Vérité terrain** : 600 lignes `catalog` `bpm_source=key_source='beatport'` (autorité BPM/key, invariant #3)
  + `has_preview` + `deezer_id`. Échantillon **gelé** ([`ground_truth.csv`](ground_truth.csv)), réutilisé aux 2 rounds.
  599/600 analysés (1 échec transitoire).
- **Preview** : résolue en direct via l'API Deezer publique `GET api.deezer.com/track/{id}` → champ `.preview`
  (URL jamais stockée en base ; seul `has_preview` l'est). MP3 30 s analysé **transitoirement puis supprimé**
  (posture CGU : aucune persistance audio).
- **Exécution** : conteneur **Linux Docker** (Windows ne peut pas héberger Essentia ; ffmpeg absent ; Python 3.13
  trop récent). R2 utilise une base **Debian bullseye** (ffmpeg 4.x) car la binding `keyfinder` ne compile pas
  sur bookworm (API libav `channel_layout` retirée en ffmpeg 5.x). Conversion key→Camelot par classe de hauteur
  (indépendante de l'enharmonie), recoupée sur `_KEY_TO_CAMELOT` du repo (`server/api/beatport/client.py`).

## BPM — résultats (599 tracks)

```
                        raw(déployable)  strict-fold(oracle)  ext-fold(plafond)  médiane
RhythmExtractor2013         73.3%            79.5%               84.6%             0.19
TempoCNN (deeptemp)         75.8%            81.6%               85.0%             0.00

TempoCNN par gate de confiance (RhythmExtractor conf) — raw <=2 = correct :
   conf>=0.0 : couv 100%  raw 75.8%      conf>=2.0 : couv 82%  raw 83.8%
   conf>=1.5 : couv  89%  raw 81.6%      conf>=2.5 : couv 75%  raw 84.7%

Repli sur PRIOR DE PLAGE FIXE (déployable, sans vérité) : N'AIDE PAS
   tcnn_bpm  raw 75.8%  |  [90,180) 74.8%  |  [76,152) 75.6%  |  oracle 81.6%
```

- **TempoCNN > RhythmExtractor** de ~+2 pts partout (médiane 0,00) — mais **modeste**, et TempoCNN exige
  **TensorFlow** (~500 Mo) + un modèle `.pb` → non retenu pour le worker (voir décision).
- **Le prior de plage n'aide pas** : le catalog s'étale réellement 60→180 BPM (masse à 65-90 ET 150+, pas que
  120-140), donc replier vers une fenêtre fixe crée autant d'erreurs qu'il en corrige → l'**oracle-fold (~82 %)
  n'est PAS atteignable**. Le vrai levier déployable = **le gate de confiance** (~84 %).
- Les ~15 % d'échecs restants ne sont PAS métriques (le repli étendu plafonne à ~85 % pour les 2 méthodes) :
  matériel non-4/4 (folk, art-pop, ambient) + rare bruit de version. Beatport BPM = vérité fiable.

## KEY — résultats (599 tracks)

```
                exact(tous)  voisin(tous)   meilleur (strength>=0.8)
Essentia edma      47.9%        62.4%         voisin 75.1% (couv 56%)
Essentia shaath    47.1%        63.1%         voisin 81.4% (couv 45%)
real libkeyfinder  37.2%        54.9%         — (pas de score de confiance)
```

- **libkeyfinder (la référence DJ) est le PIRE** des trois. Le spike 20-tracks qui montrait shaath >> edma
  était du bruit d'échantillon ; sur 600, **edma ≈ shaath**.
- Même la meilleure key (shaath à strength≥0,8) = 81 % voisin / 66 % exact sur **45 %** des tracks.
  L'exact ne dépasse jamais ~66 %.
- **Caveat** : vérité = key **Beatport** (elle-même algorithmique) → taux d'**accord entre algos**, pas accuracy
  absolue. Mais 3 méthodes convergent bas → la key sur 30 s de preview est structurellement insuffisante pour du
  mix harmonique (une mauvaise key est activement nuisible, invariant #4).

## Recommandation E2.b (retenue)

- **Écrire le BPM uniquement**, `bpm_source='analysis'`, **gate `RhythmExtractor conf ≥ 2.0`** (~84 %, couvre 82 %),
  **valeur labellisée « estimée »** en UI. Les ~18 % basse-confiance restent `NULL` (mieux rien qu'un mauvais BPM).
- **Moteur : RhythmExtractor2013** (essentia standard, PAS de TF) — léger, ~73 % brut / ~81 % gaté. TempoCNN
  (+TensorFlow) réservé si le +2-3 pts devient nécessaire (swap contenu : le harnais + l'image existent).
- **Backfill LOCAL** (pattern A7-07, PC) — CPU-bound + ~20 Go de previews à télécharger ; le VPS partage son CPU
  avec Postgres et est contraint en mémoire. *Fil de l'eau* (nouveaux tracks previewés) = question séparée
  (run local périodique, ou tâche VPS légère puisque essentia-standard est peu lourd).
- **NE PAS écrire de key** en v1.
- **Garde-fous provenance** (mesurés — reader « provenance-guards ») : garder `bpm IS NULL` (pas `bpm_source IS NULL`,
  protège le legacy) ; idempotence (skip si déjà 'analysis') ; un run Beatport ultérieur écrase 'analysis' sans code
  (`'analysis' != 'beatport'`) MAIS seulement si `beatport_id IS NULL` → décider du sort des rows déjà `beatport_id`
  non-null ; le merge NULL-fill ne range pas les sources ; `bpm_source` String(20) sans CHECK. **Aucune migration**.

## Reproduction

Kit dans ce dossier (tourne en conteneur Linux, aucune persistance audio) :

| Fichier | Rôle |
|---|---|
| [`query.sql`](query.sql) | Requête de la vérité terrain (COPY … TO STDOUT), gèle 600 refs Beatport+preview |
| [`ground_truth.csv`](ground_truth.csv) | L'échantillon gelé (600 lignes) |
| [`camelot.py`](camelot.py) | Conversion key→Camelot (classe de hauteur), voisins Camelot, repli d'octave |
| [`benchmark.py`](benchmark.py) | R1 — Essentia RhythmExtractor2013 + KeyExtractor edma/edmm + librosa |
| [`benchmark2.py`](benchmark2.py) | R2 — RhythmExtractor2013 vs TempoCNN ; edma vs shaath vs libkeyfinder |
| [`analyze_prior.py`](analyze_prior.py) | Analyse « prior de plage » (déployable) sur les résultats |
| [`Dockerfile`](Dockerfile) | Image R1 (essentia + librosa + ffmpeg) |
| [`Dockerfile2`](Dockerfile2) / [`Dockerfile2b`](Dockerfile2b) | Image R2 (essentia-tensorflow + TempoCNN ; 2b = bullseye + libkeyfinder) |
| [`results_full.csv`](results_full.csv) / [`results2_full.csv`](results2_full.csv) | Résultats par-track R1 / R2 |

```bash
# 1. geler la vérité terrain depuis la prod (read-only)
ssh diggy-vps "cd /root/diggy && docker compose exec -T postgres sh -c 'psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -q -f -'" < query.sql > ground_truth.csv
# 2. R2 (image bullseye avec libkeyfinder réel) puis run 600
docker build -f Dockerfile2b -t e2a-bench2b .
docker run --rm -v "$PWD:/work" e2a-bench2b python /work/benchmark2.py --workers 4 --out /work/results2_full.csv
# 3. re-générer le rapport / l'analyse déployable sans re-télécharger
docker run --rm -v "$PWD:/work" e2a-bench2b python /work/benchmark2.py --report-only /work/results2_full.csv
python analyze_prior.py results2_full.csv
```
