# Brief C2.d — Refonte barème similarité v2

## Contexte projet

Application web DJ — **Diggy** (`diggy-music.fr`).
Stack : FastAPI + SQLAlchemy async + PostgreSQL 16 + Vue.js 3.
Catalogue : ~7 400 tracks.

---

## Ce qui est déjà déployé (C2.b + C2.c)

Fichier principal : `server/api/services/similarity_service.py`

Le moteur actuel calcule :
```
score = Σ(w_i × sim_i)   pour chaque feature disponible
```

Features : `bpm` (0.25), `key` (0.20), `genre` (0.25), `label` (0.08), `era` (0.04), `cooc_playlist` (0.10), `cooc_set` (0.08).

- `sim_*` retournent toutes [0, 1]
- `sim_cooc` = Jaccard sur frozensets d'IDs
- candidats = union(fenêtre BPM ±16, tracks co-occurrentes)

---

## Problème avec le scoring actuel

La somme `Σ(w × sim)` avec poids fixes = 1.0 crée deux problèmes :

1. **BPM + Key parfaits = 0.45** — jamais 100%, semble arbitraire
2. **Co-occurrence Jaccard** — avec 27 sets seulement, 2 tracks dans 1 set commun donnent Jaccard = 1/1 = 1.0, ce qui est trompeur (ne distingue pas "1 set" de "6 sets")

---

## Nouveau système : barème à 4 segments (8 pts max)

Remplace le scoring linéaire par 4 barèmes additifs. Le score final = total / 8 → [0, 1].

### Barème 1 — Sets (3 pts max, priorité 1)
```
score_sets = 3.0 × (1 - e^(-K_SETS × n_sets_partagés))
K_SETS = 2.0
```
Signal le plus fort : un DJ les a mixées ensemble.
- n=1 → 2.59 pts (86%)
- n=2 → 2.95 pts (98%)
- n=6 → ~3.0 pts (100%)

### Barème 2 — Playlists (2 pts max, priorité 2)
```
score_playlists = 2.0 × (1 - e^(-K_PLAYLISTS × n_playlists_partagées))
K_PLAYLISTS = 0.8
```
- n=1 → 1.10 pts (55%)
- n=2 → 1.82 pts (91%)
- n=3 → ~2.0 pts (97%)

### Barème 3 — Style (2 pts max, priorité 2)
```
score_style = genre_jaccard × bpm_factor × 2.0

bpm_factor ∈ [BPM_FACTOR_FLOOR, 1.0]
BPM_FACTOR_FLOOR = 0.3

bpm_factor(a, b):
    raw = max(direct, half_time × 0.9, double_time × 0.9)
    où direct = max(0, 1 - |a-b| / 15)
    return 0.3 + 0.7 × raw
```
- Si BPM manquant : utiliser BPM_FACTOR_FLOOR (0.3) par défaut
- Si genre manquant : genre_jaccard = 0 → style = 0

### Barème 4 — Contexte (1 pt max, priorité 3)
```
score_context = 1.0 × (0.6 × label_match + 0.4 × era_sim)
```
- `label_match` = 1 si même label (case-insensitive), 0 sinon
- `era_sim` = 1 si diff ≤ 1 an, décroit linéairement jusqu'à 0 à 9 ans
- Plateau naturel : sans label commun → max 0.40 (era seule)

### Key
Conservée dans le code et les tests unitaires, mais **poids = 0 dans le scoring** (signal trop faible/redondant avec genre).

---

## Valeurs calibrées (notebook `docs/similarity_calibration.ipynb`)

Données réelles sur le catalogue complet :
- **17.2M paires** après pré-filtre BPM
- **1.2M paires** avec co-occurrence playlist (7%), médiane n=1, max=4
- **11.8K paires** avec co-occurrence set (0.07%), médiane n=1, max=6

Résultats section 9 du notebook :
```
SETS :       k=2.0  p90=2.594 pts (86% du plafond 3)  ← CIBLE ✓
PLAYLISTS :  k=0.8  p90=1.101 pts (55%)  — choix sémantique (n=2 → 91%)
STYLE :      p90=1.067 pts (53% du plafond 2)  — bonne discrimination
CONTEXTE :   p90=0.400 pts (40% du plafond 1)  — plateau era sans label
TOTAL :      81.9% des paires sous 10% de score
```

---

## Remplacement de min_score par TOP-N + plancher

Ancien : `min_score=0.4` (seuil fixe)
Nouveau :
- Calculer tous les scores
- Garder le top `top_n=20` (configurable, max 50)
- Appliquer un plancher `score_floor=0.10` (coupe le bruit pur)
- Le `limit` param de l'API reste pour paginer dans ces 20 résultats

---

## Fichiers à modifier

### 1. `server/api/services/similarity_service.py`

**a) Remplacer `SimilarityConfig`** :
```python
import math

@dataclass(frozen=True)
class SimilarityConfig:
    # BPM
    BPM_MAX_DIFF: float = 15.0
    HALF_DOUBLE_PENALTY: float = 0.9
    BPM_PREFILTER_WINDOW: float = 16.0
    BPM_FACTOR_FLOOR: float = 0.3
    # Era / Label
    ERA_MAX_DIFF: int = 9
    LABEL_MIN_TRACKS: int = 3
    # Barème caps (pts)
    CAP_SETS: float = 3.0
    CAP_PLAYLISTS: float = 2.0
    CAP_STYLE: float = 2.0
    CAP_CONTEXT: float = 1.0
    SCORE_TOTAL_CAP: float = 8.0
    # k asymptotiques (calibrés)
    K_SETS: float = 2.0
    K_PLAYLISTS: float = 0.8
    # Poids contexte
    W_LABEL: float = 0.6
    W_ERA: float = 0.4
    # Filtre résultats
    TOP_N: int = 20
    SCORE_FLOOR: float = 0.10
```

Supprimer : `MIN_FEATURES`, `COOC_MIN_SHARED`.
Supprimer : `DEFAULT_WEIGHTS` dict.

**b) Ajouter `import math`** en tête de fichier.

**c) Ajouter nouvelles fonctions de scoring** (après les fonctions `sim_*` existantes) :
```python
def bpm_factor(a: float, b: float) -> float:
    """BPM alignment factor ∈ [BPM_FACTOR_FLOOR, 1.0]."""
    def _raw(x: float, y: float) -> float:
        return max(0.0, 1.0 - abs(x - y) / CFG.BPM_MAX_DIFF)
    raw = max(
        _raw(a, b),
        _raw(a, b / 2.0) * CFG.HALF_DOUBLE_PENALTY,
        _raw(a, b * 2.0) * CFG.HALF_DOUBLE_PENALTY,
    )
    return CFG.BPM_FACTOR_FLOOR + (1.0 - CFG.BPM_FACTOR_FLOOR) * raw


def score_style(genre_jac: float, bpm_fac: float) -> float:
    return genre_jac * bpm_fac * CFG.CAP_STYLE


def score_context(label_sim: float, era_sim_val: float) -> float:
    return CFG.CAP_CONTEXT * (CFG.W_LABEL * label_sim + CFG.W_ERA * era_sim_val)


def score_cooc(n: int, k: float, cap: float) -> float:
    """Asymptotic barème: cap × (1 - e^(-k×n))."""
    if n <= 0:
        return 0.0
    return cap * (1.0 - math.exp(-k * n))
```

**d) Conserver les fonctions existantes** `sim_bpm`, `sim_key`, `sim_genre`, `sim_label`, `sim_era`, `sim_cooc` — elles sont importées et testées dans les tests unitaires. Ne pas les supprimer.

**e) Remplacer la signature de `get_similar_tracks()`** :
```python
async def get_similar_tracks(
    db: AsyncSession,
    catalog_id: int,
    user_id: int | None = None,
    *,
    limit: int = 10,
    top_n: int = CFG.TOP_N,
    score_floor: float = CFG.SCORE_FLOOR,
    in_lib: bool | None = None,
) -> list[dict]:
```
Supprimer tous les `w_*` params.

**f) Remplacer la boucle de scoring** (étape 4) :
```python
# 4. Score each candidate
scored: list[tuple[CatalogEntry, float, dict[str, float], list[str]]] = []

for cand in all_candidates:
    # Genre
    cand_genres = _expand_genre_nodes(cand.genres or [], name_to_node, parent_map)
    gj = sim_genre(ref_genres, cand_genres) if (ref_genres and cand_genres) else 0.0

    # BPM factor
    if ref.bpm is not None and cand.bpm is not None:
        bf = bpm_factor(ref.bpm, cand.bpm)
    else:
        bf = CFG.BPM_FACTOR_FLOOR

    # Style
    s_style = score_style(gj, bf)

    # Context
    cand_label = (cand.label or "").strip().lower()
    cand_label_valid = cand_label and label_counts.get(cand_label, 0) >= CFG.LABEL_MIN_TRACKS
    lm = sim_label(ref.label, cand.label) if (ref_label_valid and cand_label_valid) else 0.0
    es = sim_era(ref.release_date, cand.release_date) if (ref.release_date and cand.release_date) else 0.0
    s_context = score_context(lm, es)

    # Co-occurrence
    cand_playlists = playlist_map.get(cand.id, frozenset())
    n_pl = len(ref_playlists & cand_playlists)
    s_playlists = score_cooc(n_pl, CFG.K_PLAYLISTS, CFG.CAP_PLAYLISTS)

    cand_sets = set_map.get(cand.id, frozenset())
    n_st = len(ref_sets & cand_sets)
    s_sets = score_cooc(n_st, CFG.K_SETS, CFG.CAP_SETS)

    total_pts = s_sets + s_playlists + s_style + s_context
    score_pct = total_pts / CFG.SCORE_TOTAL_CAP

    if score_pct < score_floor:
        continue

    available = []
    components = {
        "sets": round(s_sets, 4),
        "playlists": round(s_playlists, 4),
        "style": round(s_style, 4),
        "context": round(s_context, 4),
    }
    if n_st > 0:
        available.append("sets")
    if n_pl > 0:
        available.append("playlists")
    if gj > 0:
        available.append("style")
    if lm > 0 or es > 0:
        available.append("context")

    scored.append((cand, score_pct, components, available))
```

**g) Remplacer le tri/limit** (étape 5) :
```python
# 5. Sort, top_n, then limit
scored.sort(key=lambda x: x[1], reverse=True)
top = scored[:top_n][:limit]
```

**h) Mettre à jour la construction de `SimilarityBlock`** dans l'étape 8 :
```python
"similarity": SimilarityBlock(
    score=round(score, 4),
    components=SimilarityComponents(
        sets=components["sets"],
        playlists=components["playlists"],
        style=components["style"],
        context=components["context"],
    ),
    available_features=available,
).model_dump(),
```

---

### 2. `server/api/schemas.py`

Remplacer `SimilarityComponents` (autour de la ligne 216) :
```python
class SimilarityComponents(BaseModel):
    sets: float = 0.0       # pts 0-3
    playlists: float = 0.0  # pts 0-2
    style: float = 0.0      # pts 0-2
    context: float = 0.0    # pts 0-1
```
`SimilarityBlock` ne change pas.

---

### 3. `server/api/routers/catalog.py`

Remplacer les query params de `GET /{catalog_id}/similar` :
```python
@router.get("/{catalog_id}/similar")
async def get_similar_tracks(
    catalog_id: int,
    limit: int = Query(10, ge=1, le=50),
    top_n: int = Query(20, ge=1, le=100),
    score_floor: float = Query(0.10, ge=0, le=1),
    in_lib: bool | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    try:
        return await similarity_service.get_similar_tracks(
            db, catalog_id, _uid(user),
            limit=limit, top_n=top_n,
            score_floor=score_floor, in_lib=in_lib,
        )
    except LookupError as e:
        raise HTTPException(404, str(e))
```

---

### 4. Tests — `tests/api/test_services/test_similarity_service.py`

**Ne rien supprimer** des tests existants (`TestSimBpm`, `TestSimKey`, `TestSimGenre`, `TestSimCooc`, etc.) — les fonctions `sim_*` sont conservées.

**Ajouter** une nouvelle classe :
```python
class TestBpmFactor:
    def test_identical(self):
        # BPMs identiques → factor = 1.0
        assert bpm_factor(128.0, 128.0) == 1.0

    def test_floor_at_max_diff(self):
        # Diff = 15 BPM → raw=0 → factor = BPM_FACTOR_FLOOR
        assert bpm_factor(128.0, 143.0) == CFG.BPM_FACTOR_FLOOR

    def test_beyond_max_diff(self):
        # Diff > 15 → clampé au floor
        assert bpm_factor(128.0, 160.0) == CFG.BPM_FACTOR_FLOOR

    def test_half_time_boosted(self):
        # 130 vs 65 → half-time avec pénalité 0.9
        f = bpm_factor(130.0, 65.0)
        assert f > CFG.BPM_FACTOR_FLOOR
        assert f < 1.0


class TestScoreCooc:
    def test_zero(self):
        assert score_cooc(0, 2.0, 3.0) == 0.0

    def test_one_set(self):
        # k=2.0, n=1, cap=3 → 3*(1-e^-2) ≈ 2.594
        s = score_cooc(1, 2.0, 3.0)
        assert abs(s - 2.594) < 0.01

    def test_approaches_cap(self):
        assert score_cooc(10, 2.0, 3.0) > 2.99

    def test_monotone(self):
        assert score_cooc(2, 0.8, 2.0) > score_cooc(1, 0.8, 2.0)
```

**Mettre à jour les imports** en tête du fichier de tests :
```python
from services.similarity_service import (
    CFG,
    _expand_genre_nodes,
    bpm_factor,
    parse_camelot,
    score_cooc,
    sim_bpm,
    sim_cooc,
    sim_era,
    sim_genre,
    sim_key,
    sim_label,
)
```

---

### 5. Tests intégration — `tests/api/test_catalog.py`

Dans `TestCatalogSimilar`, mettre à jour les tests qui passent des `w_*` params — ils n'existent plus.

Exemple : remplacer
```python
result = await similarity_service.get_similar_tracks(
    db, entries[0].id, min_score=0.0,
)
```
par
```python
result = await similarity_service.get_similar_tracks(
    db, entries[0].id, score_floor=0.0,
)
```

Vérifier que `test_similarity_block_structure` teste les nouveaux champs :
```python
sim = result[0]["similarity"]
assert "score" in sim
assert "components" in sim
assert "sets" in sim["components"]
assert "playlists" in sim["components"]
assert "style" in sim["components"]
assert "context" in sim["components"]
```

Les tests `test_cooc_playlist_signal` et `test_cooc_set_signal` restent valables — vérifier que `"playlists"` et `"sets"` sont dans `available_features` quand n > 0.

---

## Ce qui NE change PAS

- Aucune migration Alembic (pas de nouvelle table/colonne)
- Pas de changement Docker
- Pas de changement frontend (le debug JSON affiche déjà les components)
- Les fonctions `sim_bpm`, `sim_key`, `sim_genre`, `sim_label`, `sim_era`, `sim_cooc` restent dans le module et dans les tests
- La logique de candidats (union BPM + co-occurrence) reste identique
- Le loader `_load_label_counts` reste (utilisé pour `LABEL_MIN_TRACKS` validation)

---

## Workflow avant commit

```bash
# Backend
ruff check server/

# Tests
cd server && pytest tests/ --tb=short -q

# Frontend (pas de changement prévu)
cd server/frontend && npm run lint
```

Déploiement : push sur `master` → GitHub Actions → SSH → `docker compose up -d --build`.
