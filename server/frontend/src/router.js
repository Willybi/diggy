import { createRouter, createWebHistory } from 'vue-router'
import GenresView        from './views/GenresView.vue'
import GenreDetailView   from './views/GenreDetailView.vue'
import CatalogView       from './views/CatalogView.vue'
import RadarView         from './views/RadarView.vue'
import WatchlistView     from './views/WatchlistView.vue'
import TrackDetailView   from './views/TrackDetailView.vue'
import ArtistDetailView  from './views/ArtistDetailView.vue'
import SetDetailView     from './views/SetDetailView.vue'
import PlaylistDetailView from './views/PlaylistDetailView.vue'
import ArtistsView        from './views/ArtistsView.vue'
import SetsView           from './views/SetsView.vue'
import AdminView          from './views/AdminView.vue'
import LoginView          from './views/LoginView.vue'

const routes = [
  { path: '/',             redirect: '/catalog' },
  { path: '/login',        component: LoginView, meta: { public: true } },
  { path: '/tracks',       redirect: '/catalog?inlib=true' },
  { path: '/genres',       component: GenresView },
  { path: '/tags',         redirect: '/genres' },
  { path: '/style/:genre(.*)', component: GenreDetailView, props: true },
  { path: '/catalog',      component: CatalogView },
  { path: '/catalog/:id',  component: TrackDetailView, props: true },
  { path: '/artist/:id',   component: ArtistDetailView, props: true },
  { path: '/sets',          component: SetsView },
  { path: '/set/:id',      component: SetDetailView, props: true },
  { path: '/artists',      component: ArtistsView },
  { path: '/admin',        component: AdminView },
  { path: '/radar',        component: RadarView },
  { path: '/playlists',      component: WatchlistView },
  { path: '/playlists/:id',  component: PlaylistDetailView, props: true },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

// Soft guard — pas encore enforced, juste la route /login disponible
router.beforeEach((to) => {
  // Phase 6 : décommenter pour enforcer l'auth
  // const auth = useAuthStore()
  // if (!to.meta.public && !auth.isAuthenticated) return '/login'
})

export default router
