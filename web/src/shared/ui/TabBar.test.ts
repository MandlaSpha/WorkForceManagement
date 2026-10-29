import userEvent from '@testing-library/user-event'
import { render, screen } from '@testing-library/vue'
import { describe, expect, it } from 'vitest'
import { ref } from 'vue'

import TabBar from './TabBar.vue'

const TABS = [
  { key: 'one', label: 'One' },
  { key: 'two', label: 'Two' },
  { key: 'three', label: 'Three' },
]

function mount(initial = 'one', variant = 'underline') {
  const chosen = ref(initial)
  render({
    components: { TabBar },
    setup: () => ({ chosen, TABS }),
    template: `<TabBar v-model="chosen" :tabs="TABS" label="Things" id-prefix="x" variant="${variant}" />`,
  })
  return chosen
}

describe('TabBar', () => {
  it('names the group and marks only the chosen tab as selected', () => {
    mount('two')
    expect(screen.getByRole('tablist', { name: 'Things' })).toBeVisible()
    expect(screen.getByRole('tab', { name: 'Two' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('tab', { name: 'One' })).toHaveAttribute('aria-selected', 'false')
  })

  it('points each tab at the panel the page should give it', () => {
    mount()
    const tab = screen.getByRole('tab', { name: 'Two' })
    expect(tab).toHaveAttribute('id', 'x-tab-two')
    expect(tab).toHaveAttribute('aria-controls', 'x-panel-two')
  })

  it('chooses a tab when it is clicked', async () => {
    const chosen = mount()
    await userEvent.setup().click(screen.getByRole('tab', { name: 'Three' }))
    expect(chosen.value).toBe('three')
  })

  it('keeps only the chosen tab in the tab order', () => {
    mount('two')
    expect(screen.getByRole('tab', { name: 'Two' })).toHaveAttribute('tabindex', '0')
    expect(screen.getByRole('tab', { name: 'One' })).toHaveAttribute('tabindex', '-1')
  })

  it('moves with the arrow keys, wrapping at the ends, and moves focus with it', async () => {
    const chosen = mount('one')
    const user = userEvent.setup()
    screen.getByRole('tab', { name: 'One' }).focus()

    await user.keyboard('{ArrowRight}')
    expect(chosen.value).toBe('two')
    expect(screen.getByRole('tab', { name: 'Two' })).toHaveFocus()

    await user.keyboard('{ArrowLeft}{ArrowLeft}')
    expect(chosen.value).toBe('three') // wrapped round from the first
  })

  it('jumps to the first and last with Home and End', async () => {
    const chosen = mount('two')
    const user = userEvent.setup()
    screen.getByRole('tab', { name: 'Two' }).focus()

    await user.keyboard('{End}')
    expect(chosen.value).toBe('three')
    await user.keyboard('{Home}')
    expect(chosen.value).toBe('one')
  })

  it('ignores other keys', async () => {
    const chosen = mount('two')
    const user = userEvent.setup()
    screen.getByRole('tab', { name: 'Two' }).focus()
    await user.keyboard('a{ArrowDown}')
    expect(chosen.value).toBe('two')
  })

  it('keeps the same roles, keys and ids as a segmented pill control', async () => {
    // Failure caught: the restyled variant losing the tab semantics the underline strip has.
    const chosen = mount('one', 'pill')
    const user = userEvent.setup()
    expect(screen.getByRole('tablist', { name: 'Things' })).toHaveClass('rounded-full')
    expect(screen.getByRole('tab', { name: 'Two' })).toHaveAttribute('aria-controls', 'x-panel-two')
    screen.getByRole('tab', { name: 'One' }).focus()
    await user.keyboard('{ArrowRight}')
    expect(chosen.value).toBe('two')
    expect(screen.getByRole('tab', { name: 'Two' })).toHaveFocus()
  })
})
