# Prompt Claude Code — Genre Detail `/style/:genre`

> Copie-colle ce bloc à Claude Code dans le repo **Willybi/diggy** (FastAPI + Vue 3, branche `master`).
> Les chemins design (`design/...`) correspondent au handoff Diggy ; vérifie leur emplacement réel dans ton repo.

---

Tu implémentes le lot **Genre Detail `/style/:genre`** en réalignant sur la DA Wildflower (tokens = frontière).

## 0. À lire avant de coder
- `design/CLAUDE.md` + `design/ROADMAP-realign.md` — conventions **non-négociables** (tout via `var(--…)`, mono pour les données, `--accent` discipliné, in-lib = `--pos`, StyleTag via `diggy-style-map.js`, container-queries, densité, UTF-8 strict).
- **Maquette de référence** : `design/realign/Genre Detail (pilote).html` (la barre sombre du haut est l'outil de revue, **hors-produit**).
- **Brief détaillé** : `design/realign/BRIEF-genre-detail.md`.
- Code existant à réutiliser :
  - Backend : `server/api/routers/genres.py` (réutilise `genre_family()` **et** le pattern `PERCENTILE_CONT(0.05/0.95)`), `server/api/models.py`, `server/api/schemas.py`, `server/api/routers/{catalog,artists,sets,watchlist}.py` (patterns pagination/auth).
  - Front : `server/frontend/src/views/GenreDetailView.vue` (existe, **à réécrire**), `router.js`, et les composants partagés `components/{PageHero,StatStrip,StyleTag,TrackTable,LibDot,InLibBadge,HeroPlayer,RelBlock,AppearRow,SidebarNav}.vue`, `composables/useStyleMap.js`, `stores/{audioPlayer,auth}.js`, `utils/format.js`, `styles/diggy-tokens.css`.

## 1. 🛑 BACKEND D'ABORD — vérifier puis construire (avant le front)

**Constat** : `genres.py` ne fait que la **liste** ; il n'existe **aucun endpoint de détail**. Mais toute la donnée est dérivable des tables existantes : `catalog.genre` (string, 1 genre/track), `artists` (join `normalized_name = LOWER(catalog.artist)`), `set_tracks`→`sets`, `radar_tracks`→`watched_entities`, `user_tracks` (in-lib scopé user). Construis ces endpoints (préfixe au choix `/api/genres/{name}` ou `/api/styles/{name}` — garde-le cohérent avec le routing front) :

**`name`** = nom de genre brut **URL-décodé** (`decodeURIComponent`), matché exactement sur `catalog.genre`. Gère `/`, espaces, accents, casse. **404** si aucune track.

1. **`GET …/{name}`** — agrégats du genre (hero + StatStrip) :
   - `trackCount` = `COUNT(*)`, `artistCount` = `COUNT(DISTINCT LOWER(artist))`,
   - `bpmLo`/`bpmHi` = `PERCENTILE_CONT(0.05|0.95) WITHIN GROUP (ORDER BY bpm)` — **réutilise le pattern de `genres.py`** (p5–p95 validé willi),
   - `inLibCount` = `COUNT(DISTINCT user_tracks.catalog_id)` scopé user,
   - `setCount` (sets distincts contenant ≥1 track du genre), `playlistCount` (watched_entities distincts via `radar_tracks`),
   - `family` = `genre_family(name)`, `topArtists[]` (≤3, avec photo) + `covers[]` (≤6) — reprends les sous-requêtes artworks/artists de `list_genres`.
2. **`GET …/{name}/artists`** — artistes du genre : `id, name, trackCountInGenre, hasInLib, image`. Tri `trackCountInGenre` desc. Join `artists a ON a.normalized_name = LOWER(c.artist)`.
3. **`GET …/{name}/sets`** — sets liés : `id, title, played_date, trackTotal, trackInGenre, cover`. Via `set_tracks` join `catalog`. Tri `trackInGenre` desc.
4. **`GET …/{name}/playlists`** — playlists liées : `id, external_id, title, source, trackInGenre, cover`. Via `radar_tracks` join `catalog` join `watched_entities`. Tri `trackInGenre` desc.
5. **`GET …/{name}/tracks`** — tracklist, **pagination + tri + recherche + filtre serveur** :
   - params `?sort=recent|bpm|key|alpha&q=&inLib=0|1&limit=50&offset=`,
   - `recent` = `created_at` desc · `bpm` = bpm asc · `alpha` = title · **`key` = ordre Camelot** (1A→12B, pas alpha brut : tri sur `CAST(regexp_replace(key,'[^0-9]','','g') AS int)` puis suffixe A/B, ou en Python),
   - champs : `id, title, artist, bpm, key, duration_ms, has_artwork, preview_url, inLib`.
6. **`GET …/{name}/neighbors`** — **🔗 logique à concevoir, à valider avec willi avant de coder** :
   - Métrique **primaire proposée = artistes en commun** (cheap, signifiante) :
     ```sql
     WITH x AS (SELECT DISTINCT LOWER(artist) a FROM catalog WHERE genre=:name AND artist<>'')
     SELECT c.genre, COUNT(DISTINCT LOWER(c.artist)) common_artists
     FROM catalog c JOIN x ON LOWER(c.artist)=x.a
     WHERE c.genre IS NOT NULL AND c.genre<>:name
     GROUP BY c.genre ORDER BY common_artists DESC LIMIT :limit
     ```
   - Métrique **secondaire optionnelle = co-occurrence en sets** (genres présents dans les mêmes `set_tracks`).
   - Renvoie par voisin : `name, family (=genre_family), commonArtists, commonTracks?`. Exclure le genre courant. `X ≈ 6`.
   - **Perf** : ces agrégats + voisins grossiront avec la base → prévoir précalcul / vue matérialisée rafraîchie à l'ingest plutôt que live à chaque hit. **Propose ta formule + pondération à willi avant de l'implémenter.**

7. **Admin (role-gated, `user.is_admin`)** :
   - `PATCH …/{name}` rename → met à jour `catalog.genre` (et toute autre ref) ; **le nom = l'URL** → renvoie le nouveau nom pour rediriger le front.
   - `POST …/merge { from, into }` → réaffecte les tracks de `from` vers `into`, supprime `from`. Idempotent, transaction, renvoie le nombre de tracks impactées.

> Si un point de donnée manque ou est ambigu, **remonte-le à willi avant de coder** — ne devine pas le contrat d'API.

## 2. FRONT — réécrire `views/GenreDetailView.vue`

Reproduis la maquette à l'identique, **en réutilisant les composants partagés** (ne les ré-invente pas) :

- **Route** : `/style/:genre` (param = nom brut, `decodeURIComponent` à la lecture, `encodeURIComponent` pour les liens). Vérifie/ajoute dans `router.js`.
- **`← Genres`** (retour) puis **Hero** = `PageHero` variante "wide" teintée famille (mosaïque covers + 3 avatars + play `--accent`), `StatStrip` = **Tracks · Artistes · BPM · En bib** (En bib en `--pos`). `is-misc` ⇒ neutre (Dance/Pop). Le titre/dot prennent la couleur famille via `diggy-style-map`.
- **Bloc admin** (sous le hero, `v-if="auth.isAdmin"`, **non rendu** sinon) : champ **Renommer** + select **Fusionner dans** ; surface `--surface-2` + bordure tiretée `--line-2`, boutons neutres (hover bordure `--accent`).
- **Shelves** (scroll horizontal, `RelBlock`/`AppearRow` si adaptés) dans l'ordre **Artistes → Sets → Playlists** : carte artiste (avatar rond + N tracks + dot `--pos` si in-lib), carte set (artwork + **anneau %** `trackInGenre/trackTotal` repris du pilote Sets), carte playlist (cover + **badge source** DEEZER/SPOTIFY/TIDAL). Chaque block-head a un `Voir tout →`.
- **Bloc Tracks** = **liste compacte (PAS la table Catalog)** : barre `search` (debounce 250ms) + tri segmenté `Récent · BPM · Key · A–Z` + toggle `En bib` (`--pos`), puis rows compactes (play hover · cover 40px · titre/artiste · **BPM** mono `--ink-2` · **Key** mono `--accent-ink` · durée mono `--ink-3` · pastille `EN BIB` `--pos` ou bouton `+`). **Scroll infini** (IntersectionObserver, batch 50) branché sur la pagination serveur ; reset à chaque changement search/tri/lib. Réutilise `LibDot`/`InLibBadge`, `audioPlayer` store et `HeroPlayer` pour la preview.
- **Bloc Genres voisins** : chips/cartes `StyleTag`-teintées (dot + nom couleur famille + `N tracks · N artistes en commun`), clic → `/style/:genre`.
- **États** : hover (élévation cartes, play révélé) · empty (tracklist filtrée vide → message mono `--ink-3`) · loading (skeleton hero + shelves + rows) · **404 genre** (« Genre introuvable » + retour).
- **Responsive** : container-queries sur `.app` (≤900 sidebar rail · ≤820 outils Tracks pleine largeur · ≤640 paddings 18 + durée masquée · ≤560 mosaïque pleine largeur). Pas de media-queries viewport.

## 3. Conventions & clôture
- 100% tokens, mono pour **toutes** les données, `--accent` réservé action/key/CTA, in-lib = `--pos` uniquement, formes `--r-*`/`--shadow-*`, densité `--row-h`/`--pad`.
- Light **et** dark vérifiés ; admin **on/off** vérifié.
- À la fin : **coche** la ligne Genre Detail dans `design/ROADMAP-realign.md` et signale à willi tout écart backend rencontré.
