import { createRouter, createWebHistory } from 'vue-router'
import TagsView          from './views/TagsView.vue'
import CatalogView       from './views/CatalogView.vue'
import RadarView         from './views/RadarView.vue'
import TrackDetailView   from './views/TrackDetailView.vue'
import ArtistDetailView  from './views/ArtistDetailView.vue'
import SetDetailView     from './views/SetDetailView.vue'

const routes = [
  { path: '/',             redirect: '/catalog' },
  { path: '/tracks',       redirect: '/catalog?inlib=true' },
  { path: '/tags',         component: TagsView },
  { path: '/catalog',      component: CatalogView },
  { path: '/catalog/:id',  component: TrackDetailView, props: true },
  { path: '/artist/:id',   component: ArtistDetailView, props: true },
  { path: '/set/:id',      component: SetDetailView, props: true },
  { path: '/radar',        component: RadarView },
]

export default createRouter({
  history: createWebHistory(),
  routes,
})
