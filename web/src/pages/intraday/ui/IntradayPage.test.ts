import { screen, within } from '@testing-library/vue'
import { describe, expect, it } from 'vitest'

import type { Intraday } from '@/entities/intraday'
import { backend } from '@/test/fake-backend'
import { openScheduling, seedScheduling } from '@/test/open-scheduling'

const slots = Array.from({ length: 48 }, (_, slot) => ({
  slot,
  forecast: 10,
  actual: slot < 22 ? 12 : null,
  reforecast: 12,
  scheduled: 3,
  required: 3,
  expectedRequired: slot >= 22 ? 4 : null,
}))

const day = (over: Partial<Intraday> = {}): Intraday => ({
  queue: 'QueueA',
  day: '2031-03-03',
  elapsed: 22,
  hasForecast: true,
  ratio: 1.2,
  dataThrough: 21,
  serviceLevelPct: 78.5,
  slots,
  alerts: [
    { slot: 23, scheduled: 3, required: 4, short: 1, severity: 'warning' },
    { slot: 24, scheduled: 1, required: 4, short: 3, severity: 'critical' },
  ],
  ...over,
})

async function open(role = 'planner', over: Partial<Intraday> = {}) {
  seedScheduling()
  backend.intraday = day(over)
  return openScheduling('/intraday', role)
}

describe('intraday', () => {
  it('says how the day is running and how far the data reaches', async () => {
    // Failure caught: imported calls presented as live, with no hint of how stale they are.
    await open()
    expect(await screen.findByTestId('running')).toHaveTextContent('120% of forecast')
    expect(screen.getByTestId('running')).toHaveTextContent('Calls are imported up to 10:30')
    expect(screen.getByTestId('sl')).toHaveTextContent('78.5%')
  })

  it('lists where cover falls short, worst marked critical, with a way to act', async () => {
    await open()
    const critical = await screen.findByTestId('alert-24')
    expect(critical).toHaveTextContent('Critical')
    expect(critical).toHaveTextContent('12:00: 1 scheduled, 4 needed (3 short)')
    expect(within(screen.getByTestId('alert-23')).getByText('Warning')).toBeVisible()
    expect(screen.getByTestId('alert-count')).toHaveTextContent('2')
    expect(screen.getByTestId('alert-count')).toHaveTextContent('1 critical')
    const actions = screen.getByTestId('actions')
    expect(within(actions).getByRole('link', { name: 'overtime' })).toHaveAttribute(
      'href',
      '/overtime',
    )
  })

  it('shows dashes, not zeros, when no calls have been imported', async () => {
    await open('planner', { ratio: null, dataThrough: null, serviceLevelPct: null })
    expect(await screen.findByTestId('running')).toHaveTextContent(
      'No calls imported for this day yet',
    )
    expect(screen.getByTestId('sl')).toHaveTextContent(/^Service level so far-/)
  })

  it('says nothing is short when nothing is', async () => {
    await open('planner', { alerts: [] })
    expect(await screen.findByTestId('no-alerts')).toBeVisible()
  })

  it('explains the missing forecast instead of drawing a flat line', async () => {
    await open('planner', { hasForecast: false, alerts: [] })
    expect(await screen.findByTestId('no-forecast')).toBeVisible()
  })

  it.each(['agent', 'executive', 'customer_ops'])('keeps %s out', async (role) => {
    await open(role)
    expect(
      await screen.findByRole('heading', { name: "You don't have access to this page" }),
    ).toBeVisible()
  })
})
