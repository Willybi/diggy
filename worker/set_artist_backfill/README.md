# Backfill artistes de set — local (C13 C3)

Outillage **local** (pattern A7-07 : tourne sur le PC de l'opérateur, pas sur le
VPS) qui **backfille les liens artiste** des ~42k sets TrackID **existants** encore
non liés. La tâche fil-de-l'eau `link_set_artists` ne traite que les **nouveaux**
sets (bornée) ; le stock historique est le travail de cet outil. Résoudre un set =
dériver les candidats artistes de son `(title, channel)` puis, sur un **miss base**,
taper Deezer — un workload **Deezer de masse INTERDIT sur le VPS** (fair-use CPU +
rate limiting, leçon AV10). Le compute tourne donc **en local** (IP résidentielle)
et l'**écriture** est faite sur le VPS par le script OPS
[`server/api/scripts/import_set_artists_matches.py`](../../server/api/scripts/import_set_artists_matches.py).

Jumeau de [`worker/beatport_backfill/`](../beatport_backfill/README.md) : même canal
SSH/psql, même forme dry-run/apply + checkpoint + relançable en salves (`--shard`),
même compute en conteneur Docker.

**Différence clé** : l'outil ne fait QUE **résoudre** (dans le conteneur) et produit
un **NDJSON** de liens proposés ; il **n'écrit JAMAIS** en base et **ne crée JAMAIS**
d'artiste. Un match Deezer est émis en `(name, deezer_id)` ; l'artiste est
**get-or-créé LIVE au push** par le script OPS (invariant #4). Zéro vendoring : le
conteneur exécute le **vrai code serveur** (`set_artist_extract` + `set_artist_link`
+ le matcher Deezer `tasks.artists._matching_deezer_hits`, byte-identiques au
fil-de-l'eau), seule l'**IP** change.

> **Leçon C9 (IP résidentielle)** : un débit Deezer résidentiel soutenu se fait
> rate-limiter ; **~1 rps** le lève. D'où `--deezer-rate 1.0` par défaut — un
> **plancher inter-requête** appliqué PAR-DESSUS le `RateLimiter` (la config
> `deezer` du serveur est figée à 10 rps et ne lit pas d'env, donc ce plancher est
> la seule knob). **Ne JAMAIS relever le débit prod.**

## Les 3 étapes (orchestrées par `backfill_set_artists.py`)

1. **PULL** — lecture seule via `ssh diggy-vps "... psql -q -f -"` alimenté de
   `COPY (...) TO STDOUT` :

   - la **worklist** des sets non liés (miroir exact de `_select_unlinked_sets`) :

     ```sql
     SELECT s.id, s.title, s.channel
     FROM sets s
     WHERE s.source = 'trackid'
       AND s.parent_set_id IS NULL
       AND NOT EXISTS (SELECT 1 FROM set_artists sa WHERE sa.set_id = s.id)
       -- [AND s.id > :after_id] [AND s.id % :N = :M]
     ORDER BY s.id  -- [LIMIT :n]
     ```

     Le `NOT EXISTS` est le **garde d'idempotence inter-runs** (un set écrit sort du
     pull suivant), équivalent au `searched_at IS NULL` de beatport.
   - la **base artistes** : `artists.name` PUIS `artist_aliases.normalized_alias` →
     `(name, artist_id)`. Le driver la folde par `build_artist_lookup` en local →
     des **artist_id VALIDES en prod** (le main gagne sur l'alias en cas de collision
     de fold, parité avec `_load_artist_lookup`).

   → `data/worklist.csv`, `data/artists.csv`, `data/aliases.csv`.
2. **RESOLVE** — `docker run` du driver dans l'**image serveur de prod**, débit
   Deezer cadencé par `DEEZER_RATE` (`--deezer-rate`, défaut 1.0) + `DEEZER_CONCURRENCY`
   (`--deezer-concurrency`, défaut 5), fan-floor optionnel `LINK_SET_ARTIST_FAN_FLOOR`
   (`--fan-floor`). Pour chaque set : candidats extraits, **base d'abord**
   (`resolve_name_to_id`), Deezer en **dernier recours** (`_matching_deezer_hits` +
   plancher fans, réutilisés verbatim, **sans créer d'artiste**), + scan des artistes
   connus enfouis. Écrit `data/links.ndjson` :

   ```
   {"set_id": <id>, "title": <str>, "channel": <str|null>, "links": [
      {"source": "base",   "name": <str>, "artist_id": <int>},
      {"source": "deezer", "name": <str>, "deezer_id": <str>}
   ]}
   ```

   `source` = la **voie d'identité** : `base` porte un `artist_id` prod, `deezer` un
   `deezer_id` confirmé (artiste résolu/créé au push). `links: []` = set sans
   résolution (tentative complète). Une **panne Deezer** sur un candidat **n'émet
   aucun lien** pour lui (coût de rappel, jamais de précision — invariant #4).
3. **APPLY** — `links.ndjson` est pipé via ssh stdin au script OPS avec
   propagation de `--apply`. En **dry-run** (défaut) le script OPS tourne SANS
   `--apply` : il résout l'identité live, imprime ses compteurs **+ un ÉCHANTILLON
   des liens qu'il créerait** (titre du set → artiste[s]) puis **rollback** — aucune
   écriture. **Lis l'échantillon** = vecteur de contrôle de précision à l'échelle.

## Checkpoint & salves

`data/processed_set_ids.txt` : après un `--apply` **réussi**, tout set id émis (avec
ou sans lien) est enregistré → un re-run ne re-pull que du **neuf** (y compris les
sets sans-résolution, qui n'ont pas de ligne `set_artists` et seraient sinon
re-résolus indéfiniment). Supprime le checkpoint pour forcer une passe complète.
`--shard M/N` (`id % N`) découpe le backlog pour des salves parallèles disjointes ;
`--after-id` reprend un keyset ; `--reuse-links --apply` écrit un `links.ndjson`
d'un dry-run précédent sans re-résoudre.

## Séquence OPS (dump-first, comme tout script `--apply`)

```bash
# 1. déployer le script OPS (push → CI → image) — il ship sous api/
# 2. dry-run échantillon
python worker/set_artist_backfill/backfill_set_artists.py --limit 50
# 3. dry-run pleine échelle → LIRE l'échantillon de liens (précision)
python worker/set_artist_backfill/backfill_set_artists.py
# 4. DUMP PROD (docs/restore.md) AVANT tout --apply
# 5. écrire (par salves conseillé)
python worker/set_artist_backfill/backfill_set_artists.py --shard 0/4 --apply
```

> ⚠️ `--apply` **mute la prod** (écrit `set_artists` + peut créer des `artists` depuis
> un id Deezer). **DUMP PROD D'ABORD.** L'outil lui-même n'écrit jamais ; le script
> OPS oui, et il est idempotent (skip des `set_artists` existants), mais un mauvais
> dump n'est pas récupérable.

## Tests

- `pytest worker/set_artist_backfill/test_backfill_set_artists.py -q` — logique PURE
  de l'orchestrateur host (stdlib, hors CI ; requêtes, shard, NDJSON, checkpoint).
- `pytest tests/worker/test_backfill_set_artists_resolve.py -q` — résolution PURE du
  driver (`resolve_set_links`, base vs deezer, dédup, ordre, scan) — dans CI.
- `pytest tests/worker/test_import_set_artists_matches.py -q` — cœur du script OPS
  (routing, idempotence, dry-run/apply, échantillon) — dans CI.
