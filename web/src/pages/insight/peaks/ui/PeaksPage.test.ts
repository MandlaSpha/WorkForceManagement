import { fireEvent, screen, waitFor, within } from '@testing-library/vue'
import { describe, expect, it } from 'vitest'

import type { Peaks } from '@/entities/peaks'
import { backend } from '@/test/fake-backend'
import { openScheduling, seedScheduling } from '@/test/open-scheduling'
import { peaksOf } from '@/test/peaks-fixtures'

async function open(role = 'planner', peaks: Peaks = peaksOf()) {
  seedScheduling()
  backend.peaks = peaks
  return openScheduling('/peaks', role)
}

const EMPTY: Partial<Peaks> = {
  daysMeasured: 0,
  busiestDays: [],
  quietestDays: [],
  busiestSlots: [],
  quietestSlots: [],
  busiestIntervals: [],
  daily: [],
  profile: [],
  heat: [],
}

describe('peaks and troughs', () => {
  it('ranks the busiest and quietest days and half-hours with a bar each', async () => {
    await open()
    expect(await screen.findByTestId('busiest-days')).toHaveTextContent('Mon 10 Mar')
    expect(screen.getByTestId('busiest-days')).toHaveTextContent('50 calls')
    expect(screen.getByTestId('quietest-days')).toHaveTextContent('Tue 04 Mar')
    expect(screen.getByTestId('busiest-slots')).toHaveTextContent('35.8 calls · 3 days')
    expect(screen.getByTestId('quietest-slots')).toHaveTextContent('08:30')
    expect(screen.getByTestId('busiest-intervals')).toHaveTextContent('Mon 03 Mar 10:30')
  })

  it('says in one plain sentence what the data shows', async () => {
    // Failure caught: a sentence that names a weekday or time the numbers do not support.
    await open()
    expect(
      await screen.findByText(
        'Mondays carry the most calls; the busiest half-hour is 10:30 with 35.8 calls on average.',
      ),
    ).toBeVisible()
  })

  it('shows the stat tiles with the peak-to-trough ratio', async () => {
    await open()
    const tiles = await screen.findByTestId('peaks-tiles')
    expect(within(tiles).getByText('Busiest day')).toBeVisible()
    expect(tiles).toHaveTextContent('Mon 10 Mar')
    expect(tiles).toHaveTextContent('7.2×') // 35.8 / 5.0
  })

  it('leaves the ratio out when there is a single open half-hour', async () => {
    // Failure caught: a ratio of a half-hour to itself shown as 1.0x.
    await open(
      'planner',
      peaksOf({ profile: [{ slot: '08:00', averageOffered: '25.0', days: 2 }] }),
    )
    const tiles = await screen.findByTestId('peaks-tiles')
    expect(tiles).not.toHaveTextContent('×')
    expect(tiles).toHaveTextContent('Needs two open half-hours with calls')
  })

  it('marks the busiest and quietest day on the daily chart and leaves gaps empty', async () => {
    // Failure caught: a day without data drawn as a zero bar, or the extremes not marked.
    await open()
    const daily = await screen.findByTestId('peaks-daily')
    expect(within(daily).getByText('Busiest')).toBeVisible()
    expect(within(daily).getByText('Quietest')).toBeVisible()
    expect(within(daily).getByLabelText('Mon 10 Mar: 50')).toBeVisible()
    expect(within(daily).getByLabelText('Wed 05 Mar: no value')).toBeVisible()
    expect(daily.querySelectorAll('.bg-chart-3')).toHaveLength(1)
    expect(daily.querySelectorAll('.bg-chart-2')).toHaveLength(1)
  })

  it('draws 48 half-hours, marks the peak and leaves closed half-hours without a bar', async () => {
    await open()
    const profile = await screen.findByTestId('peaks-profile')
    expect(profile.querySelectorAll('li[data-testid^="bar-"]')).toHaveLength(48)
    expect(profile.querySelectorAll('.bar-grow')).toHaveLength(3)
    expect(within(profile).getByText('Peak')).toBeVisible()
    expect(profile.querySelectorAll('.bg-chart-3')).toHaveLength(1)
  })

  it('gives every heat cell a text label so the grid does not depend on colour', async () => {
    // Failure caught: a heat grid that is only colour.
    await open()
    const heat = await screen.findByTestId('peaks-heat')
    expect(within(heat).getByRole('table')).toBeInTheDocument()
    expect(within(heat).getAllByRole('rowheader')).toHaveLength(7)
    expect(within(heat).getByText('Monday 10:30: 40.0 calls on average')).toBeInTheDocument()
    expect(within(heat).getByText('Sunday 00:00: no calls')).toBeInTheDocument()
    expect(within(heat).getByTestId('heat-legend')).toHaveTextContent('busiest cell: 40.0')
  })

  it('says so, and draws no chart, when no calls were measured', async () => {
    // Failure caught: empty lists shown as if every day were equally quiet, or fake charts.
    await open('planner', peaksOf(EMPTY))
    expect(await screen.findByTestId('peaks-none')).toBeVisible()
    expect(screen.queryByTestId('busiest-days')).toBeNull()
    expect(screen.queryByTestId('peaks-daily')).toBeNull()
    expect(screen.queryByTestId('peaks-heat')).toBeNull()
  })

  it('asks for the preset chosen, and for custom dates only after choosing Custom', async () => {
    await open()
    await screen.findByTestId('peaks-tiles')
    expect(screen.queryByLabelText('From')).toBeNull()
    await fireEvent.click(screen.getByRole('button', { name: 'Last 7 days' }))
    await waitFor(() => {
      const [, a, b] = backend.peaksQueries.at(-1)!.split(' ') as [string, string, string]
      expect((Date.parse(b) - Date.parse(a)) / 86_400_000).toBe(6)
    })
    await fireEvent.click(screen.getByRole('button', { name: 'Custom' }))
    await fireEvent.update(screen.getByLabelText('From'), '2031-03-01')
    await fireEvent.update(screen.getByLabelText('To'), '2031-03-31')
    await waitFor(() => expect(backend.peaksQueries.at(-1)).toMatch(/ 2031-03-01 2031-03-31$/))
    const sent = backend.peaksQueries.length
    await fireEvent.update(screen.getByLabelText('To'), '2031-02-01')
    expect(await screen.findByText('The start date is after the end date.')).toBeVisible()
    expect(backend.peaksQueries).toHaveLength(sent)
  })

  it('keeps an agent out', async () => {
    await open('agent')
    expect(
      await screen.findByRole('heading', { name: "You don't have access to this page" }),
    ).toBeVisible()
  })
})
