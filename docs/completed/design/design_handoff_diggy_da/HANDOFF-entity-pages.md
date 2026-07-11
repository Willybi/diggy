# Diggy — Handoff : Pages d'entité v2 (Track · Artiste · Set)

> Aligné sur le schéma PostgreSQL v0002 · 14 juin 2026  
> Base : `design_handoff_diggy_da/` (tokens, components, style-map)

---

## Vue d'ensemble — gabarit commun

Trois pages, un seul gabarit :

```
[ Sidebar ] | CrumbBar (← retour · chemin · pill type)
             | Hero (visuel · kicker · titre · sub · tags · actions)
             | StatStrip (rangée de stats horizontale)
             | Blocs de relations (empilés)
```

Composants partagés entre les 3 pages :
- `<PageHero>` — seul `visual` change (cover carré / photo ronde / wide 16:9)
- `<StatStrip>` — peuplé différemment, même rendu
- `<RelBlock>` — header + body + optionnel footer expand
- `<AppearRow>` — une ligne "apparaît dans"
- `<LibDot>` — pastille ✓/✕ (22px, même taille partout)
- `<Rating>` — étoiles 1–5
- `<ScorePill>` — score radar 1–10 avec meter

---

## Page TRACK

**Route :** `/catalog/:id` ou `/track/:id`  
**Source BDD :** table `catalog` (hub central)

### Champs utilisés

| UI | Champ BDD | Notes |
|---|---|---|
| Titre | `catalog.title` | |
| Artiste | `catalog.artist` | String brut — lien artiste si `artists` résolus |
| Genre/Style | `catalog_genres → genres.name` | Many-to-many — afficher comme tags |
| BPM | `catalog.bpm` | Float → `Math.round()` à l'affichage |
| Key | `catalog.key` | String, ex. `"8A"` |
| Durée | `catalog.duration_ms` | ms → `m:ss` (helper `fmtMs`) |
| Année | `catalog.release_date` | Date → `.getFullYear()` |
| Cover | MinIO `catalog-artworks/{catalog_id}.jpg` si `has_artwork = true` |
| Preview | `catalog.preview_url` si `has_preview = true` | URL expirante — rafraîchir hebdo |
| Rating | `lib_tracks.rating` (0–5) via `lib_tracks.catalog_id` | **Conditionnel** : `—` si pas in lib |
| Radar score | champ calculé API (nb playlists où détecté) | `—` si null ou 0 |
| In lib | `lib_tracks.catalog_id = catalog.id` → booléen | Badge `<InLibBadge>` |

### Règle rating
```js
// Afficher le rating SEULEMENT si la track est in lib
const rating = track.lib_track?.rating;
rating && rating > 0 ? <Rating n={rating} /> : <span>—</span>
```

### Hero player
Afficher uniquement si `has_preview = true` ET `preview_url` non null.
```jsx
{track.has_preview && track.preview_url && (
  <HeroPlayer elapsed="0:00" total={fmtMs(track.duration_ms)} progress={0} />
)}
```

### Blocs de relations

**« Apparaît dans »** — `set_tracks` où `catalog_id = track.id` → jointure `sets`
```sql
SELECT s.id, s.title, sa.name as artist, s.duration_ms,
       st.timecode_ms
FROM set_tracks st
JOIN sets s ON s.id = st.set_id
LEFT JOIN set_artists sea ON sea.set_id = s.id AND sea.role = 'main'
LEFT JOIN artists sa ON sa.id = sea.artist_id
WHERE st.catalog_id = :catalog_id
ORDER BY s.played_date DESC LIMIT 5
```

**« Détecté dans »** — `radar_tracks` où `catalog_id = track.id` → `watched_playlists`
```sql
SELECT wp.id, wp.title, wp.track_count, rt.detected_at
FROM radar_tracks rt
JOIN watched_playlists wp ON wp.id = rt.watched_playlist_id
WHERE rt.catalog_id = :catalog_id
ORDER BY rt.detected_at DESC LIMIT 5
```
> ⚠️ Renommé "Détecté dans" (pas "Dans les playlists") — ce sont des playlists surveillées Deezer, pas des playlists utilisateur.

**« Du même artiste »** — string match approximatif sur `catalog.artist`
```sql
SELECT c.*, lt.rating
FROM catalog c
LEFT JOIN lib_tracks lt ON lt.catalog_id = c.id
WHERE c.artist = :artist_name AND c.id != :catalog_id
ORDER BY lt.rating DESC NULLS LAST LIMIT 5
```

---

## Page ARTISTE

**Route :** `/artist/:id`  
**Source BDD :** table `artists`

### Champs utilisés

| UI | Champ BDD | Notes |
|---|---|---|
| Nom | `artists.name` | |
| Nom réel | `artists.real_name` | Afficher en sub si non null |
| Pays | `artists.country` | Code ISO 2 lettres (FR, DE…) |
| Bio | `artists.bio` | Bloc dédié si non null |
| Photo | MinIO `artist-artworks/{artist_id}.jpg` si `has_artwork = true` |
| Genres/Tags | `artist_genres → genres.name` | Many-to-many |
| Lien Deezer | `artists.deezer_id` → `https://deezer.com/artist/{deezer_id}` | Si non null |
| Lien SoundCloud | `artists.soundcloud_id` → `https://soundcloud.com/{soundcloud_id}` | Si non null |
| Lien TrackID | `artists.trackid_id` → `https://trackid.net/artist/{trackid_id}` | Si non null |
| Aliases | `artist_aliases.alias` | Afficher en sub si présents |

### Liens externes — règle d'affichage
```jsx
// N'afficher que les liens dont l'ID est renseigné — jamais de bouton mort
{artist.deezer_id && <a className="btn-ghost" href={`https://deezer.com/artist/${artist.deezer_id}`}>{PI.ext} Deezer</a>}
{artist.soundcloud_id && <a className="btn-ghost" href={`https://soundcloud.com/${artist.soundcloud_id}`}>{PI.ext} SoundCloud</a>}
{artist.trackid_id && <a className="btn-ghost" href={`https://trackid.net/artist/${artist.trackid_id}`}>{PI.ext} TrackID</a>}
```

### Stats strip

| Stat | Source |
|---|---|
| Tracks dans la lib | `COUNT(lib_tracks)` où `catalog.artist = artist.name` (string match) |
| Tracks au catalog | `COUNT(catalog)` où `catalog.artist = artist.name` (string match) |
| Sets | `COUNT(set_artists)` où `artist_id = artist.id` |
| Rating moyen | `AVG(lib_tracks.rating)` des tracks matchées, arrondi |

> ⚠️ **Limitation schéma** : `catalog.artist` est une String, pas un FK vers `artists`. Les requêtes "tracks de cet artiste" passent par un string match sur `artist.name` + `artist_aliases.normalized_alias`. Ce n'est pas fiable à 100% — prévoir un fallback "artiste non résolu" si 0 résultats.

### Blocs de relations

**« Ses tracks dans la lib »**
```sql
SELECT c.*, lt.rating, lt.tags
FROM catalog c
JOIN lib_tracks lt ON lt.catalog_id = c.id
WHERE c.artist = :artist_name OR c.artist = ANY(:artist_aliases)
ORDER BY lt.rating DESC NULLS LAST
```

**« Sets où il apparaît »** — via `set_artists`
```sql
SELECT s.id, s.title, s.played_date, s.duration_ms,
       sea.role, COUNT(st.id) as track_count
FROM sets s
JOIN set_artists sea ON sea.set_id = s.id
LEFT JOIN set_tracks st ON st.set_id = s.id
WHERE sea.artist_id = :artist_id
GROUP BY s.id, sea.role
ORDER BY s.played_date DESC
```
Afficher le `role` dans le sub de l'AppearRow : `"main"` → rien, `"b2b"` → badge `B2B`.

**Bloc bio** — conditionnel
```jsx
{artist.bio && (
  <RelBlock icon={PI.user} title="Biographie">
    <p>{artist.bio}</p>
  </RelBlock>
)}
```

---

## Page SET

**Route :** `/set/:id`  
**Source BDD :** table `sets`

### Champs utilisés

| UI | Champ BDD | Notes |
|---|---|---|
| Titre | `sets.title` | |
| Événement | `sets.event` | Afficher dans sub et stat strip |
| Lieu | `sets.venue` | Afficher dans sub |
| Date | `sets.played_date` | Date → `DD/MM/YYYY` |
| Durée | `sets.duration_ms` | ms → `H:MM:SS` |
| Cover | MinIO `set-artworks/{set_id}.jpg` si `has_artwork = true` |
| Source URL | `sets.source_url` | Lien externe dynamique |
| Source type | `sets.source` | `"youtube"`, `"1001tracklists"`, `"trackid"`, `"manual"` |
| Artiste(s) | `set_artists → artists` avec `role` (main/b2b) | Voir ci-dessous |
| Genres | `set_genres → genres.name` | Tags du hero |

### Artistes — affichage B2B
```js
// Construire la ligne artiste :
// "Maru Sol" (main seul) ou "Maru Sol × Côte Ouest (B2B)" (b2b)
const artistLine = set.artists
  .sort((a, b) => (a.position ?? 99) - (b.position ?? 99))
  .map(a => a.role === 'b2b' ? `${a.name} (B2B)` : a.name)
  .join(' × ');
```

### Bouton source — dynamique
```jsx
const SOURCE_META = {
  youtube:       { label: "YouTube",       icon: <YTIcon /> },
  "1001tracklists": { label: "1001Tracklists", icon: <ExtIcon /> },
  trackid:       { label: "TrackID.net",   icon: <ExtIcon /> },
  manual:        null,
};
const meta = SOURCE_META[set.source];
{meta && set.source_url && (
  <a className="btn-accent" href={set.source_url} target="_blank">
    {meta.icon} Voir sur {meta.label}
  </a>
)}
// Si source = "manual" ou source_url null → pas de bouton
```

### Tracklist — 3 états de ligne

| État | Condition | Rendu |
|---|---|---|
| **Résolue** | `catalog_id IS NOT NULL AND is_id = false` | Normal, play button, LibDot ✓ |
| **Non résolue** | `catalog_id IS NULL AND is_id = false` | Grisé, `raw_title`/`raw_artist`, pas de play, LibDot ✕ |
| **ID** | `is_id = true` | Très grisé, "ID — non identifié", pas de style tag, `—` partout, pastille "ID" |

```jsx
// Timecode : timecode_ms → "H:MM:SS"
const fmtCue = (ms) => {
  if (ms == null) return "—";
  const s = Math.floor(ms / 1000);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  return `${h}:${String(m).padStart(2,'0')}:${String(sec).padStart(2,'0')}`;
};
```

### Stats strip

| Stat | Source |
|---|---|
| Durée | `sets.duration_ms` → H:MM:SS |
| Date | `sets.played_date` → DD/MM/YYYY |
| Événement | `sets.event` |
| Tracks total | `COUNT(set_tracks)` où `set_id = set.id` |
| Identifiées | `COUNT(set_tracks)` où `catalog_id IS NOT NULL AND is_id = false` |

---

## Helpers communs (à partager en utils)

```js
// ms → "m:ss" ou "H:MM:SS"
const fmtMs = (ms) => {
  if (!ms || ms === 0) return "—";
  const s = Math.floor(ms / 1000);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  return h > 0
    ? `${h}:${String(m).padStart(2,'0')}:${String(sec).padStart(2,'0')}`
    : `${m}:${String(sec).padStart(2,'0')}`;
};

// Valeur absente/zéro → "—"
const fmt = (v) => (!v || v === '0:00' || v === 0) ? '—' : v;

// BPM float → entier
const fmtBpm = (v) => v ? Math.round(v) : '—';

// Date → DD/MM/YYYY
const fmtDate = (d) => d
  ? new Date(d).toLocaleDateString('fr-FR', { day:'2-digit', month:'2-digit', year:'numeric' })
  : '—';
```

---

## Checklist de validation

### Page Track
- [ ] Cover depuis MinIO `catalog-artworks/{id}.jpg` si `has_artwork`
- [ ] BPM entier (`Math.round`)
- [ ] Durée depuis `duration_ms` via `fmtMs`, jamais `0:00`
- [ ] Rating affiché seulement si `lib_tracks.catalog_id` match (sinon `—`)
- [ ] Hero player visible seulement si `has_preview = true`
- [ ] Tags depuis `catalog_genres → genres` (pas `catalog.genre` string brut)
- [ ] Bloc "Détecté dans" (pas "Dans les playlists")
- [ ] Bloc "Du même artiste" via string match `catalog.artist`

### Page Artiste
- [ ] Photo depuis MinIO `artist-artworks/{id}.jpg`
- [ ] `real_name` dans le sub si non null
- [ ] Liens externes affichés uniquement si l'ID est renseigné
- [ ] Tags depuis `artist_genres → genres`
- [ ] Bio bloc visible uniquement si `artists.bio` non null
- [ ] Sets avec badge `B2B` sur les sets à `role = "b2b"`
- [ ] String match `catalog.artist` pour les tracks (prévoir fallback "0 résultats")

### Page Set
- [ ] Cover depuis MinIO `set-artworks/{id}.jpg`
- [ ] Artistes B2B formatés (`× ` entre artistes)
- [ ] Bouton source dynamique selon `sets.source` — absent si `manual` ou `source_url` null
- [ ] `timecode_ms` → `fmtCue` (H:MM:SS)
- [ ] Lignes tracklist : 3 états (résolue / non résolue / ID)
- [ ] Stat "Identifiées" = tracks où `catalog_id IS NOT NULL AND is_id = false`
