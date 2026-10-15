import { useQuery } from '@tanstack/vue-query'

import { fetchContracts, fetchCustomers } from '../api/contracts'

/** Any change to a customer or contract invalidates `all`. */
export const contractKeys = {
  all: ['contracts'] as const,
  list: ['contracts', 'list'] as const,
  customers: ['contracts', 'customers'] as const,
}

export function useContracts() {
  return useQuery({ queryKey: contractKeys.list, queryFn: fetchContracts })
}

export function useCustomers() {
  return useQuery({ queryKey: contractKeys.customers, queryFn: fetchCustomers })
}
