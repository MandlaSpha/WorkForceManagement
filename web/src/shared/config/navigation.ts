/**
 * Every screen of the app: where it lives, what it is called, which sidebar group it sits in and
 * which delivery phase builds it (tech spec section 8). Who may open it is decided separately, in
 * entities/session (access rules), so this file stays plain data.
 */

import type { components } from '@/shared/api'

export type NavGroup = 'Home' | 'My work' | 'Operate' | 'People' | 'Insight' | 'Admin'

/** A sellable module, or `core` for screens that are always on. Typed from the API schema, so a
 * name the API does not know is a compile error. */
export type FeatureKey = components['schemas']['Feature'] | 'core'

export interface NavItem {
  readonly key: string
  readonly path: string
  readonly label: string
  readonly group: NavGroup
  readonly icon: string
  /** The feature this screen belongs to; when it is switched off the screen is unavailable. */
  readonly feature: FeatureKey
  /** One plain sentence saying what the screen does (UI principle 1). */
  readonly subtitle: string
  /** Delivery phase that builds the real screen; 0 means it exists already. */
  readonly phase: number
}

export const NAV_ITEMS = [
  {
    key: 'dashboard',
    path: '/',
    label: 'Dashboard',
    group: 'Home',
    icon: 'home',
    feature: 'core',
    phase: 0,
    subtitle:
      'Measured service across every queue, month by month. Coverage and headcount join once rosters exist.',
  },

  {
    key: 'my-schedule',
    path: '/my-schedule',
    label: 'My schedule',
    group: 'My work',
    icon: 'calendar',
    feature: 'people',
    phase: 3,
    subtitle: 'Your published shifts, breaks and leave.',
  },
  {
    key: 'my-availability',
    path: '/my-availability',
    label: 'My availability',
    group: 'My work',
    icon: 'clock',
    feature: 'people',
    phase: 3,
    subtitle: 'Tell the planner when you cannot or prefer to work.',
  },

  {
    key: 'planner',
    path: '/planner',
    label: 'Planner',
    group: 'Operate',
    icon: 'layout-grid',
    feature: 'scheduling',
    phase: 2,
    subtitle: 'Coverage against requirement at 30-minute resolution.',
  },
  {
    key: 'intraday',
    path: '/intraday',
    label: 'Intraday',
    group: 'Operate',
    icon: 'activity',
    feature: 'intraday',
    phase: 5,
    subtitle: "Today's volumes, coverage and alerts as the day unfolds.",
  },
  {
    key: 'roster',
    path: '/roster',
    label: 'Roster',
    group: 'Operate',
    icon: 'calendar-days',
    feature: 'scheduling',
    phase: 2,
    subtitle: 'Who works when. Assign or clear a shift and coverage updates instantly.',
  },
  {
    key: 'forecast',
    path: '/forecast',
    label: 'Forecast',
    group: 'Operate',
    icon: 'trending-up',
    feature: 'forecasting',
    phase: 1,
    subtitle: 'Per-interval contacts, then Erlang C and shrinkage, give the agents required.',
  },
  {
    key: 'recommendations',
    path: '/recommendations',
    label: 'Recommendations',
    group: 'Operate',
    icon: 'sparkles',
    feature: 'optimisation',
    phase: 4,
    subtitle: 'Concrete fixes for the day’s coverage gaps. Apply one and watch coverage close.',
  },
  {
    key: 'contracts',
    path: '/contracts',
    label: 'Contracts',
    group: 'Operate',
    icon: 'clipboard-check',
    feature: 'capacity',
    phase: 3,
    subtitle: 'The service level each customer is promised, and which contracts are at risk.',
  },
  {
    key: 'capacity',
    path: '/capacity',
    label: 'Capacity',
    group: 'Operate',
    icon: 'layers',
    feature: 'capacity',
    phase: 5,
    subtitle: 'Establishment, attrition and hiring over the planning horizon.',
  },
  {
    key: 'scheduling',
    path: '/scheduling',
    label: 'Scheduling',
    group: 'Operate',
    icon: 'repeat',
    feature: 'scheduling',
    phase: 4,
    subtitle: 'Availability, cross-queue flexing, standby rota and rotations.',
  },
  {
    key: 'imports',
    path: '/imports',
    label: 'Data import',
    group: 'Operate',
    icon: 'upload',
    feature: 'telephony',
    phase: 1,
    subtitle: 'Bring in the ACD call detail report. Calls already imported are skipped.',
  },
  {
    key: 'service-desk',
    path: '/service-desk',
    label: 'Service desk',
    group: 'Operate',
    icon: 'ticket',
    feature: 'service_desk',
    phase: 2,
    subtitle: 'Ticket workload by resource pool: effort due by the deadline over productive time.',
  },

  {
    key: 'leave',
    path: '/leave',
    label: 'Leave',
    group: 'People',
    icon: 'sun',
    feature: 'people',
    phase: 3,
    subtitle:
      'Apply for or approve leave. Approval writes it into the schedule and updates coverage.',
  },
  {
    key: 'swaps',
    path: '/shift-swaps',
    label: 'Shift swaps',
    group: 'People',
    icon: 'arrow-left-right',
    feature: 'people',
    phase: 3,
    subtitle: 'Offer, accept and approve shift swaps within the scheduling rules.',
  },
  {
    key: 'employees',
    path: '/employees',
    label: 'Employees',
    group: 'People',
    icon: 'users',
    feature: 'scheduling',
    phase: 1,
    subtitle: 'People, skills, contracts and the ACD logins mapped to each of them.',
  },
  {
    key: 'overtime',
    path: '/overtime',
    label: 'Overtime',
    group: 'People',
    icon: 'moon',
    feature: 'overtime',
    phase: 4,
    subtitle: 'Authorise premium pay, run the standby rota and reconcile worked against approved.',
  },
  {
    key: 'attendance',
    path: '/attendance',
    label: 'Attendance',
    group: 'People',
    icon: 'clipboard-check',
    feature: 'people',
    phase: 6,
    subtitle: 'What happened against what was planned.',
  },

  {
    key: 'analytics',
    path: '/analytics',
    label: 'Analytics',
    group: 'Insight',
    icon: 'bar-chart-3',
    feature: 'insight',
    phase: 5,
    subtitle: 'Executive KPIs and what-if planning, each labelled measured or modelled.',
  },
  {
    key: 'calibration',
    path: '/calibration',
    label: 'Calibration',
    group: 'Insight',
    icon: 'sliders-horizontal',
    feature: 'forecasting',
    phase: 2,
    subtitle:
      'Tune how forecasts look back, and back-test the result against what really happened.',
  },
  {
    key: 'reports',
    path: '/reports',
    label: 'Reports',
    group: 'Insight',
    icon: 'download',
    feature: 'insight',
    phase: 5,
    subtitle: 'Daily, weekly and monthly packs, peaks and troughs, payroll export.',
  },

  {
    key: 'configure',
    path: '/configure',
    label: 'Configure',
    group: 'Admin',
    icon: 'settings',
    feature: 'core',
    phase: 2,
    subtitle: 'Shifts, queues, skills, adherence targets and reference data.',
  },
  {
    key: 'users',
    path: '/users',
    label: 'Users',
    group: 'Admin',
    icon: 'users',
    feature: 'core',
    phase: 3,
    subtitle: 'Who can sign in, what role they have, and which employee they are.',
  },
  {
    key: 'audit',
    path: '/audit',
    label: 'Audit log',
    group: 'Admin',
    icon: 'shield-check',
    feature: 'core',
    phase: 5,
    subtitle: 'Who did what, when, and with what outcome.',
  },
] as const satisfies readonly NavItem[]

export type NavKey = (typeof NAV_ITEMS)[number]['key']

export const NAV_GROUP_ORDER: readonly NavGroup[] = [
  'Home',
  'My work',
  'Operate',
  'People',
  'Insight',
  'Admin',
]
