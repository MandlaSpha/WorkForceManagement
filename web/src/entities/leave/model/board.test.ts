import { describe, expect, it } from 'vitest'

import { requestOf } from '@/test/leave-fixtures'

import { canMoveLeave, groupLeave, isMovableLeave } from './board'

describe('leave board', () => {
  it('totals the days in each column and hides Cancelled when empty', () => {
    const cols = groupLeave(
      [
        requestOf({ id: 1, days: 2 }),
        requestOf({ id: 2, days: 1 }),
        requestOf({ id: 3, status: 'approved', days: 5 }),
      ],
      true,
    )
    expect(cols.map((c) => c.key)).toEqual(['pending', 'approved', 'rejected'])
    expect(cols.map((c) => c.total)).toEqual(['3 days', '5 days', '0 days'])
    const withCancelled = groupLeave([requestOf({ status: 'cancelled' })], true)
    expect(withCancelled.map((c) => c.key)).toContain('cancelled')
  })

  it('shows an agent only their own requests', () => {
    // Failure caught: other people's leave on an agent's board.
    const cols = groupLeave([requestOf({ id: 1 }), requestOf({ id: 2, mine: false })], false)
    expect(cols.flatMap((c) => c.items.map((r) => r.id))).toEqual([1])
  })

  it("allows approve and reject of somebody else's pending leave only", () => {
    const other = requestOf({ mine: false })
    expect(canMoveLeave(other, 'approved', true)).toEqual({ ok: true })
    expect(canMoveLeave(other, 'rejected', true)).toEqual({ ok: true })
    expect(canMoveLeave(other, 'approved', false).ok).toBe(false)
    expect(canMoveLeave(requestOf(), 'approved', true).ok).toBe(false) // my own
    expect(canMoveLeave(other, 'cancelled', true).ok).toBe(false)
    expect(canMoveLeave(requestOf({ status: 'approved', mine: false }), 'rejected', true).ok).toBe(
      false,
    )
    expect(isMovableLeave(other, true)).toBe(true)
    expect(isMovableLeave(other, false)).toBe(false)
  })
})
