import { createRouter, createWebHistory } from 'vue-router'
import TagsView          from './views/TagsView.vue'
import CatalogView       from './views/CatalogView.vue'
import RadarView         from './views/RadarView.vue'
import WatchlistView     from './views/WatchlistView.vue'
import TrackDetailView   from './views/TrackDetailView.vue'
import ArtistDetailView  from './views/ArtistDetailView.vue'
import SetDetailView     from './views/SetDetailView.vue'
import LoginView         from './views/LoginView.vue'

const routes = [
  { path: '/',             redirect: '/catalog' },
  { path: '/login',        component: LoginView, meta: { public: true } },
  { path: '/tracks',       redirect: '/catalog?inlib=true' },
  { path: '/tags',         component: TagsView },
  { path: '/catalog',      component: CatalogView },
  { path: '/catalog/:id',  component: TrackDetailView, props: true },
  { path: '/artist/:id',   component: ArtistDetailView, props: true },
  { path: '/set/:id',      component: SetDetailView, props: true },
  { path: '/radar',        component: RadarView },
  { path: '/playlists',    component: WatchlistView },
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
