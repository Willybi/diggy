---
description: Supervise un outil de backfill/hydratation local (bpm, embedding, beatport, trackid_hydrate) — pré-vol, dry-run, barrière dump, apply surveillé, convergence, salves auto
allowed-tools: Read, Glob, Grep, AskUserQuestion, Skill, Bash(python worker/bpm_backfill/backfill_bpm.py:*), Bash(python worker/embedding_backfill/backfill_embeddings.py:*), Bash(python worker/beatport_backfill/backfill_beatport.py:*), Bash(python worker/trackid_hydrate/hydrate.py:*), Bash(ssh diggy-vps:*), Bash(docker:*), Bash(git log:*), Bash(git diff:*)
argument-hint: <bpm|embedding|beatport|trackid_hydrate> [--apply] [--limit N] [--loop] [options passées à l'outil]
---

Tu supervises un run d'un **outil de backfill/hydratation LOCAL** de Diggy (pattern A7-07 : il tourne sur CE PC, pas sur le VPS). Les 4 outils partagent le même cycle de vie : **PULL** (worklist depuis la prod, lecture seule via `ssh diggy-vps … psql`) → **COMPUTE** (conteneur Docker) → **APPLY** (écriture prod). Ton rôle n'est pas de réimplémenter la procédure — chaque outil la documente dans son README — mais de la **piloter avec garde-fous** : dry-run d'abord, barrière dump avant tout write, surveillance CPU du VPS pendant l'apply, bilan de convergence entre salves.

Argument `$ARGUMENTS` : le **1er token** = l'outil (`bpm` | `embedding` | `beatport` | `trackid_hydrate`). Le reste = mode + options :
- **`--apply` absent → dry-run** (défaut, AUCUNE écriture). C'est le comportement natif des outils : sans `--apply`, rien n'est écrit.
- **`--apply` présent → écriture prod**, mais tu ne le lances JAMAIS avant d'avoir passé la barrière de l'Étape 3.
- **`--loop`** → après une 1ʳᵉ salve `--apply` validée par moi, tu proposes d'enchaîner les salves automatiquement via le skill `/loop` (Étape 6).
- Toute autre option (`--limit`, `--after-id`, `--after-score`, `--shard`, `--reuse-*`, `--rate`, `--executor-workers`, …) est **passée verbatim** à l'outil.

Si aucun outil valide n'est donné, demande-le-moi (liste les 4) et arrête-toi.

## Contrat par outil (source de vérité = le README de l'outil)

| Outil (`$1`) | Paquet / entrée | Compute | Écrit | Dump avant `--apply` ? | Fenêtre VPS à éviter |
|---|---|---|---|---|---|
| `bpm` | `worker/bpm_backfill/backfill_bpm.py` | Essentia (RhythmExtractor) | `catalog.bpm` (garde `bpm IS NULL`) | **Recommandé** (mute `catalog`, mais gardé, ni delete ni merge) | Deezer 05:00 |
| `embedding` | `worker/embedding_backfill/backfill_embeddings.py` | EffNet 1280-d | `track_embeddings` (INSERT, `ON CONFLICT DO NOTHING`) | **Non requis** (INSERT-only table neuve) | Deezer 05:00 |
| `beatport` | `worker/beatport_backfill/backfill_beatport.py` | scrape Beatport (IP résidentielle) | via OPS VPS `import_beatport_matches.py` (mute `catalog`, artwork, merge) | **OBLIGATOIRE** | Beatport 6h→23h → lancer ~23h→6h |
| `trackid_hydrate` | `worker/trackid_hydrate/hydrate.py` | TrackID + Deezer/Beatport/BPM/EffNet | via OPS VPS `import_trackid_clean.py` (mute nombreuses tables + merge) | **OBLIGATOIRE** | Beatport 6h→23h + BPM 00h→03h ; salves lourdes en heures creuses |

**Toujours lire le README de l'outil ciblé AVANT de lancer** (`worker/<paquet>/README.md`) : il porte le contrat exact des options, les préconditions et les pièges à jour. Ne présume pas — vérifie.

**Garde-fous transverses (valent pour les 4) :**
- **Ne JAMAIS relever le débit en prod** (`--rate`/`--beatport-rate`/`--detail-rate`). Les défauts sont calibrés sur des leçons de rate-limit (C9 Deezer 1 rps, probe Beatport 6 rps → marge 4). Si je demande un débit plus haut, refuse et rappelle la leçon.
- **CPU résidentiel** : `--workers`/`--executor-workers` bas (1 sur machine chargée) — EffNet/Essentia sont CPU-bound.
- **Dry-run ne checkpointe rien.** Pour écrire un compute déjà fait sans le refaire : `--reuse-results` (bpm/embedding) / `--reuse-matches` (beatport) / `--reuse-bundle` (trackid_hydrate) + `--apply`.
- **Idempotence** : chaque salve se re-filtre côté PULL (`bpm IS NULL`, `te.id IS NULL`, `beatport_searched_at IS NULL`, `hydration_state='not_hydrated'`) → une relance ne retraite que du neuf.

## Étape 1 — Pré-vol

Adapté à l'outil ciblé. N'aller plus loin que si tout est vert.
- **Environnement local** : `docker` répond, `ssh diggy-vps "echo ok"` répond. (Le compute exige Docker ; le PULL/APPLY exige le SSH.)
- **Script OPS déployé** (beatport / trackid_hydrate) : le script `server/api/scripts/import_*.py` correspondant doit être dans l'image prod. Vérifie côté VPS : `ssh diggy-vps "cd /root/diggy && docker compose exec -T api ls scripts/ | grep import_"`. Si absent → **STOP** : « déployer L1b/le script OPS d'abord (push → CI → image) ».
- **Précondition data** :
  - `embedding` : table `track_embeddings` présente (migration 0049 + extension `vector`).
  - `trackid_hydrate` : scores importés (`SELECT count(*) FROM trackid_index WHERE score IS NOT NULL AND hydration_state='not_hydrated'` > 0) ; sinon le PULL est vide → rien à faire.
- **Taille du backlog** : lance un dry-run `--limit 20` (voir Étape 2) qui te donne les compteurs d'éligibilité ; sers-t'en pour estimer le volume restant et le nombre de salves.

Reporte le pré-vol en 3-4 lignes (env OK, script OPS OK/KO, précondition OK/KO, backlog ~N).

## Étape 2 — Dry-run d'abord, SYSTÉMATIQUEMENT

Même si j'ai demandé `--apply`, tu commences par un **dry-run** (sans `--apply`). Si c'est un premier run de la session et que je n'ai pas fixé de `--limit`, ajoute `--limit 20` pour un échantillon rapide.

Lance l'outil et **lis-moi les compteurs** de son plan : `eligible` / `no_preview` / `low_conf` / `errors` / `not_found` / `merged` / `enriched` (selon l'outil). Pour beatport/trackid_hydrate, le dry-run fait aussi tourner le funnel OPS côté VPS (`--dry-run-push` pour trackid_hydrate) qui **rollback** et imprime SES compteurs — remonte-les.

Si le dry-run remonte un taux d'erreur anormal (ex. beaucoup de `error:*` réseau, ou une avalanche de 403 Beatport), **arrête-toi** et diagnostique avant tout `--apply`.

## Étape 3 — Barrière avant `--apply`

À franchir UNIQUEMENT si j'ai demandé `--apply`. Ne lance jamais un write sans avoir coché ceci :

1. **DUMP** (selon la colonne du tableau) :
   - `beatport` / `trackid_hydrate` → **dump chiffré OBLIGATOIRE** (cf. `docs/restore.md`). Demande-moi de confirmer qu'un dump **frais** existe. Ne lance rien tant que je n'ai pas confirmé. Un mauvais merge est une corruption coûteuse (invariant #4) et un mauvais dump ne se rattrape pas.
   - `bpm` → dump **recommandé** (mutation gardée `bpm IS NULL`, sans delete/merge) : mentionne-le, laisse-moi trancher.
   - `embedding` → non requis (INSERT-only) : signale-le, on peut continuer.
2. **Fenêtre horaire VPS** : vérifie qu'on n'est pas dans la fenêtre à éviter de l'outil (tableau). Si on l'est, préviens et propose de reporter en heures creuses (le recouvrement = double travail + 2 IPs sur Beatport). Pour `trackid_hydrate` le drain VPS peut tourner **en parallèle** (réservation dynamique CLAIM/LEASE, migration 0055) — pas besoin de le stopper ; ne stoppe le sentinel Redis `trackid_backfill_done` QUE si je le demande explicitement.
3. **Récap de ce qui va muter** : une phrase précise (tables + volume estimé de la salve) pour que je valide en connaissance de cause.

## Étape 4 — Salve `--apply` surveillée

Une fois la barrière franchie, lance la salve `--apply` avec les options passées. **Pendant** qu'elle tourne, surveille le CPU du VPS (leçon fair-use Hostinger, throttle AV10 = 6-7 j de CPU soutenu) :
- échantillonne `ssh diggy-vps "docker stats --no-stream"` (et au besoin `ssh diggy-vps "sar -u 1 3"`) au fil de la salve ;
- **alerte-moi** si le CPU part en plateau soutenu (> ~80 % sur plusieurs minutes) ou si l'autovacuum s'emballe sur `catalog` → propose de réduire la taille des salves (`--limit`) et d'étaler.

À la fin, remonte le résumé de la salve (écrits / rejets / erreurs, ids checkpointés).

## Étape 5 — Convergence

Après une salve `--apply` :
- lis le checkpoint (`worker/<paquet>/data/processed_ids.txt`) pour le cumul traité ;
- relance un **dry-run** court pour mesurer le backlog restant → dis-moi « backlog passé de X à Y, reste ~N salves à cette cadence » ;
- confirme l'idempotence (un re-`--apply` recompterait tout en `already_*` sans rien re-stamper).

## Étape 6 — Salves auto (`--loop`, opt-in)

Seulement si `--loop` est demandé ET qu'une 1ʳᵉ salve `--apply` a été validée par moi (Étapes 3-5 passées au moins une fois). La barrière dump de l'Étape 3 reste acquise pour la session tant que le dump reste frais.

Propose d'enchaîner les salves via le skill `/loop` : une salve `--apply --limit <cadence raisonnable>` à intervalle, calé en **heures creuses du VPS** pour l'outil concerné, avec **conditions d'arrêt dures** :
- backlog `not_hydrated`/éligible tombé à 0 (convergence),
- CPU VPS en plateau soutenu (repli),
- plafond de salves que je fixe.

Entre deux salves du loop, rejoue une mini-Étape 5 (convergence) et une vérif CPU. **Ne masque jamais** une salve en échec ou un CPU qui grimpe sous un « ça avance » — remonte-le et arrête le loop si besoin. Toute écriture prod reste sous la barrière ; si le dump n'est plus frais (nouvelle journée, gros changement), re-demande confirmation avant de reprendre les `--apply`.

## Rapport

À chaque étape marquante, un point court : quelle salve, quels compteurs, état du backlog, état CPU VPS. En fin de session : bilan cumulé (traité / restant / salves faites), et la suite recommandée (autre salve, `/loop`, ou clôture). Reste factuel : une salve « réussie » avec un CPU VPS qui monte n'est pas un succès neutre — signale le coût.
