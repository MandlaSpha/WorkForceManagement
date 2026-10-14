/** The roster legend: how a shift is coloured by its kind. One mapping, used by the cells and the
 * legend, so they cannot drift apart. */
export const SHIFT_TONE: Record<string, string> = {
  early: 'bg-warn-soft text-warn',
  day: 'bg-brand-soft text-brand-ink',
  late: 'bg-violet-100 text-violet-900 dark:bg-violet-900/50 dark:text-violet-100',
  night: 'bg-indigo-100 text-indigo-900 dark:bg-indigo-900/50 dark:text-indigo-100',
}

export const SHIFT_KIND_LABEL: Record<string, string> = {
  early: 'Early (before 09:00)',
  day: 'Day (09:00 to 13:00)',
  late: 'Late (from 13:00)',
  night: 'Night (overnight)',
}

export const SHIFT_KINDS = ['early', 'day', 'late', 'night'] as const
