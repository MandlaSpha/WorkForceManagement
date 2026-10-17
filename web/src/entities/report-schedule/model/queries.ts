import { useQuery } from '@tanstack/vue-query'

import { fetchAllowedDomains, fetchSchedules } from '../api/report-schedule'

export const reportKeys = {
  all: ['reports'] as const,
  schedules: ['reports', 'schedules'] as const,
  domains: ['reports', 'domains'] as const,
}

export function useSchedules() {
  return useQuery({ queryKey: reportKeys.schedules, queryFn: fetchSchedules })
}

export function useAllowedDomains() {
  return useQuery({ queryKey: reportKeys.domains, queryFn: fetchAllowedDomains })
}
