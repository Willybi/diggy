# TrackID title miner (C13.b — corpus mining + benchmark GATE)

Outil **local, read-only, stdlib pur** (pattern A7-07 : tourne sur le PC, jamais
sur le VPS) qui mine les titres de sets TrackID pour produire le **matériel de
décision** du chantier C13. Il ne se connecte **jamais** à la prod, n'importe
**jamais** le paquet `server`, ne fait **aucun appel réseau** et n'écrit que des
fichiers locaux.

> **Pourquoi cet outil.** TrackID.net n'expose **aucun champ artiste** au niveau
> d'un set : le DJ n'existe que dans le `channel` et/ou noyé dans le `title`. On
> veut, à terme, **dériver** l'artiste depuis le titre par un extracteur
> **soustractif** (C13.c). Avant d'écrire cet extracteur, il faut un **GATE** :
> mesurer, SUR CHIFFRES, la distribution des « squelettes » de titres pour décider
> si un LLM est nécessaire (déterministe seul ≈ 85 % → pas de LLM ; ≈ 60 % avec
> une longue traîne riche en artistes → LLM utile). Cet outil produit ces chiffres ;
> **il ne tranche pas** — voir « Décision GO/NO-GO » plus bas.

C'est un outil de **décision**, PAS l'extracteur final. Il ne crée aucun lien
`SetArtist` (c'est C13.c, post-gate).

## Approche : soustractive → squelettes

Chaque titre est réduit à son **squelette** : on reconnaît les **briques de bruit**
et les **connecteurs** qui structurent les artistes, on remplace chaque brique
reconnue par un placeholder, et ce qui reste (le résidu, souvent un nom d'artiste)
devient `?`. Le squelette est la **séquence** de placeholders et de résidus.

| Placeholder | Brique reconnue |
|-------------|-----------------|
| `<DATE>` | date, toutes formes : `05/09/2025`, `2025-09-05`, `05092025`, `050925`, `20th Feb 2032`, `June 2026`, `Feb 20 2032`, année nue `1900`–`2039` |
| `<EP>` | marqueur d'épisode/volume : `EP12`, `#12`, `Vol.3`, `Part 2`, `Set 5`, `Mix 5`, `S01E02`, run de `\d{3,}` isolé |
| `<FORMAT>` | mot de format : `DJ Set`, `DJ Mix`, `Guest Mix`, `Live`, `Podcast`, `Exclusive`, `FREE DOWNLOAD`, `Official`, `Mixtape`, `Session`… |
| `<DELIM>` | connecteur qui STRUCTURE les artistes : `B2B`, `B3B`, `B4B`, `F2F`, `VS`, `X`, `&`, `feat.`, `ft.`, `presents`, `pres.` |
| `?` | résidu non reconnu (candidat artiste / autre texte) |

**Exemple.** `Amelie Lens B2B Charlotte de Witte @ Tomorrowland 2024`
→ `? <DELIM> ? <DATE>`. `Bicep - Live at Boiler Room 05/09/2025`
→ `? <FORMAT> ? <DATE>`.

Par défaut les placeholders **consécutifs identiques sont fusionnés** (`? ?` → `?`,
`<FORMAT> <FORMAT>` → `<FORMAT>`) : un squelette abstrait la STRUCTURE, pas le
nombre de mots inconnus — c'est ce qui fait converger la distribution sur un petit
top-N décidable. `--no-collapse` garde la multiplicité exacte.

### Choix de reconnaissance assumés (grossiers par design)

Un GATE de mining n'a pas besoin d'une désambiguïsation parfaite, mais d'un
placeholdering **cohérent**. Quelques arbitrages consignés :

- **`FORMAT` avant `EP`** : `Guest Mix #128` → `<FORMAT> <EP>` (la phrase « guest
  mix » est captée avant que la règle EP « mix #128 » ne la vole). Un `Set 5` /
  `Mix 5` seul (sans phrase de format) tombe bien en `<EP>`.
- **`DATE` avant `EP`** : une année (`2024`) est une `<DATE>`, jamais le `\d{3,}`
  isolé d'EP.
- **`0509` (4 chiffres non-année)** → `<EP>` (indiscernable d'un numéro d'épisode ;
  seules les années `1900`–`2039` sont traitées en date à 4 chiffres nus).
- **Nombre nu résiduel après une phrase de format** (`A B2B Set` → `? <DELIM> ?`) :
  un mot de bruit résiduel peut rester en `?`. Rare, sans conséquence sur le GATE.
- **`with` / `and` NON traités en `<DELIM>`** (trop communs → sur-marquage). Le
  symbole `&` et le `x` isolé, eux, sont des connecteurs.

Les vocabulaires (`_FORMAT_TERMS`, `_DELIM_WORDS`, `_MONTHS`) sont des constantes
en tête de `bricks.py`, ajustables en un seul endroit. Cet outil reste
volontairement **stdlib pur** : il n'importe PAS `server/workers/artist_names.py`
(l'arsenal de fold/normalisation que l'extracteur déterministe C13.c réutilisera),
mais s'aligne sur son esprit.

## Format d'entrée

Un export **NDJSON** (défaut) ou **CSV** des titres de sets. Champs :

- **`title`** (requis) — le titre brut du set.
- **`channel`** (optionnel mais recommandé) — la chaîne source (meilleur proxy de
  l'artiste ; reporté tel quel dans le template d'étiquetage).

Noms de champs surchargables par `--title-field` / `--channel-field`. NDJSON = un
objet JSON par ligne (lignes vides, JSON invalide et objets sans titre ignorés).
CSV = une ligne d'en-tête nommant au moins la colonne titre. Le format est
auto-détecté par l'extension (`.ndjson`/`.jsonl` → NDJSON, `.csv` → CSV ; défaut
NDJSON), forçable par `--format`.

### Comment l'opérateur produit l'export

Les ~381k titres vivent dans la table prod `trackid_index` (colonne `title`, +
`channel`). Export read-only depuis le VPS (cf. la section *Deploy* de `CLAUDE.md`
pour le canal `ssh diggy-vps … psql`), par ex. en NDJSON :

```bash
ssh diggy-vps "cd /root/diggy && docker compose exec -T postgres sh -c \
  'psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -Aqt -c \
   \"SELECT json_build_object('\''title'\'', title, '\''channel'\'', channel) \
     FROM trackid_index WHERE title IS NOT NULL\"'" > data/titles.ndjson
```

(ou un simple `COPY … TO STDOUT (FORMAT csv, HEADER)` sur `title,channel` →
`data/titles.csv`). L'export est le SEUL contact avec la prod ; le mining lui-même
est 100 % local.

## Lancer le mining

```bash
python scripts/local/trackid_titles/mine.py data/titles.ndjson
# options utiles :
#   --workdir data              répertoire de sortie (défaut: ./data)
#   --top 40                    nb de squelettes détaillés dans samples.md
#   --samples-per-skeleton 8    titres réels gardés par squelette
#   --label-sample 300          taille du template d'étiquetage
#   --label-strategy representative|stratified
#   --no-collapse               garder la multiplicité exacte des placeholders
#   --title-field / --channel-field / --format
```

### Sorties (dans `--workdir`, défaut `data/`, gitignoré)

| Fichier | Contenu |
|---------|---------|
| `skeletons.csv` | **distribution complète** : `skeleton, count, pct, cumulative_pct`, triée du plus fréquent au moins fréquent (déterministe, tie-break lexical) |
| `samples.md` | le **top-N** squelettes, chacun avec quelques **titres réels** d'exemple (+ `channel`) pour juger à l'œil ce que contient chaque famille |
| `label_template.csv` | un **échantillon de titres à étiqueter à la main** : `title, channel, skeleton, expected_artist` — `expected_artist` **vide**, à remplir |
| `report.md` | **synthèse** : taille du corpus, nb de squelettes distincts, **couverture cumulée du top-N** (10/20/40/100/250/500/1000), top 40, et le mode d'emploi du GO/NO-GO |

### Stratégies d'échantillonnage du template

- **`representative`** (défaut) : titres régulièrement espacés dans le corpus → un
  échantillon **pondéré par la fréquence** (les squelettes communs apparaissent en
  proportion de leur poids). Métriques précision/rappel fidèles au monde réel.
- **`stratified`** : allocation **proportionnelle par squelette**, en round-robin
  (chaque squelette livre son 1ᵉʳ titre avant tout 2ᵉ) → garantit la **couverture
  de la traîne** qu'un échantillon représentatif raterait.

Les deux sont **déterministes** (aucun aléa) : re-lancer produit les mêmes fichiers.

## Décision GO/NO-GO (LLM) — se prend sur les chiffres, pas ici

L'outil **ne tranche pas**. La décision se lit sur l'export RÉEL :

1. Ouvrir `report.md` : regarder **combien de squelettes** couvrent ~85 % du corpus.
2. Ouvrir `samples.md` : vérifier que les positions `?` de ces squelettes de tête
   contiennent **réellement des noms d'artistes** (matière que C13.c extraira).
3. Remplir `label_template.csv` à la main (artiste(s) attendu(s) par titre), puis
   mesurer **précision/rappel** de l'extracteur déterministe C13.c contre ce jeu.
4. **Verdict** : petit top-N couvrant ~85 % avec des résidus artistes propres →
   **PAS de LLM**. Couverture qui plafonne vers ~60 % avec une longue traîne riche
   en artistes → un **LLM sur le résidu** (C13.d) devient intéressant.

La nécessité du LLM se décide sur CES chiffres, **pas a priori**.

## Tests & lint

```bash
pytest scripts/local/trackid_titles/ -q          # 24 tests, aucun réseau ni prod
ruff check scripts/local/trackid_titles/
```

Volontairement **hors `tests/`** : le CI ne doit pas dépendre de cet outillage
local. Les tests couvrent chaque type de brique (DATE/EP/FORMAT/DELIM sous toutes
leurs formes), l'assemblage du squelette (ordre quelconque, collapse), les cas
limites (titre vide, titre = pur bruit, titre = un seul nom), la lecture NDJSON/CSV,
les deux stratégies d'échantillonnage et les artefacts de bout en bout — sur des
titres **synthétiques** uniquement. **Aucun accès à trackid.net ni à la prod.**

Les artefacts de run (`data/`, exports, distributions, rapports) sont gitignorés.
