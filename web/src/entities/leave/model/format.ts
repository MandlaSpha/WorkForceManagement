import { formatDayLabel } from '@/shared/lib/datetime'

/** "Mon 25 May" for one day, "Mon 25 May to Tue 26 May" for a range. */
export function rangeLabel(start: string, end: string): string {
  return start === end
    ? formatDayLabel(start)
    : `${formatDayLabel(start)} to ${formatDayLabel(end)}`
}

export const STATUS_LABEL: Record<string, string> = {
  pending: 'Waiting for a decision',
  approved: 'Approved',
  rejected: 'Rejected',
  cancelled: 'Cancelled',
}

export const STATUS_TONE: Record<string, string> = {
  pending: 'bg-warn-soft text-warn',
  approved: 'bg-brand-soft text-brand-ink',
  rejected: 'bg-danger-soft text-danger',
  cancelled: 'bg-surface-muted text-ink-muted',
}

/** "13 of 15 days left", or "no limit" for a kind of leave without one. */
export function daysLeft(available: number | null, entitlement: number | null): string {
  if (available === null || entitlement === null) return 'no limit'
  return `${available} of ${entitlement} days left`
}

/** A leave request can still be withdrawn while it waits, or before its last day if approved. */
export function canCancel(status: string, endDate: string, today: string): boolean {
  return status === 'pending' || (status === 'approved' && endDate >= today)
}
