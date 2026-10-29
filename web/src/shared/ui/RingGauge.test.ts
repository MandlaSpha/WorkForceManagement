import { render, screen } from '@testing-library/vue'
import { describe, expect, it } from 'vitest'

import RingGauge from './RingGauge.vue'

describe('RingGauge', () => {
  it('names the value for people who cannot see the ring', () => {
    render(RingGauge, { props: { value: 92.4, label: 'Adherence this week' } })
    expect(screen.getByRole('img', { name: 'Adherence this week: 92%' })).toBeVisible()
  })

  it('shows "No data" and draws no arc for null, never a zero', () => {
    // Failure caught: a missing feed drawn as an empty 0 % ring.
    const { container } = render(RingGauge, { props: { value: null, label: 'Adherence' } })
    expect(screen.getByRole('img', { name: 'Adherence: No data' })).toBeVisible()
    expect(container.querySelector('.ring-arc')).toBeNull()
    expect(container).not.toHaveTextContent('0%')
  })

  it('clamps out-of-range values', () => {
    const { container } = render(RingGauge, { props: { value: 140, label: 'x' } })
    expect(container.querySelector('.ring-arc')?.getAttribute('stroke-dasharray')).toBe('100 100')
  })
})
