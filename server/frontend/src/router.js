import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from './stores/auth'
import HubView from './views/HubView.vue'

const GenresView = () => import('./views/GenresView.vue')
const GenreDetailView = () => import('./views/GenreDetailView.vue')
const ExplorerView = () => import('./views/ExplorerView.vue')
const WatchlistView = () => import('./views/WatchlistView.vue')
const TrackDetailView = () => import('./views/TrackDetailView.vue')
const ArtistDetailView = () => import('./views/ArtistDetailView.vue')
const SetDetailView = () => import('./views/SetDetailView.vue')
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
  { path: '/artists', component: ArtistsView },
  { path: '/admin', component: AdminView },
  // Assumed gap until the dedicated Radar page ships (D6): plain Explorer.
  { path: '/radar', redirect: '/explorer' },
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

export default router
