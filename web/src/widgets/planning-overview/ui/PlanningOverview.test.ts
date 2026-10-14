import userEvent from '@testing-library/user-event'
import { screen, waitFor, within } from '@testing-library/vue'
import { describe, expect, it } from 'vitest'

import { backend } from '@/test/fake-backend'
import { openScheduling, seedScheduling } from '@/test/open-scheduling'
import { overviewOf } from '@/test/scheduling-fixtures'

async function open(role = 'planner') {
  seedScheduling()
  backend.overview = overviewOf()
  return openScheduling('/', role)
}

describe('the planning overview on the dashboard', () => {
  it('shows the week at a glance from the server totals', async () => {
    await open()

    expect(await screen.findByTestId('card-gap')).toHaveTextContent('12')
    expect(screen.getByTestId('card-under')).toHaveTextContent('4 of 96 (4%)')
    expect(screen.getByTestId('card-forecast')).toHaveTextContent('2 of 3')
    expect(screen.getByTestId('card-rosters')).toHaveTextContent('0 of 3')
    expect(screen.getByTestId('card-headcount')).toHaveTextContent('2')
  })

  it('lists the queues worst-staffed first, with their own figures', async () => {
    await open()
    const table = await screen.findByTestId('queue-table')
    const rows = within(table).getAllByRole('row').slice(1)
    expect(rows.map((r) => within(r).getByRole('button').textContent?.trim())).toEqual([
      'QueueB',
      'QueueA',
      'QueueC',
    ])
    const b = within(screen.getByTestId('queue-2'))
    expect(b.getByText('8')).toBeVisible()
    expect(b.getByText('2 of 48')).toBeVisible()
    expect(b.getByText(/\u22124 at 10:00 on Mon 25 May/)).toBeVisible()
  })

  it('says a queue has no forecast instead of showing zeros for it', async () => {
    await open()
    const c = within(await screen.findByTestId('queue-3'))
    expect(c.getByText('No forecast for this week')).toBeVisible()
    expect(screen.getByTestId('queue-3').querySelector('[data-col="gap"]')).toBeNull()
  })

  it('draws the gap by day, all of it on Monday', async () => {
    await open()
    expect(await screen.findByTestId('trend-2026-05-25')).toHaveTextContent('12')
    expect(screen.getByTestId('trend-2026-05-26')).toHaveTextContent('0')
  })

  it('lists what needs attention, most serious first, with a way to fix each', async () => {
    await open()
    const box = within(await screen.findByTestId('attention'))
    const items = box.getAllByRole('listitem')
    expect(items).toHaveLength(4)
    expect(items[0]).toHaveTextContent('QueueA: 2 under-staffed intervals')
    expect(items[2]).toHaveTextContent('no published forecast')
    expect(items[3]).toHaveTextContent('the roster is still a draft')
  })

  it('opens the planner on the queue that was chosen', async () => {
    const user = userEvent.setup()
    const view = await open()

    await user.click(await screen.findByRole('button', { name: 'Open the planner for QueueB' }))

    await waitFor(() => expect(view.router.currentRoute.value.path).toBe('/planner'))
    expect(
      (await import('@/features/context-filters')).useContextStore(view.pinia).queueNumber,
    ).toBe(2)
  })

  it('sends each attention item to where it is fixed', async () => {
    const user = userEvent.setup()
    const view = await open()
    const box = within(await screen.findByTestId('attention'))

    await user.click(box.getAllByRole('button')[2]!) // QueueC: no forecast

    await waitFor(() => expect(view.router.currentRoute.value.path).toBe('/forecast'))
  })
})

describe('when the overview cannot say much', () => {
  it('says nothing is forecast, with dashes, when no queue has a forecast', async () => {
    seedScheduling()
    backend.overview = overviewOf({
      totals: {
        queues: 3,
        queuesWithForecast: 0,
        intervalsKnown: 0,
        underIntervals: 0,
        gap: 0,
        headcount: 2,
        rostersPublished: 0,
      },
    })
    await openScheduling('/')

    expect(await screen.findByTestId('overview-no-forecast')).toBeVisible()
    expect(screen.getByTestId('card-gap')).toHaveTextContent('\u2014')
    expect(screen.getByTestId('trend-2026-05-25')).toHaveTextContent('\u2014')
  })

  it('says there are no queues yet', async () => {
    seedScheduling()
    backend.overview = overviewOf({
      totals: {
        queues: 0,
        queuesWithForecast: 0,
        intervalsKnown: 0,
        underIntervals: 0,
        gap: 0,
        headcount: 0,
        rostersPublished: 0,
      },
      queues: [],
      attention: [],
    })
    await openScheduling('/')
    expect(await screen.findByTestId('no-queues')).toBeVisible()
  })

  it('says nothing needs attention when nothing does', async () => {
    seedScheduling()
    backend.overview = overviewOf({ attention: [] })
    await openScheduling('/')
    expect(await screen.findByText('Nothing needs attention.')).toBeVisible()
  })
})

describe('who sees it', () => {
  it.each(['planner', 'admin', 'lead'])('shows it to %s', async (role) => {
    await open(role)
    expect(await screen.findByTestId('card-gap')).toBeVisible()
  })

  it.each(['executive', 'customer_ops'])(
    'does not show it to %s, and does not even ask for it',
    async (role) => {
      await open(role)
      await screen.findByRole('heading', { name: 'Dashboard' })
      expect(screen.queryByText(/^Planning, week of/)).toBeNull()
      expect(backend.requests.filter((r) => r.path === '/api/v1/scheduling/overview')).toEqual([])
    },
  )

  it('is not shown when scheduling is not part of the plan', async () => {
    seedScheduling()
    backend.overview = overviewOf()
    backend.features = backend.features.filter((f) => f !== 'scheduling')
    await openScheduling('/')
    await screen.findByRole('heading', { name: 'Dashboard' })
    expect(screen.queryByText(/^Planning, week of/)).toBeNull()
  })
})
