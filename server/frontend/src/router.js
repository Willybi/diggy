import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from './stores/auth'
import { createChunkPrefetcher } from './utils/prefetch.js'
import HubView from './views/HubView.vue'

const GenresView = () => import('./views/GenresView.vue')
const GenreDetailView = () => import('./views/GenreDetailView.vue')
const ExplorerView = () => import('./views/ExplorerView.vue')
const RadarView = () => import('./views/RadarView.vue')
const WatchlistView = () => import('./views/WatchlistView.vue')
const TrackDetailView = () => import('./views/TrackDetailView.vue')
const ArtistDetailView = () => import('./views/ArtistDetailView.vue')
const SetDetailView = () => import('./views/SetDetailView.vue')
const AlbumView = () => import('./views/AlbumView.vue')
const PlaylistDetailView = () => import('./views/PlaylistDetailView.vue')
const ArtistsView = () => import('./views/ArtistsView.vue')
const SetsView = () => import('./views/SetsView.vue')
const CollectionsView = () => import('./views/CollectionsView.vue')
const CollectionDetailView = () => import('./views/CollectionDetailView.vue')
const AdminView = () => import('./views/AdminView.vue')
const LoginView = () => import('./views/LoginView.vue')
const LoginCallbackView = () => import('./views/LoginCallbackView.vue')

const routes = [
  { path: '/', component: HubView, meta: { public: true } },
  { path: '/login', component: LoginView, meta: { public: true } },
  { path: '/login/callback', component: LoginCallbackView, meta: { public: true } },
  { path: '/tracks', redirect: '/explorer?lib=in' },
  { path: '/genres', component: GenresView },
  { path: '/style/:genre(.*)', component: GenreDetailView, props: true },
  { path: '/explorer', component: ExplorerView },
  // Legacy route — the query is carried over (e.g. /catalog?genre=X from old
  // links), remapping the renamed/removed filters: ?inlib=true → ?lib=in (bib
  // filter), and ?view (radar, dropped) is discarded. Anything else passes through.
  {
    path: '/catalog',
    redirect: (to) => {
      const query = { ...to.query }
      if (query.inlib === 'true') query.lib = 'in'
      delete query.inlib
      delete query.view
      return { path: '/explorer', query }
    },
  },
  { path: '/catalog/:id', component: TrackDetailView, props: true },
  { path: '/artist/:id', component: ArtistDetailView, props: true },
  { path: '/sets', component: SetsView },
  { path: '/set/:id', component: SetDetailView, props: true },
  { path: '/album/:id', component: AlbumView, props: true },
  { path: '/artists', component: ArtistsView },
  { path: '/admin', component: AdminView },
  { path: '/radar', component: RadarView },
  { path: '/collections', component: CollectionsView },
  { path: '/collections/:id', component: CollectionDetailView, props: true },
  { path: '/playlists', component: WatchlistView },
  { path: '/playlists/:id', component: PlaylistDetailView, props: true },
  // Dev-only : vitrine de non-régression visuelle du design system.
  ...(import.meta.env.DEV
    ? [
        {
          path: '/design-system',
          component: () => import('./views/DesignSystemView.vue'),
          meta: { public: true },
        },
      ]
    : []),
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to) => {
  const auth = useAuthStore()
  if (!to.meta.public && !auth.isAuthenticated) return '/'
})

// Un déploiement remplace TOUS les assets hashés. Un onglet ouvert avant le
// déploiement 404 dès qu'il charge en lazy un chunk de route qui n'existe plus
// (« Importing a module script failed »). On récupère en forçant UN rechargement
// complet de la route cible — il re-télécharge index.html et ses nouveaux hash.
// Garde anti-boucle : si un vrai déploiement est cassé (chunk réellement absent),
// on ne recharge pas en boucle, l'erreur remonte normalement dans la console.
const CHUNK_LOAD_ERROR =
  /Importing a module script failed|Failed to fetch dynamically imported module|error loading dynamically imported module/i

function reloadForStaleChunk(targetPath) {
  const KEY = 'diggy:chunk-reloaded-at'
  const last = Number(sessionStorage.getItem(KEY) || 0)
  if (Date.now() - last < 10_000) return false // déjà tenté récemment
  sessionStorage.setItem(KEY, String(Date.now()))
  window.location.assign(targetPath)
  return true
}

router.onError((error, to) => {
  if (CHUNK_LOAD_ERROR.test(error?.message || '') || error?.name === 'ChunkLoadError') {
    reloadForStaleChunk(to?.fullPath || window.location.pathname)
  }
})

// Vite émet cet événement sur window quand le modulepreload d'un import
// dynamique échoue, souvent AVANT l'erreur du routeur — même garde partagée.
window.addEventListener('vite:preloadError', (event) => {
  if (reloadForStaleChunk(window.location.pathname)) event.preventDefault()
})

// D9.c — prefetch du chunk d'une route au survol / focus de la nav. On dérive la
// map path → loader lazy des routes existantes (pas de duplication d'imports) :
// seules les vues chargées en lazy (`component` = fonction) y figurent ; les
// redirects et HubView (chargé en dur) n'ont pas de chunk à précharger.
const lazyLoaderByPath = new Map()
for (const route of routes) {
  if (typeof route.component === 'function') {
    lazyLoaderByPath.set(route.path, route.component)
  }
}

// `prefetchRoute(path)` invoque UNE fois le loader de la route cible (dédup + catch
// silencieux). Appelé par SidebarNav / BottomNav sur @mouseenter / @focus — jamais
// au montage. Ne précharge que le chunk JS, aucune donnée.
export const prefetchRoute = createChunkPrefetcher(lazyLoaderByPath)

export default router
