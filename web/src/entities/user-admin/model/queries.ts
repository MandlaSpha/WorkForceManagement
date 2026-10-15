import { useQuery } from '@tanstack/vue-query'

import { fetchUsers } from '../api/users'

/** Every change to a user invalidates `all`. */
export const userKeys = { all: ['users'] as const }

export function useUsers() {
  return useQuery({ queryKey: userKeys.all, queryFn: fetchUsers })
}
