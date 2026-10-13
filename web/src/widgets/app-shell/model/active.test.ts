import { describe, expect, it } from 'vitest'

import { NAV_ITEMS } from '@/shared/config'

import { isActivePath } from './active'

describe('isActivePath', () => {
  it('matches the dashboard on "/" only, not on every other screen', () => {
    expect(isActivePath('/', '/')).toBe(true)
    expect(isActivePath('/', '/roster')).toBe(false)
    expect(isActivePath('/', '/shift-swaps')).toBe(false)
  })

  it('matches a screen on its own path', () => {
    expect(isActivePath('/roster', '/roster')).toBe(true)
    expect(isActivePath('/roster', '/forecast')).toBe(false)
  })

  it('matches anything nested under a screen, but not a longer sibling name', () => {
    expect(isActivePath('/leave', '/leave/42')).toBe(true)
    expect(isActivePath('/leave', '/leaves')).toBe(false)
    expect(isActivePath('/shift-swaps', '/shift')).toBe(false)
  })

  it('ignores a trailing slash', () => {
    expect(isActivePath('/roster', '/roster/')).toBe(true)
    expect(isActivePath('/', '//')).toBe(true)
  })

  it('highlights exactly one entry on every screen', () => {
    for (const current of NAV_ITEMS) {
      const active = NAV_ITEMS.filter((item) => isActivePath(item.path, current.path))
      expect(active.map((i) => i.key)).toEqual([current.key])
    }
  })
})
