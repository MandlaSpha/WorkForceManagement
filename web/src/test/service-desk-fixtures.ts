import type { Demand, PoolDemand, WorkImport } from '@/entities/service-desk'

const pool = (over: Partial<PoolDemand>): PoolDemand => ({
  poolId: 1,
  pool: 'Service Desk',
  productiveMinutesPerDay: 360,
  settingsConfirmed: false,
  openCount: 5,
  breached: 1,
  backlogMin: 1440,
  dueMin: 720,
  arrivingMin: 900,
  unestimated: 1,
  noDeadline: 1,
  requiredFte: 0.9,
  complete: false,
  ...over,
})

/** The workload of the API tests, worked by hand: Service Desk needs (720 + 900) / 1800 = 0.9
 * people; NOC has no arrival rate (nothing opened recently) and needs 360 / 1800 = 0.2, a minimum. */
export function demandOf(overrides: Partial<Demand> = {}): Demand {
  return {
    asOf: '2026-05-25',
    days: 7,
    workingDays: 5,
    pools: [
      pool({}),
      pool({
        poolId: 2,
        pool: 'NOC',
        settingsConfirmed: true,
        openCount: 1,
        breached: 0,
        backlogMin: 360,
        dueMin: 360,
        arrivingMin: null,
        unestimated: 0,
        noDeadline: 0,
        requiredFte: 0.2,
      }),
    ],
    requiredFte: 1.1,
    backlogMin: 1800,
    arrivingMin: 900,
    breached: 1,
    complete: false,
    ...overrides,
  }
}

export function importResult(overrides: Partial<WorkImport> = {}): WorkImport {
  return { created: 9, updated: 0, unchanged: 0, rejected: {}, ignoredColumns: [], ...overrides }
}
