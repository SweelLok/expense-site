import { createRouter, createWebHistory } from 'vue-router'
import { api } from './api'
import { bootstrap, state } from './store'

const routes = [
  { path: '/login', name: 'login', component: () => import('./views/Login.vue'), meta: { public: true } },
  { path: '/', name: 'dashboard', component: () => import('./views/Dashboard.vue') },
  { path: '/stats', name: 'stats', component: () => import('./views/Stats.vue') },
  { path: '/subs', name: 'subs', component: () => import('./views/Subs.vue') },
  { path: '/admin', name: 'admin', component: () => import('./views/Admin.vue') },
  { path: '/:pathMatch(.*)*', redirect: '/' },
]

const router = createRouter({ history: createWebHistory(), routes })

router.beforeEach(async (to) => {
  if (!state.authed && !state.loading) {
    // Первый переход: спрашиваем бэкенд один раз, а не на каждой странице.
    await bootstrap()
  }
  if (!to.meta.public && !state.authed) return { name: 'login', query: { next: to.fullPath } }
  if (to.name === 'login' && state.authed) return { name: 'dashboard' }
  return true
})

api.onUnauthorized = () => {
  state.authed = false
}

export default router
