# Diggy - Database Schema

> PostgreSQL 16 | SQLAlchemy async | Alembic migrations (rev 0002)

## Vue d'ensemble

```
                        +-----------+
                        |  catalog  |  <-- Hub central
                        +-----------+
                       ^   ^   ^   |
                      /    |    \  +---> catalog_genres ---> genres
                     /     |     \                           ^  ^
              +----------+ | +----------+                    |  |
              |lib_tracks| | |set_tracks|            artist_genres
              +----------+ | +----------+                    |
                           |       |                         |
                    +-------------+|                     +--------+
                    |radar_tracks | |                     |artists |
                    +-------------+ |                     +--------+
                           |        v                        |  |
                           v     +------+         set_artists   |
                  +------------------+  |              |   artist_aliases
                  |watched_playlists |  +---> set_genres
                  +------------------+
```

14 tables : 9 models + 3 tables d'association pures + alembic_version

---

## Changements migration 0002

- Toutes les colonnes timestamp sont en **TIMESTAMPTZ** (UTC)
- FK `catalog_id` sur lib_tracks, radar_tracks, set_tracks : **ON DELETE SET NULL**
- FK `genres.parent_id` : **ON DELETE SET NULL**
- Index `ix_set_genres_genre_id`, `ix_artist_genres_genre_id`, `ix_catalog_genres_genre_id`
- Nouvelle table `catalog_genres` (association catalog <-> genres)

---

## Tables principales

### `catalog` -- Hub central, referentiel unique de tout morceau connu

| Colonne | Type | Contraintes | Description |
|---|---|---|---|
| `id` | Integer | PK, auto-increment | ID interne |
| `title` | String(500) | NOT NULL | Titre du morceau |
| `artist` | String(500) | nullable | Artiste (texte brut) |
| `normalized_key` | String(500) | UNIQUE, NOT NULL | Cle de dedup `artist\|title` normalise |
| `isrc` | String(20) | UNIQUE, nullable | Code ISRC (identifiant international) |
| `deezer_id` | String(64) | nullable | ID Deezer pour fetch preview |
| `bpm` | Float | nullable | BPM |
| `key` | String(10) | nullable | Tonalite musicale |
| `duration_ms` | Integer | nullable | Duree en millisecondes |
| `genre` | String(100) | nullable | Genre principal (texte brut, conserve pour affichage) |
| `release_date` | Date | nullable | Date de sortie |
| `preview_url` | Text | nullable | URL preview Deezer (expirante) |
| `has_artwork` | Boolean | default false | Cover dans MinIO `catalog-artworks` |
| `has_preview` | Boolean | default false | Preview Deezer dispo (verifie hebdo) |
| `created_at` | TIMESTAMPTZ | nullable | Date de creation (UTC) |

**Relations** : `catalog.genres` via `catalog_genres` (many-to-many avec `genres`)

**Role** : Point de convergence unique. Tout morceau (lib, radar, set) pointe ici via `catalog_id`. Dedup via `normalized_key` ou `isrc`.

---

### `lib_tracks` -- Bibliotheque Rekordbox active

| Colonne | Type | Contraintes | Description |
|---|---|---|---|
| `id` | Integer | PK (= rekordbox_id) | ID Rekordbox, pas auto-increment |
| `title` | String(255) | nullable | Titre |
| `artist` | String(255) | nullable | Artiste |
| `bpm` | Float | nullable | BPM |
| `key` | String(10) | nullable | Tonalite |
| `duration` | Integer | nullable | Duree en ms |
| `rating` | Integer | nullable | Note Rekordbox (0-5) |
| `file_path` | Text | nullable | Chemin fichier local |
| `date_added` | TIMESTAMPTZ | nullable | Date d'ajout dans RB (UTC) |
| `tags` | Text | nullable | JSON array de styles `["Tech House", "TO_CUE"]` |
| `has_artwork` | Boolean | default false | Artwork dans MinIO `artworks` |
| `catalog_id` | Integer | FK -> catalog.id (SET NULL), nullable | Lien vers le catalog |

**Role** : Miroir de la collection Rekordbox. Import via `main.py`. ~625 tracks.

---

### `watched_playlists` -- Playlists Deezer surveillees

| Colonne | Type | Contraintes | Description |
|---|---|---|---|
| `id` | Integer | PK, auto-increment | ID interne |
| `external_id` | String(64) | UNIQUE, NOT NULL | ID Deezer de la playlist |
| `source` | String(64) | NOT NULL | Source (`"deezer"`) |
| `title` | String(255) | nullable | Nom de la playlist |
| `description` | Text | nullable | Description |
| `created_at` | TIMESTAMPTZ | nullable | Date d'ajout dans Diggy (UTC) |
| `last_crawled_at` | TIMESTAMPTZ | nullable | Dernier crawl reussi (UTC) |
| `has_artwork` | Boolean | default false | Cover dans MinIO |
| `track_count` | Integer | nullable | Nombre de tracks |
| `owner` | String(255) | nullable | Proprietaire de la playlist |

**Role** : Playlists surveillees. Celery `crawl_radar` (cron 8h) les parcourt quotidiennement.

---

### `radar_tracks` -- Morceaux decouverts par le radar Deezer

| Colonne | Type | Contraintes | Description |
|---|---|---|---|
| `id` | Integer | PK, auto-increment | ID interne |
| `watched_playlist_id` | Integer | FK -> watched_playlists.id, NOT NULL | Playlist source |
| `external_track_id` | String(255) | NOT NULL | ID Deezer du morceau |
| `source` | String(50) | NOT NULL | Source (`"deezer"`) |
| `title` | String(500) | NOT NULL | Titre (texte brut) |
| `artist` | String(500) | nullable | Artiste (texte brut) |
| `isrc` | String(20) | nullable | Code ISRC |
| `detected_at` | TIMESTAMPTZ | nullable | Date de premiere detection (UTC) |
| `catalog_id` | Integer | FK -> catalog.id (SET NULL), nullable | Resolu apres matching |

**Contrainte unique** : `(watched_playlist_id, external_track_id)`

**Role** : Chaque morceau trouve dans une playlist surveillee. ~4465 entrees.

---

## Tables Sets / DJ

### `sets` -- Sets DJ (tracklists)

| Colonne | Type | Contraintes | Description |
|---|---|---|---|
| `id` | Integer | PK, auto-increment | ID interne |
| `external_id` | String(64) | nullable | ID source (trackid.net, 1001tracklists...) |
| `source` | String(64) | NOT NULL | `"trackid"`, `"1001tracklists"`, `"manual"`... |
| `source_url` | Text | nullable | URL de la source |
| `title` | String(500) | NOT NULL | Nom du set |
| `event` | String(255) | nullable | Festival, club, Boiler Room... |
| `venue` | String(255) | nullable | Lieu |
| `played_date` | Date | nullable | Date de performance |
| `duration_ms` | Integer | nullable | Duree totale en ms |
| `description` | Text | nullable | Description |
| `has_artwork` | Boolean | default false | Cover dans MinIO `set-artworks` |
| `created_at` | TIMESTAMPTZ | nullable | Date de creation (UTC) |
| `last_crawled_at` | TIMESTAMPTZ | nullable | Dernier crawl (UTC) |

**Contrainte unique** : `(external_id, source)` -- supporte plusieurs sources sans collision

**Role** : Sets DJ avec tracklists. Source de decouverte comme le radar.

---

### `set_tracks` -- Tracklist d'un set

| Colonne | Type | Contraintes | Description |
|---|---|---|---|
| `id` | Integer | PK, auto-increment | ID interne |
| `set_id` | Integer | FK -> sets.id (CASCADE), NOT NULL, index | Set parent |
| `catalog_id` | Integer | FK -> catalog.id (SET NULL), nullable, index | Resolu apres matching |
| `position` | Integer | NOT NULL | Ordre dans la tracklist |
| `timecode_ms` | Integer | nullable | Position dans le set (ms) |
| `raw_title` | String(500) | nullable | Titre tel que scrape |
| `raw_artist` | String(500) | nullable | Artiste tel que scrape |
| `is_id` | Boolean | default false | Morceau non identifie ("ID - ID") |

**Contrainte unique** : `(set_id, position)`

**Role** : Meme philosophie que `radar_tracks` : texte brut + `catalog_id` resolu dans un second temps. Les `is_id = true` restent sans `catalog_id`.

---

### `set_artists` -- Artistes d'un set (gere B2B)

| Colonne | Type | Contraintes | Description |
|---|---|---|---|
| `set_id` | Integer | FK -> sets.id (CASCADE), PK | Set |
| `artist_id` | Integer | FK -> artists.id (CASCADE), PK, index | Artiste |
| `role` | String(32) | nullable | `"main"`, `"b2b"` |
| `position` | Integer | nullable | Ordre de billing |

**Role** : Many-to-many avec attributs. Un set peut avoir plusieurs artistes (B2B).

---

## Tables Artists

### `artists` -- Referentiel artistes

| Colonne | Type | Contraintes | Description |
|---|---|---|---|
| `id` | Integer | PK, auto-increment | ID interne |
| `name` | String(500) | NOT NULL | Nom d'artiste |
| `normalized_name` | String(500) | UNIQUE, NOT NULL | Cle de dedup |
| `real_name` | String(255) | nullable | Nom reel |
| `country` | String(2) | nullable | Code ISO 2 lettres |
| `deezer_id` | String(64) | nullable | ID Deezer |
| `soundcloud_id` | String(64) | nullable | ID SoundCloud |
| `trackid_id` | String(64) | nullable | ID TrackID.net |
| `bio` | Text | nullable | Biographie |
| `has_artwork` | Boolean | default false | Photo dans MinIO `artist-artworks` |
| `created_at` | TIMESTAMPTZ | nullable | Date de creation (UTC) |

**Role** : Referentiel artistes. Relie aux sets uniquement pour l'instant. `catalog.artist` reste une String (lien futur).

---

### `artist_aliases` -- Alias / orthographes alternatives

| Colonne | Type | Contraintes | Description |
|---|---|---|---|
| `id` | Integer | PK, auto-increment | ID interne |
| `artist_id` | Integer | FK -> artists.id (CASCADE), NOT NULL, index | Artiste canonique |
| `alias` | String(500) | NOT NULL | Forme alternative |
| `normalized_alias` | String(500) | UNIQUE, NOT NULL | Cle de resolution |

**Role** : Resolution d'un `raw_artist` : chercher d'abord `artists.normalized_name`, puis `artist_aliases.normalized_alias`.

---

## Tables Genres

### `genres` -- Genres musicaux normalises

| Colonne | Type | Contraintes | Description |
|---|---|---|---|
| `id` | Integer | PK, auto-increment | ID interne |
| `name` | String(100) | UNIQUE, NOT NULL | Nom du genre |
| `parent_id` | Integer | FK -> genres.id (SET NULL), nullable | Hierarchie (ex. Techno > Melodic Techno) |
| `created_at` | TIMESTAMPTZ | nullable | Date de creation (UTC) |

**Role** : Table de genres normalisee. Self-reference via `parent_id` pour hierarchie optionnelle. Reliee a `catalog`, `sets` et `artists` via tables d'association.

---

## Tables d'association pures

### `catalog_genres`

| Colonne | Contraintes | Index |
|---|---|---|
| `catalog_id` | FK -> catalog.id (CASCADE), PK | PK (tete) |
| `genre_id` | FK -> genres.id (CASCADE), PK | `ix_catalog_genres_genre_id` |

### `set_genres`

| Colonne | Contraintes | Index |
|---|---|---|
| `set_id` | FK -> sets.id (CASCADE), PK | PK (tete) |
| `genre_id` | FK -> genres.id (CASCADE), PK | `ix_set_genres_genre_id` |

### `artist_genres`

| Colonne | Contraintes | Index |
|---|---|---|
| `artist_id` | FK -> artists.id (CASCADE), PK | PK (tete) |
| `genre_id` | FK -> genres.id (CASCADE), PK | `ix_artist_genres_genre_id` |

---

## Relations (resume)

```
lib_tracks.catalog_id         ------> catalog.id       (SET NULL)
radar_tracks.catalog_id       ------> catalog.id       (SET NULL)
radar_tracks.watched_playlist_id ---> watched_playlists.id
set_tracks.catalog_id         ------> catalog.id       (SET NULL)
set_tracks.set_id             ------> sets.id          (CASCADE)
set_artists.set_id            ------> sets.id          (CASCADE)
set_artists.artist_id         ------> artists.id       (CASCADE)
artist_aliases.artist_id      ------> artists.id       (CASCADE)
genres.parent_id              ------> genres.id         (SET NULL)
catalog_genres                ------> catalog.id + genres.id  (CASCADE)
set_genres                    ------> sets.id + genres.id     (CASCADE)
artist_genres                 ------> artists.id + genres.id  (CASCADE)
```

## Conventions

- **`catalog`** = seul hub de convergence. Rien ne court-circuite.
- **`external_id` + `source` + `last_crawled_at`** pour toute source crawlee.
- **Texte brut + `catalog_id` nullable** pour toute donnee externe a resoudre.
- **`has_artwork`** = presence dans MinIO, jamais d'URL externe en base.
- **`normalized_*`** en UNIQUE pour toute dedup.
- **Durees et timecodes** en entier milliseconde.
- **Timestamps** en TIMESTAMPTZ, stockes en UTC.
- **CASCADE** : suppression d'un set supprime ses tracks, artist_links, genres lies. Idem pour un artiste et ses aliases.
- **SET NULL** : suppression d'une entree catalog repasse les `catalog_id` lies a NULL (non resolu). Suppression d'un genre parent remet ses enfants au niveau racine.

## Buckets MinIO

| Bucket | Contenu | Nommage |
|---|---|---|
| `artworks` | Covers lib_tracks | `{lib_track_id}.jpg` |
| `catalog-artworks` | Covers catalog | `{catalog_id}.jpg` |
| `set-artworks` | Covers sets | `{set_id}.jpg` |
| `artist-artworks` | Photos artistes | `{artist_id}.jpg` |

## Scripts one-shot

| Script | Description |
|---|---|
| `scripts/populate_catalog_genres.py` | Peuple `catalog_genres` depuis `catalog.genre` + `lib_tracks.tags` |
| `scripts/fetch_catalog_artworks.py` | Telecharge les covers catalog dans MinIO |
| `scripts/populate_has_preview.py` | Verifie la dispo des previews Deezer |
| `scripts/link_lib_to_catalog.py` | Lie les lib_tracks sans catalog_id via Deezer search |
| `scripts/backfill_deezer_id.py` | Remplit deezer_id sur catalog |
| `scripts/migrate_catalog.py` | Migration initiale du catalog |
