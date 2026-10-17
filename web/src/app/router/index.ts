import { createRouter, createWebHistory, type RouteRecordRaw, type RouterHistory } from 'vue-router'

import { useSessionStore } from '@/entities/session'
import { NAV_ITEMS, type NavKey } from '@/shared/config'
import { recordRouteChange } from '@/shared/telemetry'
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

/** Screens that exist for real. Every other screen is an honest placeholder until its phase. */
const BUILT_SCREENS: Partial<Record<NavKey, RouteRecordRaw['component']>> = {
  dashboard: () => import('@/pages/dashboard'),
  imports: () => import('@/pages/imports'),
  forecast: () => import('@/pages/forecast'),
  planner: () => import('@/pages/staffing/planner'),
  roster: () => import('@/pages/staffing/roster'),
  recommendations: () => import('@/pages/staffing/recommendations'),
  employees: () => import('@/pages/employees'),
  configure: () => import('@/pages/configure'),
  capacity: () => import('@/pages/capacity'),
  calibration: () => import('@/pages/insight/calibration'),
  leave: () => import('@/pages/leave'),
  swaps: () => import('@/pages/swaps'),
  users: () => import('@/pages/users'),
  contracts: () => import('@/pages/contracts'),
  peaks: () => import('@/pages/insight/peaks'),
  analytics: () => import('@/pages/insight/analytics'),
  intraday: () => import('@/pages/intraday'),
  reports: () => import('@/pages/insight/reports'),
  overtime: () => import('@/pages/overtime'),
  shrinkage: () => import('@/pages/shrinkage'),
  'my-schedule': () => import('@/pages/my/schedule'),
  'my-availability': () => import('@/pages/my/availability'),
  'service-desk': () => import('@/pages/service-desk'),
}

const screens: RouteRecordRaw[] = NAV_ITEMS.map((item) => ({
  // "/" is the layout's own address, so the dashboard is its empty-path child; giving the child
  // the absolute "/" too would let the bare layout match first and render an empty page.
  path: item.path === '/' ? '' : item.path,
  name: item.key,
  component: BUILT_SCREENS[item.key] ?? (() => import('@/pages/placeholder')),
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
    path: '/change-password',
    name: 'change-password',
    component: () => import('@/pages/change-password'),
  },
  {
    path: '',
    component: AppShell,
    children: [
      ...screens,
      { path: '/forbidden', name: 'forbidden', component: () => import('@/pages/forbidden') },
      {
        path: '/unavailable',
        name: 'unavailable',
        component: () => import('@/pages/unavailable'),
      },
      { path: '/:pathMatch(.*)*', name: 'not-found', component: () => import('@/pages/not-found') },
    ],
  },
]

export function createAppRouter(history: RouterHistory = createWebHistory()) {
  const router = createRouter({ history, routes })

  router.beforeEach((to) => authGuard(to, useSessionStore()))

  // Screen-reader and tab-title friendly: say which screen we are on.
  router.afterEach((to) => {
    // Route *name* only: params and query strings can hold identifiers.
    recordRouteChange(String(to.name ?? 'unknown'))
    const item = NAV_ITEMS.find((i) => i.key === to.meta.navKey)
    document.title = `${item?.label ?? (to.name === 'login' ? 'Sign in' : 'Gijima')} · Gijima WFM`
  })

  return router
}
