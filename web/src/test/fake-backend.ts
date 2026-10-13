import { http, HttpResponse } from 'msw'

import type { ImportReport, KpiSummary, QueueInfo } from '@/entities/call-data'
import type { ForecastAccuracy, ForecastInterval, ForecastVersion } from '@/entities/forecast'

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

/** Every sellable feature, as the real API lists them when nothing is switched off. */
export const ALL_FEATURES = [
  'telephony',
  'forecasting',
  'scheduling',
  'people',
  'optimisation',
  'overtime',
  'insight',
  'capacity',
  'intraday',
  'service_desk',
] as const

export const backend = {
  /** The features switched on for the signed-in person. Tests narrow it to test the switch. */
  features: [...ALL_FEATURES] as string[],
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
  queues: [] as QueueInfo[],
  /** Forecasting: what the forecast endpoints answer, and what a run or publish does. */
  versions: [] as ForecastVersion[],
  intervals: {} as Record<string, ForecastInterval[]>,
  accuracy: null as ForecastAccuracy | null,
  /** What the next forecast run returns: a new draft, or an API problem (refused). */
  runOutcome: null as
    ForecastVersion | { status: number; code: string; title: string; detail: string } | null,
  /** The JSON bodies the app sent to run a forecast, with the CSRF header it carried. */
  runs: [] as Array<{ body: Record<string, unknown>; csrf: string | null }>,
  reset(): void {
    this.signedIn = null
    this.features = [...ALL_FEATURES]
    this.requests = []
    this.providers = [LOCAL_PROVIDER]
    this.lastProvider = null
    this.months = []
    this.kpisByMonth = {}
    this.imports = []
    this.queues = []
    this.versions = []
    this.intervals = {}
    this.accuracy = null
    this.runOutcome = null
    this.runs = []
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
    return HttpResponse.json({ ...account.user, features: backend.features })
  }),

  http.get('*/api/v1/auth/me', () =>
    backend.signedIn
      ? HttpResponse.json({ ...backend.signedIn, features: backend.features })
      : problem(401, 'auth.required', 'Not authenticated'),
  ),

  http.post('*/api/v1/auth/logout', ({ request }) => {
    const csrf = request.headers.get('X-CSRFToken')
    backend.requests.push({ method: 'POST', path: '/api/v1/auth/logout', csrf })
    if (!backend.signedIn) return problem(401, 'auth.required', 'Not authenticated')
    backend.signedIn = null
    return HttpResponse.json({ ok: true })
  }),

  http.get('*/api/v1/telephony/months', ({ request }) => {
    backend.requests.push({ method: 'GET', path: new URL(request.url).pathname, csrf: null })
    return HttpResponse.json({ months: backend.months })
  }),

  http.get('*/api/v1/telephony/kpis', ({ request }) => {
    const from = new URL(request.url).searchParams.get('date_from') ?? ''
    return HttpResponse.json(backend.kpisByMonth[from.slice(0, 7)] ?? emptySummary())
  }),

  http.get('*/api/v1/telephony/imports', () => HttpResponse.json(backend.imports)),

  http.get('*/api/v1/telephony/queues', () => HttpResponse.json(backend.queues)),

  http.get('*/api/v1/forecasting/versions', ({ request }) => {
    const queueId = new URL(request.url).searchParams.get('queue_id')
    return HttpResponse.json(
      backend.versions.filter((v) => queueId === null || v.queueId === Number(queueId)),
    )
  }),

  http.get('*/api/v1/forecasting/versions/:id/intervals', ({ params }) => {
    const intervals = backend.intervals[String(params.id)]
    return intervals
      ? HttpResponse.json(intervals)
      : problem(404, 'resource.not_found', 'Not found')
  }),

  http.get('*/api/v1/forecasting/accuracy', () =>
    backend.accuracy
      ? HttpResponse.json(backend.accuracy)
      : problem(404, 'resource.not_found', 'Not found'),
  ),

  http.post('*/api/v1/forecasting/versions', async ({ request }) => {
    const csrf = request.headers.get('X-CSRFToken')
    if (csrf !== CSRF_TOKEN) return problem(403, 'auth.csrf', 'CSRF check failed')
    backend.runs.push({ body: (await request.json()) as Record<string, unknown>, csrf })
    const outcome = backend.runOutcome
    if (outcome === null) return problem(500, 'test.no_outcome', 'Test set no outcome')
    if ('code' in outcome) {
      return HttpResponse.json(
        { type: `https://wfm.local/problems/${outcome.code}`, ...outcome },
        { status: outcome.status, headers: { 'Content-Type': 'application/problem+json' } },
      )
    }
    backend.versions = [outcome, ...backend.versions]
    return HttpResponse.json(outcome, { status: 201 })
  }),

  http.post('*/api/v1/forecasting/versions/:id/publish', ({ request, params }) => {
    const csrf = request.headers.get('X-CSRFToken')
    if (csrf !== CSRF_TOKEN) return problem(403, 'auth.csrf', 'CSRF check failed')
    const version = backend.versions.find((v) => v.id === params.id)
    if (!version) return problem(404, 'resource.not_found', 'Not found')
    // The server archives the live version of the same queue and publishes this one.
    backend.versions = backend.versions.map((v) =>
      v.id === version.id
        ? { ...v, status: 'published', publishedAt: '2026-05-21T09:00:00Z' }
        : v.queueId === version.queueId && v.status === 'published'
          ? { ...v, status: 'archived' }
          : v,
    )
    return HttpResponse.json(backend.versions.find((v) => v.id === version.id))
  }),
]
