import type { Balances, Impact, LeaveRequest, LeaveType } from '@/entities/leave'

export const LEAVE_TYPES: LeaveType[] = [
  { id: 1, code: 'annual', name: 'Annual leave', paid: true, daysPerYear: 15, confirmed: false },
  { id: 2, code: 'sick', name: 'Sick leave', paid: true, daysPerYear: 10, confirmed: false },
  { id: 3, code: 'unpaid', name: 'Unpaid leave', paid: false, daysPerYear: null, confirmed: false },
]

/** Annual leave: 15 a year, 2 approved, 2 waiting, so 11 left; sick untouched; unpaid has no limit. */
export function balancesOf(): Balances {
  return {
    employeeId: 10,
    employee: 'Alex Agent',
    year: new Date().getFullYear(),
    balances: [
      {
        typeId: 1,
        code: 'annual',
        name: 'Annual leave',
        entitlement: 15,
        taken: 2,
        pending: 2,
        available: 11,
      },
      {
        typeId: 2,
        code: 'sick',
        name: 'Sick leave',
        entitlement: 10,
        taken: 0,
        pending: 0,
        available: 10,
      },
      {
        typeId: 3,
        code: 'unpaid',
        name: 'Unpaid leave',
        entitlement: null,
        taken: 0,
        pending: 0,
        available: null,
      },
    ],
  }
}

export function requestOf(over: Partial<LeaveRequest> = {}): LeaveRequest {
  return {
    id: 1,
    employeeId: 10,
    employee: 'Alex Agent',
    empNo: 'E001',
    leaveTypeId: 1,
    leaveType: 'Annual leave',
    startDate: '2099-05-25',
    endDate: '2099-05-26',
    days: 2,
    status: 'pending',
    createdAt: '2026-05-20T08:00:00Z',
    decidedAt: null,
    shiftsCleared: 0,
    mine: true,
    ...over,
  }
}

/** The impact of the API tests, worked by hand: two shifts (17 hours) of which 17 half-hours were
 * covered with none to spare. */
export function impactOf(over: Partial<Impact> = {}): Impact {
  return {
    shifts: 2,
    hours: 17,
    intervals: 34,
    newlyUnder: 17,
    alreadyUnder: 0,
    unknown: 0,
    ...over,
  }
}
