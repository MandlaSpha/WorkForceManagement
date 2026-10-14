import { computed, watch } from 'vue'

import { useQueues } from '@/entities/call-data'
import { useSessionStore } from '@/entities/session'

import { useContextStore } from './store'

/** Fill the top-bar queue picker from the API, for the roles that have queues to pick from, and
 * empty it when the signed-in person changes so nobody sees the previous person's list. */
export function useSyncQueues(): void {
  const session = useSessionStore()
  const context = useContextStore()

  const wanted = computed(
    () =>
      session.user !== null &&
      session.user.role !== 'agent' &&
      session.user.features.includes('telephony'),
  )
  const queues = useQueues(wanted)

  watch(
    () => queues.data.value,
    (list) => {
      if (list) context.setQueues(list.map((q) => ({ value: String(q.id), label: q.name })))
    },
    { immediate: true },
  )
  watch(
    () => session.user?.username ?? null,
    (username) => {
      if (username === null) context.clearScope()
    },
  )
}
