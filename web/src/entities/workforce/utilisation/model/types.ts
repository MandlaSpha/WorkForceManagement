import type { components } from '@/shared/api'

export type UtilisationReport = components['schemas']['UtilReportOut']
export type UtilisationGroup = components['schemas']['UtilGroupOut']
export type UtilisationPerson = components['schemas']['UtilPersonOut']
export type CostReport = components['schemas']['UtilCostReportOut']
export type EngineerCost = components['schemas']['UtilEngineerCostOut']
export type ContractCost = components['schemas']['UtilContractCostOut']
export type PoolCost = components['schemas']['UtilPoolCostOut']
export type TermsInput = components['schemas']['UtilTermsIn']
export type UtilisationTerms = components['schemas']['UtilTermsOut']

/** A missing figure is a dash, never 0%. */
export function pct(value: number | null | undefined): string {
  return value == null ? '-' : `${value.toFixed(1)}%`
}

/** Percentage points with a sign: "+5.0 pts" or "-12.5 pts". */
export function gapLabel(value: number | null | undefined): string {
  if (value == null) return '-'
  return `${value > 0 ? '+' : ''}${value.toFixed(1)} pts`
}

export function hours(minutes: number): string {
  return (minutes / 60).toFixed(1)
}

/** Rands for display with a plain space and comma-free grouping rules of the locale; a missing
 * figure is a dash, never R0. */
export function rands(value: number | null | undefined): string {
  if (value == null) return '-'
  const [whole = '0', cents = '00'] = Math.abs(value).toFixed(2).split('.')
  const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ' ')
  return `${value < 0 ? '-' : ''}R${grouped}.${cents}`
}
