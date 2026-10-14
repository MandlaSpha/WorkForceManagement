import { formatDayLabel } from '@/shared/lib/datetime'

import type { Swap, SwapShift } from './types'

export const STATUS_LABEL: Record<string, string> = {
  awaiting_colleague: 'Waiting for the colleague',
  awaiting_approval: 'Waiting for approval',
  approved: 'Approved',
  declined: 'Declined',
  rejected: 'Rejected',
  cancelled: 'Cancelled',
}

export const STATUS_TONE: Record<string, string> = {
  awaiting_colleague: 'bg-warn-soft text-warn',
  awaiting_approval: 'bg-warn-soft text-warn',
  approved: 'bg-brand-soft text-brand-ink',
  declined: 'bg-surface-muted text-ink-muted',
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
  return (
    `${s.fromEmployee} gives ${shiftLabel(s.fromDay, s.fromShift)} ` +
    `for ${s.toEmployee}'s ${shiftLabel(s.toDay, s.toShift)}`
  )
}

export function isOpen(status: string): boolean {
  return status === 'awaiting_colleague' || status === 'awaiting_approval'
}
