import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/', name: 'dashboard', component: () => import('./views/Dashboard.vue'), meta: { title: 'Dashboard' } },
  { path: '/gallery', name: 'gallery', component: () => import('./views/Gallery.vue'), meta: { title: 'Gallery' } },
  { path: '/compare', name: 'compare', component: () => import('./views/Compare.vue'), meta: { title: 'Compare' } },
  { path: '/videos', name: 'videos', component: () => import('./views/Videos.vue'), meta: { title: 'Videos' } },
  { path: '/render', name: 'render', component: () => import('./views/Render.vue'), meta: { title: 'Render' } },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.afterEach((to) => {
  document.title = to.meta.title ? `${to.meta.title} — Timelapse` : 'Timelapse'
})

export default router
