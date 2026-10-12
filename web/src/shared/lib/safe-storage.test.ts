import { afterEach, describe, expect, it, vi } from 'vitest'

import { safeStorage } from './safe-storage'

afterEach(() => vi.restoreAllMocks())

describe('safeStorage', () => {
  it('round-trips a value', () => {
    safeStorage.set('k', 'v')
    expect(safeStorage.get('k')).toBe('v')
  })

  it('returns null for a missing key', () => {
    expect(safeStorage.get('missing')).toBeNull()
  })

  it('does not throw when storage is blocked (private window, blocked site data)', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new DOMException('blocked', 'SecurityError')
    })
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('quota', 'QuotaExceededError')
    })

    expect(safeStorage.get('k')).toBeNull()
    expect(() => safeStorage.set('k', 'v')).not.toThrow()
  })
})
