# A4 — Audit Frontend (`server/frontend/src/`)

> Audit READ-ONLY — 2026-07-09
> Périmètre : `server/frontend/src/` (17 vues, ~30 composants, 3 composables, 4 stores Pinia, utils).
> Méthode : greps mécaniques (références croisées, couleurs hardcodées, handlers inline, imports dynamiques, `setInterval`/`onUnmounted`), lecture ciblée des stores, composables, router, client API, et des sections fetch/pagination des grosses vues ; croisement systématique avec `_inventory.md` (§5, §6, §7, §8, §12) et le backend (`routers/opinions.py`, `routers/radar.py`, `routers/genres.py`) pour valider les appels API.
> Rappel asymétrie : les findings de suppression ne sont en confiance `haute` que sur preuve mécanique (grep exhaustif incluant imports dynamiques et tests).

## Ce qui va bien

- **Zéro couleur hardcodée respecté** : le grep `#[0-9a-fA-F]{3,8}|rgba?\(` sur tous les `.vue` et `assets/*.css` ne remonte que les 4 hex du logo Google (LoginView.vue:16-28), légitimes (couleurs de marque dans un SVG). La règle `diggy-tokens.css` est tenue.
- **Zéro handler inline multi-statements** : grep `@click="...;..."` → 0 occurrence. Le piège Prettier/compilateur Vue documenté dans CLAUDE.md est évité partout.
- **Client API centralisé sain** (`utils/api.js:11-33`) : injection du token sur chaque requête, auto-logout sur 401, toast global sur 5xx/erreur réseau — filet de sécurité pour les appels sans catch local.
- **Stores Pinia propres** : `opinions.set()` fait un optimistic update avec rollback (opinions.js:23-47) ; `opinions.reset()` est bien appelé au logout (App.vue:38) — pas de fuite de données entre utilisateurs ; `audioPlayer` gère correctement le cycle de vie de l'élément Audio unique.
- **Refactor AdminView réel et abouti** : AdminView.vue = 89 LOC (shell d'onglets), logique éclatée dans 6 composants `components/admin/*` (779+448+395+375+360+160 LOC). Le point « AdminView 1725 LOC » du brief original est obsolète.
- **Code-splitting fonctionnel** : toutes les vues sauf HubView sont lazy-loadées (router.js:5-19), chunks séparés confirmés par le build (§8 inventaire).
- **Guards de ré-entrance présents** sur l'infinite scroll : `loadMore()` vérifie `loading && hasMore` avant de fetch (ArtistsView.vue:175, GenresView.vue:160).
- **Chargement parallèle** dans GenreDetailView : detail d'abord puis `Promise.all` sur les 5 sous-fetches (GenreDetailView.vue:398-404).
- **Polling propre côté non-admin** : ImportRekordboxModal (`onUnmounted(stopPoll)`, :144), PlaylistDetailView (:315), WatchlistView (:395) nettoient tous leurs intervals au démontage.
- **Images** : `loading="lazy"` + `alt=""` + conteneurs dimensionnés en CSS (ex. HubView.vue:128-134) — pas de layout shift flagrant. Le `fetch()` natif d'ImportRekordboxModal ajoute bien le header `Authorization` (:198-202).

---

## Findings

### [A4-01] Badge radar mobile mort : appel `/radar/new-count` sans préfixe `/api`
- **ID** : A4-01
- **Type** : bug
- **Sévérité** : haute
- **Effort estimé** : S (< 1h)
- **Confiance** : haute
- **Preuve** :
  - `src/components/BottomNav.vue:58` : `const res = await api.get('/radar/new-count')`
  - `src/utils/api.js:6-8` : `axios.create({ baseURL: '/' })` — aucun préfixe `/api` n'est ajouté par l'instance.
  - `src/components/BottomNav.vue:65-66` : `onMounted(fetchNewCount)` + `watch(() => route.path, fetchNewCount)` — relancé à chaque navigation.
  - Backend : `server/api/routers/radar.py:111` : `@router.get("/new-count", ...)` monté sous `/api/radar` — l'endpoint correct est `/api/radar/new-count`.
  - `vite.config.js:15-19` : seul `/api` est proxifié en dev.
- **Constat** : la requête part vers `/radar/new-count`, URL qui n'existe ni en dev (Vite ne proxifie que `/api`) ni en prod (Nginx `^~ /api/` ne matche pas → fallback SPA qui renvoie `index.html` en 200). `res.data` est donc du HTML, `res.data.count` vaut `undefined`, et `?? 0` masque tout : le badge « new » du BottomNav mobile affiche toujours 0 depuis sa création. Bonus négatif : chaque changement de route mobile télécharge inutilement l'index.html.
- **Recommandation** : corriger en `api.get('/api/radar/new-count')`. Optionnel : ne fetcher que si `auth.isAuthenticated` (l'endpoint exige un user), et débouncer le refetch par navigation.
- **Dépendances** : aucune
- **Tags optionnels** : QUICK-WIN-CANDIDAT | lié-chantier:R1

### [A4-02] Avis track jamais persistés depuis TrackDetailView : POST vers un endpoint inexistant, avalé en silence
- **ID** : A4-02
- **Type** : bug
- **Sévérité** : haute
- **Effort estimé** : S (< 1h)
- **Confiance** : haute
- **Preuve** :
  - `src/views/TrackDetailView.vue:379-386` :
    ```js
    watch(opinion, async (val) => {
      if (!track.value) return
      try {
        await api.post(`/api/opinions/${track.value.id}`, { opinion: val })
      } catch {
        // silent
      }
    })
    ```
  - Backend `server/api/routers/opinions.py` : seules routes = `@router.get("/")` (:15) et `@router.patch("/")` (:31). Aucun `POST /opinions/{id}` → 404 garanti.
  - Lecture : `TrackDetailView.vue:501` initialise `opinion` depuis `data.avis` (GET `/api/catalog/{id}`), binding `<LikeDislike v-model="opinion" />` (:57).
  - Corroboration prod (inventaire §9) : `user_tracks.avis` est ~100 % NULL.
- **Constat** : cliquer like/dislike sur la page détail d'un track déclenche un POST vers une route qui n'existe pas ; le `catch {}` silencieux masque le 404 (le toast global ne couvre que les 5xx). L'UI affiche l'état choisi mais rien n'est sauvegardé — perdu au prochain rechargement. Trois mécanismes de persistance d'avis coexistent : le store (`PATCH /api/opinions/`, opinions.js:34), CatalogView (`PATCH /api/catalog/{id}/avis`, CatalogView.vue:535), et ce POST mort.
- **Recommandation** : remplacer le watch par un appel au mécanisme existant — soit `api.patch('/api/catalog/${id}/avis', { avis: val })` comme CatalogView, soit le store opinions (`opinions.set('track', id, val)`) — et trancher lequel des deux est canonique pour les tracks (un seul chemin de persistance).
- **Dépendances** : aucune
- **Tags optionnels** : QUICK-WIN-CANDIDAT

### [A4-03] Composant mort : `AppearRow.vue` (0 référence)
- **ID** : A4-03
- **Type** : dead-code
- **Sévérité** : basse
- **Effort estimé** : S (< 1h)
- **Confiance** : haute
- **Preuve** :
  - Grep `AppearRow` sur tout `server/frontend` → une seule occurrence : le fichier lui-même (`src/components/AppearRow.vue:7`, une entité HTML).
  - Tous les imports dynamiques du projet recensés : `router.js:5-19,46` (vues uniquement) et `__tests__/a11y.test.js` (router, LikeDislike, App) — aucun ne vise AppearRow.
- **Constat** : composant présentationnel de 61 LOC (ligne titre/sous-titre/flèche) jamais importé, ni statiquement, ni dynamiquement, ni dans les tests. Confirmation du candidat §7 de l'inventaire.
- **Recommandation** : supprimer `src/components/AppearRow.vue`.
- **Dépendances** : aucune
- **Tags optionnels** : QUICK-WIN-CANDIDAT

### [A4-04] Vue morte : `TagsView.vue` (0 référence, route redirigée)
- **ID** : A4-04
- **Type** : dead-code
- **Sévérité** : basse
- **Effort estimé** : S (< 1h)
- **Confiance** : haute
- **Preuve** :
  - `src/router.js:27` : `{ path: '/tags', redirect: '/genres' }` — la route historique redirige, aucune route ne monte TagsView.
  - Grep `TagsView` sur tout `server/frontend` → 0 référence hors le fichier lui-même ; aucun import dynamique (cf. preuve A4-03).
  - `src/views/TagsView.vue:35` appelle encore `GET /api/catalog/genres` — code jamais exécuté.
- **Constat** : vue de 98 LOC remplacée par GenresView, déjà documentée « dead view » dans CLAUDE.md. Confirmé mécaniquement (router + imports + tests).
- **Recommandation** : supprimer `src/views/TagsView.vue` et retirer la mention « 17 views (16 routed + 1 dead TagsView) » de CLAUDE.md.
- **Dépendances** : aucune
- **Tags optionnels** : QUICK-WIN-CANDIDAT

### [A4-05] Duplication quasi verbatim du pattern fetch + pagination entre ArtistsView et GenresView
- **ID** : A4-05
- **Type** : dette
- **Sévérité** : moyenne
- **Effort estimé** : M (1h-1j)
- **Confiance** : haute
- **Preuve** :
  - `src/views/ArtistsView.vue:147-178` et `src/views/GenresView.vue:128-163` — blocs quasi identiques :
    ```js
    // ArtistsView:158-171 ≈ GenresView:143-156
    const { data } = await api.get('/api/...', { params })
    if (reset) { items.value = data.items } else { items.value = [...items.value, ...data.items] }
    total.value = data.total
    familyCounts.value = data.pillarCounts || {}
    hasMore.value = items.value.length < data.total
    ```
  - `loadMore()` identique au nom près : ArtistsView.vue:174-178 vs GenresView.vue:159-163 (guard `loading || !hasMore`, `offset = items.length`, fetch(false)).
  - Watchers identiques : ArtistsView.vue:181-182 vs GenresView.vue:187-188 (`watch(sortBy/familyFilter, () => fetch(true))`).
  - Même state : `offset/items/total/hasMore/loading/familyFilter/searchQuery/sortBy` dans les deux vues, même usage `useInfiniteScroll(loadMore)` (:184 / :190).
- **Constat** : deux implémentations parallèles du même pattern liste paginée + filtres famille + recherche + infinite scroll, qui divergeront à la première évolution (c'est déjà le cas : ArtistsView a une branche « opinion filter » :106-145 que GenresView traite en `displayItems` computed :117-125).
- **Recommandation** : extraire un composable `usePaginatedList({ endpoint, pageSize })` retournant `{ items, total, hasMore, loading, familyCounts, reset, loadMore, sentinel }`, l'adopter dans ces deux vues d'abord (périmètre borné ; CatalogView reste en pagination par pages, hors scope).
- **Dépendances** : A4-08 (toiletter `useInfiniteScroll` au passage)
- **Tags optionnels** : aucun

### [A4-06] Intervals de polling admin jamais nettoyés au démontage du composant
- **ID** : A4-06
- **Type** : bug
- **Sévérité** : moyenne
- **Effort estimé** : M (1h-1j)
- **Confiance** : haute
- **Preuve** :
  - 5 `setInterval` de polling de tâches Celery dans `components/admin/` : AdminArtists.vue:258 et :296, AdminBeatport.vue:53, AdminSets.vue:179 et :217.
  - Grep `onUnmounted` sur `src/components/admin/` → **0 occurrence** (contre-exemples corrects ailleurs : ImportRekordboxModal.vue:144, PlaylistDetailView.vue:315, WatchlistView.vue:395).
  - Les `clearInterval` existants ne couvrent que les états terminaux de la tâche (ex. AdminArtists.vue:299-315 : clear sur SUCCESS/FAILURE/erreur réseau).
- **Constat** : si l'admin quitte `/admin` pendant une tâche longue (sync artistes, enrich Beatport — plusieurs minutes), l'interval survit au composant et continue de poller `/api/admin/artists/sync/status/{id}` toutes les 2 s en arrière-plan, mutant l'état d'un composant démonté, jusqu'à la fin de la tâche Celery. Cumulable si l'admin revient et relance.
- **Recommandation** : dans chaque composant admin concerné, stocker le timer et le `clearInterval` dans un `onUnmounted` (ou traiter via A4-07 en une passe).
- **Dépendances** : aucune (A4-07 le résout aussi)
- **Tags optionnels** : QUICK-WIN-CANDIDAT

### [A4-07] Pattern « poll status de tâche Celery » réimplémenté 7 fois
- **ID** : A4-07
- **Type** : dette
- **Sévérité** : moyenne
- **Effort estimé** : M (1h-1j)
- **Confiance** : haute
- **Preuve** : 7 implémentations du même motif `setInterval` + GET status + clear sur état terminal :
  - AdminArtists.vue:258-276 et :296-316, AdminBeatport.vue:53-74, AdminSets.vue:179-200 et :217-238 (tous sur `/api/admin/artists/sync/status/{task_id}`)
  - ImportRekordboxModal.vue:230+ (sur `/api/import/status/{taskId}`)
  - PlaylistDetailView.vue:248-268 et WatchlistView.vue:336-370 (sur `/api/watchlist/{id}/crawl-status`)
- **Constat** : même logique (intervalle, fetch status, branchement SUCCESS/FAILURE, clear, message) copiée-collée avec de petites variations, dont l'oubli systématique du cleanup côté admin (A4-06). Toute correction (backoff, gestion d'erreur réseau, cleanup) doit aujourd'hui être répliquée 7 fois.
- **Recommandation** : extraire un composable `useTaskPoll(statusUrlFn, { intervalMs, onDone, onError })` qui gère interval, états terminaux et `onUnmounted` ; migrer d'abord les 5 occurrences admin (mêmes endpoint et sémantique).
- **Dépendances** : corrige A4-06 par construction
- **Tags optionnels** : aucun

### [A4-08] `useInfiniteScroll` : `loading` retourné mais jamais muté ni consommé
- **ID** : A4-08
- **Type** : dead-code
- **Sévérité** : basse
- **Effort estimé** : S (< 1h)
- **Confiance** : haute
- **Preuve** :
  - `src/composables/useInfiniteScroll.js:5` : `const loading = ref(false)` — jamais réassigné dans le composable ; `:27` : `return { sentinel, loading }`.
  - Les deux seuls consommateurs ne déstructurent que `sentinel` : ArtistsView.vue:184 et GenresView.vue:190 (`const { sentinel } = useInfiniteScroll(loadMore)`), chacun gérant son propre `loading` local.
- **Constat** : le `loading` du composable est du code mort trompeur — il suggère que le composable gère l'état de chargement/la ré-entrance alors qu'il ne fait ni l'un ni l'autre (la protection vit dans les `loadMore()` appelants).
- **Recommandation** : retirer `loading` du retour du composable, ou au contraire y intégrer le guard de ré-entrance (à trancher avec A4-05 si `usePaginatedList` est créé).
- **Dépendances** : A4-05 (même zone)
- **Tags optionnels** : QUICK-WIN-CANDIDAT

### [A4-09] HubView (1511 LOC) embarqué dans le bundle principal
- **ID** : A4-09
- **Type** : perf
- **Sévérité** : moyenne
- **Effort estimé** : M (1h-1j)
- **Confiance** : haute
- **Preuve** :
  - `src/router.js:3` : `import HubView from './views/HubView.vue'` — seul import statique de vue ; toutes les autres sont lazy (:5-19).
  - Inventaire §8 : `index-*.js` = 191,55 kB (gzip 72 kB), aucun chunk HubView séparé ; §12 : HubView = 1511 LOC, la plus grosse vue du projet.
- **Constat** : HubView et ses dépendances propres (FamilyChips, ShelfCard, GenreCard, SegFilter…) sont payées par tous les visiteurs sur toutes les routes d'entrée, y compris `/login` et les deep links `/catalog/:id`. Le choix est défendable (Hub = route par défaut, éviter un aller-retour au premier paint), mais le coût croît avec chaque évolution du Hub — c'est un cliquet.
- **Recommandation** : ne pas forcément lazy-loader le Hub (LCP de la route `/`), mais réduire ce qu'il embarque : scinder HubView en sections composants (recherche, tendances, shelves) et lazy-loader les sections sous le fold, ou déplacer la logique tendances dans un composant asynchrone. Mesurer avant/après avec `vite build`.
- **Dépendances** : aucune
- **Tags optionnels** : hors-domaine:design (découpage à valider avec la référence `_design/PAGES_REFERENCE.md`)

### [A4-10] Incohérence de trailing slash : `GET /api/genres/` déclenche un redirect 307 à chaque chargement du Hub
- **ID** : A4-10
- **Type** : convention
- **Sévérité** : basse
- **Effort estimé** : S (< 1h)
- **Confiance** : haute
- **Preuve** :
  - `src/views/HubView.vue:342` : `api.get('/api/genres/', ...)` — avec slash final.
  - Backend `server/api/routers/genres.py:50` : `@router.get("", ...)` — la route est `/api/genres` **sans** slash (contrairement à catalog/artists/sets/collections qui déclarent `"/"`).
  - Les autres appelants utilisent la forme correcte : GenresView.vue:143 et GenreDetailView.vue:574 (`'/api/genres'`).
- **Constat** : chaque affichage du Hub paie un aller-retour supplémentaire (307 `redirect_slashes` de Starlette) sur la requête des genres populaires. Symétriquement, le mélange `""` vs `"/"` côté routers rend l'erreur facile à reproduire.
- **Recommandation** : corriger HubView.vue:342 en `'/api/genres'`. Suggestion hors périmètre : harmoniser la déclaration racine des routers backend (`""` vs `"/"`).
- **Dépendances** : aucune
- **Tags optionnels** : QUICK-WIN-CANDIDAT | hors-domaine:backend (harmonisation routers)

### [A4-11] AdminGenres : 3 appels à `/api/taxonomy/mappings` là où 2 suffisent, et stats sans gestion d'erreur
- **ID** : A4-11
- **Type** : dette
- **Sévérité** : basse
- **Effort estimé** : S (< 1h)
- **Confiance** : haute
- **Preuve** :
  - `src/components/admin/AdminGenres.vue:177` : `fetchMappings` (limit 200) reçoit déjà `data.total`.
  - `:190-196` : `fetchMappingStats` refait deux GET `limit: 1` (total + unmapped) via `Promise.all`, sans `try/catch` — un échec produit une unhandled rejection (le toast global ne couvre que les 5xx).
- **Constat** : au chargement de l'onglet mappings, le même endpoint est appelé 3 fois ; le total du fetch principal est ignoré. Impact faible (page admin), mais le pattern « compter via limit=1 » mérite d'être borné.
- **Recommandation** : dériver la moitié des stats du fetch principal (un seul appel `limit: 1` restant pour la variante opposée), et entourer `fetchMappingStats` d'un try/catch.
- **Dépendances** : aucune
- **Tags optionnels** : QUICK-WIN-CANDIDAT

### [A4-12] Styles utilitaires re-déclarés par vue au lieu d'être factorisés (`.state` ×10, `@keyframes spin` ×4)
- **ID** : A4-12
- **Type** : dette
- **Sévérité** : basse
- **Effort estimé** : M (1h-1j)
- **Confiance** : moyenne
- **Preuve** :
  - `.state {` (message vide/chargement) déclaré dans 10 vues : ArtistDetailView.vue:846, CatalogView.vue:1125, CollectionDetailView.vue:398, CollectionsView.vue:321, PlaylistDetailView.vue:477, SetDetailView.vue:609, SetsView.vue:799, TagsView.vue:93, TrackDetailView.vue:521, WatchlistView.vue:791 — avec dérive entre copies (ex. CatalogView : `text-align:center; font mono` vs SetsView : `font-style:italic; font ui`).
  - `@keyframes spin` dupliqué dans ArtistsView.vue:257, GenreDetailView.vue:1133, GenresView.vue:318, ImportRekordboxModal.vue:444.
- **Constat** : le même concept UI (« état vide/chargement », spinner) est re-stylé localement dans chaque vue scoped, avec des variations non intentionnelles — incohérence visuelle rampante et poids CSS dupliqué (les CSS par vue pèsent 16-24 kB, §8). Confiance moyenne : les blocs ne sont pas byte-identiques, une part des variations est peut-être voulue.
- **Recommandation** : ajouter une classe utilitaire `.state` et le keyframe `spin` dans `assets/page.css` (déjà le lieu des styles partagés), migrer vue par vue en validant visuellement contre `/design-system`.
- **Dépendances** : A4-04 (TagsView disparaît de la liste)
- **Tags optionnels** : hors-domaine:design

---

## Non couvert (budget)

- **Code mort intra-fichier des grosses vues** (HubView 1511 LOC, GenreDetailView 1255, CatalogView 1193) : l'analyse fonction-par-fonction (computed/méthodes orphelins, watchers coûteux) n'a pas été réalisée — l'agent d'exploration dédié n'a pas abouti. Signal préliminaire uniquement : rien de flagrant dans les sections lues (HubView:118-202, GenreDetailView:390-620, CatalogView:380-510).
- **Comparaison exhaustive des styles inter-vues** : seuls `.state` et `@keyframes spin` ont été échantillonnés (A4-12) ; un passage outillé (ex. hash des blocs CSS) trouverait probablement d'autres doublons (tables, grids de cartes, skeletons).
- **Accessibilité** : pas d'audit — constats ponctuels positifs seulement (`aria-live="polite"` HubView:149, `aria-pressed` LikeDislike.vue:7,20, test `a11y.test.js` existant).
- **Endpoints backend sans appelant frontend** (inventaire §6, ex. `radar GET /full`, `tracks GET /`, 8 endpoints taxonomy) : la contrepartie backend (dead code côté API) relève de l'agent backend ; côté frontend, aucun appel vers un endpoint inexistant autre que A4-01/A4-02 n'a été trouvé.
