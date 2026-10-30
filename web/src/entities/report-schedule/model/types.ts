import type { components } from '@/shared/api'

export type ReportSchedule = components['schemas']['ScheduleOut']
export type ReportScheduleBody = components['schemas']['ScheduleIn']
export type ReportSchedulePatch = components['schemas']['SchedulePatch']

export const REPORT_LABEL: Record<string, string> = {
  scorecard: 'Analytics scorecard',
  peaks: 'Peaks and troughs',
  board: 'Investment-board KPI pack',
}
/** One line on what each report holds, shown beside the choice. */
export const REPORT_BLURB: Record<string, string> = {
  scorecard:
    'Service level, handling time and the other headline figures, each labelled Measured, Modelled or Needs data.',
  peaks: 'The busiest and quietest days and half-hours of one queue.',
  board: 'The investment-board KPI pack. It covers every queue, so it needs none chosen.',
}
export const FREQUENCY_LABEL: Record<string, string> = {
  daily: 'Every day',
  weekly: 'Every week',
  monthly: 'Every month',
}
export const WEEKDAYS = [
  'Monday',
  'Tuesday',
  'Wednesday',
  'Thursday',
  'Friday',
  'Saturday',
  'Sunday',
]
export const OUTCOME_LABEL: Record<string, string> = {
  '': 'Not sent yet',
  sent: 'Sent',
  failed: 'Could not be sent',
  stopped: 'Stopped',
}

/** "every day at 07:00", "every Monday at 07:00", "on the 5th at 07:00". */
export function whenLabel(s: ReportSchedule): string {
  const at = `${String(s.hour).padStart(2, '0')}:00`
  if (s.frequency === 'weekly') return `every ${WEEKDAYS[s.weekday]} at ${at}`
  if (s.frequency === 'monthly') return `on day ${s.dayOfMonth} of the month at ${at}`
  return `every day at ${at}`
}
