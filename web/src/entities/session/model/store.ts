import { defineStore } from 'pinia'
import { ref, watch } from 'vue'

import { api, ApiProblem, setUnauthorisedHandler, toProblem } from '@/shared/api'
import type { FeatureKey } from '@/shared/config'
import { setTelemetryRole } from '@/shared/telemetry'

import { isRole, type Role } from './access'

export interface SessionUser {
  username: string
  displayName: string
  role: Role
  /** Features switched on in this deployment (FEAT-01). Hiding the rest is cosmetic. */
  features: ReadonlyArray<FeatureKey>
}

type Status = 'unknown' | 'anonymous' | 'authenticated'

function toUser(data: {
  username: string
  displayName: string
  role: string
  features: ReadonlyArray<FeatureKey>
}): SessionUser {
  // A role the UI does not know is a front-end/back-end mismatch: refuse rather than guess.
  if (!isRole(data.role)) throw new Error(`Unknown role from API: ${data.role}`)
  return {
    username: data.username,
    displayName: data.displayName,
    role: data.role,
    features: data.features,
  }
}

export const useSessionStore = defineStore('session', () => {
  const user = ref<SessionUser | null>(null)
  const status = ref<Status>('unknown')
  /** True when the server ended the session (idle timeout); the login page says so. */
  const expired = ref(false)

  // Traces carry the role (never the person) so slow screens can be told apart by who sees them.
  watch(user, (u) => setTelemetryRole(u?.role ?? null), { immediate: true })

  function expire(): void {
    user.value = null
    status.value = 'anonymous'
    expired.value = true
  }

  // Any 401 on a normal call means the session is gone.
  setUnauthorisedHandler(expire)

  async function load(): Promise<void> {
    try {
      const { data, response } = await api.GET('/api/v1/auth/me')
      if (response.ok && data) {
        user.value = toUser(data)
        status.value = 'authenticated'
        return
      }
    } catch {
      // API unreachable: treat as signed out; the sign-in form will say it cannot reach the server.
    }
    user.value = null
    status.value = 'anonymous'
  }

  async function signIn(
    username: string,
    password: string,
    provider = 'local',
  ): Promise<SessionUser> {
    // Fetch a CSRF token first; the cookie it sets is read by the API client on the POST.
    await api.GET('/api/v1/auth/csrf')
    const { data, error, response } = await api.POST('/api/v1/auth/login', {
      body: { username, password, provider },
    })
    if (!response.ok || !data) throw toProblem(error, response)
    user.value = toUser(data)
    status.value = 'authenticated'
    expired.value = false
    return user.value
  }

  async function signOut(): Promise<void> {
    const { response } = await api.POST('/api/v1/auth/logout')
    if (!response.ok && response.status !== 401) {
      throw new ApiProblem({
        status: response.status,
        code: 'auth.logout_failed',
        title: 'Could not sign out',
      })
    }
    user.value = null
    status.value = 'anonymous'
    expired.value = false
  }

  return { user, status, expired, load, signIn, signOut }
})
