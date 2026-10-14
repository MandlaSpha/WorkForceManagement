import type { PlanCell } from './types'

/** "09:30" for half-hour slot 19. */
export function slotLabel(slot: number): string {
  return `${String(Math.floor(slot / 2)).padStart(2, '0')}:${slot % 2 === 0 ? '00' : '30'}`
}

/** The signed number shown in a heatmap cell: "+2", "−1", "0", or "·" when the requirement is
 * unknown. Unknown is never drawn as zero. */
export function varianceLabel(cell: Pick<PlanCell, 'variance'>): string {
  if (cell.variance === null) return '·'
  if (cell.variance === 0) return '0'
  return cell.variance > 0 ? `+${cell.variance}` : `−${Math.abs(cell.variance)}`
}

export type HeatTone = 'unknown' | 'under-high' | 'under' | 'met' | 'over' | 'over-high'

/** How strongly to colour a half-hour: deeper the further from the requirement. */
export function heatTone(cell: Pick<PlanCell, 'variance' | 'state'>): HeatTone {
  if (cell.variance === null) return 'unknown'
  if (cell.variance <= -3) return 'under-high'
  if (cell.variance < 0) return 'under'
  if (cell.variance === 0) return 'met'
  return cell.variance >= 3 ? 'over-high' : 'over'
}

/** What a screen reader hears for a cell. */
export function cellDescription(cell: PlanCell, dayName: string): string {
  const when = `${dayName} ${slotLabel(cell.slot)}`
  if (cell.required === null || cell.variance === null) {
    return `${when}: ${cell.scheduled} scheduled, requirement unknown`
  }
  return `${when}: ${cell.scheduled} scheduled, ${cell.required} required, ${varianceLabel(cell)}`
}

/** "5 of 48 (10%)": the share of half-hours with a requirement that are under-staffed. */
export function shareLabel(part: number, whole: number): string {
  if (whole === 0) return 'none known'
  return `${part} of ${whole} (${Math.round((part / whole) * 100)}%)`
}

/** Minutes as hours: 480 is "8h", 450 is "7h 30m". */
export { formatMinutes as formatHours } from '@/shared/lib/duration'
