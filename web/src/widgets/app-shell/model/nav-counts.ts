import { useQuery } from '@tanstack/vue-query'
import { computed, type ComputedRef } from 'vue'

import { fetchRequests, leaveKeys } from '@/entities/leave'
import { canOpen, useSessionStore } from '@/entities/session'
import { fetchSwaps, swapKeys } from '@/entities/swap'

const POLL_MS = 60_000

/** Roles that decide leave and approve swaps. The API refuses everyone else, so asking would only
 * produce an error; this gate is about not asking, not about protection. */
const DECIDERS = ['lead', 'planner', 'admin']

/**
 * What is waiting for the signed-in person, per sidebar item key. Built only from lists the
 * screens already read (same query keys, so a decision made on the page updates the badge at
 * once), refreshed at most once a minute and not at all while the tab is hidden. A count of zero
 * is simply absent. Nothing here is sent to telemetry.
 */
export function useNavCounts(): ComputedRef<Record<string, number>> {
  const session = useSessionStore()
  const allowed = (key: 'leave' | 'swaps'): boolean =>
    session.user !== null && DECIDERS.includes(session.user.role) && canOpen(session.user, key)

  const leave = useQuery({
    queryKey: leaveKeys.requests('pending'),
    queryFn: () => fetchRequests('pending'),
    enabled: computed(() => allowed('leave')),
    refetchInterval: POLL_MS,
    refetchIntervalInBackground: false,
  })
  const swaps = useQuery({
    queryKey: swapKeys.list('awaiting_approval'),
    queryFn: () => fetchSwaps('awaiting_approval'),
    enabled: computed(() => allowed('swaps')),
    refetchInterval: POLL_MS,
    refetchIntervalInBackground: false,
  })

  return computed(() => {
    const counts: Record<string, number> = {}
    // Your own request is not yours to decide, so it is not counted as waiting for you.
    const leaveWaiting = (leave.data.value ?? []).filter((r) => !r.mine).length
    if (leaveWaiting > 0) counts.leave = leaveWaiting
    const swapsWaiting = (swaps.data.value ?? []).length
    if (swapsWaiting > 0) counts.swaps = swapsWaiting
    return counts
  })
}

/** "9+" past nine, so a pill never grows wide. */
export function badgeText(n: number): string {
  return n > 9 ? '9+' : String(n)
}
