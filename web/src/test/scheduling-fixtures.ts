import type { Employee, Plan, PlanCell, Roster, Shift } from '@/entities/scheduling'

export const WEEK = '2026-05-25' // a Monday
export const DAYS = Array.from({ length: 7 }, (_, n) => {
  const day = new Date(Date.UTC(2026, 4, 25 + n))
  return day.toISOString().slice(0, 10)
})

export function shiftOf(overrides: Partial<Shift> = {}): Shift {
  return {
    id: 1,
    code: 'D1',
    startTime: '09:00',
    endTime: '17:30',
    paidMinutes: 480,
    minutes: 510,
    overnight: false,
    kind: 'day',
    ...overrides,
  }
}

export const SHIFTS: Shift[] = [
  shiftOf({ id: 1, code: 'E1', startTime: '07:00', endTime: '15:30', kind: 'early' }),
  shiftOf({ id: 2, code: 'D1' }),
  shiftOf({ id: 3, code: 'L1', startTime: '13:00', endTime: '22:00', minutes: 540, kind: 'late' }),
  shiftOf({
    id: 4,
    code: 'N1',
    startTime: '22:00',
    endTime: '06:00',
    minutes: 480,
    overnight: true,
    kind: 'night',
  }),
]

export function employeeOf(overrides: Partial<Employee> = {}): Employee {
  return {
    id: 10,
    empNo: 'E001',
    name: 'Alex Agent',
    contractType: 'permanent',
    workMode: 'office',
    weeklyHours: 40,
    weeklyHoursIsDefault: false,
    startDate: null,
    endDate: null,
    skills: [{ queueId: 1, queue: 'QueueA', level: 1 }],
    ...overrides,
  }
}

export function rosterOf(overrides: Partial<Roster> = {}): Roster {
  return {
    queueId: 1,
    queue: 'QueueA',
    weekStart: WEEK,
    days: DAYS,
    status: 'draft',
    publishedAt: null,
    rows: [
      {
        employeeId: 10,
        empNo: 'E001',
        name: 'Alex Agent',
        weeklyHours: 40,
        daysWorked: 2,
        paidMinutes: 960,
        cells: [
          { day: DAYS[0]!, shiftId: 2, code: 'D1' },
          { day: DAYS[1]!, shiftId: 2, code: 'D1' },
        ],
      },
      {
        employeeId: 11,
        empNo: 'E002',
        name: 'Sam Planner',
        weeklyHours: 40,
        daysWorked: 0,
        paidMinutes: 0,
        cells: [],
      },
    ],
    onCounts: Object.fromEntries(DAYS.map((d, i) => [d, i < 2 ? 1 : 0])),
    shifts: SHIFTS,
    ...overrides,
  }
}

/** A plan where nothing is known, with chosen half-hours filled in. Keys are "YYYY-MM-DD:slot". */
export function planOf(
  cells: Record<string, Partial<PlanCell>> = {},
  overrides: Partial<Plan> = {},
): Plan {
  return {
    queueId: 1,
    queue: 'QueueA',
    weekStart: WEEK,
    days: DAYS,
    rosterStatus: 'draft',
    forecast: {
      id: 'f1',
      label: 'Week 22',
      publishedAt: '2026-05-20T09:00:00Z',
      assumptionsConfirmed: true,
    },
    cells: Object.fromEntries(
      DAYS.map((day) => [
        day,
        Array.from({ length: 48 }, (_, slot) => ({
          slot,
          scheduled: 0,
          required: null,
          variance: null,
          state: null,
          ...cells[`${day}:${slot}`],
        })),
      ]),
    ),
    summary: {
      intervalsKnown: 336,
      underIntervals: 2,
      gap: 4,
      requiredTotal: 10,
      scheduledTotal: 25,
      worst: { day: DAYS[0]!, slot: 18, variance: -2 },
    },
    ...overrides,
  }
}

/** Monday 09:00 and 09:30 two short, 10:00 met, 11:00 two over, as in the API tests. */
export const MONDAY_CELLS: Record<string, Partial<PlanCell>> = {
  [`${DAYS[0]}:18`]: { scheduled: 1, required: 3, variance: -2, state: 'under' },
  [`${DAYS[0]}:19`]: { scheduled: 1, required: 3, variance: -2, state: 'under' },
  [`${DAYS[0]}:20`]: { scheduled: 2, required: 2, variance: 0, state: 'met' },
  [`${DAYS[0]}:22`]: { scheduled: 2, required: 0, variance: 2, state: 'over' },
}
