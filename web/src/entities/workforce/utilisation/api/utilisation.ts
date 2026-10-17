import { api, unwrap } from '@/shared/api'

import type { CostReport, TermsInput, UtilisationReport, UtilisationTerms } from '../model/types'

/** `month` is the first day of the month, as YYYY-MM-DD. */
export async function fetchUtilisation(month: string): Promise<UtilisationReport> {
  return unwrap(await api.GET('/api/v1/utilisation/report', { params: { query: { month } } }))
}

/** Pay roles only: the API refuses everyone else. */
export async function fetchCosts(month: string): Promise<CostReport> {
  return unwrap(await api.GET('/api/v1/utilisation/costs', { params: { query: { month } } }))
}

export async function saveTerms(contractId: number, terms: TermsInput): Promise<UtilisationTerms> {
  return unwrap(
    await api.PUT('/api/v1/utilisation/contracts/{contract_id}/terms', {
      params: { path: { contract_id: contractId } },
      body: terms,
    }),
  )
}
