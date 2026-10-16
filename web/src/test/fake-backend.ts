import { http, HttpResponse } from 'msw'

import type { ImportReport, KpiSummary, QueueInfo } from '@/entities/call-data'
import type { Capacity } from '@/entities/capacity'
import type {
  AwayLimit,
  Balances,
  Blackout,
  Impact,
  LeaveRequest,
  LeaveType,
} from '@/entities/leave'
import type { AvailabilityWindow } from '@/entities/availability'
import type { Inbox } from '@/entities/notification'
import type { ContractRow, Customer } from '@/entities/contract'
import type { AdminUser } from '@/entities/user-admin'
import type {
  AutoScheduleProposal,
  Recommendation,
  ComplianceRulesState,
  EmployeeImportReport,
  UnmappedLogin,
} from '@/entities/scheduling'
import type { MySchedule } from '@/entities/my-schedule'
import type { BoardEntry, Swap, SwapShift } from '@/entities/swap'
import type { Demand, WorkImport } from '@/entities/service-desk'
import type {
  Backtest,
  ForecastAccuracy,
  ForecastEvent,
  ForecastInterval,
  ForecastVersion,
  ScenarioResult,
  Tuning,
} from '@/entities/forecast'
import type { Employee, Overview, Plan, Roster, Shift } from '@/entities/scheduling'

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
  mustChangePassword?: boolean
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
  /** Leave: kinds, balances, requests, the coverage impact, and what a decision reports. */
  leaveTypes: [] as LeaveType[],
  blackouts: [] as Blackout[],
  awayLimit: { maxConcurrent: null } as AwayLimit,
  balances: null as Balances | null,
  noEmployeeRecord: false,
  leaveRequests: [] as LeaveRequest[],
  impact: null as Impact | null,
  requestQueries: [] as string[],
  decision: { shiftsCleared: 0, shiftsRestored: 0, shiftsNotRestored: 0 },
  /** Employee import: what a file check or an import answers, and the logins nobody owns. */
  employeeImport: null as EmployeeImportReport | null,
  employeeImports: [] as Array<{
    dryRun: boolean
    multipart: boolean
    filePart: boolean
    csrf: string | null
  }>,
  unmapped: [] as UnmappedLogin[],
  /** Compliance rules: what is in force and the versions; `rulesWarnings` is what a save returns. */
  rules: {
    inForce: { effectiveFrom: null, minRestHours: 11, maxConsecutiveDays: 6, maxWeeklyHours: null },
    versions: [],
    warnings: [],
  } as ComplianceRulesState,
  rulesWarnings: [] as string[],
  /** Auto-schedule: what a preview returns, and what the roster refused when applying. */
  autoProposal: {
    status: 'optimal',
    placements: [],
    shortBefore: 0,
    shortAfter: 0,
    overAfter: 0,
    kept: 0,
  } as AutoScheduleProposal,
  autoSkipped: {} as Record<string, number>,
  /** Recommendations for the chosen queue and week; applying one takes it off the list. */
  recommendations: [] as Recommendation[],
  /** Customers and contracts, with how each is doing. */
  contracts: [] as ContractRow[],
  customers: [] as Customer[],
  /** User administration: every account, as the admin sees them. */
  users: [] as AdminUser[],
  /** Notifications: the signed-in person's inbox. */
  inbox: { unread: 0, items: [] } as Inbox,
  /** Self-service: declared availability and the signed-in person's own schedule. */
  availability: [] as AvailabilityWindow[],
  mySchedule: null as MySchedule | null,
  noScheduleRecord: false,
  scheduleQueries: [] as string[],
  /** Shift swaps: my shifts, the colleagues' shifts on offer, and the swaps themselves. */
  myShifts: [] as SwapShift[],
  board: [] as BoardEntry[],
  swapOffers: [] as SwapShift[],
  swaps: [] as Swap[],
  offerQueries: [] as string[],
  /** Service desk: the workload, the answer to an import, and the queries it was asked. */
  demand: null as Demand | null,
  workImport: null as WorkImport | null,
  demandQueries: [] as string[],
  /** The planning overview the dashboard shows. */
  overview: null as Overview | null,
  /** Calibration: the saved tuning, the back-test it answers, and the queries it was asked. */
  tuning: null as Tuning | null,
  backtest: null as Backtest | null,
  backtestQueries: [] as string[],
  /** What the scenario endpoint answers. */
  scenario: null as ScenarioResult | null,
  /** Capacity: what the capacity endpoint answers, and the queries it was asked. */
  capacity: null as Capacity | null,
  capacityQueries: [] as string[],
  /** The events calendar. */
  events: [] as ForecastEvent[],
  /** Scheduling: what the roster, plan, shift and employee endpoints answer. */
  shifts: [] as Shift[],
  employees: [] as Employee[],
  roster: null as Roster | null,
  plan: null as Plan | null,
  /** Every write the app sent to scheduling or queue settings, with the CSRF header it carried. */
  writes: [] as Array<{ method: string; path: string; body: unknown; csrf: string | null }>,
  /** When set, the next scheduling write is refused with this problem (and then cleared). */
  nextProblem: null as { status: number; code: string; title: string; detail: string } | null,
  /** Lets a test change the fake world when an assignment is accepted, e.g. move the plan. */
  onAssign: null as ((body: Record<string, unknown>) => void) | null,
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
    this.events = []
    this.capacity = null
    this.scenario = null
    this.tuning = null
    this.backtest = null
    this.backtestQueries = []
    this.overview = null
    this.demand = null
    this.leaveTypes = []
    this.blackouts = []
    this.awayLimit = { maxConcurrent: null }
    this.balances = null
    this.noEmployeeRecord = false
    this.leaveRequests = []
    this.impact = null
    this.requestQueries = []
    this.decision = { shiftsCleared: 0, shiftsRestored: 0, shiftsNotRestored: 0 }
    this.inbox = { unread: 0, items: [] }
    this.users = []
    this.contracts = []
    this.customers = []
    this.rules = {
      inForce: {
        effectiveFrom: null,
        minRestHours: 11,
        maxConsecutiveDays: 6,
        maxWeeklyHours: null,
      },
      versions: [],
      warnings: [],
    }
    this.rulesWarnings = []
    this.autoProposal = {
      status: 'optimal',
      placements: [],
      shortBefore: 0,
      shortAfter: 0,
      overAfter: 0,
      kept: 0,
    }
    this.autoSkipped = {}
    this.recommendations = []
    this.employeeImport = null
    this.employeeImports = []
    this.unmapped = []
    this.availability = []
    this.mySchedule = null
    this.noScheduleRecord = false
    this.scheduleQueries = []
    this.myShifts = []
    this.board = []
    this.swapOffers = []
    this.swaps = []
    this.offerQueries = []
    this.workImport = null
    this.demandQueries = []
    this.capacityQueries = []
    this.shifts = []
    this.employees = []
    this.roster = null
    this.plan = null
    this.writes = []
    this.nextProblem = null
    this.onAssign = null
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

  http.get('*/api/v1/forecasting/tuning/backtest', ({ request }) => {
    backend.backtestQueries.push(new URL(request.url).search)
    return backend.backtest
      ? HttpResponse.json(backend.backtest)
      : problem(404, 'resource.not_found', 'Not found')
  }),

  http.get('*/api/v1/forecasting/tuning', () =>
    backend.tuning
      ? HttpResponse.json(backend.tuning)
      : problem(404, 'resource.not_found', 'Not found'),
  ),

  http.put('*/api/v1/forecasting/tuning', async (info) => {
    const sent = (await info.request.clone().json()) as Record<string, number>
    const response = await schedulingWrite(info, 'PUT')
    if (response.ok && backend.tuning) {
      backend.tuning = {
        ...backend.tuning,
        weeks: sent.weeks!,
        decay: sent.decay!,
        volumeMultiplier: sent.volumeMultiplier!,
        ahtMultiplier: sent.ahtMultiplier!,
        saved: true,
      }
    }
    return response
  }),

  http.post('*/api/v1/forecasting/scenarios', async (info) => {
    const response = await schedulingWrite(info, 'POST')
    return response.ok && backend.scenario ? HttpResponse.json(backend.scenario) : response
  }),

  http.get('*/api/v1/capacity', ({ request }) => {
    backend.capacityQueries.push(new URL(request.url).search)
    return backend.capacity
      ? HttpResponse.json(backend.capacity)
      : problem(404, 'resource.not_found', 'Not found')
  }),

  http.put('*/api/v1/capacity/limits', async (info) => {
    const sent = (await info.request.clone().json()) as Record<string, number>
    const response = await schedulingWrite(info, 'PUT')
    if (response.ok && backend.capacity) {
      backend.capacity = {
        ...backend.capacity,
        limits: {
          permanentLimit: Number(sent.permanentLimit),
          seasonalLimit: Number(sent.seasonalLimit),
          confirmed: true,
        },
      }
    }
    return response
  }),

  http.get('*/api/v1/forecasting/events', ({ request }) => {
    const queue = new URL(request.url).searchParams.get('queue_id')
    return HttpResponse.json(
      backend.events.filter((e) => queue === null || e.queueId === null || e.queueId === +queue),
    )
  }),

  http.post('*/api/v1/forecasting/events', async (info) => {
    const sent = (await info.request.clone().json()) as Record<string, unknown>
    const response = await schedulingWrite(info, 'POST', 201)
    if (response.ok) {
      const queueId = (sent.queueId as number | null) ?? null
      backend.events = [
        ...backend.events,
        {
          id: 100 + backend.events.length,
          name: String(sent.name),
          queueId,
          queue: backend.queues.find((q) => q.id === queueId)?.name ?? null,
          dateFrom: String(sent.dateFrom),
          dateTo: String(sent.dateTo),
          upliftPct: Number(sent.upliftPct),
        },
      ]
    }
    return response
  }),

  http.delete('*/api/v1/forecasting/events/:id', async (info) => {
    const response = await schedulingWrite(info, 'DELETE')
    if (response.ok) backend.events = backend.events.filter((e) => e.id !== +String(info.params.id))
    return response
  }),

  http.get('*/api/v1/scheduling/shifts', () => HttpResponse.json(backend.shifts)),

  http.get('*/api/v1/scheduling/employees', () => HttpResponse.json(backend.employees)),

  http.get('*/api/v1/scheduling/roster', () =>
    backend.roster
      ? HttpResponse.json(backend.roster)
      : problem(404, 'resource.not_found', 'Not found'),
  ),

  http.get('*/api/v1/people/leave/blackouts', () => HttpResponse.json(backend.blackouts)),

  http.post('*/api/v1/people/leave/blackouts', async (info) => {
    const sent = (await info.request.clone().json()) as Record<string, string>
    const response = await schedulingWrite(info, 'POST', 201)
    if (!response.ok) return response
    const created: Blackout = {
      id: 100 + backend.blackouts.length,
      name: String(sent.name),
      dateFrom: String(sent.dateFrom),
      dateTo: String(sent.dateTo),
    }
    backend.blackouts = [...backend.blackouts, created]
    return HttpResponse.json(created, { status: 201 })
  }),

  http.delete('*/api/v1/people/leave/blackouts/:id', async (info) => {
    const response = await schedulingWrite(info, 'DELETE')
    if (response.ok)
      backend.blackouts = backend.blackouts.filter((b) => b.id !== Number(info.params.id))
    return response
  }),

  http.get('*/api/v1/people/leave/limit', () => HttpResponse.json(backend.awayLimit)),

  http.put('*/api/v1/people/leave/limit', async (info) => {
    const sent = (await info.request.clone().json()) as AwayLimit
    const response = await schedulingWrite(info, 'PUT')
    if (!response.ok) return response
    backend.awayLimit = { maxConcurrent: sent.maxConcurrent }
    return HttpResponse.json(backend.awayLimit)
  }),

  http.get('*/api/v1/people/leave/types', () => HttpResponse.json(backend.leaveTypes)),

  http.get('*/api/v1/people/leave/balances', () =>
    backend.noEmployeeRecord
      ? problem(422, 'leave.no_employee_record', 'Leave refused')
      : HttpResponse.json(backend.balances),
  ),

  http.get('*/api/v1/people/leave/requests', ({ request }) => {
    const status = new URL(request.url).searchParams.get('status')
    backend.requestQueries.push(new URL(request.url).search)
    return HttpResponse.json(
      backend.leaveRequests.filter((r) => status === null || r.status === status),
    )
  }),

  http.post('*/api/v1/people/leave/requests', async (info) => {
    const sent = (await info.request.clone().json()) as Record<string, string | number>
    const response = await schedulingWrite(info, 'POST', 201)
    if (!response.ok) return response
    const created: LeaveRequest = {
      id: 100 + backend.leaveRequests.length,
      employeeId: 10,
      employee: 'Alex Agent',
      empNo: 'E001',
      leaveTypeId: Number(sent.leaveTypeId),
      leaveType: backend.leaveTypes.find((t) => t.id === Number(sent.leaveTypeId))?.name ?? '',
      startDate: String(sent.startDate),
      endDate: String(sent.endDate),
      days: 2,
      status: 'pending',
      createdAt: '2026-05-20T08:00:00Z',
      decidedAt: null,
      shiftsCleared: 0,
      mine: true,
    }
    backend.leaveRequests = [...backend.leaveRequests, created]
    return HttpResponse.json(created, { status: 201 })
  }),

  http.post('*/api/v1/people/leave/requests/:id/:what', async (info) => {
    const response = await schedulingWrite(info, 'POST')
    if (!response.ok) return response
    const what = String(info.params.what)
    const status =
      { approve: 'approved', reject: 'rejected', cancel: 'cancelled' }[what] ?? 'pending'
    backend.leaveRequests = backend.leaveRequests.map((r) =>
      r.id === Number(info.params.id) ? { ...r, status } : r,
    )
    const request = backend.leaveRequests.find((r) => r.id === Number(info.params.id))
    return HttpResponse.json({ request, ...backend.decision })
  }),

  http.get('*/api/v1/people/leave/requests/:id/impact', () =>
    backend.impact
      ? HttpResponse.json(backend.impact)
      : problem(404, 'resource.not_found', 'Not found'),
  ),

  http.put('*/api/v1/people/leave/types/:id', async (info) => {
    const sent = (await info.request.clone().json()) as { daysPerYear: number | null }
    const response = await schedulingWrite(info, 'PUT')
    if (!response.ok) return response
    backend.leaveTypes = backend.leaveTypes.map((t) =>
      t.id === Number(info.params.id)
        ? { ...t, daysPerYear: sent.daysPerYear, confirmed: true }
        : t,
    )
    return HttpResponse.json(backend.leaveTypes.find((t) => t.id === Number(info.params.id)))
  }),

  http.get('*/api/v1/scheduling/agent-logins/unmapped', () => HttpResponse.json(backend.unmapped)),

  http.put('*/api/v1/scheduling/employees/:id/agent-logins', async (info) => {
    const sent = (await info.request.clone().json()) as { logins: string[] }
    const response = await schedulingWrite(info, 'PUT')
    if (!response.ok) return response
    const id = Number(info.params.id)
    backend.employees = backend.employees.map((e) =>
      e.id === id ? { ...e, agentLogins: sent.logins } : e,
    )
    backend.unmapped = backend.unmapped.filter((u) => !sent.logins.includes(u.login))
    return HttpResponse.json(backend.employees.find((e) => e.id === id))
  }),

  http.post('*/api/v1/scheduling/roster/auto-schedule/preview', async (info) => {
    const response = await schedulingWrite(info, 'POST')
    if (!response.ok) return response
    return HttpResponse.json(backend.autoProposal)
  }),

  http.post('*/api/v1/scheduling/roster/auto-schedule', async (info) => {
    const response = await schedulingWrite(info, 'POST')
    if (!response.ok) return response
    const refused = Object.values(backend.autoSkipped).reduce((a, b) => a + b, 0)
    return HttpResponse.json({
      ...backend.autoProposal,
      placed: backend.autoProposal.placements.length - refused,
      skipped: backend.autoSkipped,
    })
  }),

  http.get('*/api/v1/scheduling/recommendations', () => HttpResponse.json(backend.recommendations)),

  http.post('*/api/v1/scheduling/recommendations/apply', async (info) => {
    const sent = (await info.request.clone().json()) as {
      employeeId: number
      day: string
      templateId: number
    }
    const response = await schedulingWrite(info, 'POST')
    if (!response.ok) return response
    const applied = backend.recommendations.find(
      (r) =>
        r.employeeId === sent.employeeId && r.day === sent.day && r.templateId === sent.templateId,
    )
    backend.recommendations = backend.recommendations.filter((r) => r !== applied)
    return HttpResponse.json({ applied: true, closes: applied?.closes ?? 0 })
  }),

  http.get('*/api/v1/scheduling/compliance-rules', () => HttpResponse.json(backend.rules)),

  http.put('*/api/v1/scheduling/compliance-rules', async (info) => {
    const sent = (await info.request.clone().json()) as ComplianceRulesState['inForce']
    const response = await schedulingWrite(info, 'PUT')
    if (!response.ok) return response
    return HttpResponse.json({ saved: sent, warnings: backend.rulesWarnings })
  }),

  http.get('*/api/v1/contracts/customers', () => HttpResponse.json(backend.customers)),

  http.post('*/api/v1/contracts/customers', async (info) => {
    const sent = (await info.request.clone().json()) as { name: string }
    const response = await schedulingWrite(info, 'POST', 201)
    if (!response.ok) return response
    const created: Customer = { id: 50 + backend.customers.length, name: sent.name }
    backend.customers = [...backend.customers, created]
    return HttpResponse.json(created, { status: 201 })
  }),

  http.get('*/api/v1/contracts', () => HttpResponse.json(backend.contracts)),

  http.post('*/api/v1/contracts', async (info) => {
    const sent = (await info.request.clone().json()) as Record<string, unknown>
    const response = await schedulingWrite(info, 'POST', 201)
    if (!response.ok) return response
    const created: ContractRow = {
      id: 100 + backend.contracts.length,
      customerId: Number(sent.customerId),
      customer: backend.customers.find((c) => c.id === Number(sent.customerId))?.name ?? '',
      name: String(sent.name),
      slTargetPct: Number(sent.slTargetPct),
      slThresholdS: Number(sent.slThresholdS),
      active: true,
      queues: [],
      offered: 0,
      measuredSlPct: null,
      intervalsKnown: 0,
      underIntervals: 0,
      gap: 0,
      atRisk: false,
      risks: [],
    }
    backend.contracts = [...backend.contracts, created]
    return HttpResponse.json(created, { status: 201 })
  }),

  http.put('*/api/v1/contracts/:id', async (info) => {
    const sent = (await info.request.clone().json()) as Record<string, unknown>
    const response = await schedulingWrite(info, 'PUT')
    if (!response.ok) return response
    const id = Number(info.params.id)
    backend.contracts = backend.contracts.map((c) =>
      c.id === id
        ? {
            ...c,
            name: String(sent.name),
            slTargetPct: Number(sent.slTargetPct),
            slThresholdS: Number(sent.slThresholdS),
            active: Boolean(sent.active),
          }
        : c,
    )
    return HttpResponse.json(backend.contracts.find((c) => c.id === id))
  }),

  http.get('*/api/v1/users', () => HttpResponse.json(backend.users)),

  http.post('*/api/v1/users', async (info) => {
    const sent = (await info.request.clone().json()) as Record<string, string>
    const response = await schedulingWrite(info, 'POST', 201)
    if (!response.ok) return response
    const created: AdminUser = {
      id: 100 + backend.users.length,
      username: String(sent.username),
      name: `${sent.firstName} ${sent.lastName}`.trim(),
      role: String(sent.role),
      roleFromDirectory: false,
      active: true,
      locked: false,
      hasPassword: true,
      mustChangePassword: true,
      employee: null,
      lastLogin: null,
    }
    backend.users = [...backend.users, created]
    return HttpResponse.json(created, { status: 201 })
  }),

  http.put('*/api/v1/users/:id/role', async (info) => {
    const sent = (await info.request.clone().json()) as { role: string }
    const response = await schedulingWrite(info, 'PUT')
    if (!response.ok) return response
    return changeUser(Number(info.params.id), { role: sent.role })
  }),

  http.put('*/api/v1/users/:id/active', async (info) => {
    const sent = (await info.request.clone().json()) as { active: boolean }
    const response = await schedulingWrite(info, 'PUT')
    if (!response.ok) return response
    return changeUser(Number(info.params.id), { active: sent.active })
  }),

  http.post('*/api/v1/users/:id/unlock', async (info) => {
    const response = await schedulingWrite(info, 'POST')
    if (!response.ok) return response
    return changeUser(Number(info.params.id), { locked: false })
  }),

  http.post('*/api/v1/users/:id/password', async (info) => {
    const response = await schedulingWrite(info, 'POST')
    if (!response.ok) return response
    return changeUser(Number(info.params.id), { mustChangePassword: true, locked: false })
  }),

  http.put('*/api/v1/scheduling/employees/:id/login', async (info) => {
    const sent = (await info.request.clone().json()) as { userId: number | null }
    const response = await schedulingWrite(info, 'PUT')
    if (!response.ok) return response
    const id = Number(info.params.id)
    backend.employees = backend.employees.map((e) =>
      e.id === id ? { ...e, hasLogin: sent.userId !== null } : e,
    )
    const emp = backend.employees.find((e) => e.id === id)
    backend.users = backend.users.map((u) =>
      u.id === sent.userId
        ? { ...u, employee: emp?.empNo ?? null }
        : u.employee === emp?.empNo && sent.userId === null
          ? { ...u, employee: null }
          : u,
    )
    return HttpResponse.json(emp)
  }),

  http.post('*/api/v1/auth/change-password', async (info) => {
    const response = await schedulingWrite(info, 'POST')
    if (!response.ok) return response
    if (backend.signedIn) backend.signedIn = { ...backend.signedIn, mustChangePassword: false }
    return HttpResponse.json({ ok: true })
  }),

  http.get('*/api/v1/notifications', () => HttpResponse.json(backend.inbox)),

  http.post('*/api/v1/notifications/read-all', async (info) => {
    const response = await schedulingWrite(info, 'POST')
    if (!response.ok) return response
    backend.inbox = {
      unread: 0,
      items: backend.inbox.items.map((n) => ({ ...n, read: true })),
    }
    return HttpResponse.json({ marked: 1 })
  }),

  http.post('*/api/v1/notifications/:id/read', async (info) => {
    const response = await schedulingWrite(info, 'POST')
    if (!response.ok) return response
    const items = backend.inbox.items.map((n) =>
      n.id === Number(info.params.id) ? { ...n, read: true } : n,
    )
    backend.inbox = { unread: items.filter((n) => !n.read).length, items }
    return HttpResponse.json(items.find((n) => n.id === Number(info.params.id)))
  }),

  http.get('*/api/v1/people/availability', () =>
    backend.noScheduleRecord
      ? problem(422, 'availability.no_employee_record', 'Not on the employee list')
      : HttpResponse.json(backend.availability),
  ),

  http.post('*/api/v1/people/availability', async (info) => {
    const sent = (await info.request.clone().json()) as Record<string, string | number>
    const response = await schedulingWrite(info, 'POST', 201)
    if (!response.ok) return response
    const created: AvailabilityWindow = {
      id: 100 + backend.availability.length,
      employeeId: 10,
      employee: 'Alex Agent',
      weekday: Number(sent.weekday),
      startTime: `${String(sent.startTime)}:00`,
      endTime: `${String(sent.endTime)}:00`,
      kind: String(sent.kind),
    }
    backend.availability = [...backend.availability, created]
    return HttpResponse.json(created, { status: 201 })
  }),

  http.delete('*/api/v1/people/availability/:id', async (info) => {
    const response = await schedulingWrite(info, 'DELETE')
    if (response.ok)
      backend.availability = backend.availability.filter((w) => w.id !== Number(info.params.id))
    return response
  }),

  http.get('*/api/v1/people/my-schedule', ({ request }) => {
    const query = new URL(request.url).searchParams
    backend.scheduleQueries.push(new URL(request.url).search)
    if (backend.noScheduleRecord)
      return problem(422, 'schedule.no_employee_record', 'Not on the employee list')
    const all = backend.mySchedule
    if (!all) return problem(404, 'resource.not_found', 'Not found')
    // Answer for the range that was asked for, like the API does.
    const fromDate = query.get('from_date') ?? all.fromDate
    const toDate = query.get('to_date') ?? all.toDate
    return HttpResponse.json({
      ...all,
      fromDate,
      toDate,
      shifts: all.shifts.filter((s) => s.day >= fromDate && s.day <= toDate),
      leave: all.leave.filter((l) => l.endDate >= fromDate && l.startDate <= toDate),
    })
  }),

  http.get('*/api/v1/people/swaps/my-shifts', () => HttpResponse.json(backend.myShifts)),

  http.get('*/api/v1/people/swaps/board', () => HttpResponse.json(backend.board)),

  http.get('*/api/v1/people/swaps/:id/offers', ({ request }) => {
    backend.offerQueries.push(new URL(request.url).pathname)
    return HttpResponse.json(backend.swapOffers)
  }),

  http.get('*/api/v1/people/swaps', ({ request }) => {
    const status = new URL(request.url).searchParams.get('status')
    return HttpResponse.json(backend.swaps.filter((s) => status === null || s.status === status))
  }),

  http.post('*/api/v1/people/swaps', async (info) => {
    const sent = (await info.request.clone().json()) as Record<string, number>
    const response = await schedulingWrite(info, 'POST', 201)
    if (!response.ok) return response
    const give = backend.myShifts.find((s) => s.assignmentId === sent.giveAssignmentId)
    const created: Swap = {
      id: 100 + backend.swaps.length,
      queue: give?.queue ?? '',
      status: 'open',
      fromEmployee: give?.employee ?? '',
      fromDay: give?.day ?? '',
      fromShift: give?.shift ?? '',
      toEmployee: null,
      toDay: null,
      toShift: null,
      createdAt: '2026-05-20T08:00:00Z',
      decidedAt: null,
      asker: true,
      colleague: false,
    }
    backend.swaps = [...backend.swaps, created]
    return HttpResponse.json(created, { status: 201 })
  }),

  http.post('*/api/v1/people/swaps/:id/accept', async (info) => {
    const sent = (await info.request.clone().json()) as Record<string, number>
    const response = await schedulingWrite(info, 'POST')
    if (!response.ok) return response
    const mine = backend.swapOffers.find((s) => s.assignmentId === sent.assignmentId)
    const id = Number(info.params.id)
    const posted = backend.board.find((b) => b.id === id)
    const taken: Swap = {
      id,
      queue: posted?.queue ?? '',
      status: 'awaiting_approval',
      fromEmployee: 'Sam Colleague',
      fromDay: posted?.day ?? '',
      fromShift: posted?.shift ?? '',
      toEmployee: mine?.employee ?? '',
      toDay: mine?.day ?? '',
      toShift: mine?.shift ?? '',
      createdAt: '2026-05-20T08:00:00Z',
      decidedAt: null,
      asker: false,
      colleague: true,
    }
    backend.board = backend.board.filter((b) => b.id !== id)
    backend.swaps = [...backend.swaps.filter((s) => s.id !== id), taken]
    return HttpResponse.json(taken)
  }),

  http.post('*/api/v1/people/swaps/:id/:what', async (info) => {
    const response = await schedulingWrite(info, 'POST')
    if (!response.ok) return response
    const status =
      { approve: 'approved', reject: 'rejected', cancel: 'cancelled' }[String(info.params.what)] ??
      'open'
    backend.swaps = backend.swaps.map((s) =>
      s.id === Number(info.params.id) ? { ...s, status } : s,
    )
    return HttpResponse.json(backend.swaps.find((s) => s.id === Number(info.params.id)))
  }),

  http.get('*/api/v1/service-desk/demand', ({ request }) => {
    backend.demandQueries.push(new URL(request.url).search)
    return backend.demand
      ? HttpResponse.json(backend.demand)
      : problem(404, 'resource.not_found', 'Not found')
  }),

  http.put('*/api/v1/service-desk/pools/:id', (info) => schedulingWrite(info, 'PUT')),

  http.get('*/api/v1/scheduling/overview', () =>
    backend.overview
      ? HttpResponse.json(backend.overview)
      : problem(404, 'resource.not_found', 'Not found'),
  ),

  http.get('*/api/v1/scheduling/plan', () =>
    backend.plan
      ? HttpResponse.json(backend.plan)
      : problem(404, 'resource.not_found', 'Not found'),
  ),

  http.post('*/api/v1/scheduling/shifts', (info) => schedulingWrite(info, 'POST', 201)),
  http.delete('*/api/v1/scheduling/shifts/:id', (info) => schedulingWrite(info, 'DELETE')),
  http.post('*/api/v1/scheduling/employees', (info) => schedulingWrite(info, 'POST', 201)),
  http.put('*/api/v1/scheduling/employees/:id', (info) => schedulingWrite(info, 'PUT')),
  http.put('*/api/v1/scheduling/roster/assignments', (info) => schedulingWrite(info, 'PUT')),
  http.post('*/api/v1/scheduling/roster/publish', (info) => schedulingWrite(info, 'POST')),
  http.post('*/api/v1/scheduling/roster/reopen', (info) => schedulingWrite(info, 'POST')),
  http.put('*/api/v1/telephony/queues/:id/settings', (info) => schedulingWrite(info, 'PUT')),
]

/** Every scheduling write: demand the CSRF token, record the request, refuse when a test says so,
 * otherwise echo what a real server would return for it. */
function changeUser(id: number, change: Partial<AdminUser>): Response {
  backend.users = backend.users.map((u) => (u.id === id ? { ...u, ...change } : u))
  return HttpResponse.json(backend.users.find((u) => u.id === id))
}

async function schedulingWrite(
  { request }: { request: Request },
  method: string,
  status = 200,
): Promise<Response> {
  const csrf = request.headers.get('X-CSRFToken')
  if (csrf !== CSRF_TOKEN) return problem(403, 'auth.csrf', 'CSRF check failed')
  const path = new URL(request.url).pathname
  // Some writes (approve, cancel, delete) carry no body at all.
  const text = await request.text()
  const body = text === '' ? null : (JSON.parse(text) as Record<string, unknown>)
  backend.writes.push({ method, path, body, csrf })

  const refusal = backend.nextProblem
  if (refusal) {
    backend.nextProblem = null
    return HttpResponse.json(
      { type: `https://wfm.local/problems/${refusal.code}`, ...refusal },
      { status: refusal.status, headers: { 'Content-Type': 'application/problem+json' } },
    )
  }
  const settingsFor = /\/queues\/(\d+)\/settings$/.exec(path)
  if (settingsFor)
    backend.queues = backend.queues.map((q) =>
      q.id === Number(settingsFor[1]) ? { ...q, ...body, settingsConfirmed: true } : q,
    )
  if (path.endsWith('/roster/assignments')) backend.onAssign?.(body ?? {})
  if (path.endsWith('/roster/publish') && backend.roster)
    backend.roster = { ...backend.roster, status: 'published' }
  if (path.endsWith('/roster/reopen') && backend.roster)
    backend.roster = { ...backend.roster, status: 'draft' }
  return HttpResponse.json(
    path.endsWith('/roster/assignments')
      ? {
          employeeId: body?.employeeId,
          day: body?.day,
          shiftId: body?.templateId,
          code: null,
          weekStatus: 'draft',
        }
      : (body ?? { ok: true }),
    { status },
  )
}
