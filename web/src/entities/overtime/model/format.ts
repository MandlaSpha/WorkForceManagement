export const KIND_LABEL: Record<string, string> = {
  weekday: 'Weekday',
  sunday: 'Sunday',
  holiday: 'Public holiday',
}

/** "18:00 to 20:30 (2h 30m)" from the stored times and minutes. */
export function timeLabel(start: string, end: string, minutes: number): string {
  const h = Math.floor(minutes / 60)
  const m = minutes % 60
  const length = m === 0 ? `${h}h` : h === 0 ? `${m}m` : `${h}h ${m}m`
  return `${start.slice(0, 5)} to ${end.slice(0, 5)} (${length})`
}

/** Rands to the cent, "R 1 234.50" style with a thin grouping space. */
export function rands(amount: number): string {
  return `R ${amount.toLocaleString('en-ZA', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

/** A request can be withdrawn while it waits, or before its day is over if approved. */
export function canCancel(status: string, day: string, today: string): boolean {
  return status === 'pending' || (status === 'approved' && day >= today)
}
