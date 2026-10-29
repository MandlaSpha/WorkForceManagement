import type { Peaks } from './types'

export const WEEKDAYS = [
  'Monday',
  'Tuesday',
  'Wednesday',
  'Thursday',
  'Friday',
  'Saturday',
  'Sunday',
]

/** "10:30" for half-hour 21. */
export function slotName(slot: number): string {
  return `${String(Math.floor(slot / 2)).padStart(2, '0')}:${slot % 2 === 0 ? '00' : '30'}`
}

/** 0 = Monday .. 6 = Sunday for a plain calendar day. No time zone is involved. */
export function weekdayOf(day: string): number {
  return (new Date(`${day}T12:00:00Z`).getUTCDay() + 6) % 7
}

interface SlotFigure {
  slot: string
  average: number
}

export interface PeaksSummary {
  /** The weekday with the highest average calls a day, or null with no data. */
  busiestWeekday: number | null
  busiestSlot: SlotFigure | null
  quietestSlot: SlotFigure | null
  /** Busiest slot average divided by the quietest open slot average; only when both exist. */
  ratio: number | null
  sentence: string | null
}

export function summarise(p: Peaks): PeaksSummary {
  const byWeekday = new Map<number, { total: number; days: number }>()
  for (const d of p.daily) {
    const w = weekdayOf(d.day)
    const cur = byWeekday.get(w) ?? { total: 0, days: 0 }
    byWeekday.set(w, { total: cur.total + d.offered, days: cur.days + 1 })
  }
  let busiestWeekday: number | null = null
  let best = -1
  for (const [w, { total, days }] of [...byWeekday].sort((a, b) => a[0] - b[0])) {
    if (total / days > best) {
      best = total / days
      busiestWeekday = w
    }
  }
  const slots: SlotFigure[] = p.profile.map((s) => ({
    slot: s.slot,
    average: Number(s.averageOffered),
  }))
  let busiestSlot: SlotFigure | null = null
  let quietestSlot: SlotFigure | null = null
  for (const s of slots) {
    if (busiestSlot === null || s.average > busiestSlot.average) busiestSlot = s
    if (quietestSlot === null || s.average < quietestSlot.average) quietestSlot = s
  }
  const ratio =
    busiestSlot && quietestSlot && slots.length > 1 && quietestSlot.average > 0
      ? busiestSlot.average / quietestSlot.average
      : null
  const parts: string[] = []
  if (busiestWeekday !== null && byWeekday.size > 1) {
    parts.push(`${WEEKDAYS[busiestWeekday]}s carry the most calls`)
  }
  if (busiestSlot) {
    parts.push(
      `the busiest half-hour is ${busiestSlot.slot} with ${busiestSlot.average.toFixed(1)} calls on average`,
    )
  }
  const joined = parts.join('; ')
  return {
    busiestWeekday,
    busiestSlot,
    quietestSlot,
    ratio,
    sentence: joined ? `${joined.charAt(0).toUpperCase()}${joined.slice(1)}.` : null,
  }
}
