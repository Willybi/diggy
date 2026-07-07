# Diggy - Database Schema

> **Auto-generated** from `server/api/models/`. Do not edit below the MANUAL block — regenerate via `/schema_doc`.
> 25 tables across 7 domains.

<!-- MANUAL:BEGIN -->
## Conventions & domain rules

These notes are maintained by hand. Everything below the END marker
is auto-generated — do not edit it directly.

### Sentinels
- `artists.deezer_id = "NOT_FOUND"` marks an artist confirmed absent from Deezer.

### Deduplication
- `catalog.normalized_key` = lower(`artist|title`). Primary dedup key.
- `catalog.isrc` = secondary dedup key when available.

### Genre system
- `catalog.genres` is a `TEXT[]` of raw genre names as received from sources.
- Normalization uses the Wikidata-based graph: `genre_nodes` (canonical genres)
  linked by `genre_edges` (subgenre_of, related_to) and mapped from raw names
  via `genre_mappings`.
- Artist genres are computed dynamically from their catalog tracks
  (`artist_service._artist_genres()`), there is no association table.

### Provenance columns
- `catalog.bpm_source` / `catalog.key_source`: track which external source
  provided the authoritative BPM / key value (e.g. `"beatport"`, `"deezer"`).

### Lifecycle & radar columns
- `catalog.scope`: `"shared"` (default) or `"private"` (Rekordbox-only entries before enrichment).
- `catalog.origin`: how the entry entered the catalog (`"deezer"`, `"rekordbox"`, etc.).
- `catalog.status`: `"official"` (default), `"pending"`, etc.
- `radar_tracks.removed_at`: soft-delete timestamp for tracks removed from a playlist.
- `radar_tracks.is_initial_detection`: `true` for tracks present at first crawl
  (avoids inflating trend scores).

### Merge asymmetry
- Duplicate rows (false negatives) are cheap storage debt.
- Bad merges (false positives) are expensive data corruption.
- Always err toward separation.

### Model vs DB caveat
- This doc reflects SQLAlchemy model declarations. The actual DB may diverge
  if a migration altered a constraint manually (e.g. `ON DELETE`). When in
  doubt, check `alembic/versions/`.
<!-- MANUAL:END -->

## Table of contents

**Catalog hub:** `catalog` · `catalog_artists` · `user_tracks`
**Users:** `users` · `user_opinions` · `user_collections` · `collection_items`
**Radar:** `watched_entities` · `user_follows` · `radar_tracks` · `radar_trends` · `user_radar_state`
**Artists:** `artists` · `artist_aliases` · `artist_flags`
**Sets:** `sets` · `set_artists` · `set_tracks` · `set_flags` · `user_set_follows`
**Genres:** `genre_nodes` · `genre_edges` · `genre_mappings`
**System:** `admin_audit_log` · `crawl_logs`

## Catalog hub

### `catalog`

PK: `id`

| Column | Type | Nullable | Unique | FK | Default |
|--------|------|----------|--------|----|---------|
| `id` **PK** | Integer | no |  |  |  |
| `title` | String(500) | no |  |  |  |
| `artist` | String(500) | yes |  |  |  |
| `normalized_key` | String(500) | no | yes |  |  |
| `isrc` | String(20) | yes | yes |  |  |
| `deezer_id` | String(64) | yes |  |  |  |
| `beatport_id` | String(64) | yes |  |  |  |
| `bpm` | Float | yes |  |  |  |
| `key` | String(10) | yes |  |  |  |
| `duration_ms` | Integer | yes |  |  |  |
| `genres` | TEXT[] | yes |  |  | server_default='{}', default=func |
| `release_date` | Date | yes |  |  |  |
| `preview_url` | Text | yes |  |  |  |
| `has_artwork` | Boolean | yes |  |  | default=False |
| `has_preview` | Boolean | yes |  |  | default=False |
| `created_at` | DateTime(tz) | yes |  |  |  |
| `scope` | String(10) | no |  |  | server_default='shared', default='shared' |
| `owner_id` | Integer | yes |  | FK → users.id ON DELETE SET NULL |  |
| `origin` | String(50) | no |  |  | server_default='deezer', default='deezer' |
| `status` | String(20) | no |  |  | server_default='official', default='official' |
| `bpm_source` | String(20) | yes |  |  |  |
| `key_source` | String(20) | yes |  |  |  |
| `label` | String(255) | yes |  |  |  |
| `fingerprint` | String | yes | yes |  |  |
| `needs_reconciliation` | Boolean | yes |  |  | server_default='false' |
| `deezer_searched_at` | DateTime(tz) | yes |  |  |  |
| `beatport_searched_at` | DateTime(tz) | yes |  |  |  |

### `catalog_artists`

Composite PK: (`catalog_id`, `artist_id`)

| Column | Type | Nullable | Unique | FK | Default |
|--------|------|----------|--------|----|---------|
| `catalog_id` **PK** | Integer | no |  | FK → catalog.id ON DELETE CASCADE |  |
| `artist_id` **PK** | Integer | no |  | FK → artists.id ON DELETE CASCADE |  |
| `role` | String(32) | yes |  |  |  |
| `position` | Integer | yes |  |  |  |

**Indexes:**
- `ix_catalog_artists_artist_id`: `artist_id`

### `user_tracks`

Composite PK: (`user_id`, `catalog_id`)

| Column | Type | Nullable | Unique | FK | Default |
|--------|------|----------|--------|----|---------|
| `user_id` **PK** | Integer | no |  | FK → users.id ON DELETE CASCADE |  |
| `catalog_id` **PK** | Integer | no |  | FK → catalog.id ON DELETE RESTRICT |  |
| `rekordbox_id` | Integer | yes |  |  |  |
| `date_added` | DateTime(tz) | yes |  |  |  |
| `source` | String(50) | yes |  |  | server_default='rekordbox_import', default='rekordbox_import' |
| `file_path` | Text | yes |  |  |  |
| `rb_bpm` | Float | yes |  |  |  |
| `rb_key` | String(10) | yes |  |  |  |
| `rb_mytags` | JSON | yes |  |  | server_default='[]', default=func |
| `rating` | Integer | yes |  |  |  |
| `avis` | String(20) | yes |  |  |  |
| `has_artwork` | Boolean | yes |  |  | default=False |
| `created_at` | DateTime(tz) | yes |  |  |  |

## Users

### `users`

PK: `id`

| Column | Type | Nullable | Unique | FK | Default |
|--------|------|----------|--------|----|---------|
| `id` **PK** | Integer | no |  |  |  |
| `email` | String(255) | no | yes |  |  |
| `username` | String(100) | no | yes |  |  |
| `google_id` | String(255) | no | yes |  |  |
| `picture_url` | Text | yes |  |  |  |
| `is_active` | Boolean | no |  |  | default=True |
| `is_admin` | Boolean | no |  |  | server_default='false', default=False |
| `settings` | JSON | no |  |  | server_default='{}', default=func |
| `created_at` | DateTime(tz) | yes |  |  |  |

### `user_opinions`

Composite PK: (`user_id`, `entity_type`, `entity_key`)

| Column | Type | Nullable | Unique | FK | Default |
|--------|------|----------|--------|----|---------|
| `user_id` **PK** | Integer | no |  | FK → users.id ON DELETE CASCADE |  |
| `entity_type` **PK** | String(20) | no |  |  |  |
| `entity_key` **PK** | String(255) | no |  |  |  |
| `opinion` | String(20) | no |  |  |  |
| `created_at` | DateTime(tz) | yes |  |  |  |

### `user_collections`

PK: `id`

| Column | Type | Nullable | Unique | FK | Default |
|--------|------|----------|--------|----|---------|
| `id` **PK** | Integer | no |  |  |  |
| `user_id` | Integer | no |  | FK → users.id ON DELETE CASCADE |  |
| `name` | String(255) | no |  |  |  |
| `type` | String(20) | yes |  |  | server_default='playlist', default='playlist' |
| `created_at` | DateTime(tz) | yes |  |  |  |

**Indexes:**
- `ix_user_collections_user_id`: `user_id`

### `collection_items`

Composite PK: (`collection_id`, `catalog_id`)

| Column | Type | Nullable | Unique | FK | Default |
|--------|------|----------|--------|----|---------|
| `collection_id` **PK** | Integer | no |  | FK → user_collections.id ON DELETE CASCADE |  |
| `catalog_id` **PK** | Integer | no |  | FK → catalog.id ON DELETE CASCADE |  |
| `position` | Integer | yes |  |  | server_default='0', default=0 |
| `added_at` | DateTime(tz) | yes |  |  |  |

## Radar

### `watched_entities`

PK: `id`

| Column | Type | Nullable | Unique | FK | Default |
|--------|------|----------|--------|----|---------|
| `id` **PK** | Integer | no |  |  |  |
| `external_id` | String(64) | no | yes |  |  |
| `source` | String(64) | no |  |  |  |
| `type` | String(20) | no |  |  | server_default='playlist', default='playlist' |
| `title` | String(255) | yes |  |  |  |
| `description` | Text | yes |  |  |  |
| `created_at` | DateTime(tz) | yes |  |  |  |
| `last_crawled_at` | DateTime(tz) | yes |  |  |  |
| `has_artwork` | Boolean | yes |  |  | default=False |
| `track_count` | Integer | yes |  |  |  |
| `owner` | String(255) | yes |  |  |  |
| `current_task_id` | String(255) | yes |  |  |  |
| `crawl_started_at` | DateTime(tz) | yes |  |  |  |

### `user_follows`

Composite PK: (`user_id`, `entity_id`)

| Column | Type | Nullable | Unique | FK | Default |
|--------|------|----------|--------|----|---------|
| `user_id` **PK** | Integer | no |  | FK → users.id ON DELETE CASCADE |  |
| `entity_id` **PK** | Integer | no |  | FK → watched_entities.id ON DELETE CASCADE |  |
| `followed_at` | DateTime(tz) | yes |  |  |  |

### `radar_tracks`

PK: `id`

| Column | Type | Nullable | Unique | FK | Default |
|--------|------|----------|--------|----|---------|
| `id` **PK** | Integer | no |  |  |  |
| `watched_entity_id` | Integer | no |  | FK → watched_entities.id ON DELETE CASCADE |  |
| `external_track_id` | String(255) | no |  |  |  |
| `source` | String(50) | no |  |  |  |
| `title` | String(500) | no |  |  |  |
| `artist` | String(500) | yes |  |  |  |
| `isrc` | String(20) | yes |  |  |  |
| `detected_at` | DateTime(tz) | yes |  |  |  |
| `catalog_id` | Integer | yes |  | FK → catalog.id ON DELETE SET NULL |  |
| `removed_at` | DateTime(tz) | yes |  |  |  |
| `is_initial_detection` | Boolean | yes |  |  | server_default='false', default=False |

**Unique constraints:**
- `watched_entity_id`, `external_track_id` (`uq_radar_playlist_track`)

### `radar_trends`

PK: `catalog_id`

| Column | Type | Nullable | Unique | FK | Default |
|--------|------|----------|--------|----|---------|
| `catalog_id` **PK** | Integer | no |  | FK → catalog.id ON DELETE CASCADE |  |
| `trend_score` | Float | no |  |  | server_default='0', default=0 |
| `window_days` | Integer | yes |  |  | server_default='30', default=30 |
| `detection_count` | Integer | yes |  |  | server_default='0', default=0 |
| `family` | String(50) | yes |  |  |  |
| `rank_in_family` | Integer | yes |  |  |  |
| `rank_global` | Integer | yes |  |  |  |
| `velocity` | Float | yes |  |  |  |
| `source_count` | Integer | yes |  |  |  |
| `computed_at` | DateTime(tz) | yes |  |  |  |

### `user_radar_state`

Composite PK: (`user_id`, `catalog_id`)

| Column | Type | Nullable | Unique | FK | Default |
|--------|------|----------|--------|----|---------|
| `user_id` **PK** | Integer | no |  | FK → users.id ON DELETE CASCADE |  |
| `catalog_id` **PK** | Integer | no |  | FK → catalog.id ON DELETE CASCADE |  |
| `status` | String(20) | no |  |  | server_default='new', default='new' |
| `updated_at` | DateTime(tz) | yes |  |  |  |

## Artists

### `artists`

PK: `id`

| Column | Type | Nullable | Unique | FK | Default |
|--------|------|----------|--------|----|---------|
| `id` **PK** | Integer | no |  |  |  |
| `name` | String(500) | no |  |  |  |
| `normalized_name` | String(500) | no | yes |  |  |
| `real_name` | String(255) | yes |  |  |  |
| `country` | String(2) | yes |  |  |  |
| `deezer_id` | String(64) | yes |  |  |  |
| `soundcloud_id` | String(64) | yes |  |  |  |
| `trackid_id` | String(64) | yes |  |  |  |
| `bio` | Text | yes |  |  |  |
| `has_artwork` | Boolean | yes |  |  | default=False |
| `created_at` | DateTime(tz) | yes |  |  |  |

### `artist_aliases`

PK: `id`

| Column | Type | Nullable | Unique | FK | Default |
|--------|------|----------|--------|----|---------|
| `id` **PK** | Integer | no |  |  |  |
| `artist_id` | Integer | no |  | FK → artists.id ON DELETE CASCADE |  |
| `alias` | String(500) | no |  |  |  |
| `normalized_alias` | String(500) | no | yes |  |  |

**Indexes:**
- `ix_artist_aliases_artist_id`: `artist_id`

### `artist_flags`

PK: `id`

| Column | Type | Nullable | Unique | FK | Default |
|--------|------|----------|--------|----|---------|
| `id` **PK** | Integer | no |  |  |  |
| `raw_artist_string` | String(500) | no | yes |  |  |
| `reason` | String(64) | no |  |  |  |
| `tokens` | JSON | no |  |  |  |
| `deezer_ids` | JSON | no |  |  |  |
| `status` | String(32) | no |  |  | server_default='pending', default='pending' |
| `resolved_artist_ids` | JSON | yes |  |  |  |
| `created_at` | DateTime(tz) | yes |  |  |  |
| `updated_at` | DateTime(tz) | yes |  |  |  |

## Sets

### `sets`

PK: `id`

| Column | Type | Nullable | Unique | FK | Default |
|--------|------|----------|--------|----|---------|
| `id` **PK** | Integer | no |  |  |  |
| `external_id` | String(64) | yes |  |  |  |
| `source` | String(64) | no |  |  |  |
| `source_url` | Text | yes |  |  |  |
| `title` | String(500) | no |  |  |  |
| `event` | String(255) | yes |  |  |  |
| `venue` | String(255) | yes |  |  |  |
| `played_date` | Date | yes |  |  |  |
| `duration_ms` | Integer | yes |  |  |  |
| `description` | Text | yes |  |  |  |
| `external_slug` | String(500) | yes |  |  |  |
| `has_artwork` | Boolean | yes |  |  | default=False |
| `created_at` | DateTime(tz) | yes |  |  |  |
| `last_crawled_at` | DateTime(tz) | yes |  |  |  |
| `parent_set_id` | Integer | yes |  | FK → sets.id ON DELETE SET NULL |  |
| `is_virtual` | Boolean | no |  |  | server_default='false', default=False |
| `platform` | String(32) | yes |  |  |  |
| `normalized_title` | String(500) | yes |  |  |  |
| `part_number` | Integer | yes |  |  |  |

**Indexes:**
- `ix_sets_parent_set_id`: `parent_set_id`

**Unique constraints:**
- `external_id`, `source` (`uq_set_external_source`)

### `set_artists`

Composite PK: (`set_id`, `artist_id`)

| Column | Type | Nullable | Unique | FK | Default |
|--------|------|----------|--------|----|---------|
| `set_id` **PK** | Integer | no |  | FK → sets.id ON DELETE CASCADE |  |
| `artist_id` **PK** | Integer | no |  | FK → artists.id ON DELETE CASCADE |  |
| `role` | String(32) | yes |  |  |  |
| `position` | Integer | yes |  |  |  |

**Indexes:**
- `ix_set_artists_artist_id`: `artist_id`

### `set_tracks`

PK: `id`

| Column | Type | Nullable | Unique | FK | Default |
|--------|------|----------|--------|----|---------|
| `id` **PK** | Integer | no |  |  |  |
| `set_id` | Integer | no |  | FK → sets.id ON DELETE CASCADE |  |
| `catalog_id` | Integer | yes |  | FK → catalog.id ON DELETE SET NULL |  |
| `position` | Integer | no |  |  |  |
| `timecode_ms` | Integer | yes |  |  |  |
| `raw_title` | String(500) | yes |  |  |  |
| `raw_artist` | String(500) | yes |  |  |  |
| `is_id` | Boolean | yes |  |  | default=False |
| `trackid_music_track_id` | Integer | yes |  |  |  |

**Indexes:**
- `ix_set_tracks_trackid_music_track_id`: `trackid_music_track_id`
- `ix_set_tracks_set_id`: `set_id`
- `ix_set_tracks_catalog_id`: `catalog_id`

**Unique constraints:**
- `set_id`, `position` (`uq_set_track_position`)

### `set_flags`

PK: `id`

| Column | Type | Nullable | Unique | FK | Default |
|--------|------|----------|--------|----|---------|
| `id` **PK** | Integer | no |  |  |  |
| `set_id_a` | Integer | no |  | FK → sets.id ON DELETE CASCADE |  |
| `set_id_b` | Integer | no |  | FK → sets.id ON DELETE CASCADE |  |
| `flag_type` | Enum | no |  |  |  |
| `confidence` | Float | yes |  |  |  |
| `signals` | JSON | yes |  |  |  |
| `status` | Enum | no |  |  | server_default='pending', default=<SetFlagStatus.pending: 'pending'> |
| `resolved_by` | Integer | yes |  | FK → users.id ON DELETE SET NULL |  |
| `resolved_at` | DateTime(tz) | yes |  |  |  |
| `created_at` | DateTime(tz) | no |  |  |  |

**Indexes:**
- `ix_set_flags_set_id_a`: `set_id_a`
- `ix_set_flags_set_id_b`: `set_id_b`

**Unique constraints:**
- `set_id_a`, `set_id_b` (`uq_set_flag_pair`)

### `user_set_follows`

Composite PK: (`user_id`, `set_id`)

| Column | Type | Nullable | Unique | FK | Default |
|--------|------|----------|--------|----|---------|
| `user_id` **PK** | Integer | no |  | FK → users.id ON DELETE CASCADE |  |
| `set_id` **PK** | Integer | no |  | FK → sets.id ON DELETE CASCADE |  |
| `followed_at` | DateTime(tz) | yes |  |  |  |

## Genres

### `genre_nodes`

PK: `id`

| Column | Type | Nullable | Unique | FK | Default |
|--------|------|----------|--------|----|---------|
| `id` **PK** | Integer | no |  |  |  |
| `wikidata_id` | String(64) | no | yes |  |  |
| `label` | String(255) | no |  |  |  |
| `created_at` | DateTime(tz) | yes |  |  |  |

**Indexes:**
- `ix_genre_nodes_label`: `label`

### `genre_edges`

PK: `id`

| Column | Type | Nullable | Unique | FK | Default |
|--------|------|----------|--------|----|---------|
| `id` **PK** | Integer | no |  |  |  |
| `from_node_id` | Integer | no |  | FK → genre_nodes.id ON DELETE CASCADE |  |
| `to_node_id` | Integer | no |  | FK → genre_nodes.id ON DELETE CASCADE |  |
| `type` | String(20) | no |  |  |  |
| `source` | String(50) | no |  |  |  |

**Indexes:**
- `ix_genre_edges_from_node_id`: `from_node_id`
- `ix_genre_edges_to_node_id`: `to_node_id`

**Unique constraints:**
- `from_node_id`, `to_node_id`, `type` (`uq_genre_edge`)

### `genre_mappings`

PK: `id`

| Column | Type | Nullable | Unique | FK | Default |
|--------|------|----------|--------|----|---------|
| `id` **PK** | Integer | no |  |  |  |
| `raw_name` | String(255) | no | yes |  |  |
| `node_id` | Integer | yes |  | FK → genre_nodes.id ON DELETE SET NULL |  |

**Indexes:**
- `ix_genre_mappings_node_id`: `node_id`

## System

### `admin_audit_log`

PK: `id`

| Column | Type | Nullable | Unique | FK | Default |
|--------|------|----------|--------|----|---------|
| `id` **PK** | Integer | no |  |  |  |
| `user_id` | Integer | yes |  | FK → users.id ON DELETE SET NULL |  |
| `action` | String(64) | no |  |  |  |
| `target_type` | String(64) | yes |  |  |  |
| `target_id` | Integer | yes |  |  |  |
| `details` | JSON | yes |  |  |  |
| `created_at` | DateTime(tz) | no |  |  |  |

**Indexes:**
- `ix_admin_audit_log_action`: `action`
- `ix_admin_audit_log_user_id`: `user_id`

### `crawl_logs`

PK: `id`

| Column | Type | Nullable | Unique | FK | Default |
|--------|------|----------|--------|----|---------|
| `id` **PK** | Integer | no |  |  |  |
| `task_type` | String(64) | no |  |  |  |
| `target_id` | Integer | yes |  |  |  |
| `target_label` | String(500) | yes |  |  |  |
| `source` | String(64) | yes |  |  |  |
| `status` | String(20) | no |  |  | server_default='running', default='running' |
| `started_at` | DateTime(tz) | no |  |  |  |
| `finished_at` | DateTime(tz) | yes |  |  |  |
| `duration_ms` | Integer | yes |  |  |  |
| `stats` | JSON | yes |  |  |  |
| `error_message` | Text | yes |  |  |  |
| `celery_task_id` | String(255) | yes |  |  |  |

**Indexes:**
- `ix_crawl_logs_task_type`: `task_type`
