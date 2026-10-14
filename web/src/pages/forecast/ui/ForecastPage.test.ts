import userEvent from '@testing-library/user-event'
import { screen, waitFor, within } from '@testing-library/vue'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it } from 'vitest'

import { accuracyFor, dayIntervals, forecastVersion, queueInfo } from '@/test/forecast-fixtures'
import { backend } from '@/test/fake-backend'
import { renderApp } from '@/test/render-app'
import { server } from '@/test/server'

const asRole = (role: string) => {
  backend.signedIn = { username: role, displayName: `Test ${role}`, role }
  // A signed-in browser already holds the CSRF cookie from sign-in.
  document.cookie = 'csrftoken=test-csrf-token'
}

function withLiveForecast(overrides: Parameters<typeof forecastVersion>[0] = {}) {
  backend.queues = [queueInfo()]
  backend.versions = [forecastVersion(overrides)]
  backend.intervals = { 'v-live': dayIntervals() }
  backend.accuracy = accuracyFor()
}

const user = () => userEvent.setup()

beforeEach(() => {
  backend.runOutcome = null
})

describe('reading a forecast', () => {
  it('opens on the live forecast and shows the numbers worked out for it', async () => {
    withLiveForecast()
    asRole('planner')
    await renderApp('/forecast')

    expect(await screen.findByTestId('total-calls')).toHaveTextContent('31.9') // 19.9 + 12
    expect(screen.getByTestId('peak')).toHaveTextContent('10:00')
    expect(screen.getByTestId('peak')).toHaveTextContent('19.9 calls')
    expect(screen.getByTestId('max-required')).toHaveTextContent('6')
  })

  it('draws the chart and says what it rests on', async () => {
    withLiveForecast()
    asRole('planner')
    await renderApp('/forecast')

    expect(
      await screen.findByRole('img', { name: /Busiest half-hour 10:00 with 19.9 calls/ }),
    ).toBeVisible()
    expect(screen.getByTestId('evidence')).toHaveTextContent(/3 most recent earlier days/)
    expect(screen.getByTestId('evidence')).toHaveTextContent(/30% shrinkage/)
  })

  it('shows the staffing assumptions as unconfirmed defaults until someone confirms them', async () => {
    withLiveForecast({ assumptionsConfirmed: false })
    asRole('planner')
    await renderApp('/forecast')

    const notice = await screen.findByTestId('assumptions-notice')
    expect(notice).toHaveTextContent(/defaults that nobody has confirmed/)
    expect(notice).toHaveTextContent(/80% of calls answered within 20 s/)
    expect(notice).toHaveTextContent(/occupancy ceiling of 85%/)
  })

  it('does not call the assumptions defaults once they are confirmed', async () => {
    withLiveForecast({ assumptionsConfirmed: true })
    asRole('planner')
    await renderApp('/forecast')

    await screen.findByTestId('total-calls')
    expect(screen.queryByTestId('assumptions-notice')).toBeNull()
  })
})

describe('a forecast that rests on little or old evidence says so', () => {
  it('warns when the newest call data is weeks older than the forecast', async () => {
    withLiveForecast({ dateFrom: '2026-07-20', dateTo: '2026-07-20', historyThrough: '2026-05-31' })
    backend.intervals = { 'v-live': dayIntervals('2026-07-20') }
    asRole('planner')
    await renderApp('/forecast')

    expect(await screen.findByTestId('stale-notice')).toHaveTextContent(
      /newest call data is from 2026-05-31, 50 days before/,
    )
  })

  it('stays quiet when the data is recent', async () => {
    withLiveForecast({ historyThrough: '2026-05-18' }) // 7 days before 25 May
    asRole('planner')
    await renderApp('/forecast')

    await screen.findByTestId('total-calls')
    expect(screen.queryByTestId('stale-notice')).toBeNull()
  })

  it('names the days that could not be forecast and does not offer them as a choice', async () => {
    withLiveForecast({
      dateFrom: '2026-05-25',
      dateTo: '2026-05-27',
      daysWithoutHistory: ['2026-05-26', '2026-05-27'],
    })
    asRole('planner')
    await renderApp('/forecast')

    expect(await screen.findByTestId('missing-days-notice')).toHaveTextContent(
      /2 days were left out.*Tue 26 May, Wed 27 May/,
    )
    const options = within(screen.getByLabelText('Day')).getAllByRole('option')
    expect(options.map((o) => o.textContent?.trim())).toEqual([
      expect.stringMatching(/Mon.*25.*May/),
    ])
  })

  it('does not present an interval with no requirement as needing zero agents', async () => {
    withLiveForecast()
    backend.intervals = {
      'v-live': dayIntervals().map((i) =>
        i.volume > 0 ? { ...i, required: null, requiredRaw: null } : i,
      ),
    }
    asRole('planner')
    await renderApp('/forecast')

    expect(await screen.findByTestId('max-required')).toHaveTextContent('—')
  })
})

describe('forecast accuracy', () => {
  it('shows the measured accuracy and what it is measured against', async () => {
    withLiveForecast()
    asRole('planner')
    await renderApp('/forecast')

    expect(await screen.findByTestId('accuracy-daily')).toHaveTextContent('90.2%')
    expect(screen.getByTestId('accuracy-interval')).toHaveTextContent('81.4%')
    expect(screen.getByTestId('accuracy-days')).toHaveTextContent('Over 2 past days')
    expect(screen.getByText(/only the days before it/)).toBeVisible()
  })

  it('says there is not enough data instead of showing a made-up score', async () => {
    withLiveForecast()
    backend.accuracy = accuracyFor({
      overallAccuracyPct: null,
      overallDailyAccuracyPct: null,
      days: [],
    })
    asRole('planner')
    await renderApp('/forecast')

    expect(await screen.findByText(/Not enough call data yet/)).toBeVisible()
    expect(screen.queryByTestId('accuracy-daily')).toBeNull()
  })
})

describe('when there is nothing to show', () => {
  it('says there are no queues until call data is imported', async () => {
    asRole('planner')
    await renderApp('/forecast')
    expect(await screen.findByText(/There are no queues yet/)).toBeVisible()
  })

  it('says no forecast has been run, and still offers to run one', async () => {
    backend.queues = [queueInfo()]
    backend.accuracy = accuracyFor()
    asRole('planner')
    await renderApp('/forecast')

    expect(await screen.findByText(/No forecast has been run for this queue yet/)).toBeVisible()
    expect(screen.getByRole('button', { name: 'Run forecast' })).toBeEnabled()
  })

  it('shows the reason and no numbers when a forecast cannot be loaded', async () => {
    withLiveForecast()
    server.use(http.get('*/api/v1/forecasting/versions/:id/intervals', () => HttpResponse.error()))
    asRole('planner')
    await renderApp('/forecast')

    expect(
      await screen.findByText(/Could not load this forecast. Something went wrong/),
    ).toBeVisible()
    expect(screen.queryByTestId('total-calls')).toBeNull()
  })
})

describe('running a forecast', () => {
  it('sends the queue, the days and the label with the CSRF token, and shows the new draft', async () => {
    withLiveForecast()
    const draft = forecastVersion({
      id: 'v-new',
      label: 'Next week',
      status: 'draft',
      publishedAt: null,
      dateFrom: '2026-06-01',
      dateTo: '2026-06-01',
    })
    backend.runOutcome = draft
    backend.intervals['v-new'] = dayIntervals('2026-06-01')
    asRole('planner')
    const u = user()
    await renderApp('/forecast')

    await u.clear(await screen.findByLabelText('From'))
    await u.type(screen.getByLabelText('From'), '2026-06-01')
    await u.clear(screen.getByLabelText('To'))
    await u.type(screen.getByLabelText('To'), '2026-06-01')
    await u.type(screen.getByLabelText('Label (optional)'), 'Next week')
    await u.click(screen.getByRole('button', { name: 'Run forecast' }))

    await waitFor(() => expect(backend.runs).toHaveLength(1))
    expect(backend.runs[0]).toEqual({
      body: {
        queueId: 1,
        dateFrom: '2026-06-01',
        dateTo: '2026-06-01',
        label: 'Next week',
        method: 'prophet',
      },
      csrf: 'test-csrf-token',
    })
    // The new draft is listed and opened.
    expect(await screen.findByRole('rowheader', { name: 'Next week' })).toBeVisible()
    expect(await screen.findByRole('heading', { name: /QueueA: Next week/ })).toBeVisible()
  })

  it('shows why nothing was created, and adds no version, when the server refuses', async () => {
    withLiveForecast()
    backend.runOutcome = {
      status: 422,
      code: 'forecast.no_history',
      title: 'Forecast refused',
      detail: 'There is no earlier day with the same weekday to forecast from.',
    }
    asRole('planner')
    const u = user()
    await renderApp('/forecast')

    await u.click(await screen.findByRole('button', { name: 'Run forecast' }))

    const error = await screen.findByTestId('run-error')
    expect(error).toHaveTextContent(/No forecast was created/)
    expect(error).toHaveTextContent(/no earlier day with the same weekday/)
    const table = within(screen.getByRole('table', { name: 'Versions' }))
    expect(table.getAllByRole('row')).toHaveLength(2) // header + the one existing version
  })
})

describe('publishing', () => {
  const draft = forecastVersion({
    id: 'v-draft',
    label: 'Draft plan',
    status: 'draft',
    publishedAt: null,
  })

  it('makes a draft live and archives the one it replaces, both shown at once', async () => {
    withLiveForecast()
    backend.versions = [draft, forecastVersion()]
    backend.intervals['v-draft'] = dayIntervals()
    asRole('planner')
    const u = user()
    await renderApp('/forecast')

    await u.click(await screen.findByRole('button', { name: /Publish Draft plan/ }))

    const table = within(await screen.findByRole('table', { name: 'Versions' }))
    await waitFor(() => {
      const rows = table.getAllByRole('row')
      expect(within(rows[1]!).getByText('published')).toBeVisible() // Draft plan, now live
      expect(within(rows[2]!).getByText('archived')).toBeVisible() // Week 22, retired
    })
    expect(table.queryByRole('button', { name: /Publish/ })).toBeNull()
  })

  it('does not offer to publish something that is already live or archived', async () => {
    withLiveForecast()
    backend.versions = [forecastVersion(), forecastVersion({ id: 'v-old', status: 'archived' })]
    backend.intervals['v-old'] = dayIntervals()
    asRole('planner')
    await renderApp('/forecast')

    await screen.findByRole('table', { name: 'Versions' })
    expect(screen.queryByRole('button', { name: /Publish/ })).toBeNull()
  })
})

describe('who may change forecasts', () => {
  it('lets a lead read them but offers no way to run or publish', async () => {
    withLiveForecast()
    backend.versions = [
      forecastVersion({ id: 'v-draft', label: 'Draft plan', status: 'draft', publishedAt: null }),
      forecastVersion(),
    ]
    asRole('lead')
    await renderApp('/forecast')

    expect(await screen.findByText(/Planners and admins run and publish them/)).toBeVisible()
    expect(screen.queryByRole('button', { name: 'Run forecast' })).toBeNull()
    expect(screen.queryByRole('button', { name: /Publish/ })).toBeNull()
    expect(await screen.findByTestId('total-calls')).toBeVisible()
  })

  it.each(['agent', 'executive', 'customer_ops'])('does not open for %s', async (role) => {
    asRole(role)
    const { router } = await renderApp('/forecast')
    expect(
      await screen.findByRole('heading', { name: "You don't have access to this page" }),
    ).toBeVisible()
    expect(router.currentRoute.value.name).toBe('forbidden')
  })
})

describe('the two accuracy scores', () => {
  it('explains why the half-hour score is lower, so a small queue is not misread', async () => {
    withLiveForecast()
    backend.accuracy = accuracyFor({ overallAccuracyPct: 12.3, overallDailyAccuracyPct: 68.8 })
    asRole('planner')
    await renderApp('/forecast')

    expect(await screen.findByTestId('accuracy-interval')).toHaveTextContent('12.3%')
    expect(screen.getByTestId('accuracy-daily')).toHaveTextContent('68.8%')
    expect(screen.getByText(/much lower for a small queue/)).toBeVisible()
  })

  it('shows no figure rather than 0% when a score cannot be worked out', async () => {
    withLiveForecast()
    backend.accuracy = accuracyFor({ overallDailyAccuracyPct: null })
    asRole('planner')
    await renderApp('/forecast')

    expect(await screen.findByTestId('accuracy-daily')).toHaveTextContent('—')
  })
})

describe('which model made the forecast', () => {
  const prophetParams = {
    slTargetPct: 80,
    slThresholdS: 20,
    occupancyCeilingPct: 85,
    shrinkagePct: 30,
    backtest: { prophetDailyPct: 93.456, baselineDailyPct: 88.1, daysScored: 21 },
  }

  it('asks for the best available model by default and for the baseline when told to', async () => {
    withLiveForecast()
    backend.runOutcome = forecastVersion({ id: 'v-new', status: 'draft', publishedAt: null })
    backend.intervals['v-new'] = dayIntervals()
    asRole('planner')
    const u = user()
    await renderApp('/forecast')

    const form = await screen.findByRole('form', { name: 'Run a forecast' })
    expect(within(form).getByLabelText('Model')).toHaveValue('prophet')
    await u.selectOptions(within(form).getByLabelText('Model'), 'baseline')
    await u.click(within(form).getByRole('button', { name: 'Run forecast' }))

    await waitFor(() => expect(backend.runs).toHaveLength(1))
    expect(backend.runs[0]?.body).toMatchObject({ method: 'baseline' })
  })

  it('says Prophet was used, with the evidence that earned it the place, and shows the range', async () => {
    withLiveForecast({ method: 'prophet-v1', params: prophetParams })
    // Prophet gives every half-hour a range, quiet ones included (zero to zero).
    backend.intervals['v-live'] = dayIntervals().map((i) => ({
      ...i,
      volumeLower: i.volume * 0.8,
      volumeUpper: i.volume * 1.25,
    }))
    asRole('planner')
    await renderApp('/forecast')

    const model = await screen.findByTestId('model')
    expect(model).toHaveTextContent('21 past days')
    expect(model).toHaveTextContent('93.5% right, against 88.1%')
    // 31.9 calls: 0.8 x 31.9 = 25.5 and 1.25 x 31.9 = 39.9, as whole numbers.
    expect(screen.getByTestId('total-range')).toHaveTextContent('80% range 26 to 40')
  })

  it('does not draw a range the baseline never had', async () => {
    withLiveForecast()
    asRole('planner')
    await renderApp('/forecast')
    await screen.findByTestId('total-calls')
    expect(screen.queryByTestId('total-range')).toBeNull()
    expect(screen.queryByTestId('model')).toBeNull()
    expect(screen.queryByTestId('fallback-notice')).toBeNull()
  })

  it('explains why the baseline was used when Prophet was asked for', async () => {
    withLiveForecast({
      fallback: {
        requested: 'prophet',
        reason: 'not_better',
        message: 'Prophet did not beat the baseline on past days.',
      },
    })
    asRole('planner')
    await renderApp('/forecast')

    const notice = await screen.findByTestId('fallback-notice')
    expect(notice).toHaveTextContent('uses the baseline, not Prophet')
    expect(notice).toHaveTextContent('did not beat the baseline')
  })
})
