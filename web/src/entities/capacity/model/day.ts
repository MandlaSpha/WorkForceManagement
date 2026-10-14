import type { CapacityDay } from './types'

export type DayStatus = 'unknown' | 'permanent' | 'seasonal' | 'overflow'

/** Where a day stands against the workforce: nothing forecast, covered by permanent staff alone,
 * needing seasonal agents, or beyond everybody (overflow). */
export function dayStatus(day: Pick<CapacityDay, 'peak' | 'seasonal' | 'overflow'>): DayStatus {
  if (day.peak === null) return 'unknown'
  if ((day.overflow ?? 0) > 0) return 'overflow'
  if ((day.seasonal ?? 0) > 0) return 'seasonal'
  return 'permanent'
}

/** A figure, or a dash when it is unknown. Unknown is never drawn as zero. */
export function figure(value: number | null): string {
  return value === null ? '\u2014' : String(value)
}
