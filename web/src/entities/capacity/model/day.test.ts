import { describe, expect, it } from 'vitest'

import { dayStatus, figure } from './day'

describe('dayStatus', () => {
  it('has no status for a day nothing is forecast for', () => {
    expect(dayStatus({ peak: null, seasonal: null, overflow: null })).toBe('unknown')
  })

  it('is permanent when the permanent staff cover the peak', () => {
    expect(dayStatus({ peak: 60, seasonal: 0, overflow: 0 })).toBe('permanent')
  })

  it('needs seasonal agents once the permanent staff are not enough', () => {
    expect(dayStatus({ peak: 160, seasonal: 60, overflow: 0 })).toBe('seasonal')
  })

  it('is overflow whenever anything is left over, even one agent', () => {
    expect(dayStatus({ peak: 351, seasonal: 250, overflow: 1 })).toBe('overflow')
  })

  it('treats a peak of zero as covered, not unknown', () => {
    expect(dayStatus({ peak: 0, seasonal: 0, overflow: 0 })).toBe('permanent')
  })
})

describe('figure', () => {
  it('shows a dash for unknown and a real zero for zero', () => {
    expect(figure(null)).toBe('\u2014')
    expect(figure(0)).toBe('0')
    expect(figure(42)).toBe('42')
  })
})
