import userEvent from '@testing-library/user-event'
import { screen, waitFor, within } from '@testing-library/vue'
import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'

import { kpiSummary, metric, queueKpis } from '@/test/call-data-fixtures'
import { backend } from '@/test/fake-backend'
import { overviewOf } from '@/test/scheduling-fixtures'
import { renderApp } from '@/test/render-app'
import { server } from '@/test/server'

const asRole = (role: string) => {
  backend.signedIn = { username: role, displayName: `Test ${role}`, role }
}

const JULY = kpiSummary({
  dateFrom: '2026-07-01',
  dateTo: '2026-07-31',
  total: queueKpis({
    queueId: null,
    queue: 'All queues',
    offered: 4837,
    answered: 4632,
    abandoned: 205,
    abandonPct: metric((205 / 4837) * 100),
    serviceLevelPct: metric((4344 / 4837) * 100),
    asaS: metric(11.73),
    ahtS: metric(202.2),
  }),
})

function withData() {
  backend.months = ['2026-05', '2026-06', '2026-07'] // June is listed but has no calls
  backend.kpisByMonth = { '2026-05': kpiSummary(), '2026-07': JULY }
  // A planner also sees the planning overview; these tests are about the call data below it.
  backend.overview = overviewOf()
}

const tile = async (key: string) => within(await screen.findByTestId(`tile-${key}`))

describe('the dashboard shows measured service figures', () => {
  it('opens on the latest month that has calls, not on an empty current week', async () => {
    withData()
    asRole('planner')
    await renderApp('/')

    expect((await tile('offered')).getByText(/4\s837/)).toBeVisible()
    expect(screen.getByLabelText('Month')).toHaveValue('2026-07')
  })

  it('says which part is the planning week and which is the chosen month', async () => {
    // Failure caught: the Month picker in the page header reading as if it also moved the planning
    // week, so a planner changes the month and wonders why the week did not follow.
    withData()
    asRole('planner')
    const user = userEvent.setup()
    await renderApp('/')

    expect(await screen.findByTestId('service-title')).toHaveTextContent(
      /Service figures · July 2026/,
    )
    expect(screen.getByTestId('planning-hint')).toHaveTextContent('top bar')
    await user.selectOptions(screen.getByLabelText('Month'), '2026-05')
    expect(await screen.findByText(/Service figures · May 2026/)).toBeVisible()
    expect(screen.getByText(/^Planning, week of/)).toBeVisible()
  })

  it('shows May exactly as the deck prints it: 8.28%, 81.1%, 18.5 s, 3:35', async () => {
    withData()
    asRole('planner')
    const user = userEvent.setup()
    await renderApp('/')

    await user.selectOptions(await screen.findByLabelText('Month'), '2026-05')

    expect((await tile('offered')).getByText(/5\s649/)).toBeVisible()
    expect((await tile('answered')).getByText(/5\s181/)).toBeVisible()
    expect((await tile('abandon')).getByText('8.28%')).toBeVisible()
    expect((await tile('sl')).getByText('81.1%')).toBeVisible()
    expect((await tile('asa')).getByText('18.5 s')).toBeVisible()
    expect((await tile('aht')).getByText('3:35')).toBeVisible()
  })

  it('says every figure is measured and what share of intervals it rests on', async () => {
    withData()
    asRole('planner')
    await renderApp('/')

    expect(await screen.findByTestId('coverage')).toHaveTextContent(
      /1.100 of 1.488 half-hour intervals in July 2026/,
    )
    expect(screen.getAllByText('Measured')).toHaveLength(6)
  })

  it('lists each queue and flags one an admin has not confirmed yet', async () => {
    withData()
    asRole('planner')
    await renderApp('/')

    const table = within(await screen.findByRole('table', { name: /Service by queue/ }))
    expect(table.getByRole('rowheader', { name: /QueueB/ })).toHaveTextContent('Unconfirmed')
    expect(table.getByRole('rowheader', { name: /QueueA/ })).not.toHaveTextContent('Unconfirmed')
  })
})

describe('the queue table', () => {
  it('lists only queues that had calls in the month, not rows of dashes', async () => {
    backend.months = ['2026-05']
    backend.kpisByMonth = {
      '2026-05': kpiSummary({
        queues: [
          queueKpis({ queueId: 1, queue: 'QueueA' }),
          queueKpis({ queueId: 3, queue: 'QuietQueue', offered: 0, answered: 0, abandoned: 0 }),
        ],
      }),
    }
    asRole('planner')
    await renderApp('/')

    const table = within(await screen.findByRole('table', { name: /Service by queue/ }))
    expect(table.getByRole('rowheader', { name: /QueueA/ })).toBeVisible()
    expect(table.queryByRole('rowheader', { name: /QuietQueue/ })).toBeNull()
  })
})

describe('the dashboard never invents a figure', () => {
  it('shows no tiles and no zeros for a month without calls', async () => {
    withData()
    asRole('planner')
    const user = userEvent.setup()
    await renderApp('/')

    await user.selectOptions(await screen.findByLabelText('Month'), '2026-06')

    expect(await screen.findByText(/No calls were recorded in June 2026/)).toBeVisible()
    expect(screen.queryByTestId('tile-offered')).toBeNull()
    expect(screen.queryByText(/0\.0%/)).toBeNull()
  })

  it('says so, with a way forward, when nothing has been imported', async () => {
    asRole('planner')
    await renderApp('/')

    const link = await screen.findByRole('link', { name: /Import a call detail report/ })
    expect(link).toHaveAttribute('href', '/imports')
    expect(screen.queryByTestId('tile-offered')).toBeNull()
  })

  it('does not offer the import to a role that may not use it', async () => {
    asRole('lead')
    await renderApp('/')

    expect(await screen.findByText(/A planner or admin imports it/)).toBeVisible()
    expect(screen.queryByRole('link', { name: /Import a call detail report/ })).toBeNull()
  })

  it('shows the reason and no figures when the figures cannot be loaded', async () => {
    withData()
    server.use(
      http.get('*/api/v1/telephony/kpis', () =>
        HttpResponse.json(
          {
            title: 'Server error',
            status: 500,
            code: 'server.error',
            detail: 'Try again shortly.',
          },
          { status: 500, headers: { 'Content-Type': 'application/problem+json' } },
        ),
      ),
    )
    asRole('planner')
    await renderApp('/')

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(/Could not load the figures for July 2026/)
    expect(alert).toHaveTextContent(/Try again shortly/)
    expect(screen.queryByTestId('tile-offered')).toBeNull()
  })

  it('does not leak internals when something other than the API fails', async () => {
    withData()
    server.use(http.get('*/api/v1/telephony/kpis', () => HttpResponse.error()))
    asRole('planner')
    await renderApp('/')

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(/Something went wrong/)
    expect(alert).not.toHaveTextContent(/fetch|TypeError|Failed to/i)
  })

  it('reports it when it cannot even tell which months have data', async () => {
    server.use(http.get('*/api/v1/telephony/months', () => HttpResponse.error()))
    asRole('planner')
    await renderApp('/')

    // The planning overview has no handler in this test, so the page shows two alerts; the one
    // about the months must be among them.
    await waitFor(() => {
      const alerts = within(screen.getByRole('main')).getAllByRole('alert')
      expect(alerts.map((a) => a.textContent).join(' ')).toMatch(/Could not check which months/)
    })
  })
})
