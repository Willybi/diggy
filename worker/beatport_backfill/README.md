# Beatport backfill local (L1a)

Outillage **local** (pattern A7-07 : tourne sur le PC de l'opérateur, pas sur le
VPS) qui draine le **backlog d'enrichissement Beatport** depuis l'**IP
résidentielle**, en parallèle du drain horaire du VPS, pour le résorber plus vite.
Jumeau de l'outil embeddings [`worker/embedding_backfill/`](../embedding_backfill/README.md) :
même canal SSH/psql, même forme dry-run/apply + checkpoint + relançable en salves,
même compute en conteneur Docker.

**Différence clé** : cet outil ne fait QUE **scraper + valider** (dans le
conteneur) et produit un **NDJSON** de matches ; il **n'écrit JAMAIS** en base.
L'**écriture** est faite sur le VPS par le script OPS
[`server/api/scripts/import_beatport_matches.py`](../../server/api/scripts/import_beatport_matches.py),
qui **réutilise verbatim** le code d'enrichissement du drain
(`beatport.enrich.enrich_from_beatport` + `workers.enrichment._mark_searched`).
Zéro vendoring des matchers : le conteneur exécute le **vrai code serveur**
(`workers.enrichment._search_beatport_async`, avec la validation X3 ISRC/titre
remix-aware/artiste), seul l'**IP** change.

> **Faisabilité réseau (probe L0)** : l'IP résidentielle tient **6 rps soutenu,
> 0×403** (`probe_beatport.py`). On garde une **marge** (défaut `--rate 4`) + un
> **garde-fou 403** (abort net après N 403 consécutifs). **Ne JAMAIS relever le
> débit en prod** (IP datacenter, réputation Cloudflare fragile).

## Les 3 étapes (orchestrées par `backfill_beatport.py`)

1. **PULL** — candidats **frais** streamés depuis la prod (lecture seule) via
   `ssh diggy-vps "... psql -q -f -"` alimenté d'un `COPY (...) TO STDOUT` :

   ```sql
   SELECT c.id, c.title, c.isrc, c.artist AS flat_artist,
          coalesce(string_agg(a.name, ', ' ORDER BY ca.position), '') AS m2m_artists
   FROM catalog c
   LEFT JOIN catalog_artists ca ON ca.catalog_id = c.id
   LEFT JOIN artists a          ON a.id = ca.artist_id
   WHERE c.beatport_id IS NULL
     AND c.beatport_searched_at IS NULL   -- FRAIS seulement (retries E1 = VPS)
     -- [AND c.id > :after_id] [AND c.id % :N = :M]
   GROUP BY c.id
   ORDER BY coalesce(c.enrich_priority, 75) DESC, c.id DESC   -- priorité C12
   -- [LIMIT :n]
   ```

   → `data/candidates.csv` (colonnes `id,title,isrc,flat_artist,m2m_artists`). Le
   driver choisit `m2m or flat` comme artiste de match, **miroir exact** de la
   règle X4 du drain. Le filtre `beatport_searched_at IS NULL` est le **garde
   primaire** de ré-éligibilité inter-runs.
2. **SCRAPE** — `docker run` du driver dans l'**image serveur de prod**
   (`beatport/` + `workers/` + curl_cffi), avec la knob de débit L1b
   `BEATPORT_RATE` passée par `-e` (`--rate`, défaut 4 rps). Le driver traite les
   lignes **séquentiellement** (le token bucket cadence), appelle
   `_search_beatport_async` et écrit `data/matches.ndjson` au **contrat L1b** :

   ```
   {"catalog_id": <id>, "status": "found",     "bp_track": <dict normalisé>}
   {"catalog_id": <id>, "status": "not_found", "bp_track": null}
   ```

   Une **panne HTTP** (`BeatportHTTPError`, ex. 403) **n'émet RIEN** pour la ligne
   (elle reste fraîche → re-tentée plus tard : *outage ≠ tentative*, invariant E1).
   Garde-fou : après `BEATPORT_MAX_CONSECUTIVE_403` (défaut 5) 403 consécutifs, le
   batch **aborte proprement** (les lignes restantes restent fraîches).
3. **APPLY** (avec `--apply`) — `matches.ndjson` est **pipé** via ssh stdin au
   script OPS :

   ```bash
   ssh diggy-vps "cd /root/diggy && docker compose exec -T api \
     python scripts/import_beatport_matches.py --apply" < data/matches.ndjson
   ```

   En **dry-run** (défaut) le script OPS est invoqué **SANS `--apply`** : il fait
   tourner le code d'enrichissement, imprime ses compteurs (`enriched` /
   `not_matched` / `merged` / …) puis **rollback** — aucune écriture (DB, MinIO,
   CDN).

## Ce que gère le côté VPS (rien à faire côté local)

- **Écriture** via `enrich_from_beatport` réutilisé → l'**artwork Beatport** ET le
  **merge sur collision d'id** (un `beatport_id` déjà détenu par une autre ligne →
  fusion FK-safe) sont gérés côté VPS. Pas de résidu de ce côté (invariant #4).
- Les **retries E1** (30 / 90 j, abandon après 3) restent **100 % VPS** : cet outil
  ne fait que le **Tier-1 frais** (`beatport_searched_at IS NULL`), jamais un
  re-scan d'entrée déjà tentée.

## Usage

```bash
# dry-run sur un petit échantillon (pull + scrape réels ; l'OPS tourne sans --apply)
python worker/beatport_backfill/backfill_beatport.py --limit 20

# dry-run sur tout le backlog frais
python worker/beatport_backfill/backfill_beatport.py

# scrape + écriture en prod
python worker/beatport_backfill/backfill_beatport.py --apply

# salves parallèles sans recouvrement (id % 4)
python worker/beatport_backfill/backfill_beatport.py --shard 0/4 --apply
python worker/beatport_backfill/backfill_beatport.py --shard 1/4 --apply   # autre terminal

# fenêtre keyset (borne d'id) + limite
python worker/beatport_backfill/backfill_beatport.py --after-id 500000 --limit 20000 --apply

# ré-importer le dernier matches.ndjson sans re-scraper
python worker/beatport_backfill/backfill_beatport.py --reuse-matches --apply
```

Options : `--limit N`, `--after-id N` (fenêtre d'id — borne grossière de salve, pas
un keyset strict sur le tri priorité ; le vrai garde inter-runs est
`beatport_searched_at IS NULL`), `--shard M/N` (`id % N = M`), `--rate R` (débit
résidentiel → `BEATPORT_RATE`, défaut 4), `--concurrency K` (override
`BEATPORT_CONCURRENCY` ; les lignes restent séquentielles, ça ne borne que les
requêtes internes par ligne), `--max-403 N` (seuil d'abort), `--workdir` (défaut
`worker/beatport_backfill/data/`, gitignoré), `--reuse-matches`.

**Défaut = dry-run** : sans `--apply`, aucune écriture ; l'OPS imprime son plan et
rollback.

## Séquence prod (OPS)

> **⚠️ `--apply` MUTE des lignes en prod** (via le code d'enrichissement réutilisé :
> `catalog.beatport_id`, bpm/key/label, artwork, éventuel merge). Un **DUMP CHIFFRÉ
> PRÉALABLE est OBLIGATOIRE** avant tout `--apply` (cf.
> [`docs/restore.md`](../../docs/restore.md)). L'outil est idempotent et
> commit par lots (un crash est sûr), mais un mauvais dump ne se rattrape pas.

1. **Déployer L1b d'abord** (push → CI → image) : le script OPS
   `import_beatport_matches.py` et la knob `BEATPORT_RATE` doivent être en prod.
2. **Dry-run** `--limit 20` : vérifier pull + scrape + le plan OPS sur un
   échantillon (aucune écriture).
3. **DUMP** chiffré de la prod (`docs/restore.md`).
4. **`--apply`** en salves (`--after-id` / `--limit` / `--shard`). Chaque salve est
   idempotente (checkpoint + `beatport_searched_at IS NULL` + `ON CONFLICT`/merge
   côté OPS).
5. **Re-dry-run** pour confirmer la convergence (le backlog frais décroît).

> **Fenêtre horaire** : le drain Beatport du VPS tourne **6h→23h**. Lancer cet outil
> de préférence en **heures creuses du VPS (~23h→6h)** pour éviter tout recouvrement
> (deux IPs tapant Beatport en même temps + double travail sur les mêmes lignes).

## Checkpoint & fil de l'eau

`data/processed_ids.txt` enregistre, **après un `--apply` réussi**, tout id **émis
dans le NDJSON** (found / not_found = tentative complétée). Une relance ne re-scrape
donc que les **nouveaux** candidats. Cas particuliers :

- Un id en **outage** (403 / non-200) n'est **pas émis** dans le NDJSON → **pas
  checkpointé** → re-tenté au prochain run.
- Un **dry-run** ne checkpointe **rien** (rien n'a été écrit) — enchaîner avec
  `--reuse-matches --apply` pour écrire le `matches.ndjson` sans re-scraper.
- Le pull re-filtre de toute façon `beatport_searched_at IS NULL` : une ligne écrite
  sort naturellement des candidats au run suivant (garde primaire).

## Le conteneur (image serveur, zéro vendoring)

Le driver doit exécuter le **vrai code serveur** (matchers X3/X4 identiques au
drain). Plutôt que dupliquer `server/Dockerfile`, l'orchestrateur **construit
l'image serveur de prod** directement depuis le contexte `./server` via
`server/Dockerfile` (tag `diggy-beatport-server`), puis une image-paquet **fine**
`FROM` celle-ci (`Dockerfile` du paquet, tag `diggy-beatport-backfill`) qui n'ajoute
rien — juste un tag local stable. Le driver `scrape_driver.py` est **monté au
runtime** (`-v <workdir>:/work`, comme `embed.py`), jamais baké. Le code serveur est
à `/app` et tourne en utilisateur `diggy` (uid 1000) dont `~/.local` porte les
dépendances → le driver fait `sys.path.insert(0, "/app")`.

> **Docker Desktop (Windows)** : les bind-mounts sont accessibles en écriture quel
> que soit l'uid du conteneur, donc le driver `diggy` écrit `matches.ndjson` dans
> `/work` sans souci de permissions.

## Tests

```bash
pytest worker/beatport_backfill/test_backfill_beatport.py -q   # logique pure hôte
ruff check worker/beatport_backfill/
```

Volontairement **hors `tests/`** : le CI n'a ni l'image serveur ni le réseau et ne
doit pas dépendre de ce paquet d'outillage local. Seule la **logique pure de
l'orchestrateur hôte** est testée (construction de la requête PULL, shard, résumé
NDJSON, gating dry-run/apply + checkpoint avec un runner injecté) ; le driver
(`scrape_driver.py`, qui importe le code serveur) est validé par le **dry-run réel**.
