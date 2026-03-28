import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/', name: 'dashboard', component: () => import('./views/Dashboard.vue') },
  { path: '/gallery', name: 'gallery', component: () => import('./views/Gallery.vue') },
  { path: '/videos', name: 'videos', component: () => import('./views/Videos.vue') },
  { path: '/render', name: 'render', component: () => import('./views/Render.vue') },
]

export default createRouter({
  history: createWebHistory(),
  routes,
})
