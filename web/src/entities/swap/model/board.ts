import type { Swap } from './types'

/** The stages of the swap board, in the order a swap passes through them. */
export const SWAP_STAGES = [
  { key: 'waiting', label: 'Waiting for a colleague', dot: 'bg-warn', empty: 'Nothing waiting' },
  {
    key: 'accepted',
    label: 'Accepted - needs approval',
    dot: 'bg-brand',
    empty: 'Nothing to approve',
  },
  { key: 'approved', label: 'Approved', dot: 'bg-ok', empty: 'Nothing approved yet' },
  {
    key: 'declined',
    label: 'Declined or cancelled',
    dot: 'bg-danger',
    empty: 'Nothing declined or cancelled',
  },
] as const

export type SwapStage = (typeof SWAP_STAGES)[number]['key']
export type MoveVerdict = { ok: true } | { ok: false; reason: string }

export function stageOf(status: string): SwapStage {
  if (status === 'open') return 'waiting'
  if (status === 'awaiting_approval') return 'accepted'
  if (status === 'approved') return 'approved'
  return 'declined' // rejected and cancelled
}

/** Cosmetic, like the buttons on the list: the API decides who may answer a swap. A swap the
 * person is in is never theirs to decide, whatever their role. */
export function canMoveSwap(swap: Swap, to: string, decides: boolean): MoveVerdict {
  const from = stageOf(swap.status)
  if (from === 'waiting') return { ok: false, reason: 'No colleague has taken this swap yet.' }
  if (from !== 'accepted') return { ok: false, reason: 'This swap has already been decided.' }
  if (to !== 'approved' && to !== 'declined') {
    return { ok: false, reason: 'A swap that a colleague accepted cannot go back to waiting.' }
  }
  if (!decides) return { ok: false, reason: 'Only a lead, planner or admin can decide a swap.' }
  if (swap.asker || swap.colleague) {
    return { ok: false, reason: 'Somebody else decides a swap you are in.' }
  }
  return { ok: true }
}

/** Does this person get the Move to button on this swap? */
export function isMovableSwap(swap: Swap, decides: boolean): boolean {
  return decides && swap.status === 'awaiting_approval'
}

/** Cards per column. An agent sees only the swaps they are in. */
export function groupSwaps(swaps: ReadonlyArray<Swap>, decides: boolean) {
  const visible = decides ? swaps : swaps.filter((s) => s.asker || s.colleague)
  return SWAP_STAGES.map((stage) => ({
    ...stage,
    items: visible.filter((s) => stageOf(s.status) === stage.key),
  }))
}
