import type { Shift } from '@/entities/scheduling'

export type SortKey = 'code' | 'startTime' | 'endTime' | 'paidMinutes'
export interface Sort {
  key: SortKey
  dir: 'asc' | 'desc'
}

/** How many rows the table adds each time. */
export const PAGE_SIZE = 20

/** Shifts matching the search (code or times, case-insensitive), in the chosen order. Codes sort
 * the way people read them (D2 before D10). */
export function visibleShifts(shifts: ReadonlyArray<Shift>, search: string, sort: Sort): Shift[] {
  const needle = search.trim().toLowerCase()
  const found = needle
    ? shifts.filter((s) => `${s.code} ${s.startTime} ${s.endTime}`.toLowerCase().includes(needle))
    : [...shifts]
  const sign = sort.dir === 'asc' ? 1 : -1
  return found.sort((a, b) => {
    const x = a[sort.key]
    const y = b[sort.key]
    const order =
      typeof x === 'number' && typeof y === 'number'
        ? x - y
        : String(x).localeCompare(String(y), 'en', { numeric: true })
    return sign * order || a.code.localeCompare(b.code, 'en', { numeric: true })
  })
}
