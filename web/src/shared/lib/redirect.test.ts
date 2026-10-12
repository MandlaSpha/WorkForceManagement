import { describe, expect, it } from 'vitest'

import { safeRedirect } from './redirect'

describe('safeRedirect', () => {
  it('keeps same-site paths, including query strings', () => {
    expect(safeRedirect('/planner')).toBe('/planner')
    expect(safeRedirect('/roster?week=2026-08-17')).toBe('/roster?week=2026-08-17')
  })

  it.each([
    'https://evil.example/phish',
    '//evil.example',
    '/\\evil.example',
    'javascript:alert(1)',
    'planner',
    '',
  ])('refuses %j', (target) => {
    expect(safeRedirect(target)).toBe('/')
  })

  it('refuses non-strings and arrays from a repeated query parameter', () => {
    expect(safeRedirect(undefined)).toBe('/')
    expect(safeRedirect(['/a', '/b'])).toBe('/')
  })

  it('never bounces back to the login page', () => {
    expect(safeRedirect('/login?redirect=/x')).toBe('/')
  })

  it('uses the supplied fallback', () => {
    expect(safeRedirect('//evil', '/my-schedule')).toBe('/my-schedule')
  })
})
