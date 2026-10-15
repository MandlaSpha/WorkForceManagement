import { api, unwrap } from '@/shared/api'

import type { BoardEntry, Swap, SwapBody, SwapShift } from '../model/types'

export async function fetchMyShifts(): Promise<SwapShift[]> {
  return unwrap(await api.GET('/api/v1/people/swaps/my-shifts'))
}

export async function fetchBoard(): Promise<BoardEntry[]> {
  return unwrap(await api.GET('/api/v1/people/swaps/board'))
}

/** Which of my shifts could be offered in return for an open request. */
export async function fetchOffers(swapId: number): Promise<SwapShift[]> {
  return unwrap(
    await api.GET('/api/v1/people/swaps/{swap_id}/offers', {
      params: { path: { swap_id: swapId } },
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

export async function postSwap(body: SwapBody): Promise<Swap> {
  return unwrap(await api.POST('/api/v1/people/swaps', { body }))
}

export async function takeSwap(swapId: number, assignmentId: number): Promise<Swap> {
  return unwrap(
    await api.POST('/api/v1/people/swaps/{swap_id}/accept', {
      params: { path: { swap_id: swapId } },
      body: { assignmentId },
    }),
  )
}

export type SwapAnswer = 'approve' | 'reject' | 'cancel'

export async function answerSwap(swapId: number, what: SwapAnswer): Promise<Swap> {
  const path = `/api/v1/people/swaps/{swap_id}/${what}` as const
  return unwrap(await api.POST(path, { params: { path: { swap_id: swapId } } }))
}
