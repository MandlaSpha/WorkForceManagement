import type { TeamOverview, TeamPerson } from '@/entities/workforce/team'

/** Synthetic people only. The week is the fixed test week of the scheduling fixtures. */
export function teamPerson(over: Partial<TeamPerson> = {}): TeamPerson {
  return {
    employeeId: 10,
    empNo: 'E001',
    name: 'Alex Agent',
    contractType: 'permanent',
    contractHours: 40,
    rosteredHours: 32,
    shifts: 4,
    adherencePct: 94.5,
    onTrack: true,
    pendingLeave: 0,
    openSwaps: 0,
    checkIn: false,
    shiftList: [
      {
        day: '2026-05-25',
        shift: 'D1',
        startTime: '09:00',
        endTime: '17:30',
        paidHours: 8,
        adherencePct: 94.5,
      },
      {
        day: '2026-05-26',
        shift: 'D1',
        startTime: '09:00',
        endTime: '17:30',
        paidHours: 8,
        adherencePct: null,
      },
    ],
    leaveBalances: [
      {
        leaveType: 'Annual leave',
        entitlementDays: 15,
        takenDays: 3,
        pendingDays: 2,
        availableDays: 10,
      },
    ],
    pendingRequests: [],
    ...over,
  }
}

export function teamOverview(over: Partial<TeamOverview> = {}): TeamOverview {
  const people = over.people ?? [
    teamPerson(),
    teamPerson({
      employeeId: 11,
      empNo: 'E002',
      name: 'Sam Planner',
      adherencePct: 78,
      onTrack: false,
      rosteredHours: 36,
      pendingLeave: 1,
      openSwaps: 1,
      checkIn: true,
      pendingRequests: [
        { leaveType: 'Annual leave', startDate: '2026-06-08', endDate: '2026-06-09', days: 2 },
      ],
    }),
    teamPerson({
      employeeId: 12,
      empNo: 'E003',
      name: 'Kim Newhire',
      adherencePct: null,
      onTrack: null,
      rosteredHours: 40,
      shiftList: [],
      shifts: 0,
    }),
  ]
  return {
    weekStart: '2026-05-25',
    weekEnd: '2026-05-31',
    adherenceThresholdPct: 90,
    summary: {
      headcount: people.length,
      withAdherence: people.filter((p) => p.adherencePct !== null).length,
      onTrack: people.filter((p) => p.onTrack === true).length,
      rosteredHours: 108,
      contractHours: 120,
      rosteredPct: 90,
    },
    managers: [],
    people,
    ...over,
  }
}
