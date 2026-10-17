import { afterEach, describe, expect, it, vi } from 'vitest'

import { isPhone, PHONE_QUERY } from './viewport'

afterEach(() => {
  vi.unstubAllGlobals()
})

function windowAt(matches: boolean) {
  const matchMedia = vi.fn((query: string) => ({ matches: matches && query === PHONE_QUERY }))
  vi.stubGlobal('matchMedia', matchMedia)
  return matchMedia
}

describe('isPhone', () => {
  it('is true when the window is narrower than the sm breakpoint', () => {
    const matchMedia = windowAt(true)
    expect(isPhone()).toBe(true)
    expect(matchMedia).toHaveBeenCalledWith('(max-width: 639px)')
  })

  it('is false on a wider window', () => {
    windowAt(false)
    expect(isPhone()).toBe(false)
  })

  it('is false where the browser cannot say, so the full layout is shown', () => {
    vi.stubGlobal('matchMedia', undefined)
    expect(isPhone()).toBe(false)
  })
})
