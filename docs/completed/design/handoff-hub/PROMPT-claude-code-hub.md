# Prompt Claude Code — Hub de recherche / Accueil `/`

> Copie-colle ce bloc à Claude Code dans le repo **Willybi/diggy** (FastAPI + Vue 3, branche `master`).
> Lis d'abord `design/CLAUDE.md`. Maquette de référence : `design/realign/Hub de recherche (pilote).html` — **Direction A « Spotlight »** (gros logo + barre centrée). Brief détaillé : `design/realign/BRIEF-hub.md`.
> Les Directions B/C de la maquette n'étaient que de l'exploration → **ne pas les coder**.
> Zéro valeur hors-tokens. Mono = données, UI = libellés. `--accent` = action/CTA/key/surlignage ; bib = `--pos`.

---

## Contexte & objectif

Diggy n'a pas de page d'accueil : `router.js` fait `{ path: '/', redirect: '/catalog' }`. On crée une **vraie landing** :
un **hub de recherche** qui devient **la page par défaut**, et **la seule page accessible en non-connecté**.

- **Visiteur (non-connecté)** : arrive sur `/`. Peut **chercher dans tout** (tracks, artistes, sets, playlists, genres) et
  **écouter les aperçus 30s**, mais **pas deep-dive** : ouvrir une fiche, actions bib, tri/filtres et les résultats
  au-delà des N premiers sont **verrouillés** (relance login). **Pas de sidebar** : le hub est plein cadre.
- **Connecté** : la **même page**, **déverrouillée** (résultats cliquables → fiches, actions bib, tri/filtres), et la
  **sidebar réapparaît** — le hub devient une entrée de navigation normale (item « Recherche » en tête de sidebar).

Tout le comportement (moteur, scope, gating, lignes de résultats) est dans la maquette Dir A. Reproduis-la au pixel via les composants existants.

---

## 1. 🛑 BACKEND D'ABORD — endpoint de recherche unifié (n'existe pas)

Crée `server/api/routers/search.py`, monté dans `main.py` : `app.include_router(search.router, prefix="/api")`.

```
GET /api/search?q=<str>&scope=all|track|artist|set|playlist|genre&limit=<int>&offset=<int>
```

- **Auth** : `user: User | None = Depends(get_current_user_optional)` + `uid = _uid(user)` (même soft-mode que `catalog.py`). **Doit répondre sans token.**
- **Recherche** : `ilike('%q%')` sur le champ nom de chaque entité (réutilise les requêtes existantes) :
  - `track` → `CatalogEntry.title | CatalogEntry.artist` (cf. `routers/catalog.py › list_catalog`, branche `search`). Renvoie `{id, title, artist, bpm, key, duration_ms, has_artwork, has_preview, in_lib}`.
  - `artist` → `Artist.name` (cf. `routers/artists.py`). Renvoie `{id, name, track_count, has_artwork, in_lib_count}`.
  - `set` → `DJSet.title` (cf. `routers/sets.py`). Renvoie `{id, title, played_date, track_count, has_artwork}`.
  - `playlist` → `WatchedEntity.title` (cf. `routers/watchlist.py`). Renvoie `{id, title, source, track_count, artwork_url}`.
  - `genre` → `DISTINCT CatalogEntry.genre` (réutilise `routers/genres.py` : `genre_family()` + agrégats `trackCount/artistCount/bpm p5–p95`). Renvoie `{name, family, track_count, artist_count, bpm_lo, bpm_hi}`.
- **Réponse** : liste **typée mélangée** `{ items: [{type, ...}], total: <int>, totals: {track, artist, ...} }`, **triée par pertinence serveur** : exact > prefix (`ilike('q%')`) > substring, tie-break sur la popularité (nb tracks / nb appearances). `scope != all` ⇒ filtre au type.
- **Gating serveur** : si `user is None` ⇒ **cap** la liste à `GUEST_CAP` (constante = **6**, alignée maquette) **et** force les champs perso (`in_lib`, `in_lib_count`, `avis`) à `null/0`. Renvoie quand même `total` (réel) pour afficher « N autres résultats ».
- **Perf** : `LIMIT` par type avant fusion ; pas de N+1. Pas de nouvelle table ni migration (lecture seule).

> Réutilise au maximum les sous-requêtes/agrégats déjà écrits (`in_lib` via `UserTrack`, `track_count`, percentiles BPM). Ne réécris pas la logique genre — appelle/duplique le helper de `genres.py`.

---

## 2. Frontend — nouvelle vue `HubView.vue`

Crée `server/frontend/src/views/HubView.vue` d'après la maquette **Dir A**. Réutilise l'existant, n'invente rien :

- **Stores** : `useAuthStore()` (`isAuthenticated`, `user`, `logout`), `useAudioPlayer()` (`play({catalog_id,title,artist,bpm,key})` pour une track ; `playRandomArtist(artistId)` pour l'aperçu d'un artiste), `useOpinionsStore()` si besoin. `axios.get('/api/search', { params })` avec `auth.authHeaders()`.
- **Composants partagés** : `StyleTag`, `LibDot`, `InLibBadge`, `format.js` (durée/nombres), `diggy-style-map.js` (teinte famille des genres/artworks).
- **Barre** : input (debounce ~150 ms) + **dropdown scope** `Tout · Tracks · Artistes · Sets · Playlists · Genres` (défaut **Tout**). Surligne le terme (`<mark>` → `--accent-soft`/`--accent-ink`).
- **État vide** : gros wordmark Diggy centré + tagline + barre + **genres populaires** (chips teintés famille) + quelques **suggestions de requête**. (Charge les genres top via `/api/search?scope=genre&q=` ou l'endpoint genres existant.)
- **Résultats** : **liste unique mélangée** triée pertinence, chaque ligne avec **badge de type** (icône + label mono) ; rendu par type exactement comme la maquette (track : artwork+play, bpm/key/durée, zone bib ; artist : avatar rond initiales/PP, N tracks, play=aperçu ; set : artwork+titre+date·N ; playlist : cover+badge source ; genre : pastille famille+stats).
- **Aperçu** : clic sur l'artwork d'une track → `player.play(...)` ; sur un artiste → `player.playRandomArtist(id)`. **Autorisé visiteur ET connecté** (le `PlayerBar` global de `App.vue` s'affiche déjà via `player.visible`).

### Gating (selon `auth.isAuthenticated`)
| | Visiteur | Connecté |
|---|---|---|
| Résultats | cappés (serveur) + **lock row** « Connecte-toi pour voir les N autres » | tous |
| Clic sur une ligne (hors play) | **relance** → `router.push('/login')` (toast/contextuel, cf. maquette) | navigue vers la fiche (`/catalog/:id`, `/artist/:id`, `/set/:id`, `/playlists/:id`, `/style/:genre`) |
| Boutons bib (ajout/avis) | masqués | visibles (réutilise le pattern `PATCH /api/catalog/:id/avis` / lib) |
| Tri & filtres | chip verrouillé « connecte-toi » | actifs |
| Sidebar | masquée | visible |
| Haut-droite | **Se connecter** (+ Créer un compte) → `/login` | chip user |

---

## 3. Frontend — câblage (router + App.vue)

**`router.js`**
- Remplace `{ path: '/', redirect: '/catalog' }` par `{ path: '/', component: HubView, meta: { public: true } }` (importe `HubView`).
- Garde toutes les autres routes. Active le **soft guard** existant en mode « hub » : pour un visiteur, une route **non `public`** redirige vers **`/`** (le hub), **pas** `/login` :
  ```js
  router.beforeEach((to) => {
    const auth = useAuthStore()
    if (!to.meta.public && !auth.isAuthenticated) return '/'
  })
  ```
  (`/login` est déjà `meta.public`. Laisse les pages profondes accessibles une fois connecté.)

**`App.vue`**
- **Masque la sidebar quand non-connecté** et passe en colonne unique :
  ```vue
  <SidebarNav v-if="auth.isAuthenticated" class="app-sidebar" />
  ```
  ```css
  .app-container:has(.app-sidebar) .app-shell { grid-template-columns: var(--sidebar-w) 1fr; }
  /* sans sidebar → 1 colonne */
  .app-shell { grid-template-columns: 1fr; }
  ```
  (ou bind une classe `:class="{ 'no-sidebar': !auth.isAuthenticated }"`). Le `PlayerBar` et le container query 900px restent inchangés.
- Quand connecté, ajoute l'item **« Recherche »** en tête de `SidebarNav.vue` (icône loupe, route `/`, actif sur `/`).

---

## Checklist de sortie
- [ ] `/api/search` répond **sans token**, liste typée triée pertinence, `total` + cap visiteur (6) + champs perso nullés en visiteur.
- [ ] `/` = HubView, public, rendu **plein cadre sans sidebar** en visiteur, **avec sidebar** en connecté.
- [ ] Recherche transverse + scope (défaut Tout) + surlignage + debounce.
- [ ] Aperçu 30s OK visiteur & connecté (track + artiste) via le store audio existant.
- [ ] Gating : lock row, clic fiche → `/login` en visiteur / navigation en connecté, bib & tri masqués en visiteur.
- [ ] Se connecter / Créer un compte → `/login` ; retour sur `/` après login.
- [ ] 100% tokens, mono/ui respectés, dark mode OK, responsive (rail 900 / durée masquée 680).
- [ ] **Ne pas** coder les Directions B/C.

## À confirmer avec willi (avant de coder)
- `GUEST_CAP` = 6 ?  ·  Afficher le `total` réel (« N autres ») au visiteur ou un libellé flou ?
- Scope par défaut = Tout, dropdown complet — OK ?
- Aperçu artiste = `playRandomArtist` (top/random track) — OK ?
