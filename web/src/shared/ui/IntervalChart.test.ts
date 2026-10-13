import { render, screen, within } from '@testing-library/vue'
import { describe, expect, it } from 'vitest'

import IntervalChart, { type ChartPoint } from './IntervalChart.vue'

const props = (points: ChartPoint[]) => ({
  points,
  summary: 'Expected calls and agents required, 10:00 to 11:00',
  barLabel: 'Expected calls',
  lineLabel: 'Agents to roster',
})

const POINTS: ChartPoint[] = [
  { label: '10:00', bars: 20, line: 6 },
  { label: '10:30', bars: 10, line: 4 },
  { label: '11:00', bars: 0, line: 0 },
]

describe('IntervalChart', () => {
  it('is described to people who cannot see it', () => {
    render(IntervalChart, { props: props(POINTS) })
    expect(screen.getByRole('img')).toHaveAccessibleName(/Expected calls and agents required/)
  })

  it('draws one bar per half-hour, scaled so the biggest fills the height', () => {
    const { container } = render(IntervalChart, { props: props(POINTS) })
    const bars = [...container.querySelectorAll('[data-testid="chart-bar"]')]
    const heights = bars.map((b) => Number(b.getAttribute('height')))
    expect(bars).toHaveLength(3)
    expect(heights[1]).toBeCloseTo(heights[0]! / 2) // 10 calls is half of 20
    expect(heights[2]).toBe(0)
  })

  it('breaks the line where there is no value instead of dropping it to zero', () => {
    const { container } = render(IntervalChart, {
      props: props([
        { label: '10:00', bars: 5, line: 4 },
        { label: '10:30', bars: 5, line: null },
        { label: '11:00', bars: 5, line: 4 },
      ]),
    })
    const path = container.querySelector('[data-testid="chart-line"]')?.getAttribute('d') ?? ''
    expect(path.match(/M/g)).toHaveLength(2) // two separate pieces
    expect(path).not.toMatch(/L/) // never joined across the gap
  })

  it('draws no line at all when nothing has a value', () => {
    const { container } = render(IntervalChart, {
      props: props([{ label: '10:00', bars: 5, line: null }]),
    })
    expect(container.querySelector('[data-testid="chart-line"]')).toBeNull()
  })

  it('offers the same numbers as a table', () => {
    render(IntervalChart, { props: props(POINTS) })
    const table = within(screen.getByRole('table'))
    expect(table.getAllByRole('row')).toHaveLength(4) // header + three half-hours
    expect(table.getByRole('rowheader', { name: '10:00' }).parentElement).toHaveTextContent('20.0')
    expect(table.getByRole('rowheader', { name: '10:00' }).parentElement).toHaveTextContent('6')
  })

  it('copes with an empty day', () => {
    const { container } = render(IntervalChart, { props: props([]) })
    expect(container.querySelectorAll('[data-testid="chart-bar"]')).toHaveLength(0)
  })
})
