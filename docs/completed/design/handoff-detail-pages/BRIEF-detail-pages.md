# BRIEF — Refacto pages détail (Vague 3)

> Maquette pilote : `Pages détail (pilote).html` (+ `pages-detail.css`, `pages-detail-data.js`).
> 4 pages dans un seul fichier — sélecteur **Page** dans la toolbar de revue.
> Toggle **Annot. backend** = surligne (contour magenta + puce ⚙) tout ce qui **demande du backend**.
> Tout en tokens `diggy-tokens.css`. Cible DA = Wildflower v1 (inchangée).

Chaque page suit le même pattern : `dv-back → hero → stat-strip → admin-card (role-gated) → rel-blocks`.
Les composants existants restent : `PageHero`, `StatStrip`, `RelBlock`, `AppearRow`, `AdminCard`, `StyleTag`, `ArtistLinks`, `LibDot`, `InLibBadge`, `HeroPlayer`, `SourceBadge`, `RingPct`.

---

## Légende priorités

- ✅ **Sans backend** — la donnée est déjà dans le payload, c'est du câblage front.
- 🔧 **Front enrichi** — composant existant à ajouter (endpoint déjà là).
- ⚙ **Backend requis** — nouveau champ / agrégat / endpoint à produire côté API.

---

## 1. TrackDetail `/catalog/:id`

| # | Changement | Niveau |
|---|---|---|
| T1 | Subtitle hero = `<ArtistLinks :artists="track.artists">` (liens cliquables) au lieu du string brut `track.artist` | ✅ `artists[]` déjà renvoyé |
| T2 | Badges hero : garder `InLibBadge` + `StyleTag`, ajouter les **tags Rekordbox** (`tags[]`) en chips secondaires (`.rb-tag`) | ✅ `tags[]` dispo |
| T3 | Contrôle **like / dislike** (avis) dans les actions hero — réutiliser `LikeDislike.vue` ; état initial depuis `track.avis` | 🔧 composant existant, `avis` déjà dans payload |
| T4 | StatStrip : ajouter cellule **Radar sets** (`nb_radar_sets`) à côté de Radar playlists | ✅ `nb_radar_sets` dispo |
| T5 | Admin : ajouter `isrc` dans la ligne d'IDs | ✅ dispo |
| T6 | « Détecté dans » : badge **source** (`playlist_source`) sur chaque ligne + date | ✅ dispo |
| T7 | « Apparaît dans » : lien **timecode** cliquable (`timecode_ms`) vers le set horodaté | ✅ dispo |
| T8 | « Du même artiste » : remplacer les `AppearRow` par une **mini-table** (cover, track+ArtistLinks, BPM, Key, Rating, LibDot) | ✅ `same_artist_tracks[]` porte déjà `bpm/key/has_artwork/in_lib/rating/artists` |

> Note T8 : `same_artist_tracks[]` ne contient **pas** `genres[]` → pas de colonne Style ici (sinon ⚙). La maquette n'en met pas.

---

## 2. ArtistDetail `/artist/:id`

| # | Changement | Niveau |
|---|---|---|
| A1 | Bouton hero **« Écouter un aperçu »** (`btn-accent`) → `GET /api/artists/random-track?artist_id=X` (déjà utilisé par GenreDetail) | 🔧 endpoint existant |
| A2 | Mini-table Tracks : colonne **Durée** (`duration_ms`) | ✅ dispo |
| A3 | Mini-table Tracks : bouton **play** au hover (`has_preview`) → `audioPlayer` | ✅ dispo |
| A4 | Mini-table Tracks : **LibDot** (`in_lib`) en dernière colonne | ✅ dispo |
| A5 | Bloc Sets : **vignette** `set-artworks/{id}.jpg` (`has_artwork`) sur chaque `AppearRow` | ✅ dispo |
| A6 | Bloc Sets : **anneau %** `identified_tracks / total_tracks` à droite (comp. `RingPct`) | ✅ dispo |
| A7 | Note pagination « … et N autres » sous la table (limite 50 hardcodée) | ⚙ pagination API à câbler |

---

## 3. SetDetail `/set/:id`

| # | Changement | Niveau |
|---|---|---|
| S1 | **Fix `heroSub`** : garder `event` + `venue` même quand `artists.length > 1`. Format : `artistes (B2B) · event · venue` | ✅ bug de logique |
| S2 | **Description** : ajouter le `RelBlock` manquant (`djSet.description` est déjà fetché, jamais rendu) | ✅ oubli pur |
| S3 | Bloc « Artistes » : **photo ronde** (`has_artwork` de `SetArtistDetailOut`) sur chaque ligne | ✅ dispo |
| S4 | StatStrip « Identifiées » : afficher l'**anneau %** (`RingPct` value=identified total=total) au lieu du compteur brut | ✅ dispo |
| S5 | Tracklist : bouton **play** au hover (`has_preview` de `SetTrackDetailOut`) | ✅ dispo |
| S6 | Badges hero : **StyleTags genres** du set | ⚙ `set_genres` existe en DB mais **absent de `DJSetDetailOut`** — exposer `genres[]` (name, pillar, depth) dans le schéma API |

> S6 est le seul vrai chantier backend de cette page. Maquette : 2 StyleTags marqués ⚙.

---

## 4. PlaylistDetail `/playlists/:id`

| # | Changement | Niveau |
|---|---|---|
| P1 | Subtitle/badges hero : **`SourceBadge`** (deezer/tidal/spotify) au lieu du mot `source` en texte brut | ✅ dispo |
| P2 | **Fix lien externe** : construire l'URL selon `source` (Deezer / TIDAL / Spotify), plus de `deezer.com` hardcodé | ✅ bug |
| P3 | Tracklist : **LibDot** (`in_lib`) — seule table de l'app qui n'en a pas | ✅ dispo |
| P4 | Bloc **« Dans cette playlist »** : Artistes principaux (avatars) + Genres dominants (barres %) | ⚙ agrégats à calculer côté API (top artistes + top genres des tracks de la playlist) |

> P4 = chantier backend. Maquette : section entière marquée ⚙.

---

## Récap backend requis (⚙ uniquement)

1. **`DJSetDetailOut.genres[]`** — exposer `set_genres` (name/pillar/depth) — *déblocage S6*.
2. **Agrégats playlist** — top artistes + top genres (name/pillar/depth/pct) des tracks — *déblocage P4*.
3. **Pagination tracks artiste** — au-delà de la limite 50 (offset/total) — *déblocage A7*.

Tout le reste (✅ / 🔧) est câblable sans toucher l'API.

---

## Grille d'audit — vérifiée sur la maquette

- Couleurs 100 % tokens · Responsive (large→narrow, container queries) · Admin role-gated 2 états
- Accent discipliné (action / key / rating) · In-lib = `--pos` partout · Mono pour toutes les données
- Densité `--row-h`/`--pad` · StyleTag via 5 familles bornées · Dark mode vérifié

---

## MàJ round 2 (retours William)

Décisions layout appliquées à la maquette — à répercuter côté Vue :

- **Blocs admin en bas de page** — sur toutes les pages détail, l'`AdminCard` passe **tout en bas** (après les rel-blocks, avant le footer), plus juste sous le hero.
- **Track — avatar artiste** : le subtitle du hero devient une puce `artist-chip` (petit avatar rond + nom, cliquable → `/artist/:id`) plutôt qu'un simple lien texte.
- **Track — densité 2 colonnes** : « Détecté dans » et « Apparaît dans » passent en **grille 2 colonnes** (`.rel-cols`) sur large, 1 colonne sous ~720px (container query). « Du même artiste » reste pleine largeur (table).
- **Artist — hero bannière** : nouveau hero `hero--banner` = **mosaïque de covers** des tracks de l'artiste (bandeau) + scrim, avec l'avatar rond en débord. Pattern **réutilisable** (`.hero-banner` / `.hb-tiles`) — candidat pour Playlist/Set plus tard. Source covers : `catalog-artworks/{id}.jpg` des top tracks (⚙ endpoint à confirmer : liste d'IDs de covers pour la bannière).
- **Set — bloc « Dans ce set »** : même composant que « Dans cette playlist » (Artistes récurrents + Genres dominants avec barres %). ⚙ agrégats API (top artistes de la tracklist + distribution de genres).
- **Barres « genres dominants » alignées** : la colonne StyleTag est **à largeur fixe** (grid `132px 1fr 38px`) → toutes les barres démarrent au même x et ont la même longueur de piste. Barre d'une famille *autres* = grise (`--ink-3`), pas de teinte.
