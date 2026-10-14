import { describe, expect, it } from 'vitest'

import { canCancel, daysLeft, rangeLabel } from './format'

describe('rangeLabel', () => {
  it('names one day once and a range with both ends', () => {
    expect(rangeLabel('2026-05-25', '2026-05-25')).toBe('Mon 25 May')
    expect(rangeLabel('2026-05-25', '2026-05-26')).toBe('Mon 25 May to Tue 26 May')
  })
})

describe('daysLeft', () => {
  it('says how much is left, and that a kind with no limit has none', () => {
    expect(daysLeft(13, 15)).toBe('13 of 15 days left')
    expect(daysLeft(null, null)).toBe('no limit')
  })

  it('shows an overdrawn balance as it is', () => {
    expect(daysLeft(-2, 15)).toBe('-2 of 15 days left')
  })
})

describe('canCancel', () => {
  it('lets a waiting request be withdrawn at any time', () => {
    expect(canCancel('pending', '2026-01-01', '2026-05-20')).toBe(true)
  })

  it('lets approved leave be cancelled until its last day, and not after', () => {
    expect(canCancel('approved', '2026-05-26', '2026-05-26')).toBe(true)
    expect(canCancel('approved', '2026-05-26', '2026-05-27')).toBe(false)
  })

  it('does not let a decided or withdrawn request be cancelled', () => {
    expect(canCancel('rejected', '2099-01-01', '2026-05-20')).toBe(false)
    expect(canCancel('cancelled', '2099-01-01', '2026-05-20')).toBe(false)
  })
})
