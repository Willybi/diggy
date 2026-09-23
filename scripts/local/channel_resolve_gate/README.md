# Channel resolve gate (C14.b — GATE 🅱, artiste → chaîne YouTube)

Outil **local, read-only, stdlib pur** (pattern A7-07 : tourne sur le PC, jamais sur
le VPS). Il **MESURE la faisabilité** de la résolution « artiste → sa chaîne YouTube »
avant de construire le pilier 🅱 de C14.b. Il ne se connecte **jamais** à la prod
(il lit un fichier d'entrée que l'opérateur produit), n'importe **jamais** le paquet
`server`, et n'écrit que dans son dossier `--out`.

> **Ce n'est PAS le pilier.** Aucun résolveur prod, aucun endpoint, aucun front,
> aucune écriture dans `channels`. Le gate produit des **chiffres** (yield + précision)
> pour trancher **GO/NO-GO** et le **mode** (pilier plein vs assisté-manuel). Voir
> `docs/prompts/C14b-3-piliers.md` §5.

## La cascade mesurée (par artiste, arrêt à la 1re méthode qui résout)

| Méthode | Comment | `method` | `confidence` |
|---|---|---|---|
| **(a) Wikidata** | `wbsearchentities`(nom) → top Q-id → `wbgetentities` claims → **P2397** (YouTube channel id). Note aussi **P3040** (SoundCloud) + **P434** (MBID). | `wikidata` | `high` |
| **(b) MusicBrainz** | MBID (via P434 sinon recherche MB) → `artist?inc=url-rels` → un lien **YouTube** officiel (channel/@handle/c/user). Note aussi un lien SoundCloud. **STRICT 1 req/s.** | `musicbrainz` | `high` |
| **(c) Recherche YouTube vérifiée** | (si `YOUTUBE_API_KEY` **et** budget non épuisé) `search.list type=channel` → **vérification par nom foldé** (`fold_match` : égal OU inclusion avec garde de longueur mini). Repli **risqué**. | `search` | `NEEDS_VERIFY` |
| aucune | rien ne résout | `none` | — |
| erreur | exception réseau isolée par artiste (jamais de crash global) | `error` | — |

`has_soundcloud` est **toujours** enregistré (P3040 **ou** rel MB SoundCloud) pour
dimensionner le futur volet SoundCloud (les non-P2397 ont tous P3040, cf. sonde §4).

**Débit poli** : ~0,5 s entre appels Wikidata, **1,0 s MusicBrainz** (strict), 0,2 s
avant une recherche YouTube. La couche HTTP est la **seule** fonction injectable
`fetch_json(url, headers)` (les tests la remplacent → zéro réseau réel). User-Agent
explicite sur **tous** les appels (Wikidata et MusicBrainz l'exigent).

**Quota YouTube** : chaque `search.list` = **100 unités**. `--max-search N` (défaut 60)
borne le nombre de recherches ; au-delà, la recherche est **loggée sautée** (jamais de
troncature silencieuse) et l'artiste reste en `none`.

## Installation

Aucune. Python 3.13, **stdlib uniquement** (`urllib`, `json`, `csv`, `argparse`,
`unicodedata`). La méthode (c) a besoin de la variable d'environnement
`YOUTUBE_API_KEY` (clé Data API v3, gratuite/instantanée) ; absente → méthode (c)
**sautée** pour tous les artistes + warning (la couverture lira bas, c'est attendu).

## Produire l'échantillon (~50 artistes, stratifié) — SQL READ-ONLY

L'entrée est un **NDJSON d'artistes** (1 objet/ligne, `name` requis ; `artist_id`/
`tier` pour le rapport ; `nb_sets`/`nb_lib` informatifs). On le tire de la cohorte
C14.a via le canal `ssh diggy-vps … psql` **en lecture seule** (voir la section
*Deploy* de `CLAUDE.md`). La requête ci-dessous est un **`SELECT` pur, aucune
écriture** — 3 strates ≈ 1/3 chacune (T1 forte activité = self-publishers probables ;
T1 milieu ; underground = ≥1 set DJ lié et catalog mince, type Schrotthagen).
**L'opérateur peut ajuster les strates / les LIMIT** selon ce qu'il veut mesurer.

Sauver dans `sample.sql` :

```sql
-- READ-ONLY. Échantillon stratifié cohorte→gate. Sortie: 1 objet JSON/ligne (NDJSON).
WITH sig AS (
  SELECT
    ac.artist_id,
    ac.tier,
    a.name,
    COALESCE(s.nb_sets, 0)    AS nb_sets,     -- sets DJ liés, roots-only, fiables
    COALESCE(c.nb_catalog, 0) AS nb_catalog,  -- titres catalog de l'artiste
    COALESCE(l.nb_lib, 0)     AS nb_lib       -- titres de l'artiste dans la bib
  FROM artist_cohort ac
  JOIN artists a ON a.id = ac.artist_id
  LEFT JOIN (
    SELECT sa.artist_id, COUNT(*) AS nb_sets
    FROM set_artists sa
    JOIN sets se ON se.id = sa.set_id
    WHERE sa.role = 'dj'
      AND se.parent_set_id IS NULL
      AND se.is_virtual = false
      AND se.unreliable IS NOT TRUE
    GROUP BY sa.artist_id
  ) s ON s.artist_id = ac.artist_id
  LEFT JOIN (
    SELECT artist_id, COUNT(*) AS nb_catalog
    FROM catalog_artists GROUP BY artist_id
  ) c ON c.artist_id = ac.artist_id
  LEFT JOIN (
    SELECT ca.artist_id, COUNT(DISTINCT ut.catalog_id) AS nb_lib
    FROM catalog_artists ca
    JOIN user_tracks ut ON ut.catalog_id = ca.catalog_id
    GROUP BY ca.artist_id
  ) l ON l.artist_id = ac.artist_id
  WHERE ac.excluded IS NOT TRUE
),
t1_high AS (      -- T1 self-publishers probables : forte activité de sets
  SELECT *, 'T1_high' AS strate FROM sig
  WHERE tier = 1 ORDER BY nb_sets DESC, nb_lib DESC LIMIT 17
),
t1_mid AS (       -- T1 milieu : présence moyenne, hors tête
  SELECT *, 'T1_mid' AS strate FROM sig
  WHERE tier = 1 AND artist_id NOT IN (SELECT artist_id FROM t1_high)
  ORDER BY nb_lib DESC, nb_catalog DESC LIMIT 17
),
underground AS (  -- underground : ≥1 set DJ lié, catalog mince (type Schrotthagen)
  SELECT *, 'underground' AS strate FROM sig
  WHERE nb_sets >= 1 AND nb_catalog <= 5
    AND artist_id NOT IN (SELECT artist_id FROM t1_high)
    AND artist_id NOT IN (SELECT artist_id FROM t1_mid)
  ORDER BY nb_sets DESC, nb_catalog ASC LIMIT 16
)
SELECT json_build_object(
  'artist_id', artist_id, 'name', name, 'tier', tier,
  'nb_sets', nb_sets, 'nb_lib', nb_lib, 'nb_catalog', nb_catalog, 'strate', strate
)
FROM (
  SELECT * FROM t1_high
  UNION ALL SELECT * FROM t1_mid
  UNION ALL SELECT * FROM underground
) x;
```

Puis exporter en NDJSON (psql en mode `-Aqt` = non-aligné, silencieux, tuples seuls) :

```bash
ssh diggy-vps "cd /root/diggy && docker compose exec -T postgres sh -c \
  'psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -Aqt'" \
  < sample.sql > artists.ndjson
```

C'est le **seul** contact avec la prod, et il est en lecture. Le gate lui-même est
100 % local.

## Lancer le gate

```bash
export YOUTUBE_API_KEY=…            # sinon méthode (c) sautée
python scripts/local/channel_resolve_gate/resolve.py artists.ndjson
# options utiles :
#   --out ./gate_out        répertoire de sortie (défaut)
#   --max-search 60         plafond de recherches YouTube (100 unités/recherche)
#   --limit 0               borne le nb d'artistes traités (0 = tous)
#   --user-agent "…"        UA envoyé à Wikidata/MusicBrainz
```

### Sorties (dans `--out`, défaut `./gate_out/`, gitignoré)

| Fichier | Contenu |
|---|---|
| `results.ndjson` | 1 ligne/artiste : `{artist_id, name, tier, method, yt_channel_id, yt_channel_title, yt_url, has_soundcloud, sc_ref, confidence}` |
| `summary.txt` | **couverture** totale + **par méthode** (wikidata/musicbrainz/search/none/error), nb `NEEDS_VERIFY`, « sans YouTube mais SoundCloud : X/Y » (dimensionne le volet SC), et le décompte du budget de recherche |
| `review.csv` | `name, method, confidence, yt_url, correct` (dernière colonne **vide**) — l'opérateur ouvre le ↗ `yt_url` et marque **1/0** (surtout les `method=search`) |

## Mesurer la précision (`--score`)

Après avoir marqué la colonne `correct` (0/1) de `review.csv` à la main :

```bash
python scripts/local/channel_resolve_gate/resolve.py --score gate_out/review.csv
#   --total 50    (optionnel) taille de l'échantillon → couverture confirmée en %
```

Imprime la **précision globale** + **par méthode** (surtout `search`, le repli risqué)
et la **couverture confirmée** (trouvés **ET** corrects). Lignes non marquées =
exclues du calcul (jamais comptées à tort comme fausses).

## Décision (GO/NO-GO + calibration) — se lit sur les chiffres

- **Yield** (found/total) **et** précision corrects → **🅱 = vrai pilier** (générateur
  de candidats artistes classés par pertinence cohorte).
- **Repli recherche imprécis** (faible précision sur `method=search`) → **🅱 en mode
  assisté-manuel** : la résolution est **proposée**, l'admin confirme via l'UI de
  pré-sélection existante.
- Dans **tous les cas**, le repli recherche reste **confirmé humain** (invariant #4) —
  le gate ne lie rien, il chiffre.

## Tests & lint

```bash
pytest scripts/local/channel_resolve_gate/         # aucun réseau ni prod (fetch_json mocké)
ruff check scripts/local/channel_resolve_gate/
```

Volontairement **hors `tests/`** : le CI ne dépend pas de cet outillage local. Les
tests couvrent le fold-match (égal / inclusion / accents / ponctuation / garde de
longueur), la cascade complète (P2397 → wikidata ; rel MB YouTube → musicbrainz ;
search vérifiée → NEEDS_VERIFY ; tout absent → none ; erreur réseau → error sans
crash ; sans clé → search sautée ; budget épuisé → sautée), le parsing des 3 formats
de réponse, et le `--score` — sur des **fixtures JSON synthétiques uniquement**.
Les artefacts de run (`gate_out/`, exports) sont gitignorés.
