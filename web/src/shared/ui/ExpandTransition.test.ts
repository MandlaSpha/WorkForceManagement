import { render, screen } from '@testing-library/vue'
import { defineComponent, h, nextTick, ref, vShow, withDirectives } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'

import ExpandTransition from './ExpandTransition.vue'

function mount(open: ReturnType<typeof ref<boolean>>) {
  const Host = defineComponent({
    setup: () => () =>
      h(ExpandTransition, null, {
        default: () => withDirectives(h('ul', { 'data-testid': 'panel' }), [[vShow, open.value]]),
      }),
  })
  return render(Host)
}

afterEach(() => {
  vi.restoreAllMocks()
  // @ts-expect-error - remove the stub added by a test
  delete HTMLElement.prototype.animate
})

describe('opening and closing a block', () => {
  it('shows and hides at once where animation is unavailable', async () => {
    // Failure caught: a closed menu group left visible (and tabbable) when the browser cannot
    // animate, or the content never appearing because the animation never "finished".
    const open = ref(false)
    mount(open)
    expect(screen.getByTestId('panel')).not.toBeVisible()
    open.value = true
    await nextTick()
    expect(screen.getByTestId('panel')).toBeVisible()
    open.value = false
    await nextTick()
    expect(screen.getByTestId('panel')).not.toBeVisible()
  })

  it('goes straight to the end when the person asks for less motion', async () => {
    // Failure caught: an animation running for someone who set prefers-reduced-motion.
    const animate = vi.fn()
    HTMLElement.prototype.animate = animate as never
    vi.stubGlobal('matchMedia', () => ({ matches: true, addEventListener: () => {} }))
    const open = ref(false)
    mount(open)
    open.value = true
    await nextTick()
    expect(animate).not.toHaveBeenCalled()
    expect(screen.getByTestId('panel')).toBeVisible()
    vi.unstubAllGlobals()
  })
})
