import { useQuery } from '@tanstack/vue-query'
import { computed } from 'vue'
import type { Ref } from 'vue'

import { fetchAssignees, fetchContracts, fetchCustomers } from '../api/contracts'

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

/** Who looks after a customer (admin only). */
export function useAssignees(customerId: Ref<number>) {
  return useQuery({
    queryKey: computed(() => [...contractKeys.customers, customerId.value, 'assignees']),
    queryFn: () => fetchAssignees(customerId.value),
  })
}
