import { createRouter, createWebHistory } from 'vue-router'
import TracksView  from './views/TracksView.vue'
import TagsView    from './views/TagsView.vue'
import CatalogView from './views/CatalogView.vue'
import RadarView   from './views/RadarView.vue'

const routes = [
  { path: '/',        redirect: '/tracks' },
  { path: '/tracks',  component: TracksView },
  { path: '/tags',    component: TagsView },
  { path: '/catalog', component: CatalogView },
  { path: '/radar',   component: RadarView },
]

export default createRouter({
  history: createWebHistory(),
  routes,
})
