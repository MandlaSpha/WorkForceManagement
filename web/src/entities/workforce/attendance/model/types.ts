import type { components } from '@/shared/api'

export type AttendanceDay = components['schemas']['AttendanceQueueDayOut']
export type AttendancePerson = components['schemas']['AttendancePersonOut']
export type MyAttendance = components['schemas']['AttendanceMineOut']
export type StateImportReport = components['schemas']['AttendanceImportOut']

export const STATE_LABEL: Record<string, string> = {
  available: 'Available',
  on_call: 'On a call',
  wrap_up: 'Wrap-up',
  break: 'Break',
  lunch: 'Lunch',
  training: 'Training',
  meeting: 'Meeting',
  away: 'Away',
  logged_out: 'Logged out',
}

/** The states that count as doing the queue's work (the API's rule, shown to the person). */
export const WORKING_STATES = new Set(['available', 'on_call', 'wrap_up'])

export const EXCEPTION_LABEL: Record<string, string> = {
  no_show: 'Not on the phones',
  late_start: 'Late start',
  early_finish: 'Early finish',
  out_of_adherence: 'Below adherence target',
}

/** "09:30" from an ISO date-time that already carries the South African offset. */
export function clockOf(iso: string): string {
  return iso.slice(11, 16)
}
