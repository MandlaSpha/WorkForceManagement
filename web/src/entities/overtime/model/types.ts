import type { components } from '@/shared/api'

export type Overtime = components['schemas']['OvertimeOut']
export type OvertimeBody = components['schemas']['OvertimeIn']
export type PayStatus = components['schemas']['OvertimePayOut']
export type PayBody = components['schemas']['OvertimePayIn']
export type OvertimeStatus = 'pending' | 'approved' | 'rejected' | 'cancelled'
