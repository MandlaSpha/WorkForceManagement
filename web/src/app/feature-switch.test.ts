import { screen, within } from '@testing-library/vue'
import { describe, expect, it } from 'vitest'

import { isAvailable } from '@/entities/session'
import type { FeatureKey } from '@/shared/config'
import { ALL_FEATURES, backend } from '@/test/fake-backend'
import { renderApp } from '@/test/render-app'

function signedInAs(role: string, features: string[]) {
  backend.signedIn = { username: role, displayName: `Test ${role}`, role }
  backend.features = features
}

const sidebar = async () =>
  within(await screen.findByRole('navigation', { name: 'Main navigation' }))

describe('the web feature list matches the API', () => {
  it('knows every feature the API can switch, and no others', () => {
    // If the API gains or renames a feature, regenerating the client makes this object fail to
    // compile, which is the cue to update the fake backend and the navigation.
    const known: Record<Exclude<FeatureKey, 'core'>, true> = {
      telephony: true,
      forecasting: true,
      scheduling: true,
      people: true,
      optimisation: true,
      overtime: true,
      insight: true,
      capacity: true,
      intraday: true,
      service_desk: true,
    }
    expect(Object.keys(known).sort()).toEqual([...ALL_FEATURES].sort())
  })
})

describe('isAvailable', () => {
  it('is true for core screens whatever is switched off', () => {
    expect(isAvailable([], 'dashboard')).toBe(true)
    expect(isAvailable([], 'audit')).toBe(true)
  })

  it("follows the screen's feature", () => {
    expect(isAvailable(['telephony'], 'imports')).toBe(true)
    expect(isAvailable(['telephony'], 'forecast')).toBe(false)
    expect(isAvailable(['forecasting'], 'forecast')).toBe(true)
  })
})

describe('a switched-off feature disappears from the sidebar', () => {
  it('hides the screens of features that are not on, and keeps the rest', async () => {
    signedInAs('planner', ['telephony'])
    await renderApp('/')

    const nav = await sidebar()
    expect(nav.getByRole('link', { name: 'Data import' })).toBeVisible()
    expect(nav.getByRole('link', { name: 'Dashboard' })).toBeVisible()
    for (const hidden of ['Forecast', 'Roster', 'Planner', 'Leave', 'Overtime', 'Analytics']) {
      expect(nav.queryByRole('link', { name: hidden })).toBeNull()
    }
  })

  it('with every feature off leaves only the screens that are always there', async () => {
    signedInAs('admin', [])
    await renderApp('/')

    const nav = await sidebar()
    expect(nav.getAllByRole('link').map((link) => link.textContent?.trim())).toEqual([
      'Dashboard',
      'Configure',
      'Users',
      'Audit log',
    ])
  })
})

describe('typing the address of a switched-off screen', () => {
  it('says it is not part of the plan, not that the role lacks access', async () => {
    signedInAs('planner', ['telephony'])
    const { router } = await renderApp('/forecast')

    expect(
      await screen.findByRole('heading', { name: 'This is not part of your plan' }),
    ).toBeVisible()
    expect(router.currentRoute.value.name).toBe('unavailable')
  })

  it('still says "no access" first when the role may not open it either', async () => {
    signedInAs('agent', [])
    const { router } = await renderApp('/planner')

    expect(
      await screen.findByRole('heading', { name: "You don't have access to this page" }),
    ).toBeVisible()
    expect(router.currentRoute.value.name).toBe('forbidden')
  })
})

describe('the dashboard without call data', () => {
  it('says call data is not part of the plan and does not ask for it', async () => {
    signedInAs('planner', ['forecasting'])
    backend.months = ['2026-05']
    await renderApp('/')

    expect(await screen.findByText(/Call data is not part of your plan/)).toBeVisible()
    expect(backend.requests.filter((r) => r.path.includes('/telephony/'))).toEqual([])
  })
})
