import { render, screen } from '@testing-library/vue'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, nextTick } from 'vue'

import { smoothPath } from './chart-math'
import BarSeries from './BarSeries.vue'
import DeltaChip from './DeltaChip.vue'
import Sparkline from './Sparkline.vue'
import StackedBar from './StackedBar.vue'
import StatTile from './StatTile.vue'
import { useCountUp } from './useCountUp'

function motion(reduce: boolean) {
  vi.stubGlobal('matchMedia', (q: string) => ({ matches: reduce && q.includes('reduce') }))
}
afterEach(() => vi.unstubAllGlobals())

describe('Sparkline', () => {
  it('has a text alternative and draws one line for a real series', () => {
    const { container } = render(Sparkline, {
      props: { values: [1, 3, 2, 5], label: 'Gap by day: 1, 3, 2, 5' },
    })
    // Failure caught: a chart that a screen reader cannot name.
    expect(screen.getByRole('img')).toHaveAccessibleName('Gap by day: 1, 3, 2, 5')
    expect(container.querySelectorAll('[data-testid="sparkline-line"]')).toHaveLength(1)
    expect(container.innerHTML).not.toContain('NaN')
  })

  it('says there is no data instead of drawing a fake line', () => {
    const { container } = render(Sparkline, { props: { values: [null, null], label: 'x' } })
    // Failure caught: an empty series drawn as a flat line at zero.
    expect(screen.getByTestId('sparkline-empty')).toHaveTextContent('No data yet')
    expect(container.querySelector('path')).toBeNull()
  })

  it('handles a single point and a flat series without NaN', () => {
    const one = render(Sparkline, { props: { values: [4], label: 'one' } })
    expect(one.container.innerHTML).not.toContain('NaN')
    expect(one.container.querySelector('circle')).not.toBeNull()
    const flat = render(Sparkline, { props: { values: [0, 0, 0], label: 'flat' } })
    expect(flat.container.innerHTML).not.toContain('NaN')
  })

  it('breaks the line at a missing value', () => {
    const { container } = render(Sparkline, {
      props: { values: [1, 2, null, 3, 4], label: 'gap' },
    })
    // Failure caught: a missing day bridged as if it had a value.
    expect(container.querySelectorAll('[data-testid="sparkline-line"]')).toHaveLength(2)
  })

  it('smoothPath returns nothing for no points', () => {
    expect(smoothPath([])).toBe('')
  })
})

describe('DeltaChip', () => {
  it('gives direction in text, not colour alone, and judges good by goodWhen', () => {
    render(DeltaChip, { props: { value: -2.5, goodWhen: 'down', versus: 'vs last month' } })
    const chip = screen.getByTestId('delta-chip')
    // Failure caught: a drop in abandon rate shown as bad.
    expect(chip).toHaveAttribute('data-tone', 'good')
    expect(chip).toHaveTextContent('−2.5%')
    expect(chip).toHaveTextContent('Down 2.5% vs last month')
  })

  it('is red when the change is the wrong way, neutral when nothing changed or is known', () => {
    const bad = render(DeltaChip, { props: { value: 4, goodWhen: 'down' } })
    expect(bad.getByTestId('delta-chip')).toHaveAttribute('data-tone', 'bad')
    bad.unmount()
    const flat = render(DeltaChip, { props: { value: 0.0001 } })
    expect(flat.getByTestId('delta-chip')).toHaveTextContent('No change')
    flat.unmount()
    const none = render(DeltaChip, { props: { value: null } })
    // Failure caught: a missing comparison shown as 0%.
    expect(none.getByTestId('delta-chip')).toHaveTextContent('No comparison')
    expect(none.getByTestId('delta-chip')).toHaveAttribute('data-tone', 'neutral')
  })
})

describe('StackedBar', () => {
  const segments = [
    { key: 'ok', label: 'Covered', value: 80, tone: 'ok' as const },
    { key: 'short', label: 'Short', value: 20, tone: 'danger' as const },
    { key: 'none', label: 'No forecast', value: 0, tone: 'chart-4' as const, hatched: true },
  ]

  it('is summarised, sized by share, has a legend with numbers and a labelled marker', () => {
    render(StackedBar, {
      props: { segments, summary: '80 covered, 20 short', marker: { label: 'Today', at: 0.5 } },
    })
    expect(screen.getByRole('img')).toHaveAccessibleName('80 covered, 20 short')
    expect(screen.getByTestId('segment-ok')).toHaveStyle({ width: '80%' })
    expect(screen.getByTestId('segment-short')).toHaveStyle({ width: '20%' })
    expect(screen.getByTestId('stacked-marker')).toHaveTextContent('Today')
    expect(screen.getByText('Short:').closest('li')).toHaveTextContent('20')
  })

  it('shows an empty message when everything is zero', () => {
    render(StackedBar, {
      props: { segments: segments.map((s) => ({ ...s, value: 0 })), summary: 'x' },
    })
    // Failure caught: 0/0 giving NaN widths.
    expect(screen.getByTestId('stacked-empty')).toBeVisible()
  })

  it('leaves the marker out when none is given', () => {
    render(StackedBar, { props: { segments, summary: 'x' } })
    expect(screen.queryByTestId('stacked-marker')).toBeNull()
  })
})

describe('BarSeries', () => {
  const items = [
    { label: 'Mon', value: 12, line: 6 },
    { label: 'Tue', value: 0, line: 3 },
    { label: 'Wed', value: null, line: 4 },
  ]

  it('is summarised, reachable by keyboard and names each bar', () => {
    const { container } = render(BarSeries, {
      props: { items, valueLabel: 'Short', lineLabel: 'Target', summary: 'Short by day' },
    })
    expect(screen.getByRole('img')).toHaveAccessibleName('Short by day')
    const first = screen.getByTestId('bar-0')
    expect(first).toHaveAttribute('tabindex', '0')
    expect(first).toHaveAccessibleName('Mon: 12, Target 6')
    // Failure caught: a missing value drawn as a zero-height bar.
    expect(screen.getByTestId('bar-2')).toHaveAccessibleName('Wed: no value, Target 4')
    expect(container.querySelectorAll('.bar-grow')).toHaveLength(2)
    expect(screen.getByTestId('bars-line')).toBeInTheDocument()
    expect(container.innerHTML).not.toContain('NaN')
  })

  it('says so when no bar has a value', () => {
    render(BarSeries, {
      props: { items: [{ label: 'Mon', value: null }], valueLabel: 'x', summary: 'x' },
    })
    expect(screen.getByTestId('bars-empty')).toBeVisible()
  })

  it('copes with all zeros', () => {
    const { container } = render(BarSeries, {
      props: { items: [{ label: 'Mon', value: 0 }], valueLabel: 'x', summary: 'x' },
    })
    expect(container.innerHTML).not.toContain('NaN')
  })
})

describe('useCountUp and StatTile', () => {
  const Probe = defineComponent({
    setup() {
      const { text, shown, animating } = useCountUp(
        () => 1234,
        (n) => String(Math.round(n)),
      )
      return () =>
        h('p', { 'data-shown': shown.value, 'data-animating': String(animating.value) }, text.value)
    },
  })

  it('is instant under reduced motion, with the final text present', async () => {
    motion(true)
    render(Probe)
    await nextTick()
    // Failure caught: a number that animates for people who asked for no motion.
    expect(screen.getByText('1234')).toHaveAttribute('data-animating', 'false')
    expect(screen.getByText('1234')).toHaveAttribute('data-shown', '1234')
  })

  it('keeps the final text from the first frame when motion is allowed', () => {
    motion(false)
    render(Probe)
    // Failure caught: assistive tech and tests reading a half-counted number.
    expect(screen.getByText('1234')).toHaveAttribute('data-animating', 'true')
  })

  it('renders label, value and a delta, and no sparkline without a series', () => {
    render(StatTile, {
      props: { label: 'Answered', value: 4632, delta: 3, deltaVersus: 'vs June' },
      slots: { default: 'Reached an agent' },
    })
    const li = screen.getByRole('listitem')
    expect(li).toHaveTextContent('Answered')
    expect(li).toHaveTextContent(/4\s632/)
    expect(li).toHaveTextContent('Up 3.0% vs June')
    expect(screen.queryByTestId('sparkline')).toBeNull()
  })

  it('shows a string as given, a zero as zero, and the feature variant is solid brand', () => {
    render(StatTile, { props: { label: 'Gap', value: 0, variant: 'feature', spark: [1, 2] } })
    const li = screen.getByRole('listitem')
    expect(li).toHaveTextContent('0')
    expect(li).not.toHaveTextContent('NaN')
    expect(li.className).toContain('bg-brand')
    expect(screen.getByTestId('sparkline')).toBeInTheDocument()
  })
})
