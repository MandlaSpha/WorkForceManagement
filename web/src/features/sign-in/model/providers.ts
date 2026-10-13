import { api } from '@/shared/api'

/** One way of signing in that the organisation has switched on (GET /api/v1/auth/providers). */
export interface SignInProvider {
  id: string
  kind: string
  label: string
  /** "credentials": a username and password form. "redirect": send the browser to the provider. */
  flow: 'credentials' | 'redirect'
  startUrl: string | null
  /** Local accounts limited to break-glass roles: offered as emergency access only. */
  restricted: boolean
}

export const LOCAL_ONLY: readonly SignInProvider[] = [
  {
    id: 'local',
    kind: 'local',
    label: 'Username and password',
    flow: 'credentials',
    startUrl: null,
    restricted: false,
  },
]

/**
 * What the login page may offer. If the API cannot be reached, fall back to plain local sign-in:
 * the form then reports "cannot reach the server" on submit instead of showing an empty page.
 */
export async function fetchProviders(): Promise<readonly SignInProvider[]> {
  try {
    const { data, response } = await api.GET('/api/v1/auth/providers')
    if (response.ok && data && data.length > 0) {
      return data.map((p) => ({
        id: p.id,
        kind: p.kind,
        label: p.label,
        flow: p.flow === 'redirect' ? 'redirect' : 'credentials',
        startUrl: p.startUrl ?? null,
        restricted: p.restricted ?? false,
      }))
    }
  } catch {
    // unreachable: use the fallback below
  }
  return LOCAL_ONLY
}
