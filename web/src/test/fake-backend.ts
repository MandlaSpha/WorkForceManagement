import { http, HttpResponse } from 'msw'

import type { ImportReport, KpiSummary } from '@/entities/call-data'

import { emptySummary } from './call-data-fixtures'

/**
 * A tiny in-memory stand-in for the Django auth API, enough to exercise the real client, store
 * and guards. It enforces the same CSRF rule as the real server (token cookie echoed in
 * X-CSRFToken), so a client that forgets the header fails here like it would in production.
 */
export interface FakeUser {
  username: string
  displayName: string
  role: string
}

export const ACCOUNTS: Record<string, { password: string; user: FakeUser }> = {
  planner: {
    password: 'correct-horse-battery',
    user: { username: 'planner', displayName: 'Pat Planner', role: 'planner' },
  },
  agent: {
    password: 'correct-horse-battery',
    user: { username: 'agent', displayName: 'Alex Agent', role: 'agent' },
  },
  admin: {
    password: 'correct-horse-battery',
    user: { username: 'admin', displayName: 'Ash Admin', role: 'admin' },
  },
}

export interface FakeProvider {
  id: string
  kind: string
  label: string
  flow: 'credentials' | 'redirect'
  startUrl: string | null
  restricted: boolean
}

export const LOCAL_PROVIDER: FakeProvider = {
  id: 'local',
  kind: 'local',
  label: 'Username and password',
  flow: 'credentials',
  startUrl: null,
  restricted: false,
}

export const backend = {
  signedIn: null as FakeUser | null,
  providers: [LOCAL_PROVIDER] as FakeProvider[],
  /** The provider named in the last login request. */
  lastProvider: null as string | null,
  requests: [] as Array<{ method: string; path: string; csrf: string | null }>,
  /** Call data: what the telephony endpoints answer. Tests set these before rendering. */
  /** The months (YYYY-MM) that have call data. */
  months: [] as string[],
  kpisByMonth: {} as Record<string, KpiSummary>,
  imports: [] as ImportReport[],
  reset(): void {
    this.signedIn = null
    this.requests = []
    this.providers = [LOCAL_PROVIDER]
    this.lastProvider = null
    this.months = []
    this.kpisByMonth = {}
    this.imports = []
  },
}

const CSRF_TOKEN = 'test-csrf-token'

function problem(status: number, code: string, title: string) {
  return HttpResponse.json(
    { type: `https://wfm.local/problems/${code}`, title, status, code },
    { status, headers: { 'Content-Type': 'application/problem+json' } },
  )
}

export const handlers = [
  http.get('*/api/v1/auth/csrf', ({ request }) => {
    backend.requests.push({ method: 'GET', path: new URL(request.url).pathname, csrf: null })
    document.cookie = `csrftoken=${CSRF_TOKEN}`
    return HttpResponse.json({ csrfToken: CSRF_TOKEN })
  }),

  http.get('*/api/v1/auth/providers', () => HttpResponse.json(backend.providers)),

  http.post('*/api/v1/auth/login', async ({ request }) => {
    const csrf = request.headers.get('X-CSRFToken')
    backend.requests.push({ method: 'POST', path: '/api/v1/auth/login', csrf })
    if (csrf !== CSRF_TOKEN) return problem(403, 'auth.csrf', 'CSRF check failed')
    const body = (await request.json()) as {
      username: string
      password: string
      provider?: string
    }
    backend.lastProvider = body.provider ?? null
    const account = ACCOUNTS[body.username]
    if (!account || account.password !== body.password) {
      return problem(401, 'auth.invalid_credentials', 'Invalid credentials')
    }
    backend.signedIn = account.user
    return HttpResponse.json(account.user)
  }),

  http.get('*/api/v1/auth/me', () =>
    backend.signedIn
      ? HttpResponse.json(backend.signedIn)
      : problem(401, 'auth.required', 'Not authenticated'),
  ),

  http.post('*/api/v1/auth/logout', ({ request }) => {
    const csrf = request.headers.get('X-CSRFToken')
    backend.requests.push({ method: 'POST', path: '/api/v1/auth/logout', csrf })
    if (!backend.signedIn) return problem(401, 'auth.required', 'Not authenticated')
    backend.signedIn = null
    return HttpResponse.json({ ok: true })
  }),

  http.get('*/api/v1/telephony/months', () => HttpResponse.json({ months: backend.months })),

  http.get('*/api/v1/telephony/kpis', ({ request }) => {
    const from = new URL(request.url).searchParams.get('date_from') ?? ''
    return HttpResponse.json(backend.kpisByMonth[from.slice(0, 7)] ?? emptySummary())
  }),

  http.get('*/api/v1/telephony/imports', () => HttpResponse.json(backend.imports)),
]
