import { createRouter, createWebHistory } from 'vue-router'
import TracksView from './views/TracksView.vue'
import TagsView from './views/TagsView.vue'

const routes = [
  { path: '/', redirect: '/tracks' },
  { path: '/tracks', component: TracksView },
  { path: '/tags', component: TagsView },
]

export default createRouter({
  history: createWebHistory(),
  routes,
})
