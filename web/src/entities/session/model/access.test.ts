import { describe, expect, it } from 'vitest'

import { NAV_ITEMS, type NavKey } from '@/shared/config'

import { ACCESS, canAccess, homePathFor, isRole, ROLES, type Role } from './access'

const keysFor = (role: Role): NavKey[] =>
  NAV_ITEMS.filter((i) => canAccess(role, i.key)).map((i) => i.key)

describe('role matrix (docs/04-UML.md section 2.6)', () => {
  it('has an access rule for every screen and no rule for an unknown one', () => {
    expect(Object.keys(ACCESS).sort()).toEqual(NAV_ITEMS.map((i) => i.key).sort())
  })

  it('gives every screen at least one role', () => {
    for (const item of NAV_ITEMS) expect(ACCESS[item.key].length).toBeGreaterThan(0)
  })

  it('gives every role at least one screen', () => {
    for (const role of ROLES) expect(keysFor(role).length).toBeGreaterThan(0)
  })

  it('limits agents to their own schedule, availability, leave and swaps', () => {
    expect(keysFor('agent').sort()).toEqual(['leave', 'my-availability', 'my-schedule', 'swaps'])
  })

  it('keeps configuration and the audit log admin-only', () => {
    for (const key of ['configure', 'audit'] as const) {
      expect(ACCESS[key]).toEqual(['admin'])
    }
  })

  it('keeps executives read-only: dashboards, capacity and reporting, no editing screens', () => {
    const exec = keysFor('executive')
    expect(exec).toEqual(expect.arrayContaining(['dashboard', 'analytics', 'reports', 'capacity']))
    for (const writing of ['roster', 'leave', 'overtime', 'configure', 'employees'] as const) {
      expect(exec).not.toContain(writing)
    }
  })

  it('keeps pay-related screens away from agents and executives', () => {
    for (const role of ['agent', 'executive'] as const) {
      expect(canAccess(role, 'overtime')).toBe(false)
    }
  })

  it('lets admins open everything a planner or lead can', () => {
    for (const item of NAV_ITEMS) {
      if (canAccess('planner', item.key) || canAccess('lead', item.key)) {
        expect(canAccess('admin', item.key)).toBe(true)
      }
    }
  })
})

describe('homePathFor', () => {
  it('sends agents to their schedule and everyone else to the dashboard', () => {
    expect(homePathFor('agent')).toBe('/my-schedule')
    for (const role of ROLES.filter((r) => r !== 'agent')) expect(homePathFor(role)).toBe('/')
  })

  it('lands each role on a screen it may actually open', () => {
    for (const role of ROLES) {
      const home = NAV_ITEMS.find((i) => i.path === homePathFor(role))
      expect(home).toBeDefined()
      expect(canAccess(role, home!.key)).toBe(true)
    }
  })
})

describe('isRole', () => {
  it('accepts known roles and rejects everything else', () => {
    expect(isRole('planner')).toBe(true)
    expect(isRole('root')).toBe(false)
    expect(isRole(undefined)).toBe(false)
  })
})
