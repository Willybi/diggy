import { createRouter, createWebHistory } from 'vue-router'
import TagsView    from './views/TagsView.vue'
import CatalogView from './views/CatalogView.vue'
import RadarView   from './views/RadarView.vue'

const routes = [
  { path: '/',        redirect: '/catalog' },
  { path: '/tracks',  redirect: '/catalog?inlib=true' },
  { path: '/tags',    component: TagsView },
  { path: '/catalog', component: CatalogView },
  { path: '/radar',   component: RadarView },
]

export default createRouter({
  history: createWebHistory(),
  routes,
})
