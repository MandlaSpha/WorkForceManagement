import type { components } from '@/shared/api'

export type Shift = components['schemas']['ShiftOut']
export type ShiftRequest = components['schemas']['ShiftIn']
export type Employee = components['schemas']['EmployeeOut']
export type EmployeeRequest = components['schemas']['EmployeeIn']
export type Roster = components['schemas']['RosterOut']
export type RosterRow = components['schemas']['RosterRowOut']
export type AssignRequest = components['schemas']['AssignIn']
export type AssignResult = components['schemas']['AssignOut']
export type RosterWeek = components['schemas']['WeekOut']
export type Plan = components['schemas']['PlanOut']
export type PlanCell = components['schemas']['PlanCellOut']
