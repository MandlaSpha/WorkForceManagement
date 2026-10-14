import userEvent from '@testing-library/user-event'
import { screen, waitFor, within } from '@testing-library/vue'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it } from 'vitest'

import {
  accuracyFor,
  dayIntervals,
  forecastVersion,
  queueInfo,
  scenarioResult,
} from '@/test/forecast-fixtures'
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

  it('marks the planner and capacity figures stale, because they rest on the live forecast', async () => {
    withLiveForecast()
    backend.versions = [draft, forecastVersion()]
    backend.intervals['v-draft'] = dayIntervals()
    asRole('planner')
    const u = user()
    const { queryClient } = await renderApp('/forecast')
    // Figures an earlier visit to those screens left in the cache.
    queryClient.setQueryData(['capacity', '2026-05-25', 4], { limits: {}, weeks: [] })
    queryClient.setQueryData(['scheduling', 'plan', 1, '2026-05-25'], { cells: {} })

    await u.click(await screen.findByRole('button', { name: /Publish Draft plan/ }))

    await waitFor(() => {
      expect(queryClient.getQueryState(['capacity', '2026-05-25', 4])?.isInvalidated).toBe(true)
      expect(
        queryClient.getQueryState(['scheduling', 'plan', 1, '2026-05-25'])?.isInvalidated,
      ).toBe(true)
    })
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

describe('the events calendar', () => {
  const payment = {
    id: 1,
    name: 'Payment run',
    queueId: null,
    queue: null,
    dateFrom: '2026-05-25',
    dateTo: '2026-05-27',
    upliftPct: 20,
  }

  it('lists events with their days, queue and signed change', async () => {
    withLiveForecast()
    backend.events = [
      payment,
      {
        ...payment,
        id: 2,
        name: 'Outage',
        queueId: 1,
        queue: 'QueueA',
        dateTo: '2026-05-25',
        upliftPct: -50,
      },
    ]
    asRole('planner')
    await renderApp('/forecast')

    const table = await screen.findByRole('table', { name: 'Events' })
    const run = within(within(table).getByRole('rowheader', { name: 'Payment run' }).closest('tr')!)
    expect(run.getByText('All queues')).toBeVisible()
    expect(run.getByText('+20%')).toBeVisible()
    expect(run.getByText(/to Wed 27 May/)).toBeVisible()
    const outage = within(within(table).getByRole('rowheader', { name: 'Outage' }).closest('tr')!)
    expect(outage.getByText('QueueA')).toBeVisible()
    expect(outage.getByText('−50%')).toBeVisible() // a real minus sign
  })

  it('adds an event for the chosen queue with the CSRF token, and lists it', async () => {
    withLiveForecast()
    asRole('planner')
    const u = user()
    await renderApp('/forecast')

    const form = await screen.findByRole('form', { name: 'Add an event' })
    await u.type(within(form).getByLabelText('Name'), 'Campaign')
    await u.clear(within(form).getByLabelText('First day'))
    await u.type(within(form).getByLabelText('First day'), '2026-06-01')
    await u.clear(within(form).getByLabelText('Last day'))
    await u.type(within(form).getByLabelText('Last day'), '2026-06-03')
    await u.selectOptions(within(form).getByLabelText('Applies to'), 'QueueA')
    await u.clear(within(form).getByLabelText('Change in calls (%)'))
    await u.type(within(form).getByLabelText('Change in calls (%)'), '-30')
    await u.click(within(form).getByRole('button', { name: 'Add event' }))

    await waitFor(() => expect(backend.writes).toHaveLength(1))
    expect(backend.writes[0]).toEqual({
      method: 'POST',
      path: '/api/v1/forecasting/events',
      body: {
        name: 'Campaign',
        queueId: 1,
        dateFrom: '2026-06-01',
        dateTo: '2026-06-03',
        upliftPct: -30,
      },
      csrf: 'test-csrf-token',
    })
    expect(await screen.findByRole('rowheader', { name: 'Campaign' })).toBeVisible()
    await waitFor(() => expect(within(form).getByLabelText('Name')).toHaveValue(''))
  })

  it('sends every queue as no queue at all', async () => {
    withLiveForecast()
    asRole('planner')
    const u = user()
    await renderApp('/forecast')

    const form = await screen.findByRole('form', { name: 'Add an event' })
    expect(within(form).getByLabelText('Applies to')).toHaveValue('')
    await u.type(within(form).getByLabelText('Name'), 'Everywhere')
    await u.click(within(form).getByRole('button', { name: 'Add event' }))
    await waitFor(() => expect(backend.writes).toHaveLength(1))
    expect(backend.writes[0]?.body).toMatchObject({ queueId: null })
  })

  it('shows why an event was refused and keeps what was typed', async () => {
    withLiveForecast()
    backend.nextProblem = {
      status: 422,
      code: 'event.uplift_invalid',
      title: 'Invalid request',
      detail: 'The change is between -100% and +500%.',
    }
    asRole('planner')
    const u = user()
    await renderApp('/forecast')

    const form = await screen.findByRole('form', { name: 'Add an event' })
    await u.type(within(form).getByLabelText('Name'), 'Too much')
    await u.click(within(form).getByRole('button', { name: 'Add event' }))

    expect(await screen.findByTestId('event-error')).toHaveTextContent(/between -100% and \+500%/)
    expect(within(form).getByLabelText('Name')).toHaveValue('Too much')
  })

  it('cannot add an event without a name', async () => {
    withLiveForecast()
    asRole('planner')
    await renderApp('/forecast')
    const form = await screen.findByRole('form', { name: 'Add an event' })
    expect(within(form).getByRole('button', { name: 'Add event' })).toBeDisabled()
  })

  it('removes an event', async () => {
    withLiveForecast()
    backend.events = [payment]
    asRole('planner')
    const u = user()
    await renderApp('/forecast')

    await u.click(await screen.findByRole('button', { name: 'Remove event Payment run' }))

    await waitFor(() => expect(backend.writes).toHaveLength(1))
    expect(backend.writes[0]).toMatchObject({
      method: 'DELETE',
      path: '/api/v1/forecasting/events/1',
      csrf: 'test-csrf-token',
    })
    expect(await screen.findByText(/No events yet/)).toBeVisible()
  })

  it('lets a lead read the calendar but gives no way to change it', async () => {
    withLiveForecast()
    backend.events = [payment]
    asRole('lead')
    await renderApp('/forecast')

    expect(await screen.findByRole('rowheader', { name: 'Payment run' })).toBeVisible()
    expect(screen.queryByRole('form', { name: 'Add an event' })).toBeNull()
    expect(screen.queryByRole('button', { name: /^Remove event/ })).toBeNull()
  })

  it('tells the reader which events adjusted the forecast they are looking at', async () => {
    withLiveForecast({
      params: {
        slTargetPct: 80,
        slThresholdS: 20,
        occupancyCeilingPct: 85,
        shrinkagePct: 30,
        events: [
          { id: 1, name: 'Payment run', upliftPct: 20, days: ['2026-05-25'] },
          { id: 2, name: 'Outage', upliftPct: -50, days: ['2026-05-26'] },
        ],
      },
    })
    asRole('planner')
    await renderApp('/forecast')

    const notice = await screen.findByTestId('events-notice')
    expect(notice).toHaveTextContent('Payment run (+20%)')
    expect(notice).not.toHaveTextContent('Outage') // that one is for another day
  })

  it('says nothing about events when none adjusted the forecast', async () => {
    withLiveForecast()
    asRole('planner')
    await renderApp('/forecast')
    await screen.findByTestId('total-calls')
    expect(screen.queryByTestId('events-notice')).toBeNull()
  })
})

describe('what-if scenarios', () => {
  const open = async (role = 'planner') => {
    withLiveForecast()
    backend.scenario = scenarioResult()
    asRole(role)
    await renderApp('/forecast')
    return screen.findByRole('form', { name: 'What if' })
  }

  it('asks about the forecast on screen with the CSRF token, and shows base against scenario', async () => {
    const form = await open()
    const u = user()

    await u.clear(within(form).getByLabelText('Change in calls (%)'))
    await u.type(within(form).getByLabelText('Change in calls (%)'), '100')
    await u.click(within(form).getByRole('button', { name: 'Show what changes' }))

    await waitFor(() => expect(backend.writes).toHaveLength(1))
    expect(backend.writes[0]).toEqual({
      method: 'POST',
      path: '/api/v1/forecasting/scenarios',
      body: {
        versionId: 'v-live',
        volumeChangePct: 100,
        ahtChangePct: 0,
        shrinkagePct: null,
        slTargetPct: null,
      },
      csrf: 'test-csrf-token',
    })
    const day = within(await screen.findByTestId('scenario-2026-05-25'))
    expect(day.getByText(/10 to 20/)).toBeVisible()
    expect(day.getByText(/5 to 6/)).toBeVisible()
    expect(day.getByText('(+1)')).toBeVisible()
    expect(day.getByText(/2\.5 to 3\.0/)).toBeVisible()
    expect(within(screen.getByTestId('scenario-total')).getByText('(+0.5)')).toBeVisible()
  })

  it('sends shrinkage and the target when they are filled in, and says what they became', async () => {
    const form = await open()
    const u = user()
    backend.scenario = scenarioResult({
      scenario: { slTargetPct: 95, slThresholdS: 20, occupancyCeilingPct: 85, shrinkagePct: 0 },
    })

    await u.type(within(form).getByLabelText(/^Shrinkage/), '0')
    await u.type(within(form).getByLabelText(/^Service-level target/), '95')
    await u.click(within(form).getByRole('button', { name: 'Show what changes' }))

    await waitFor(() => expect(backend.writes).toHaveLength(1))
    expect(backend.writes[0]?.body).toMatchObject({ shrinkagePct: 0, slTargetPct: 95 })
    expect(await screen.findByTestId('scenario-assumptions')).toHaveTextContent(
      'Shrinkage 30% to 0%, service level target 80% to 95% in 20 s',
    )
  })

  it('marks figures as minimums when some half-hours could not be staffed', async () => {
    const form = await open()
    const u = user()
    backend.scenario = scenarioResult({
      days: [{ ...scenarioResult().days[0]!, complete: false }],
    })

    await u.click(within(form).getByRole('button', { name: 'Show what changes' }))

    expect(await screen.findByTestId('scenario-minimum')).toHaveTextContent(/at least this much/)
    expect(within(screen.getByTestId('scenario-2026-05-25')).getByText(/5 to 6\*/)).toBeVisible()
  })

  it('shows why a scenario was refused and no table', async () => {
    const form = await open()
    const u = user()
    backend.nextProblem = {
      status: 422,
      code: 'scenario.volume_invalid',
      title: 'Invalid scenario',
      detail: 'Calls can change by -100% to +500%.',
    }

    await u.click(within(form).getByRole('button', { name: 'Show what changes' }))

    expect(await screen.findByTestId('scenario-error')).toHaveTextContent(/-100% to \+500%/)
    expect(screen.queryByTestId('scenario-table')).toBeNull()
  })

  it('shows no table before anything has been asked', async () => {
    await open()
    expect(screen.queryByTestId('scenario-table')).toBeNull()
  })

  it('lets a lead ask, since it changes nothing', async () => {
    const form = await open('lead')
    expect(within(form).getByRole('button', { name: 'Show what changes' })).toBeEnabled()
  })

  it('offers nothing when there is no forecast to ask about', async () => {
    backend.queues = [queueInfo()]
    backend.versions = []
    asRole('planner')
    await renderApp('/forecast')
    await screen.findByText(/No forecast has been run for this queue yet/)
    expect(screen.queryByRole('form', { name: 'What if' })).toBeNull()
  })
})
