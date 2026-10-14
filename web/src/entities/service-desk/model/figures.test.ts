import { describe, expect, it } from 'vitest'

import { fteLabel, rejectReason } from './figures'

describe('fteLabel', () => {
  it('shows two decimals, a dash for unknown and never a made-up zero', () => {
    expect(fteLabel(0.9)).toBe('0.90')
    expect(fteLabel(0)).toBe('0.00')
    expect(fteLabel(null)).toBe('\u2014')
  })

  it('says "at least" when the figure is a minimum', () => {
    expect(fteLabel(0.2, false)).toBe('at least 0.20')
    expect(fteLabel(null, false)).toBe('\u2014')
  })
})

describe('rejectReason', () => {
  it('puts a reason in words and passes an unknown one through', () => {
    expect(rejectReason('bad_effort')).toMatch(/whole number of minutes/)
    expect(rejectReason('something_new')).toBe('something_new')
  })
})
