import { describe, expect, it } from 'vitest'

import { matchedOf, swapOf } from '@/test/swap-fixtures'

import { canMoveSwap, groupSwaps, isMovableSwap, stageOf } from './board'

describe('swap board columns', () => {
  it('puts every status in its stage, rejected and cancelled together', () => {
    expect(['open', 'awaiting_approval', 'approved', 'rejected', 'cancelled'].map(stageOf)).toEqual(
      ['waiting', 'accepted', 'approved', 'declined', 'declined'],
    )
  })

  it('shows an agent only the swaps they are in', () => {
    // Failure caught: a colleague's swap leaking onto an agent's board.
    const mine = swapOf({ id: 1, asker: true })
    const theirs = swapOf({ id: 2, asker: false, colleague: false })
    const cols = groupSwaps([mine, theirs], false)
    expect(cols.flatMap((c) => c.items.map((s) => s.id))).toEqual([1])
    expect(groupSwaps([mine, theirs], true).flatMap((c) => c.items)).toHaveLength(2)
  })
})

describe('legal swap moves', () => {
  const decider = matchedOf({ asker: false, colleague: false })

  it('lets a decider approve or decline an accepted swap', () => {
    expect(canMoveSwap(decider, 'approved', true)).toEqual({ ok: true })
    expect(canMoveSwap(decider, 'declined', true)).toEqual({ ok: true })
  })

  it.each([
    ['an agent', decider, false, 'approved', /Only a lead/],
    ['a swap the decider is in', matchedOf({ asker: true }), true, 'approved', /Somebody else/],
    ['back to waiting', decider, true, 'waiting', /cannot go back/],
    ['a swap nobody took', swapOf({ asker: false }), true, 'approved', /No colleague/],
    ['a decided swap', swapOf({ status: 'approved' }), true, 'declined', /already been decided/],
  ])('refuses %s, with a reason', (_n, swap, decides, to, reason) => {
    // Failure caught: an illegal drop target looking legal.
    const verdict = canMoveSwap(swap, to, decides)
    expect(verdict.ok).toBe(false)
    expect(verdict.ok ? '' : verdict.reason).toMatch(reason)
  })

  it('gives the Move button only to deciders, on swaps awaiting approval', () => {
    expect(isMovableSwap(decider, true)).toBe(true)
    expect(isMovableSwap(decider, false)).toBe(false)
    expect(isMovableSwap(swapOf(), true)).toBe(false)
  })
})
