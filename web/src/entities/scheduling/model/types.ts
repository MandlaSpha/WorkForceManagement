import type { components } from '@/shared/api'

export type Shift = components['schemas']['ShiftOut']
export type ShiftRequest = components['schemas']['ShiftIn']
export type Employee = components['schemas']['EmployeeOut']
export type EmployeeImportReport = components['schemas']['EmployeeImportOut']
export type UnmappedLogin = components['schemas']['UnmappedLoginOut']
export type EmployeeRequest = components['schemas']['EmployeeIn']
export type Roster = components['schemas']['RosterOut']
export type RosterRow = components['schemas']['RosterRowOut']
export type AssignRequest = components['schemas']['AssignIn']
export type AssignResult = components['schemas']['AssignOut']
export type RosterWeek = components['schemas']['WeekOut']
export type Overview = components['schemas']['OverviewOut']
export type OverviewQueue = components['schemas']['OverviewQueueOut']
export type Attention = components['schemas']['AttentionOut']
export type Plan = components['schemas']['PlanOut']
export type PlanCell = components['schemas']['PlanCellOut']
export type ComplianceRules = components['schemas']['RulesOut']
export type ComplianceRulesState = components['schemas']['RulesState']
export type ComplianceRulesRequest = components['schemas']['RulesIn']
export type ComplianceRulesSaved = components['schemas']['RulesSaved']
export type AutoScheduleRequest = components['schemas']['AutoIn']
export type AutoScheduleProposal = components['schemas']['ProposalOut']
export type AutoScheduleJob = components['schemas']['JobOut']
/** What a finished auto-schedule job reports: counts only, never names. */
export interface AutoScheduleResult {
  status: string
  placed: number
  skipped: Record<string, number>
  shortBefore: number
  shortAfter: number
  overAfter: number
  kept: number
}
export type Recommendation = components['schemas']['RecommendationOut']
export type RecommendationApply = components['schemas']['ApplyIn']
