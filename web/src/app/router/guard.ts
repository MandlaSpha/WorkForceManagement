import type { RouteLocationNormalized, RouteLocationRaw } from 'vue-router'

import { canAccess, homePathFor, isAvailable, type useSessionStore } from '@/entities/session'

type SessionStore = ReturnType<typeof useSessionStore>

/**
 * Route guard: sign-in required for everything except public routes, and each screen only for the
 * roles allowed to open it. This is a courtesy for the user; the API refuses anything a role may
 * not do regardless of what the UI shows.
 */
export async function authGuard(
  to: RouteLocationNormalized,
  session: SessionStore,
): Promise<true | RouteLocationRaw> {
  if (session.status === 'unknown') await session.load()
  const user = session.status === 'authenticated' ? session.user : null

  if (to.meta.public) {
    return user && to.name === 'login' ? homePathFor(user.role) : true
  }
  if (!user) return { name: 'login', query: { redirect: to.fullPath } }

  const key = to.meta.navKey
  if (key && !canAccess(user.role, key)) {
    // "/" is the generic landing address: send each role to its own home instead of a 403.
    return to.path === '/' ? homePathFor(user.role) : { name: 'forbidden' }
  }
  // The role may open it but the feature is switched off for this deployment (FEAT-04).
  if (key && !isAvailable(user.features, key)) return { name: 'unavailable' }
  return true
}
