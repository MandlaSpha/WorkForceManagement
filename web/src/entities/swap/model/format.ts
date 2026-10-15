import { formatDayLabel } from '@/shared/lib/datetime'

import type { Swap, SwapShift } from './types'

export const STATUS_LABEL: Record<string, string> = {
  open: 'Open: waiting for a colleague',
  awaiting_approval: 'Waiting for approval',
  approved: 'Approved',
  rejected: 'Rejected',
  cancelled: 'Cancelled',
}

export const STATUS_TONE: Record<string, string> = {
  open: 'bg-warn-soft text-warn',
  awaiting_approval: 'bg-warn-soft text-warn',
  approved: 'bg-brand-soft text-brand-ink',
  rejected: 'bg-danger-soft text-danger',
  cancelled: 'bg-surface-muted text-ink-muted',
}

/** "Mon 25 May, D1 09:00-17:30" */
export function shiftLabel(day: string, shift: string, start?: string, end?: string): string {
  const times = start && end ? ` ${start.slice(0, 5)}-${end.slice(0, 5)}` : ''
  return `${formatDayLabel(day)}, ${shift}${times}`
}

export function optionLabel(s: SwapShift): string {
  return `${shiftLabel(s.day, s.shift, s.startTime, s.endTime)} (${s.queue})`
}

/** What the swap is, in a sentence the people in it would say. */
export function describe(s: Swap): string {
  const gives = `${s.fromEmployee} gives ${shiftLabel(s.fromDay, s.fromShift)}`
  return s.toEmployee && s.toDay && s.toShift
    ? `${gives} for ${s.toEmployee}'s ${shiftLabel(s.toDay, s.toShift)}`
    : `${s.fromEmployee} offers ${shiftLabel(s.fromDay, s.fromShift)}, and nobody has taken it yet`
}

export function isOpen(status: string): boolean {
  return status === 'open' || status === 'awaiting_approval'
}
