# C1.a+b — Moteur de Trend v2 (formule + velocite + API)

Tu dois refondre le calcul de tendance radar de Diggy : nouvelle formule ponderee, velocite, rang par famille de genre, et exposition API.

Lis `CLAUDE.md` a la racine pour les conventions du projet.

---

## Contexte

### Formule actuelle (`server/workers/tasks/trends.py`)

```python
Score = SUM(0.5^(age_days/14)) * COUNT(DISTINCT playlists)
```

Problemes :
- Ignore le type de source (set DJ vs playlist)
- Ignore la taille de la playlist (une detection dans une playlist de 50 tracks vaut autant qu'une de 5000)
- Pas de convergence multi-sources (detectee sur Deezer + TIDAL + Spotify devrait scorer plus)
- Pas de calcul par famille de genre (biais de surveillance : plus de playlists House → les tracks House scorent plus)
- Pas de velocite (acceleration recente)
- Sortie en score brut, pas en rang

### Donnees disponibles

- `radar_tracks` (~5000 rows) : `catalog_id`, `watched_entity_id`, `source`, `detected_at`, `removed_at`, `is_initial_detection`
- `watched_entities` (~29 rows) : `source`, `type` (playlist/set), `track_count`
- `catalog` : `genres` (ARRAY text)
- `radar_trends` : table existante (PK: `catalog_id`, colonnes: `trend_score`, `detection_count`, `window_days`, `computed_at`)

### Table RadarTrend actuelle (`models.py:495`)

```python
class RadarTrend(Base):
    __tablename__ = "radar_trends"
    catalog_id = Column(Integer, ForeignKey("catalog.id", ondelete="CASCADE"), primary_key=True)
    trend_score = Column(Float, nullable=False, server_default="0", default=0)
    window_days = Column(Integer, server_default="30", default=30)
    detection_count = Column(Integer, server_default="0", default=0)
    computed_at = Column(DateTime(timezone=True))
```

---

## Tache 1 : Migration — enrichir RadarTrend

**Fichier** : creer `server/api/alembic/versions/0027_trend_v2.py`

Ajouter les colonnes sur `radar_trends` :

```python
op.add_column("radar_trends", sa.Column("family", sa.String(50), nullable=True))
op.add_column("radar_trends", sa.Column("rank_in_family", sa.Integer, nullable=True))
op.add_column("radar_trends", sa.Column("rank_global", sa.Integer, nullable=True))
op.add_column("radar_trends", sa.Column("velocity", sa.Float, nullable=True))
op.add_column("radar_trends", sa.Column("source_count", sa.Integer, nullable=True))
```

Mettre a jour le modele `RadarTrend` dans `models.py` en coherence.

---

## Tache 2 : Nouvelle formule dans compute_trends

**Fichier** : `server/workers/tasks/trends.py`

### Formule v2

Pour chaque `catalog_id` :

```
base_score = SUM(
    decay(age_days) * source_weight(type) * size_weight(track_count)
)

velocity = ratio(detections_7j_recents / detections_7j_precedents)

convergence_bonus = 1 + 0.3 * (nombre_sources_distinctes - 1)

final_score = base_score * convergence_bonus * (1 + 0.5 * velocity)
```

### Ponderations

**Decay temporel** (conserve, half-life 14 jours) :
```
decay(age) = 0.5 ^ (age_days / 14)
```

**Ponderation type de source** :
```python
SOURCE_WEIGHT = {
    "set": 3.0,           # detection dans un set DJ (tracklist)
    "deezer": 1.0,        # playlist Deezer
    "tidal": 1.0,         # playlist TIDAL
    "spotify": 1.0,       # playlist Spotify
}
```
Le type de source vient de `watched_entities.type` : si `type = 'set'` (tracklist DJ), poids 3x. Sinon, poids 1x.

**Ponderation taille playlist** :
```
size_weight = 1 / sqrt(track_count)
```
Une playlist de 25 tracks donne un poids 4x plus eleve qu'une playlist de 400 tracks. Utiliser `sqrt` pour adoucir (pas l'inverse lineaire qui serait trop agressif).

**Convergence multi-sources** :
Compter le nombre de **plateformes distinctes** (`radar_tracks.source`) pour chaque `catalog_id`. Si une track est detectee sur Deezer ET TIDAL : bonus 1.3x. Sur 3 plateformes : bonus 1.6x.

**Velocite** (C1.b) :
```
recent = COUNT detections dans les 7 derniers jours (excluant is_initial_detection)
previous = COUNT detections dans les 7 jours d'avant (J-14 a J-7)
velocity = recent / MAX(previous, 1) - 1    (0 = stable, >0 = acceleration)
```
Clamper velocity entre 0 et 5 (eviter les explosions sur des tracks qui passent de 0 a N).

**Exclusion premier crawl** : filtrer `WHERE is_initial_detection = false` pour le calcul de velocite (C0.1 a mis ce flag en place).

### Calcul par famille de genre

Chaque track a un champ `genres` (ARRAY text) dans `catalog`. Il faut determiner la **famille** (pillar) de chaque track pour calculer le rang par famille.

Approche :
1. Joindre `catalog.genres` dans la requete
2. Pour chaque track, utiliser le premier genre et le mapper a sa famille via la taxonomie (table `genre_nodes` → racine → pillar)
3. Stocker la `family` dans `radar_trends`
4. Calculer `rank_in_family` = rang par score decroissant au sein de chaque famille
5. Calculer `rank_global` = rang global tous genres confondus

**Mapping famille** : la logique existe deja dans `server/api/services/genre_service.py` (fonction `genre_pillar`). Mais le worker est sync et n'a pas acces au service async. Deux options :
- **Option A (recommandee)** : requeter `genre_nodes` et `genre_edges` directement en SQL sync pour construire le mapping genre → pillar dans le worker
- **Option B** : hardcoder un mapping statique des 6 familles (House, Techno, Trance, D&B, Hardcore, Hard Dance, Autre) — moins maintenable mais plus simple

### Implementation SQL

La requete peut etre faite en une seule passe SQL avec des CTE :

```sql
WITH detections AS (
    SELECT
        rt.catalog_id,
        rt.watched_entity_id,
        rt.source,
        rt.detected_at,
        rt.is_initial_detection,
        we.type AS entity_type,
        we.track_count,
        c.genres
    FROM radar_tracks rt
    JOIN watched_entities we ON we.id = rt.watched_entity_id
    JOIN catalog c ON c.id = rt.catalog_id
    WHERE rt.catalog_id IS NOT NULL
      AND rt.detected_at >= NOW() - INTERVAL '30 days'
      AND rt.removed_at IS NULL
),
scores AS (
    SELECT
        catalog_id,
        genres,
        COUNT(DISTINCT source) AS source_count,
        SUM(
            POWER(0.5, EXTRACT(EPOCH FROM (NOW() - detected_at)) / 86400.0 / 14.0)
            * CASE WHEN entity_type = 'set' THEN 3.0 ELSE 1.0 END
            * (1.0 / SQRT(GREATEST(track_count, 1)))
        ) AS base_score,
        COUNT(DISTINCT watched_entity_id) AS detection_count
    FROM detections
    GROUP BY catalog_id, genres
),
velocity AS (
    SELECT
        catalog_id,
        COUNT(*) FILTER (WHERE detected_at >= NOW() - INTERVAL '7 days' AND NOT is_initial_detection) AS recent,
        COUNT(*) FILTER (WHERE detected_at >= NOW() - INTERVAL '14 days' AND detected_at < NOW() - INTERVAL '7 days' AND NOT is_initial_detection) AS previous
    FROM detections
    GROUP BY catalog_id
)
SELECT
    s.catalog_id,
    s.genres,
    s.detection_count,
    s.source_count,
    s.base_score * (1 + 0.3 * (s.source_count - 1)) * (1 + 0.5 * LEAST(GREATEST(v.recent::float / GREATEST(v.previous, 1) - 1, 0), 5)) AS trend_score,
    LEAST(GREATEST(v.recent::float / GREATEST(v.previous, 1) - 1, 0), 5) AS velocity
FROM scores s
LEFT JOIN velocity v ON v.catalog_id = s.catalog_id
```

Ensuite en Python : assigner la `family` a chaque track (via le mapping genre → pillar), calculer les rangs, et UPSERT.

### UPSERT enrichi

Le UPSERT existant doit etre etendu pour stocker les nouvelles colonnes :

```python
values = [
    {
        "catalog_id": r.catalog_id,
        "trend_score": round(r.trend_score, 4),
        "window_days": window_days,
        "detection_count": r.detection_count,
        "source_count": r.source_count,
        "velocity": round(r.velocity or 0, 4),
        "family": family,
        "rank_in_family": rank,
        "rank_global": global_rank,
        "computed_at": now,
    }
    for ...
]
```

---

## Tache 3 : Exposer le rang par famille dans l'API

**Fichier** : `server/api/services/radar_service.py`

Le `RadarFullOut` schema (`schemas.py:120`) a deja `trend_score`. Ajouter :

```python
# Dans schemas.py, classe RadarFullOut
trend_rank: Optional[int] = None       # rang global
trend_family: Optional[str] = None     # famille (House, Techno, etc.)
trend_rank_family: Optional[int] = None # rang dans la famille
velocity: Optional[float] = None       # acceleration
source_count: Optional[int] = None     # nb plateformes distinctes
```

Dans `radar_service.py`, la jointure avec `RadarTrend` existe deja (alias `rt`). Ajouter les colonnes dans le SELECT :

```python
rt.rank_global.label("trend_rank"),
rt.family.label("trend_family"),
rt.rank_in_family.label("trend_rank_family"),
rt.velocity.label("velocity"),
rt.source_count.label("source_count"),
```

### Nouvel endpoint : top trends par famille

Ajouter dans `server/api/routers/radar.py` :

```python
@router.get("/trends")
async def list_trends(
    family: str | None = Query(None, max_length=50),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Top trending tracks, optionally filtered by genre family."""
    return await radar_service.list_trends(db, user.id, family=family, limit=limit)
```

Implementer `radar_service.list_trends()` : query `radar_trends` ordonne par `rank_in_family` (si family filtre) ou `rank_global`, jointure avec `catalog` pour les infos track, jointure avec `user_tracks` pour `in_lib`.

---

## Tache 4 : Tests

Ajouter dans `tests/worker/` un fichier `test_trends_v2.py` :

- `test_source_weight` : verifier que les detections set DJ pesent 3x plus
- `test_size_weight` : verifier que les petites playlists pesent plus
- `test_convergence_bonus` : verifier le bonus multi-sources
- `test_velocity_calculation` : verifier le ratio recent/previous
- `test_initial_detection_excluded_from_velocity` : verifier que `is_initial_detection=True` est exclu
- `test_rank_by_family` : verifier que les rangs sont calcules par famille
- `test_removed_tracks_excluded` : verifier que `removed_at IS NOT NULL` est exclu

Ces tests peuvent mocker la DB ou utiliser le conftest PostgreSQL existant.

---

## Points d'attention

- **Performance** : la requete SQL avec CTE sur 5000 rows + 29 playlists est rapide. Pas de souci.
- **`removed_at`** : exclure les tracks retirees des playlists (`removed_at IS NOT NULL`) du calcul de score. Elles ne sont plus dans la playlist → ne doivent plus contribuer.
- **Genres null** : certaines tracks n'ont pas de genres. Leur `family` sera `null` → elles sont comptees dans le rang global mais pas dans un rang par famille.
- **Celery schedule** : ne pas modifier. `compute_trends` tourne deja a 7h chaque jour.
- **Backward compat** : le champ `trend_score` existant reste, il est juste recalcule avec la nouvelle formule. L'API `/api/radar/full?sort=trend_score` continue de fonctionner.

---

## Definition of Done

```bash
# Migration 0027 appliquee (nouvelles colonnes sur radar_trends)
# compute_trends utilise la formule v2 (ponderations + velocite + convergence)
# radar_trends contient family, rank_in_family, rank_global, velocity, source_count
# GET /api/radar/trends?family=House&limit=20 retourne le top par famille
# GET /api/radar/full inclut trend_rank, trend_family, velocity
# Tests passent
# Lint OK : ruff check server/ && cd server/frontend && npm run lint
```

## Commit

```
feat(api): trend v2 — weighted formula, velocity, rank by genre family (C1.a+b)
```

Ne pousse PAS sur master — je review avant.
