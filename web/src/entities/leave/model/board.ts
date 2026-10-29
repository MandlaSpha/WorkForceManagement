import { formatDays } from './format'
import type { LeaveRequest } from './types'

export const LEAVE_STAGES = [
  { key: 'pending', label: 'Pending', dot: 'bg-warn', empty: 'Nothing waiting' },
  { key: 'approved', label: 'Approved', dot: 'bg-ok', empty: 'Nothing approved yet' },
  { key: 'rejected', label: 'Rejected', dot: 'bg-danger', empty: 'Nothing rejected' },
  { key: 'cancelled', label: 'Cancelled', dot: 'bg-ink-muted', empty: 'Nothing cancelled' },
] as const

export type MoveVerdict = { ok: true } | { ok: false; reason: string }

/** Cosmetic: the API decides who may decide leave. Nobody decides their own. */
export function canMoveLeave(request: LeaveRequest, to: string, decides: boolean): MoveVerdict {
  if (request.status !== 'pending') {
    return { ok: false, reason: 'This request has already been decided.' }
  }
  if (to === 'cancelled') {
    return { ok: false, reason: 'Only the person who asked can cancel their leave.' }
  }
  if (to !== 'approved' && to !== 'rejected') {
    return { ok: false, reason: 'A request cannot go back to waiting once it has been asked.' }
  }
  if (!decides) return { ok: false, reason: 'Only a lead, planner or admin can decide leave.' }
  if (request.mine) return { ok: false, reason: 'Somebody else decides your leave.' }
  return { ok: true }
}

export function isMovableLeave(request: LeaveRequest, decides: boolean): boolean {
  return decides && request.status === 'pending'
}

/** Cards per column, with the total days in each. The Cancelled column appears only when there is
 * something cancelled to show. An agent sees only their own requests. */
export function groupLeave(requests: ReadonlyArray<LeaveRequest>, decides: boolean) {
  const visible = decides ? requests : requests.filter((r) => r.mine)
  return LEAVE_STAGES.map((stage) => {
    const items = visible.filter((r) => r.status === stage.key)
    return { ...stage, items, total: formatDays(items.reduce((sum, r) => sum + r.days, 0)) }
  }).filter((c) => c.key !== 'cancelled' || c.items.length > 0)
}
