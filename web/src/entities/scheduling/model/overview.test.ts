import { describe, expect, it } from 'vitest'

import { attentionRoute, barShare } from './overview'

describe('attentionRoute', () => {
  it('sends each kind of item to where it is fixed', () => {
    expect(attentionRoute({ kind: 'understaffed' }).path).toBe('/planner')
    expect(attentionRoute({ kind: 'no_forecast' }).path).toBe('/forecast')
    expect(attentionRoute({ kind: 'assumptions' }).path).toBe('/configure')
    expect(attentionRoute({ kind: 'draft_roster' }).path).toBe('/roster')
  })

  it('falls back to the planner for a kind it does not know', () => {
    expect(attentionRoute({ kind: 'something_new' }).path).toBe('/planner')
  })
})

describe('barShare', () => {
  it('is the worst day at full height and the others in proportion', () => {
    expect(barShare(12, 12)).toBe('100%')
    expect(barShare(6, 12)).toBe('50%')
  })

  it('keeps a small gap visible, and draws nothing when there is no gap at all', () => {
    expect(barShare(1, 1000)).toBe('2%')
    expect(barShare(0, 0)).toBe('0%')
    expect(barShare(0, 12)).toBe('2%')
  })
})
