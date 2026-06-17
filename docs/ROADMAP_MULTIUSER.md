# Diggy — Roadmap Multi-User

> Document de référence pour la migration mono-user → multi-user.
> Chaque phase est incrémentale : l'app reste fonctionnelle à chaque étape.

---

## Vue d'ensemble

```
Phase 0  Résolution catalog_id (data cleanup)
   ↓
Phase 1  Table users + auth JWT
   ↓
Phase 2  catalog scope/origin + user_tracks + migration lib_tracks  ← CHEMIN CRITIQUE
   ↓
   ├── Phase 3  watched_entities + user_follows
   ├── Phase 4  user_radar_state (per-user discovery)
   └── Phase 5  radar_trends + user_collections
         ↓
      Phase 6  Enforcement auth + drop lib_tracks
         ↓
      Phase 7  Import multi-user
```

Les phases 3, 4, 5 peuvent être parallélisées après la phase 2.

---

## Phase 0 — Résolution des catalog_id manquants

**Objectif :** Tous les `lib_tracks` pointent vers une entrée `catalog` avant migration.

**Contexte :** Actuellement, seuls les tracks RB qui matchent un morceau déjà dans le catalog (via `normalized_key`) ont un `catalog_id`. Les autres (~74%) sont orphelins. La migration vers `user_tracks` exige que chaque track ait un `catalog_id`.

### Tâches

- [ ] Script batch `scripts/resolve_lib_catalog.py` :
  - Itérer tous les `lib_tracks WHERE catalog_id IS NULL`
  - Pour chaque track : tenter un match via `normalized_key` (déjà en place)
  - Si pas de match : recherche Deezer (titre + artiste) → créer entrée catalog si trouvé
  - Si toujours pas de match : créer entrée catalog `scope='private'` (track perso/introuvable)
- [ ] `pg_dump` complet avant toute modification structurelle
- [ ] Audit post-résolution : `SELECT count(*) FROM lib_tracks WHERE catalog_id IS NULL` → doit être **0**

### Checkpoint

```sql
-- Aucun orphelin restant
SELECT count(*) FROM lib_tracks WHERE catalog_id IS NULL;  -- → 0

-- Entrées private créées pour les tracks non matchés
SELECT count(*) FROM catalog WHERE scope = 'private';
```

---

## Phase 1 — Table `users` + Auth JWT

**Objectif :** Créer le système d'utilisateurs et l'authentification. Toutes les données existantes sont attribuées au user 1. L'auth reste optionnelle (soft mode) pendant cette phase.

### Migration Alembic `0004_users`

```sql
CREATE TABLE users (
    id            SERIAL PRIMARY KEY,
    email         VARCHAR(255) UNIQUE NOT NULL,
    username      VARCHAR(100) UNIQUE NOT NULL,
    hashed_password TEXT NOT NULL,
    is_active     BOOLEAN DEFAULT TRUE,
    settings      JSONB DEFAULT '{}',
    created_at    TIMESTAMPTZ DEFAULT now()
);

-- Seed user initial
INSERT INTO users (id, email, username, hashed_password, is_active)
VALUES (1, '<email>', 'willi', '<bcrypt_hash>', true);
```

### Stack auth

| Composant | Choix | Justification |
|-----------|-------|---------------|
| Hashing | `passlib[bcrypt]` | Standard, résistant |
| Tokens | `python-jose` (JWT HS256) | Simple, stateless, suffisant pour 1-5 users |
| Expiration | 24h, re-login pour refresh | Pas besoin de refresh token complexe pour l'instant |
| Transport | Header `Authorization: Bearer <token>` | Standard REST |

### Tâches

- [ ] **Alembic** : migration `0004_users`
- [ ] **Model** : `User` dans `models.py`
- [ ] **Backend** :
  - [ ] `server/api/auth.py` — JWT encode/decode, hash password, verify password
  - [ ] `server/api/routers/auth.py` — `POST /auth/register`, `POST /auth/login`, `GET /auth/me`
  - [ ] `server/api/dependencies.py` — `get_current_user` (obligatoire) + `get_current_user_optional` (soft mode)
- [ ] **Frontend** :
  - [ ] `src/stores/auth.js` — Pinia store (token, user, login/logout)
  - [ ] `src/views/LoginView.vue` — formulaire email + password
  - [ ] Intercepteur axios/fetch — ajouter le header `Authorization` automatiquement
- [ ] **Docker** : ajouter `JWT_SECRET` au `.env` du VPS

### Checkpoint

```bash
# Login fonctionne
curl -X POST /api/auth/login -d '{"email":"...","password":"..."}' → {"token":"eyJ..."}

# Me endpoint
curl -H "Authorization: Bearer eyJ..." /api/auth/me → {"id":1,"email":"..."}

# Tous les endpoints existants fonctionnent SANS token (soft mode)
curl /api/tracks/ → 200 OK
```

---

## Phase 2 — Catalog scope + `user_tracks` + Migration

**Objectif :** Enrichir `catalog` avec les dimensions multi-user (`scope`, `origin`, `owner_id`). Créer `user_tracks` pour remplacer `lib_tracks`. Migrer les données.

> **CHEMIN CRITIQUE** — cette phase est la plus risquée et la plus impactante.

### Migration Alembic `0005_catalog_scope_user_tracks`

**Partie A — Enrichir catalog :**

```sql
ALTER TABLE catalog ADD COLUMN scope VARCHAR(10) NOT NULL DEFAULT 'shared';
ALTER TABLE catalog ADD COLUMN owner_id INTEGER REFERENCES users(id) ON DELETE SET NULL;
ALTER TABLE catalog ADD COLUMN origin VARCHAR(50) NOT NULL DEFAULT 'deezer';
ALTER TABLE catalog ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'official';
ALTER TABLE catalog ADD COLUMN bpm_source VARCHAR(20);
ALTER TABLE catalog ADD COLUMN key_source VARCHAR(20);
ALTER TABLE catalog ADD COLUMN label VARCHAR(255);
ALTER TABLE catalog ADD COLUMN fingerprint VARCHAR UNIQUE;
ALTER TABLE catalog ADD COLUMN needs_reconciliation BOOLEAN DEFAULT FALSE;

-- Index pour filtrage scope
CREATE INDEX ix_catalog_scope ON catalog(scope);
CREATE INDEX ix_catalog_owner ON catalog(owner_id) WHERE owner_id IS NOT NULL;
```

**Partie B — Créer user_tracks :**

```sql
CREATE TABLE user_tracks (
    user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    catalog_id    INTEGER NOT NULL REFERENCES catalog(id) ON DELETE RESTRICT,
    rekordbox_id  INTEGER,
    date_added    TIMESTAMPTZ,
    source        VARCHAR(50) DEFAULT 'rekordbox_import',
    file_path     TEXT,
    rb_bpm        FLOAT,
    rb_key        VARCHAR(10),
    rb_mytags     JSONB DEFAULT '[]',
    rating        INTEGER,
    has_artwork   BOOLEAN DEFAULT FALSE,
    created_at    TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (user_id, catalog_id)
);

CREATE INDEX ix_user_tracks_catalog ON user_tracks(catalog_id);
CREATE INDEX ix_user_tracks_user_added ON user_tracks(user_id, date_added DESC);
```

**Partie C — Migration des données :**

```sql
-- lib_tracks → user_tracks pour user_id = 1
INSERT INTO user_tracks (
    user_id, catalog_id, rekordbox_id, date_added, source,
    file_path, rb_bpm, rb_key, rb_mytags, rating, has_artwork
)
SELECT
    1,
    catalog_id,
    id,              -- rekordbox_id
    date_added,
    'rekordbox_import',
    file_path,
    bpm,
    key,
    COALESCE(tags::jsonb, '[]'::jsonb),
    rating,
    has_artwork
FROM lib_tracks
WHERE catalog_id IS NOT NULL;  -- Tous après Phase 0
```

> **Note :** `lib_tracks` n'est PAS supprimée ici. Elle reste en lecture seule comme filet de sécurité jusqu'à la Phase 6.

### Tâches

- [ ] **Alembic** : migration `0005_catalog_scope_user_tracks`
- [ ] **Model** : `UserTrack` dans `models.py`, enrichir `CatalogEntry`
- [ ] **Refactor `routers/tracks.py`** :
  - [ ] Queries `lib_tracks` → `user_tracks JOIN catalog`
  - [ ] Filtrer par `current_user.id` (via `get_current_user_optional` en soft mode)
  - [ ] Endpoint bulk import → insère dans `user_tracks`
- [ ] **Refactor `routers/catalog.py`** :
  - [ ] Subquery `in_lib` : `user_tracks WHERE user_id = :uid` au lieu de `lib_tracks`
  - [ ] Filtrage scope : `WHERE scope = 'shared' OR owner_id = :uid`
  - [ ] Les jointures BPM/rating/tags/key viennent de `user_tracks`
- [ ] **Schemas** : adapter `TrackOut` pour exposer `rb_bpm`, `rb_key`, `rb_mytags`
- [ ] **Tests manuels** : vérifier que toutes les vues frontend affichent les mêmes données

### Checkpoint

```sql
-- Même nombre de tracks
SELECT count(*) FROM user_tracks WHERE user_id = 1;
-- Doit égaler :
SELECT count(*) FROM lib_tracks WHERE catalog_id IS NOT NULL;

-- Catalog enrichi
SELECT scope, count(*) FROM catalog GROUP BY scope;
-- → shared: ~3500+, private: ~100-200 (tracks perso)
```

```bash
# API renvoie les mêmes données
curl /api/tracks/ → même résultat qu'avant
curl /api/catalog/?in_lib=true → même résultat
```

---

## Phase 3 — `watched_entities` + `user_follows`

**Objectif :** Généraliser `watched_playlists` pour supporter artistes et labels. Ajouter des abonnements per-user.

### Migration Alembic `0006_watched_entities`

```sql
-- Renommer la table (instantané en PostgreSQL)
ALTER TABLE watched_playlists RENAME TO watched_entities;

-- Ajouter le type d'entité
ALTER TABLE watched_entities ADD COLUMN type VARCHAR(20) NOT NULL DEFAULT 'playlist';

-- Renommer la colonne dans radar_tracks
ALTER TABLE radar_tracks RENAME COLUMN watched_playlist_id TO watched_entity_id;

-- Table des suivis per-user
CREATE TABLE user_follows (
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    entity_id   INTEGER NOT NULL REFERENCES watched_entities(id) ON DELETE CASCADE,
    followed_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (user_id, entity_id)
);

CREATE INDEX ix_user_follows_entity ON user_follows(entity_id);

-- Migrer : toutes les entités existantes sont suivies par user 1
INSERT INTO user_follows (user_id, entity_id)
SELECT 1, id FROM watched_entities;
```

### Tâches

- [ ] **Alembic** : migration `0006_watched_entities`
- [ ] **Model** : renommer `WatchedPlaylist` → `WatchedEntity`, ajouter `type`. Créer `UserFollow`.
- [ ] **Refactor `routers/watchlist.py`** :
  - [ ] Lister uniquement les entités suivies par l'user courant
  - [ ] Follow/unfollow endpoints
- [ ] **Refactor `routers/radar.py`** : colonne `watched_playlist_id` → `watched_entity_id`
- [ ] **Celery `crawl_radar`** : adapter le nom de colonne
- [ ] **Frontend** : adapter les stores/composants qui référencent `watched_playlists`

### Checkpoint

```bash
# Watchlist renvoie les mêmes playlists
curl /api/watchlist/ → même résultat

# Crawl radar fonctionne
celery -A tasks call crawl_radar → pas d'erreur

# Radar affiche correctement
curl /api/radar/ → même résultat
```

---

## Phase 4 — `user_radar_state`

**Objectif :** Chaque user peut marquer les tracks radar comme `new` / `seen` / `added` / `ignored` indépendamment.

### Migration Alembic `0007_user_radar_state`

```sql
CREATE TABLE user_radar_state (
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    catalog_id      INTEGER NOT NULL REFERENCES catalog(id) ON DELETE CASCADE,
    status          VARCHAR(20) NOT NULL DEFAULT 'new',
    affinity_score  FLOAT,
    affinity_computed_at TIMESTAMPTZ,
    updated_at      TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (user_id, catalog_id)
);

CREATE INDEX ix_user_radar_state_status ON user_radar_state(user_id, status);

-- Seed : tous les catalog_id du radar → state='new' pour user 1
INSERT INTO user_radar_state (user_id, catalog_id, status)
SELECT DISTINCT 1, catalog_id, 'new'
FROM radar_tracks
WHERE catalog_id IS NOT NULL
ON CONFLICT DO NOTHING;
```

### Tâches

- [ ] **Alembic** : migration `0007_user_radar_state`
- [ ] **Model** : `UserRadarState` dans `models.py`
- [ ] **API** :
  - [ ] `PATCH /api/radar/{catalog_id}/state` — changer le statut pour l'user courant
  - [ ] `GET /api/radar/` — inclure le `status` per-user (JOIN `user_radar_state`)
- [ ] **Frontend RadarView** :
  - [ ] Tabs de filtrage : New / Seen / Added / Ignored
  - [ ] Boutons d'action pour changer le statut
  - [ ] Badge compteur "new" dans la sidebar

### Checkpoint

```sql
-- Tous les radar tracks résolus ont un state pour user 1
SELECT count(*) FROM user_radar_state WHERE user_id = 1;  -- > 0

-- Changement de state persiste
UPDATE user_radar_state SET status = 'seen' WHERE user_id = 1 AND catalog_id = 42;
```

---

## Phase 5 — `radar_trends` + `user_collections`

**Objectif :** Score TENDANCE global (recalculé par Celery) et collections perso (playlists/catégories).

### Migration Alembic `0008_trends_collections`

```sql
-- Score tendance global
CREATE TABLE radar_trends (
    catalog_id       INTEGER PRIMARY KEY REFERENCES catalog(id) ON DELETE CASCADE,
    trend_score      FLOAT NOT NULL DEFAULT 0,
    window_days      INTEGER DEFAULT 30,
    detection_count  INTEGER DEFAULT 0,
    computed_at      TIMESTAMPTZ DEFAULT now()
);

-- Collections perso
CREATE TABLE user_collections (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name        VARCHAR(255) NOT NULL,
    type        VARCHAR(20) DEFAULT 'playlist',
    created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE collection_items (
    collection_id INTEGER NOT NULL REFERENCES user_collections(id) ON DELETE CASCADE,
    catalog_id    INTEGER NOT NULL REFERENCES catalog(id) ON DELETE CASCADE,
    position      INTEGER DEFAULT 0,
    added_at      TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (collection_id, catalog_id)
);

CREATE INDEX ix_user_collections_user ON user_collections(user_id);
```

### Tâches

- [ ] **Alembic** : migration `0008_trends_collections`
- [ ] **Models** : `RadarTrend`, `UserCollection`, `CollectionItem`
- [ ] **Celery task `compute_trends`** :
  - [ ] Agrégation par `catalog_id` : nombre de playlists radar distinctes, récence de détection
  - [ ] Décroissance temporelle (half-life ~14 jours)
  - [ ] Cron quotidien (Celery Beat)
- [ ] **API Collections** :
  - [ ] `GET /api/collections/` — lister les collections de l'user
  - [ ] `POST /api/collections/` — créer une collection
  - [ ] `POST /api/collections/{id}/items` — ajouter un track
  - [ ] `DELETE /api/collections/{id}/items/{catalog_id}` — retirer
- [ ] **Frontend** :
  - [ ] Score tendance affiché sur les tracks radar
  - [ ] CollectionsView (liste + détail)
  - [ ] Modal "Ajouter à une collection" depuis n'importe quelle vue track

### Checkpoint

```sql
SELECT count(*) FROM radar_trends;  -- > 0 après premier compute
SELECT * FROM user_collections WHERE user_id = 1;
```

---

## Phase 6 — Enforcement auth + Cleanup

**Objectif :** Rendre l'auth obligatoire. Supprimer `lib_tracks`. Finaliser la sécurité.

### Migration Alembic `0009_drop_lib_tracks`

```sql
DROP TABLE lib_tracks;
```

### Tâches

- [ ] **Supprimer `LibTrack`** du `models.py` et toutes les références
- [ ] **Middleware auth obligatoire** : tous les endpoints sauf `/api/auth/*` et `/api/health` requièrent un JWT valide
- [ ] **CORS** : restreindre `allow_origins` au domaine frontend réel
- [ ] **Frontend** :
  - [ ] Router guard : redirection `/login` si pas de token
  - [ ] Bouton logout dans la sidebar
  - [ ] Gestion du 401 (redirect login + clear token)
- [ ] **Nginx** : ajouter headers de sécurité (`X-Content-Type-Options`, `X-Frame-Options`)
- [ ] **Import script `main.py`** : adapter pour utiliser un token JWT et `user_tracks`

### Checkpoint

```bash
# Sans token → 401
curl /api/tracks/ → 401 Unauthorized

# Avec token → 200
curl -H "Authorization: Bearer eyJ..." /api/tracks/ → 200

# lib_tracks n'existe plus
psql -c "\dt lib_tracks" → Did not find any relation

# Login + navigation complète fonctionne dans le frontend
```

---

## Phase 7 — Import multi-user

**Objectif :** Tout utilisateur authentifié peut importer sa bibliothèque Rekordbox.

### Tâches

- [ ] **Endpoint `POST /api/import/rekordbox`** :
  - [ ] Accepte le même payload bulk que l'ancien `/api/tracks/bulk`
  - [ ] Scoped à `current_user.id`
  - [ ] Résolution catalog : match `normalized_key` → Deezer search → création `private`
  - [ ] Insertion dans `user_tracks`
  - [ ] Upload artworks dans MinIO (clé = `{catalog_id}.jpg`)
- [ ] **Script `main.py` client** :
  - [ ] Accepte `--user-token` ou `--email`/`--password` pour s'authentifier
  - [ ] Envoie les batches vers le nouvel endpoint
- [ ] **Gestion des entrées `private`** :
  - [ ] Nouveau track non matchable → `catalog` avec `scope='private', owner_id=uid`
  - [ ] Si un autre user importe le même track → réconciliation possible (`needs_reconciliation = true`)
- [ ] **Promotion `private → shared`** :
  - [ ] Si match ISRC confirmé sur une entrée `private` → promouvoir en `shared` + `owner_id = NULL`
  - [ ] Repointer les `user_tracks` des autres users si applicable

### Checkpoint

```bash
# User 2 s'inscrit et importe
curl -X POST /api/auth/register -d '{"email":"user2@test.com","username":"user2","password":"..."}'
# Login
curl -X POST /api/auth/login -d '...' → token2

# Import fonctionne pour user 2
python main.py --user-token $token2

# User 2 a ses propres tracks
curl -H "Authorization: Bearer $token2" /api/tracks/ → tracks de user 2
# User 1 n'est pas affecté
curl -H "Authorization: Bearer $token1" /api/tracks/ → tracks de user 1
```

---

## Risques et mitigations

| Risque | Impact | Mitigation |
|--------|--------|------------|
| Perte de données migration lib_tracks | Critique | `pg_dump` avant Phase 2. `lib_tracks` conservée jusqu'à Phase 6. |
| Queries cassées pendant transition | Élevé | Refactor router par router, tester chacun. Garder les deux tables en parallèle. |
| Doublons catalog (private vs shared) | Moyen | `normalized_key` UNIQUE pour shared. Private peut avoir le même `normalized_key` (filtré par scope). |
| JWT secret compromis | Élevé | Stocké uniquement dans `.env` VPS, jamais dans git. Rotation = changer la variable. |
| Régression frontend | Moyen | QA manuelle complète après chaque phase (catalog list, detail, radar, player). |
| Celery tasks cassées après rename | Moyen | Mettre à jour imports et noms de colonnes dans le même commit que la migration. |
| Performance queries multi-user | Faible | Index partiels sur `scope`, `owner_id`. Monitor avec `EXPLAIN ANALYZE`. |

---

## Index strategy résumé

| Table | Index | Usage |
|-------|-------|-------|
| `user_tracks` | PK `(user_id, catalog_id)` | Lookup direct |
| `user_tracks` | `(catalog_id)` | "Qui possède ce track ?" |
| `user_tracks` | `(user_id, date_added DESC)` | Tri chronologique lib |
| `catalog` | `(scope)` | Filtrage shared/private |
| `catalog` | `(owner_id) WHERE owner_id IS NOT NULL` | Tracks privés d'un user |
| `catalog` | `(normalized_key)` UNIQUE | Dédup |
| `user_radar_state` | PK `(user_id, catalog_id)` | Lookup direct |
| `user_radar_state` | `(user_id, status)` | "Mes nouveautés non vues" |
| `user_follows` | PK `(user_id, entity_id)` | Lookup direct |
| `user_follows` | `(entity_id)` | "Qui suit cette entité ?" |
| `radar_tracks` | `(detected_at DESC)` | Tendances récentes |

---

## Décisions techniques verrouillées

1. **JWT manuel** (pas fastapi-users) — plus simple, contrôle total, peu d'users
2. **PK composite `(user_id, catalog_id)`** sur `user_tracks` — naturelle, performante
3. **`lib_tracks` conservée jusqu'à Phase 6** — rollback possible, zero downtime
4. **`scope` sur catalog** (pas table séparée) — un seul enum `shared|private`, simple
5. **`ON DELETE RESTRICT`** sur `user_tracks.catalog_id` — empêche de supprimer un catalog possédé
6. **Rekordbox = lecture seule** — jamais de write-back, plus de worker d'écriture

---

## Fichiers clés à modifier

| Fichier | Phases | Nature des changements |
|---------|--------|----------------------|
| `server/api/models.py` | 1-7 | Ajout User, UserTrack, UserFollow, UserRadarState ; enrichir CatalogEntry ; supprimer LibTrack (P6) |
| `server/api/routers/tracks.py` | 2, 6, 7 | Rewrite queries lib_tracks → user_tracks + catalog |
| `server/api/routers/catalog.py` | 2 | Subqueries in_lib, scope filtering, jointures user_tracks |
| `server/api/routers/radar.py` | 3, 4 | Rename FK, ajout state per-user |
| `server/api/routers/watchlist.py` | 3 | Rename → entities, follow/unfollow |
| `server/api/auth.py` | 1 | Nouveau fichier — JWT + hashing |
| `server/api/routers/auth.py` | 1 | Nouveau fichier — register/login/me |
| `server/api/dependencies.py` | 1 | Nouveau fichier — get_current_user |
| `server/workers/tasks.py` | 3, 5 | Adapter crawl_radar, ajouter compute_trends |
| `main.py` | 6, 7 | Adapter import pour auth + user_tracks |
| `src/stores/auth.js` | 1 | Nouveau fichier — Pinia auth store |
| `src/views/LoginView.vue` | 1 | Nouveau fichier — formulaire login |
| `src/router.js` | 1, 6 | Route /login, guards auth |
