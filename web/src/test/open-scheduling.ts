import { useContextStore } from '@/features/context-filters'

import { backend } from './fake-backend'
import { queueInfo } from './forecast-fixtures'
import { renderApp } from './render-app'
import { MONDAY_CELLS, SHIFTS, WEEK, employeeOf, planOf, rosterOf } from './scheduling-fixtures'

/** The fake backend as a typical planner finds it: one queue, four shifts, two people, a roster,
 * and a plan with a few half-hours worked out. */
export function seedScheduling(): void {
  backend.queues = [queueInfo()]
  backend.shifts = SHIFTS
  backend.employees = [
    employeeOf(),
    employeeOf({ id: 11, empNo: 'E002', name: 'Sam Planner', weeklyHoursIsDefault: true }),
  ]
  backend.roster = rosterOf()
  backend.plan = planOf(MONDAY_CELLS)
}

/** Open a screen signed in as `role`, looking at the fixed week. The CSRF cookie a signed-in
 * browser already holds is set, so writes carry the token. */
export async function openScheduling(path: string, role = 'planner') {
  backend.signedIn = { username: role, displayName: `Test ${role}`, role }
  document.cookie = 'csrftoken=test-csrf-token'
  const view = await renderApp(path)
  useContextStore(view.pinia).weekStart = WEEK
  return view
}
