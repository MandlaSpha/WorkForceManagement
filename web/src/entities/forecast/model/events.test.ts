import { describe, expect, it } from 'vitest'

import { changeLabel } from './events'

describe('changeLabel', () => {
  it('signs a rise and a fall, using a real minus sign', () => {
    expect(changeLabel(20)).toBe('+20%')
    expect(changeLabel(-50)).toBe('\u221250%')
  })

  it('shows a closed queue as a full fall and keeps decimals', () => {
    expect(changeLabel(-100)).toBe('\u2212100%')
    expect(changeLabel(12.5)).toBe('+12.5%')
  })

  it('does not sign zero as a fall', () => {
    expect(changeLabel(0)).toBe('+0%')
  })
})
