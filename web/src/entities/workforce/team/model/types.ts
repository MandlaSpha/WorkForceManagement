import type { components } from '@/shared/api'

export type TeamOverview = components['schemas']['TeamOverviewOut']
export type TeamPerson = components['schemas']['TeamPersonOut']
export type TeamSummary = components['schemas']['TeamSummaryOut']
export type TeamShift = components['schemas']['TeamShiftOut']
export type TeamLeaveBalance = components['schemas']['TeamLeaveBalanceOut']
export type TeamPendingLeave = components['schemas']['TeamPendingLeaveOut']

/** How the grid is ordered. The default is employee number, never performance: a ranking is
 * only ever something the viewer asks for. */
export type TeamSort = 'az' | 'adherence' | 'hours'
