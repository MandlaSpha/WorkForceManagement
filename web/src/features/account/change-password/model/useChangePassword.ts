import { useMutation } from '@tanstack/vue-query'

import { useSessionStore } from '@/entities/session'
import { api, unwrap } from '@/shared/api'

export function useChangePassword() {
  const session = useSessionStore()
  return useMutation({
    mutationFn: async (v: { current: string; next: string }) =>
      unwrap(
        await api.POST('/api/v1/auth/change-password', {
          body: { current: v.current, new: v.next },
        }),
      ),
    onSuccess: () => session.passwordChanged(),
  })
}
