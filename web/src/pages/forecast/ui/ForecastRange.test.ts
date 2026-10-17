import userEvent from '@testing-library/user-event'
import { screen, waitFor, within } from '@testing-library/vue'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it } from 'vitest'

import { dayIntervals, forecastVersion, queueInfo } from '@/test/forecast-fixtures'
import { backend } from '@/test/fake-backend'
import { renderApp } from '@/test/render-app'
import { server } from '@/test/server'

const asRole = (role: string) => {
  backend.signedIn = { username: role, displayName: `Test ${role}`, role }
  document.cookie = 'csrftoken=test-csrf-token'
}
const user = () => userEvent.setup()

/** A live forecast for Mon 25 to Sun 31 May 2026. Only Monday (31.9 calls, peak 6 people, 5.5
 * agent-hours) and Wednesday (twice the calls) have half-hours: the other five days could not be
 * forecast. */
function weekForecast(overrides: Parameters<typeof forecastVersion>[0] = {}) {
  backend.queues = [queueInfo()]
  backend.versions = [
    forecastVersion({
      dateFrom: '2026-05-25',
      dateTo: '2026-05-31',
      daysWithoutHistory: ['2026-05-26', '2026-05-28', '2026-05-29', '2026-05-30', '2026-05-31'],
      ...overrides,
    }),
  ]
  const wednesday = dayIntervals('2026-05-27').map((i) => ({ ...i, volume: i.volume * 2 }))
  backend.intervals = { 'v-live': [...dayIntervals('2026-05-25'), ...wednesday] }
}

beforeEach(() => {
  backend.rangeQueries = []
})

describe('the Day / Week / Month switch', () => {
  it('opens on the day, as before, and fetches no range', async () => {
    weekForecast()
    asRole('planner')
    await renderApp('/forecast')

    expect(await screen.findByTestId('total-calls')).toHaveTextContent('31.9')
    expect(screen.getByRole('button', { name: 'Day', pressed: true })).toBeVisible()
    expect(backend.rangeQueries).toEqual([])
  })

  it('shows the week from one request, with the totals worked out by hand', async () => {
    weekForecast()
    asRole('planner')
    const u = user()
    await renderApp('/forecast')

    await u.click(await screen.findByRole('button', { name: 'Week' }))

    const table = within(await screen.findByTestId('week-table'))
    const monday = table.getByRole('row', { name: /Mon 25 May/ })
    expect(monday).toHaveTextContent('31.9') // 19.9 + 12 calls
    expect(monday).toHaveTextContent('180 s')
    expect(within(monday).getAllByRole('cell')[2]).toHaveTextContent('6') // people at the peak
    expect(within(monday).getAllByRole('cell')[3]).toHaveTextContent('5.5') // (6 + 5) x 0.5 h
    expect(table.getByRole('row', { name: /Wed 27 May/ })).toHaveTextContent('63.8')
    expect(screen.getByTestId('range-heading')).toHaveTextContent('Week of Mon 25 May')
    // One request for the whole week, asking for the half-hours the heat-grid needs.
    expect(backend.rangeQueries).toHaveLength(1)
    expect(backend.rangeQueries[0]).toContain('date_from=2026-05-25')
    expect(backend.rangeQueries[0]).toContain('date_to=2026-05-31')
    expect(backend.rangeQueries[0]).toContain('detail=true')
  })

  // Failure caught: days nobody could forecast shown as quiet days with zero calls and no people.
  it('says plainly which days have no forecast and shows no number for them', async () => {
    weekForecast()
    asRole('planner')
    const u = user()
    await renderApp('/forecast')
    await u.click(await screen.findByRole('button', { name: 'Week' }))

    const table = within(await screen.findByTestId('week-table'))
    const tuesday = table.getByRole('row', { name: /Tue 26 May/ })
    expect(tuesday).toHaveTextContent('No forecast for this day')
    expect(tuesday).not.toHaveTextContent('0.0')
    const notice = screen.getByTestId('partial-notice')
    expect(notice).toHaveTextContent('5 of 7 days have no forecast')
    expect(notice).toHaveTextContent(/could not be forecast: no earlier day with the same weekday/)
  })

  it('says what the figures rest on: the version and whether it is live', async () => {
    weekForecast()
    asRole('planner')
    const u = user()
    await renderApp('/forecast')
    await u.click(await screen.findByRole('button', { name: 'Week' }))

    expect(await screen.findByTestId('range-basis')).toHaveTextContent(
      'QueueA, version "Week 22", the published (live) forecast',
    )
  })

  it('does not call a draft live', async () => {
    weekForecast({ status: 'draft', publishedAt: null })
    asRole('planner')
    const u = user()
    await renderApp('/forecast')
    await u.click(await screen.findByRole('button', { name: 'Week' }))

    const basis = await screen.findByTestId('range-basis')
    await waitFor(() => expect(basis).toHaveTextContent('a draft that is not live'))
    expect(basis).not.toHaveTextContent('published')
  })

  it('colours the heat-grid by people needed and marks days without a forecast', async () => {
    weekForecast()
    asRole('planner')
    const u = user()
    await renderApp('/forecast')
    await u.click(await screen.findByRole('button', { name: 'Week' }))

    const grid = within(await screen.findByTestId('heat-grid'))
    // 10:00 on Monday needs 6 people, 10:30 needs 5, and 09:30 needs nobody.
    expect(grid.getByTitle('Mon 25 May 10:00: 6')).toHaveAttribute('data-level', '6')
    expect(grid.getByTitle('Mon 25 May 10:30: 5')).toHaveAttribute('data-level', '5')
    expect(grid.getByTitle('Mon 25 May 09:30: 0')).toHaveAttribute('data-level', '0')
    const busy = grid.getByTitle('Mon 25 May 10:00: 6').firstElementChild as HTMLElement
    const quiet = grid.getByTitle('Mon 25 May 10:30: 5').firstElementChild as HTMLElement
    expect(Number(busy.style.opacity)).toBeGreaterThan(Number(quiet.style.opacity))
    expect(
      within(grid.getByRole('row', { name: /Tue 26 May/ })).getByText('No forecast'),
    ).toBeVisible()
  })

  it('opens a day in the Day view when it is clicked, in the table or the grid', async () => {
    weekForecast()
    asRole('planner')
    const u = user()
    const { router } = await renderApp('/forecast')
    await u.click(await screen.findByRole('button', { name: 'Week' }))

    await u.click(await screen.findByRole('button', { name: 'Open Wed 27 May in the day view' }))

    expect(await screen.findByTestId('total-calls')).toHaveTextContent('63.8')
    expect(screen.getByRole('button', { name: 'Day', pressed: true })).toBeVisible()
    expect(router.currentRoute.value.query.view).toBeUndefined()
    expect(router.currentRoute.value.query.day).toBe('2026-05-27')
  })

  it('moves to the next week, which is outside the forecast, and says so', async () => {
    weekForecast()
    asRole('planner')
    const u = user()
    await renderApp('/forecast')
    await u.click(await screen.findByRole('button', { name: 'Week' }))
    await u.click(await screen.findByRole('button', { name: 'Next week' }))

    expect(await screen.findByTestId('range-heading')).toHaveTextContent('Week of Mon 01 Jun')
    const notice = await screen.findByTestId('no-forecast-notice')
    expect(notice).toHaveTextContent(/nothing for any day shown/)
    expect(notice).toHaveTextContent(/covers Mon 25 May to Sun 31 May/)
    expect(screen.queryByTestId('week-table')).toBeTruthy()
    expect(within(screen.getByTestId('week-table')).queryByText('0.0')).toBeNull()
  })

  it('lands on the view and day the address names', async () => {
    weekForecast()
    asRole('planner')
    await renderApp('/forecast?view=week&day=2026-05-27')

    expect(await screen.findByTestId('range-heading')).toHaveTextContent('Week of Mon 25 May')
    expect(screen.getByRole('button', { name: 'Week', pressed: true })).toBeVisible()
    // Wait for the week to arrive so its request is not still in flight when the next test starts.
    expect(await screen.findByTestId('week-table')).toBeVisible()
  })

  it('falls back to the day view for a view it does not know', async () => {
    weekForecast()
    asRole('planner')
    await renderApp('/forecast?view=year')

    expect(await screen.findByTestId('total-calls')).toBeVisible()
    expect(backend.rangeQueries).toEqual([])
  })

  it('shows why the week could not be loaded and no numbers', async () => {
    weekForecast()
    server.use(
      http.get('*/api/v1/forecasting/versions/:id/range', () =>
        HttpResponse.json(
          { type: 'x', title: 'Not available', status: 500, code: 'boom', detail: 'Try later.' },
          { status: 500, headers: { 'Content-Type': 'application/problem+json' } },
        ),
      ),
    )
    asRole('planner')
    const u = user()
    await renderApp('/forecast')
    await u.click(await screen.findByRole('button', { name: 'Week' }))

    expect(await screen.findByText(/Could not load this week/)).toBeVisible()
    expect(screen.queryByTestId('week-table')).toBeNull()
  })

  it('lets a lead read the week', async () => {
    weekForecast()
    asRole('lead')
    const u = user()
    await renderApp('/forecast')
    await u.click(await screen.findByRole('button', { name: 'Week' }))

    expect(await screen.findByTestId('week-table')).toBeVisible()
  })
})

describe('the month', () => {
  it('shows a calendar with a total per day from one request without the half-hours', async () => {
    weekForecast()
    asRole('planner')
    const u = user()
    await renderApp('/forecast')
    await u.click(await screen.findByRole('button', { name: 'Month' }))

    const grid = within(await screen.findByTestId('month-grid'))
    expect(screen.getByTestId('range-heading')).toHaveTextContent('May 2026')
    expect(
      grid.getByRole('button', { name: /Mon 25 May: 32 calls, 6 people at peak/ }),
    ).toBeVisible()
    expect(grid.getByRole('button', { name: /Tue 26 May: no forecast/ })).toBeVisible()
    // The month grid covers whole weeks: Mon 27 Apr to Sun 31 May is 35 cells.
    expect(grid.getAllByRole('button')).toHaveLength(35)
    expect(backend.rangeQueries).toHaveLength(1)
    expect(backend.rangeQueries[0]).toContain('date_from=2026-04-27')
    expect(backend.rangeQueries[0]).toContain('date_to=2026-05-31')
    expect(backend.rangeQueries[0]).toContain('detail=false')
  })

  it('marks the busiest and the quietest day, and only among days with a forecast', async () => {
    // Failure caught: a day with no forecast winning "quietest" with its missing 0 calls.
    weekForecast()
    asRole('planner')
    const u = user()
    await renderApp('/forecast')
    await u.click(await screen.findByRole('button', { name: 'Month' }))

    const grid = await screen.findByTestId('month-grid')
    expect(
      within(grid.querySelector('[data-day="2026-05-27"]') as HTMLElement).getByText('Busiest'),
    ).toBeVisible()
    expect(
      within(grid.querySelector('[data-day="2026-05-25"]') as HTMLElement).getByText('Quietest'),
    ).toBeVisible()
    expect(within(grid).getAllByText('Busiest')).toHaveLength(1)
    expect(within(grid).getAllByText('Quietest')).toHaveLength(1)
  })

  it('shows the events that cover a day, and says public holidays are not recorded', async () => {
    weekForecast()
    backend.events = [
      {
        id: 1,
        name: 'Payday',
        queueId: null,
        queue: null,
        dateFrom: '2026-05-25',
        dateTo: '2026-05-26',
        upliftPct: 20,
      },
    ]
    asRole('planner')
    const u = user()
    await renderApp('/forecast')
    await u.click(await screen.findByRole('button', { name: 'Month' }))

    const grid = await screen.findByTestId('month-grid')
    expect(
      within(grid.querySelector('[data-day="2026-05-26"]') as HTMLElement).getByText('Payday'),
    ).toBeVisible()
    expect(
      within(grid.querySelector('[data-day="2026-05-27"]') as HTMLElement).queryByText('Payday'),
    ).toBeNull()
    expect(screen.getByTestId('holiday-note')).toHaveTextContent(/Public holidays are not recorded/)
  })

  it('drops into the Day view when a day is clicked', async () => {
    weekForecast()
    asRole('planner')
    const u = user()
    await renderApp('/forecast')
    await u.click(await screen.findByRole('button', { name: 'Month' }))

    await u.click(await screen.findByRole('button', { name: /Wed 27 May: 64 calls/ }))

    expect(await screen.findByTestId('total-calls')).toHaveTextContent('63.8')
  })

  it('goes to the next month, where nothing is forecast, without inventing a number', async () => {
    weekForecast()
    asRole('planner')
    const u = user()
    await renderApp('/forecast')
    await u.click(await screen.findByRole('button', { name: 'Month' }))
    await u.click(await screen.findByRole('button', { name: 'Next month' }))

    expect(await screen.findByTestId('range-heading')).toHaveTextContent('June 2026')
    expect(await screen.findByTestId('no-forecast-notice')).toBeVisible()
    const grid = within(screen.getByTestId('month-grid'))
    expect(grid.queryByText(/calls/)).toBeNull()
  })
})
