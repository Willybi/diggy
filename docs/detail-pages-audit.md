# Diggy — Audit pages détail (D4 brief design)

> Document de référence pour le chantier D4 (Pages Detail — Vague 3).
> Généré le 2026-07-01 depuis lecture du code source, des services API et des modèles DB.
>
> **Objectif** : fournir au designer une base factuelle exhaustive — ce qui existe,
> ce que l'API expose déjà, ce que la DB contient mais qu'on n'affiche pas encore —
> pour décider quoi prioriser dans la refonte visuelle.

---

## Contexte technique commun

### Composants partagés utilisés dans toutes les pages détail

| Composant | Rôle | Variantes |
|---|---|---|
| `PageHero.vue` | Zone hero (image + titre + subtitle + slots badges/actions) | `square` (160×160) · `round` (160×160, border-radius 50%) · `wide` (280×158) |
| `StatStrip.vue` | Bande de stats horizontale — tableau `[{label, value}]` | — |
| `RelBlock.vue` | Section avec titre + compteur optionnel | — |
| `AppearRow.vue` | Ligne simple titre + subtitle + lien (dans RelBlock) | — |
| `AdminCard.vue` | Zone admin role-gated (masquée si non-admin) | `warn` (amber border) · défaut |
| `StyleTag.vue` | Badge genre coloré par pillar/depth | — |
| `ArtistLinks.vue` | Liste de noms d'artistes cliquables (liens vers `/artist/:id`) | — |
| `LibDot.vue` | Indicateur "dans la bibliothèque" (point vert / gris) | — |

### Layout général (toutes pages)

```
.detail-view
  padding: var(--pad) calc(var(--pad) * 1.5)
  max-width: var(--detail-max-w)
  margin-inline: auto
```

La GenreDetailView utilise un layout custom (pas PageHero), les 4 autres suivent le pattern `PageHero + StatStrip + AdminCard + RelBlocks`.

---

## 1. TrackDetailView — `/catalog/:id`

**Fichier** : `server/frontend/src/views/TrackDetailView.vue`
**API** : `GET /api/catalog/{catalog_id}` → `catalog_service.get_detail()`

### Layout actuel

```
PageHero (variant="square", 160×160)
  image:    /storage/artworks/{lib_track_id}.jpg  (si in_lib + has_artwork)
            /storage/catalog-artworks/{id}.jpg    (sinon)
  title:    track.title
  subtitle: track.artist  ← string brut (pas de lien artiste)
  #badges:  <InLibBadge>  <StyleTag v-for genre>
  #actions: <HeroPlayer>  (si has_preview)

StatStrip
  BPM · Key · Durée · Année · Rating ★ · Radar (nb playlists)

[label + lien Beatport]  ← si track.label ou track.beatport_id

AdminCard (variant="warn")
  beatport_id + deezer_id  (mono, muted)
  Bouton "Enrichir via Beatport" / "Re-enrichir Beatport"
  Bouton "Forcer genre Beatport"
  Bouton "Genre Deezer" + bouton "Appliquer genres"

RelBlock "Détecté dans" (count=nb_radar_playlists)
  AppearRow v-for radar_appearances
    title:    playlist_title
    subtitle: detected_at (fmtDate)

RelBlock "Apparaît dans" (count=nb_set_appearances)
  AppearRow v-for set_appearances
    title:    set_title
    subtitle: played_date (fmtDate)
    link:     /set/{set_id}

RelBlock "Du même artiste" (count=same_artist_tracks.length)
  AppearRow v-for same_artist_tracks
    title:    t.title
    subtitle: "★ In lib" si in_lib, sinon rien
    link:     /catalog/{t.id}
```

### Ce que l'API retourne (`CatalogDetailOut`)

```
id, title, artist (string brut), isrc
bpm, key, duration_ms, release_date (date complète)
genres[]          → {name, pillar, depth}
label             → label de sortie (ex: "Drumcode")
deezer_id, beatport_id
has_artwork, has_preview, preview_url
in_lib, rating (1-5), avis ("liked"|"disliked"|null)
style             → tag Rekordbox (premier tag rb_mytags)
tags[]            → tous les tags Rekordbox
lib_track_id      → rekordbox_id (pour URL artwork lib)
nb_radar_playlists, nb_radar_sets
artists[]         → ArtistRef {id, name, role, has_artwork}
artist_id         → id du premier artiste lié
radar_appearances[] → {playlist_id, playlist_title, playlist_source, detected_at}
set_appearances[]   → {set_id, set_title, played_date, timecode_ms}
same_artist_tracks[] → {id, title, artist, bpm, key, duration_ms, has_artwork, in_lib, rating, artists[]}
```

### Données disponibles mais NON affichées

| Donnée | Valeur type | Pourquoi intéressant |
|---|---|---|
| `artists[]` | `[{id: 12, name: "Amelie Lens", role: "primary"}]` | Le subtitle affiche le string brut `track.artist` — pas de lien cliquable vers la page artiste. `ArtistLinks` devrait remplacer le subtitle ou être dans les badges |
| `avis` | `"liked"` / `"disliked"` / `null` | Aucun indicateur visuel d'avis sur la page détail track |
| `nb_radar_sets` | `3` | Pas dans la StatStrip (seulement `nb_radar_playlists`) |
| `tags[]` | `["Techno", "Dark"]` | Tags Rekordbox complets non affichés |
| `isrc` | `"GBAYE2100123"` | Utile pour admin/debug, absent |
| `timecode_ms` dans `set_appearances` | `3720000` | Affiché dans SetDetail comme lien timestampé — dans TrackDetail, `set_appearances` n'utilise pas le timecode |
| `same_artist_tracks[].bpm` | `132.0` | La section "Du même artiste" n'affiche que titre + in_lib — pas d'artwork ni BPM/key |
| `same_artist_tracks[].has_artwork` | `true` | Pourrait afficher une vignette sur chaque track |
| `playlist_source` dans `radar_appearances` | `"deezer"` / `"tidal"` | Source non différenciée visuellement dans les AppearRows |
| `release_date` | `"2021-03-15"` | Seule l'année est affichée dans la StatStrip |

### Problèmes de cohérence

- **Artist subtitle sans lien** : toutes les autres vues utilisent `ArtistLinks` pour rendre les noms d'artistes cliquables. TrackDetail affiche un string brut dans le subtitle de `PageHero` — exception incohérente.
- **Section "Du même artiste" appauvrie** : dans ArtistDetail, les tracks ont une mini-table avec artwork + genres + BPM + Key + Rating. Dans TrackDetail, la même section n'est qu'une liste de titres (AppearRow sans artwork ni stats).
- **avis absent** : LikeDislike est disponible dans le CatalogView et le RadarView, mais la page détail d'une track n'a aucun moyen d'exprimer un avis.

---

## 2. ArtistDetailView — `/artist/:id`

**Fichier** : `server/frontend/src/views/ArtistDetailView.vue`
**API** : `GET /api/artists/{artist_id}` → `artist_service.get_detail()`

### Layout actuel

```
PageHero (variant="round", 160×160 cercle)
  image:    /storage/artist-artworks/{id}.jpg
  title:    artist.name
  subtitle: real_name · country  (si présents)
  #badges:  <StyleTag v-for genres>
            (lien vers /style/{genre.name})
  #actions: <a> Deezer  (si deezer_id)
            <a> SoundCloud  (si soundcloud_id)
            <a> TrackID  (si trackid_id)

AdminCard
  deezer_id (mono, muted)
  Input "Rechercher sur Deezer…" + bouton Délier
  Liste résultats Deezer (photo + nom + nb_fans + lien dz:id)
  Bouton Confirmer liaison

StatStrip
  Catalog · In lib · Sets · Rating moy.

RelBlock "Aliases"  (si aliases.length)
  texte virgule : alias1, alias2, …

RelBlock "Biographie"  (si bio)
  texte brut

RelBlock "Tracks" (count=stats.nb_catalog)
  <table class="mini-table">
    thead: Track | Style | BPM | Key | Rating
    tbody: v-for catalog_tracks (max 50)
      td: RouterLink /catalog/{t.id}
            mt-title = t.title
            mt-artist = <ArtistLinks :artists="t.artists" :fallback="t.artist">
      td: <StyleTag v-for genres> ou t.style
      td: fmtBpm(t.bpm)
      td: t.key
      td: étoiles rating

RelBlock "Sets" (count=stats.nb_sets)
  AppearRow v-for sets
    title:    s.title
    subtitle: played_date · "B2B" si role=b2b · "X tracks · Y identifiées"
    link:     /set/{s.set_id}
```

### Ce que l'API retourne (`ArtistDetailOut`)

```
id, name, normalized_name
real_name, country
deezer_id, soundcloud_id, trackid_id
bio, has_artwork, created_at
aliases[]         → {alias, normalized_alias}
genres[]          → {name, pillar, depth}  (calculés depuis catalog_tracks, seuil 20%)
catalog_tracks[]  → max 50, triés rating desc puis alpha
  {id, title, artist, isrc, bpm, key, duration_ms, genres[], release_date,
   has_artwork, has_preview, in_lib, style, rating, artists[]}
sets[]            → tous les sets où l'artiste apparaît
  {set_id, title, played_date, has_artwork, role, total_tracks, identified_tracks}
stats             → {nb_catalog, nb_lib, nb_sets, avg_rating}
```

### Données disponibles mais NON affichées

| Donnée | Valeur type | Pourquoi intéressant |
|---|---|---|
| `has_preview` sur les tracks | `true` | Pas de bouton play dans la mini-table. GenreDetail a un preview player au hero ("Écouter un aperçu") — possible ici via `/api/artists/random-track?artist_id=X` (endpoint déjà existant) |
| `in_lib` sur les tracks | `true/false` | Pas de LibDot dans la mini-table. Un point vert permettrait de voir d'un coup d'oeil ce qu'on a |
| `has_artwork` sur les sets | `true` | Les sets s'affichent comme AppearRow sans vignette. Un thumbnail `/storage/set-artworks/{id}.jpg` enrichirait la liste |
| `duration_ms` sur les tracks | `421000` | Pas de colonne durée dans la mini-table |
| `created_at` de l'artiste | `"2024-11-12T..."` | Date d'ajout dans Diggy — utile pour admin, pas affiché |
| `identified_tracks` / `total_tracks` du set | `18 / 24` | Le ratio `18/24` est calculé dans `setSub()` mais le pourcentage d'identification n'est pas visualisé (anneau %) comme dans SetsView |

### Problèmes de cohérence

- **Pas de preview player** : GenreDetail a un bouton "Écouter un aperçu" en hero qui appelle `GET /api/artists/random-track`. L'endpoint `/api/artists/random-track?artist_id=X&exclude=Y` existe exactement pour ça — pas utilisé sur ArtistDetail.
- **mini-table sans in_lib** : dans SetDetail la tracklist a LibDot, dans GenreDetail les tracks ont un filtre "En bib" — dans ArtistDetail la mini-table ne montre pas du tout si la track est dans la bibliothèque.
- **Sets sans miniature** : les AppearRows des sets n'ont pas de vignette, alors que `has_artwork` est dans le payload et `/storage/set-artworks/{id}.jpg` est disponible.
- **Limite 50 tracks hardcodée** : `artist_service.get_detail()` limite à 50 tracks. Pas de pagination ni d'indication au-delà (ex: "… et 23 autres").

---

## 3. SetDetailView — `/set/:id`

**Fichier** : `server/frontend/src/views/SetDetailView.vue`
**API** : `GET /api/sets/{set_id}` → `sets.get_set_detail()`

### Layout actuel

```
PageHero (variant="wide", 280×158)
  image:    /storage/set-artworks/{id}.jpg
  title:    djSet.title
  subtitle: si 1 seul artiste → artiste · event · venue
            si plusieurs artistes → event · venue seulement  ← bug
  #badges:  (slot vide — rien)
  #actions: <a> "Voir sur YouTube/SoundCloud/1001TL/TrackID"  (si source_url)

StatStrip
  Durée · Date · Tracks · Identifiées

AdminCard (label="Admin — Artistes du set", variant="warn")
  Liste set_artists : nom + role + bouton Retirer
  Input "Rechercher un artiste…" → résultats cliquables pour ajouter

RelBlock "Artistes"  (si artists.length > 1)
  AppearRow v-for artists
    title:    artist_name
    subtitle: "B2B" si role=b2b
    link:     /artist/{artist_id}

RelBlock "Tracklist" (count=djSet.total_tracks)
  <table class="tracklist">
    thead: # | Time | (cover) | Track | Lib
    tbody: v-for tracklist
      td: position (mono)
      td: timecode → lien horodaté si YouTube/SC
      td: img /storage/catalog-artworks/{catalog_id}.jpg (32×32)
      td: RouterLink /catalog/{catalog_id}
            tl-title = catalog_title || raw_title
            tl-artist = <ArtistLinks> || raw_artist
          (fallback si is_id : "ID" italic)
      td: <LibDot>  ou  label "ID"
```

### Ce que l'API retourne (`DJSetDetailOut`)

```
id, external_id, source, source_url
title, event, venue, played_date, duration_ms
description   ← FETCHÉ mais jamais affiché
has_artwork, created_at, last_crawled_at
total_tracks, identified_tracks
artists[]     → {artist_id, artist_name, has_artwork, role, position}
tracklist[]   → {id, set_id, catalog_id, position, timecode_ms,
                  raw_title, raw_artist, is_id,
                  catalog_title, catalog_artist, catalog_artists[],
                  has_artwork, in_lib, has_preview}
```

### Données disponibles mais NON affichées

| Donnée | Valeur type | Pourquoi intéressant |
|---|---|---|
| `description` | `"Recorded live at Awakenings..."` | **Jamais rendu** — pourtant fetché dans le payload. Oubli direct. Un RelBlock "Description" suffit |
| `has_preview` sur les tracks | `true` | Pas de bouton play sur les tracks identifiées de la tracklist. PlaylistDetail l'a, SetDetail non |
| `last_crawled_at`, `created_at` | timestamps | Pas dans la StatStrip (seulement Durée/Date/Tracks/Identifiées) |
| `event` + `venue` avec plusieurs artistes | `"Awakenings"` + `"Gashouder"` | Le subtitle du hero efface event/venue si `artists.length > 1` — bug de logique dans `heroSub` computed |
| Genres du set | — | La table `set_genres` existe en DB (association `sets ↔ genres`). Pas du tout dans l'API `DJSetDetailOut` ni dans la vue |
| `has_artwork` des artistes du set | `true` | Dans le RelBlock "Artistes", les AppearRows n'ont pas de photo ronde. Pourtant `has_artwork` est dans `SetArtistDetailOut` |
| % identification visuel | `18/24 = 75%` | `identified_tracks / total_tracks` est dans la StatStrip comme compteur brut, mais pas comme anneau % comme dans SetsView |

### Problèmes de cohérence

- **`description` oubliée** : la donnée arrive dans le JSON, mais aucun `v-if="djSet.description"` dans le template. C'est le seul oubli pur du codebase.
- **Hero subtitle bugué** : `heroSub` est `if (djSet.artists.length === 1) parts.push(artists[0].artist_name)`. Avec 2 artistes en B2B, le nom des artistes disparaît du subtitle et l'event/venue prend toute la place.
- **Pas de genres sur le set** : ArtistDetail et TrackDetail ont des StyleTags dans les badges du hero. SetDetail n'en a aucun, même si `set_genres` existe côté DB.
- **Pas de preview** : PlaylistDetail a un bouton play par track (`has_preview` déjà dans le payload des tracks). SetDetail a `has_preview` dans `SetTrackDetailOut` mais ne l'utilise pas.

---

## 4. GenreDetailView — `/style/:genre`

**Fichier** : `server/frontend/src/views/GenreDetailView.vue`
**APIs** :
- `GET /api/genres/detail/{name}` → stats du genre
- `GET /api/genres/artists/{name}` → artistes paginés
- `GET /api/genres/sets/{name}` → sets paginés
- `GET /api/genres/playlists/{name}` → playlists paginées
- `GET /api/genres/tracks/{name}` → tracks paginées (infinite scroll)
- `GET /api/genres/neighbors/{name}` → genres voisins

### Layout actuel

```
← Lien retour "← Genres"

Hero custom (pas PageHero)
  .hero-mosaic (3×2 grid, 180px)
    6 tuiles couleur pillar (fond oklch)
    + img covers de tracks si has_artwork
    .hero-scrim (gradient bas)
    .hero-avatars (3 photos artistes en overlap)
    .hero-play (bouton play/pause — déclenche audio preview random)
  .hero-body
    .hero-dot (cercle coloré pillar)
    h1 genre.name  (coloré pillar)
    .hero-fam  (label famille : "House" / "Techno" / …)

.hero-actions
  btn--accent "Écouter un aperçu"
  btn--ghost-accent "Tout filtrer dans Catalog" → /catalog?genre=X

StatStrip
  Tracks · Artistes · BPM (lo–hi) · En bib · [Sets] · [Playlists]

AdminCard
  Input "Nouveau nom…" + bouton Renommer
  Input "Fusionner dans…" + autocomplete + bouton Fusionner

RelBlock "Artistes" (count=artistsTotal, max 12)
  ShelfCard v-for (scroll horizontal)
    image: /storage/artist-artworks/{id}.jpg  (round)
    title: artist.name
    subtitle: "{trackCount} tracks"
    link: /artist/{id}

RelBlock "Sets" (count=setsTotal, max 12)
  ShelfCard v-for
    image: /storage/set-artworks/{id}.jpg
    #overlay: anneau % (genreTrackCount / totalTracks)
    #badge: "Set"
    title: set.title
    subtitle: playedDate

RelBlock "Playlists" (count=playlistsTotal, max 12)
  ShelfCard v-for
    image: /storage/playlist-artworks/{id}.jpg
    #badge: source-badge (deezer/spotify/tidal)
    title: playlist.title
    subtitle: "{genreTrackCount} tracks"
    link: /playlists/{id}

Section "Tracks" (tracks-section — NE PAS utiliser RelBlock ici)
  header: titre + compteur + SearchBox + SegFilter (Récent/BPM/Key/A-Z) + toggle "En bib"
  liste: GenreTrackRow v-for (infinite scroll IntersectionObserver)

RelBlock "Genres proches"
  .neighbor-chips: RouterLink v-for neighbors
    <StyleTag> + meta "{commonArtists} artistes en commun"
```

### Données retournées par l'API

**`/api/genres/detail/{name}`** :
```
name, pillar, depth
trackCount, artistCount, inLibCount
bpmLo, bpmHi
setCount, playlistCount
artworks[]    → URLs catalog-artworks des tracks du genre
artists[]     → top 3 {id, name, image} pour avatars
```

**`/api/genres/tracks/{name}`** (GenreTrackRow) :
```
id, title, artist, bpm, key, duration_ms
genres[], has_artwork, has_preview, in_lib, rating
artists[]
```

### Remarques

- C'est la page la plus complète et la plus soignée du projet.
- Le hero custom avec mosaïque est bien plus riche que le `PageHero` commun.
- Quelques points mineurs manquants :
  - `rating` moyen du genre n'est pas dans la StatStrip
  - Les tracks de GenreTrackRow n'ont pas de bouton play individuel (seulement le preview random au hero)
  - `inLibCount` est dans la StatStrip ("En bib") mais pas le % par rapport au total

---

## 5. PlaylistDetailView — `/playlists/:id`

**Fichier** : `server/frontend/src/views/PlaylistDetailView.vue`
**API** : `GET /api/watchlist/{id}` → `watchlist` router

### Layout actuel

```
PageHero (variant="square", 160×160)
  image:    /storage/playlist-artworks/{id}.jpg
  title:    playlist.title || playlist.external_id
  subtitle: owner · source  (ex: "Drumcode · deezer")
  #actions: <a> "Deezer" → deezer.com/playlist/{external_id}
            bouton "Ne plus suivre" / "Suivre"

AdminCard  (si !has_artwork && source=deezer)
  bouton "Fetch artwork Deezer"

.crawl-banner  (si crawl en cours)
  dot animé + "Crawl en cours…" ou "en file d'attente"

StatStrip
  Tracks · Tracks radar · Dernier crawl · Ajoutée le

RelBlock "Description"  (si playlist.description)
  texte brut

RelBlock "Tracks" (count=playlist.tracks.length)
  <table class="mini-table">
    thead: (cover) | Track | BPM | Key | Durée | (play)
    tbody: v-for tracks
      td: img /storage/catalog-artworks/{catalog_id}.jpg (32×32)
      td: RouterLink /catalog/{catalog_id}
            mt-title = t.title
            mt-artist = <ArtistLinks :artists="t.artists" :fallback="t.artist">
      td: fmtBpm(t.bpm)
      td: t.key
      td: fmtMs(t.duration_ms)
      td: bouton play (si has_preview)
```

### Ce que l'API retourne (watchlist detail)

```
id, external_id, source ("deezer"|"tidal"|"spotify")
title, description, owner
has_artwork, track_count
last_crawled_at, created_at
current_task_id  → pour le crawl banner
followed (bool)
tracks[]  → RadarTracks enrichis
  {catalog_id, title, artist, bpm, key, duration_ms,
   has_artwork, has_preview, artists[],
   in_lib (si enrichi)}
```

### Données disponibles mais NON affichées

| Donnée | Valeur type | Pourquoi intéressant |
|---|---|---|
| `in_lib` sur les tracks | `true/false` | **Pas de LibDot dans la tracklist** — toutes les autres tables de tracks (SetDetail, ArtistDetail) ont soit LibDot soit une indication. PlaylistDetail est la seule exception |
| `source` visuel différencié | `"tidal"` / `"spotify"` | Le subtitle affiche la source en texte brut. Les ShelfCards de GenreDetail ont un `source-badge` coloré (deezer/spotify/tidal). Pourrait être un badge dans les actions du hero |
| Genres dominants de la playlist | — | Non calculé côté API. Enrichissement potentiel : top 3 genres des tracks de la playlist |
| Artistes principaux | — | Non calculé. Top 3 artistes présents dans les tracks |
| `track_count` vs `tracks.length` | ex: 120 vs 50 | La playlist peut avoir 120 tracks mais l'API ne retourne que 50 radar tracks. La StatStrip affiche les deux ("Tracks: 120" et "Tracks radar: 50") mais c'est confus |

### Problèmes de cohérence

- **LibDot absent** : c'est l'anomalie la plus visible — chaque autre table de tracks dans l'app a un indicateur in_lib. PlaylistDetail a une colonne vide à la place.
- **Source dans le subtitle en texte brut** : "Drumcode · deezer" — le mot "deezer" n'est pas capitalisé ni badgé. Un `SourceBadge` (composant créé dans D5) améliorerait ça.
- **Lien Deezer hardcodé** : le bouton "Deezer" dans les actions pointe toujours vers `deezer.com/playlist/{external_id}` même si la source est TIDAL ou Spotify — bug pour les playlists non-Deezer.

---

## Matrice de cohérence

| Fonctionnalité | TrackDetail | ArtistDetail | SetDetail | GenreDetail | PlaylistDetail |
|---|:---:|:---:|:---:|:---:|:---:|
| Preview player (track) | Hero player | — | — | Random hero | Par track |
| LibDot / in_lib indicator | Badge hero | — | Colonne tracklist | Filtre + toggle | — |
| ArtistLinks (cliquables) | **Non (string brut)** | Dans mini-table | Dans tracklist | Dans track rows | Dans tracklist |
| StyleTags genres (hero/badges) | Oui | Oui | **Non** | Hero coloré | — |
| Artwork tracklist (vignette) | — | — | 32×32 | Dans track rows | 32×32 |
| Source badge visuel | — | Liens boutons | Lien bouton | Badge ShelfCard | Texte brut |
| Skeleton loading | — | — | — | **Oui (seul)** | — |
| Admin section | Beatport/Deezer | Deezer link | Set artists | Rename/merge | Fetch artwork |

---

## Synthèse pour le brief design

### Corrections sans travail API (données déjà disponibles)

1. **Set description non affichée** (SetDetail) — données déjà dans le payload, juste un `RelBlock` à ajouter
2. **LibDot absent** dans PlaylistDetail tracklist — `in_lib` est dans les données
3. **ArtistLinks dans le hero** de TrackDetail — remplacer le subtitle string brut
4. **Hero subtitle bugué** pour les sets multi-artistes — `event + venue` disparaissent si ≥ 2 artistes
5. **Lien Deezer hardcodé** dans PlaylistDetail — ne fonctionne pas pour TIDAL/Spotify

### Enrichissements cohérents (étendre ce qui existe ailleurs)

6. **Preview player sur ArtistDetail** — endpoint `/api/artists/random-track` déjà existant, GenreDetail l'utilise
7. **`in_lib` indicator** dans la mini-table d'ArtistDetail
8. **Preview play individuel** dans SetDetail tracklist — `has_preview` déjà dans le payload
9. **Thumbnails sets** dans les AppearRows d'ArtistDetail — `has_artwork` disponible
10. **StyleTags genres** dans le hero de SetDetail (slot `#badges` vide)

### Nécessite travail backend

11. **Genres du set** — `set_genres` existe en DB, pas dans `DJSetDetailOut`
12. **`nb_radar_sets`** dans la StatStrip de TrackDetail — dans le payload mais pas dans les stats affichées
13. **Section "Du même artiste"** enrichie — actuellement AppearRow basique, mérite une mini-table comme ArtistDetail
14. **Pagination artistes dans ArtistDetail** — limite 50 tracks hardcodée sans indication
15. **Genres dominants et artistes principaux** dans PlaylistDetail — pas calculé côté API

---

## Référence modèle DB — champs disponibles par entité

### `catalog` (CatalogEntry)
```
id, title, artist, normalized_key, isrc
deezer_id, beatport_id
bpm, bpm_source, key, key_source
duration_ms, genres[], release_date, label
preview_url, has_preview, has_artwork
created_at, beatport_searched_at
```

### `artists`
```
id, name, normalized_name, real_name, country
deezer_id, soundcloud_id, trackid_id
bio, has_artwork, created_at
→ aliases[] (artist_aliases)
→ genres (calculés via catalog_artists + catalog.genres)
```

### `sets` (DJSet)
```
id, external_id, external_slug, source, source_url
title, event, venue, played_date, duration_ms, description
has_artwork, created_at, last_crawled_at
→ artists[] (set_artists)
→ tracks[] (set_tracks)
→ genres[] (set_genres — non exposé dans l'API actuellement)
```

### `watched_entities` (WatchedEntity / Playlist)
```
id, external_id, source, type
title, description, owner
has_artwork, track_count
created_at, last_crawled_at, current_task_id
→ tracks[] (radar_tracks avec catalog_id)
```

### `genres` (taxonomy)
```
id, name, pillar (house/techno/trance/dnb/hardcore/harddance/autres), depth
→ utilisés comme tags texte sur catalog.genres[] (array PostgreSQL)
→ association catalog_genres, artist_genres, set_genres
```
