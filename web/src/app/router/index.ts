import { createRouter, createWebHistory, type RouteRecordRaw, type RouterHistory } from 'vue-router'

import { useSessionStore } from '@/entities/session'
import { NAV_ITEMS, type NavKey } from '@/shared/config'
import { AppShell } from '@/widgets/app-shell'

import { authGuard } from './guard'

declare module 'vue-router' {
  interface RouteMeta {
    /** Which screen this is; the guard checks the role against it. */
    navKey?: NavKey
    /** Reachable without signing in. */
    public?: boolean
  }
}

const screens: RouteRecordRaw[] = NAV_ITEMS.map((item) => ({
  // "/" is the layout's own address, so the dashboard is its empty-path child; giving the child
  // the absolute "/" too would let the bare layout match first and render an empty page.
  path: item.path === '/' ? '' : item.path,
  name: item.key,
  component:
    item.key === 'dashboard'
      ? () => import('@/pages/dashboard')
      : () => import('@/pages/placeholder'),
  meta: { navKey: item.key },
}))

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'login',
    component: () => import('@/pages/login'),
    meta: { public: true },
  },
  {
    path: '',
    component: AppShell,
    children: [
      ...screens,
      { path: '/forbidden', name: 'forbidden', component: () => import('@/pages/forbidden') },
      { path: '/:pathMatch(.*)*', name: 'not-found', component: () => import('@/pages/not-found') },
    ],
  },
]

export function createAppRouter(history: RouterHistory = createWebHistory()) {
  const router = createRouter({ history, routes })

  router.beforeEach((to) => authGuard(to, useSessionStore()))

  // Screen-reader and tab-title friendly: say which screen we are on.
  router.afterEach((to) => {
    const item = NAV_ITEMS.find((i) => i.key === to.meta.navKey)
    document.title = `${item?.label ?? (to.name === 'login' ? 'Sign in' : 'Gijima')} · Gijima WFM`
  })

  return router
}
