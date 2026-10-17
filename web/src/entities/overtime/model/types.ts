import type { components } from '@/shared/api'

export type Overtime = components['schemas']['OvertimeOut']
export type OvertimeBody = components['schemas']['OvertimeIn']
export type PayStatus = components['schemas']['OvertimePayOut']
export type PayBody = components['schemas']['OvertimePayIn']
export type Standby = components['schemas']['StandbyOut']
export type OvertimeSummary = components['schemas']['SummaryOut']
export type OvertimeStatus = 'pending' | 'approved' | 'rejected' | 'cancelled'
