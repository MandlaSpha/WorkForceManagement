import { api, unwrap } from '@/shared/api'

import type { Swap, SwapBody, SwapShift } from '../model/types'

export async function fetchMyShifts(): Promise<SwapShift[]> {
  return unwrap(await api.GET('/api/v1/people/swaps/my-shifts'))
}

export async function fetchOptions(giveAssignmentId: number): Promise<SwapShift[]> {
  return unwrap(
    await api.GET('/api/v1/people/swaps/options', {
      params: { query: { give_assignment_id: giveAssignmentId } },
    }),
  )
}

export async function fetchSwaps(status: string | null): Promise<Swap[]> {
  return unwrap(
    await api.GET('/api/v1/people/swaps', {
      params: { query: status === null ? {} : { status } },
    }),
  )
}

export async function offerSwap(body: SwapBody): Promise<Swap> {
  return unwrap(await api.POST('/api/v1/people/swaps', { body }))
}

export type SwapAnswer = 'accept' | 'decline' | 'approve' | 'reject' | 'cancel'

export async function answerSwap(swapId: number, what: SwapAnswer): Promise<Swap> {
  const path = `/api/v1/people/swaps/{swap_id}/${what}` as const
  return unwrap(await api.POST(path, { params: { path: { swap_id: swapId } } }))
}
