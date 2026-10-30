import userEvent from '@testing-library/user-event'
import { screen, within } from '@testing-library/vue'
import { describe, expect, it } from 'vitest'

import type { Scorecard } from '@/entities/scorecard'
import { backend } from '@/test/fake-backend'
import { expectAriaReferencesResolve } from '@/test/aria'
import { openScheduling, seedScheduling } from '@/test/open-scheduling'

const card = (over: Partial<Scorecard> = {}): Scorecard => ({
  dateFrom: '2031-03-01',
  dateTo: '2031-03-28',
  items: [
    {
      key: 'service_level',
      label: 'Service level',
      value: 81.25,
      unit: '%',
      basis: 'measured',
      note: '',
    },
    {
      key: 'aht',
      label: 'Average handling time',
      value: 212.4,
      unit: 's',
      basis: 'measured',
      note: '',
    },
    {
      key: 'occupancy',
      label: 'Occupancy',
      value: null,
      unit: '%',
      basis: 'modelled',
      note: 'Needs a published roster.',
    },
    {
      key: 'cost_per_contact',
      label: 'Cost per contact',
      value: null,
      unit: 'R',
      basis: 'needs_data',
      note: 'Needs payroll cost.',
    },
  ],
  days: [
    { day: '2031-03-03', offered: 10, serviceLevelPct: 80 },
    { day: '2031-03-04', offered: 20, serviceLevelPct: null },
  ],
  ...over,
})

async function open(role = 'executive', over: Partial<Scorecard> = {}) {
  seedScheduling()
  backend.scorecard = card(over)
  return openScheduling('/analytics', role)
}

describe('analytics', () => {
  it('labels each figure by where it comes from', async () => {
    // Failure caught: a modelled or missing figure passing as a measurement.
    await open()
    const sl = await screen.findByTestId('item-service_level')
    expect(within(sl).getByTestId('stat-value')).toHaveTextContent(/81[.,]3%/)
    expect(within(sl).getByTestId('basis')).toHaveTextContent('Measured')
    expect(within(screen.getByTestId('item-occupancy')).getByTestId('basis')).toHaveTextContent(
      'Modelled',
    )
    expect(
      within(screen.getByTestId('item-cost_per_contact')).getByTestId('basis'),
    ).toHaveTextContent('Needs data')
  })

  it('shows a dash, not zero, for a figure with nothing behind it', async () => {
    await open()
    const occupancy = await screen.findByTestId('item-occupancy')
    expect(within(occupancy).getByTestId('stat-value')).toHaveTextContent(/^-$/)
    expect(occupancy).toHaveTextContent('Needs a published roster.')
  })

  it('shows seconds as whole seconds with their unit', async () => {
    await open()
    expect(await screen.findByTestId('item-aht')).toHaveTextContent('212 s')
  })

  it('says so when no calls were measured instead of drawing an empty chart', async () => {
    await open('executive', { days: [] })
    expect(await screen.findByTestId('no-trend')).toBeVisible()
  })

  it('shows the trend chart when there are days', async () => {
    await open()
    expect(await screen.findByText('Calls and service level by day')).toBeVisible()
  })

  it('writes one sentence from the real figures and counts those that need data', async () => {
    // Failure caught: a summary that quotes a figure with nothing behind it, or hides the gaps.
    await open()
    const sentence = await screen.findByText(/figures need more data/)
    expect(sentence.textContent).toMatch(/service level\s+81[.,]3%/)
    expect(sentence).toHaveTextContent('average handling time 212 s')
    expect(sentence).not.toHaveTextContent('occupancy')
  })

  it('keeps the basis chip on every tile, and says Needs data on the tiles that lack it', async () => {
    // Failure caught: the restyle dropping the Measured / Modelled / Needs data labels (DAT-10).
    await open()
    await screen.findByTestId('analytics-tiles')
    expect(screen.getAllByTestId('basis').map((b) => b.textContent?.trim())).toEqual([
      'Measured',
      'Measured',
      'Modelled',
      'Needs data',
    ])
  })

  it('lists the daily numbers in a table, with a dash for a day without a service level', async () => {
    await open()
    const table = await screen.findByTestId('analytics-numbers')
    const rows = within(table).getAllByRole('row')
    expect(rows).toHaveLength(3)
    expect(rows[2]).toHaveTextContent('-')
    expectAriaReferencesResolve()
  })

  it('chooses the range with a segmented control', async () => {
    const user = userEvent.setup()
    await open()
    const group = await screen.findByRole('group', { name: 'Range' })
    expect(within(group).getByRole('button', { name: 'Last 28 days' })).toHaveAttribute(
      'aria-pressed',
      'true',
    )
    await user.click(within(group).getByRole('button', { name: 'Last 7 days' }))
    expect(within(group).getByRole('button', { name: 'Last 7 days' })).toHaveAttribute(
      'aria-pressed',
      'true',
    )
  })

  it.each(['agent', 'lead'])('keeps %s out', async (role) => {
    await open(role)
    expect(
      await screen.findByRole('heading', { name: "You don't have access to this page" }),
    ).toBeVisible()
  })
})
