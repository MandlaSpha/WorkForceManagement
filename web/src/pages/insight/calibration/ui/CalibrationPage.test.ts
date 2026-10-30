import userEvent from '@testing-library/user-event'
import { screen, waitFor, within } from '@testing-library/vue'
import { describe, expect, it } from 'vitest'

import { expectAriaReferencesResolve } from '@/test/aria'
import { backtestOf, tuningOf } from '@/test/forecast-fixtures'
import { backend } from '@/test/fake-backend'
import { openScheduling, seedScheduling } from '@/test/open-scheduling'

async function open(role = 'planner') {
  seedScheduling()
  backend.tuning = tuningOf()
  backend.backtest = backtestOf()
  return openScheduling('/calibration', role)
}

const field = (name: string | RegExp) => screen.findByLabelText(name)

describe('the tuning form', () => {
  it('starts from the saved tuning and says when nobody has saved one', async () => {
    await open()
    expect(await field('Look back (weeks)')).toHaveValue(4)
    expect(screen.getByLabelText(/Recency weight/)).toHaveValue(0.7)
    expect(screen.getByLabelText('Contacts multiplier')).toHaveValue(1)
    expect(screen.getByTestId('tuning-state')).toHaveTextContent('Defaults, nobody has saved')
  })

  it('shows a saved tuning as saved, with its values', async () => {
    seedScheduling()
    backend.tuning = tuningOf({ saved: true, weeks: 2, volumeMultiplier: 1.1 })
    backend.backtest = backtestOf()
    await openScheduling('/calibration')
    expect(await field('Look back (weeks)')).toHaveValue(2)
    expect(screen.getByLabelText('Contacts multiplier')).toHaveValue(1.1)
    expect(screen.getByTestId('tuning-state')).toHaveTextContent('Saved')
  })
})

describe('the back-test', () => {
  it('shows what the saved tuning scored when the page opens', async () => {
    await open()
    expect(await screen.findByTestId('daily-current')).toHaveTextContent('51.8%')
    expect(screen.getByTestId('bias-current')).toHaveTextContent('\u221248.2% (ran low)')
    expect(backend.backtestQueries).toEqual(['?queue_id=1'])
  })

  it('scores the settings that were typed, next to the saved ones, when asked', async () => {
    const user = userEvent.setup()
    await open()
    const weeks = await field('Look back (weeks)')

    await user.clear(weeks)
    await user.type(weeks, '1')
    await user.click(screen.getByRole('button', { name: 'Back-test these settings' }))

    await waitFor(() =>
      expect(backend.backtestQueries.at(-1)).toBe(
        '?queue_id=1&weeks=1&decay=0.7&volume_multiplier=1&aht_multiplier=1',
      ),
    )
    expect(await screen.findByTestId('daily-candidate')).toHaveTextContent('60.0%')
    expect(screen.getByTestId('daily-current')).toHaveTextContent('51.8%')
    expect(screen.getByTestId('verdict')).toHaveTextContent(/predict day totals better/)
  })

  it('says how many past days it scored, and what each was forecast from', async () => {
    await open()
    expect(await screen.findByText(/Back-test on 2 past days/)).toBeVisible()
    expect(screen.getByText(/from only the days before it/)).toBeVisible()
  })

  it('says it is worse when the new settings do worse', async () => {
    seedScheduling()
    backend.tuning = tuningOf()
    backend.backtest = backtestOf({
      candidate: { dailyPct: 40, intervalPct: 30, biasPct: -60, days: 2 },
    })
    await openScheduling('/calibration')
    expect(await screen.findByTestId('verdict')).toHaveTextContent(/predict day totals worse/)
  })

  it('suggests the multiplier that removes the bias, and applies it on request', async () => {
    const user = userEvent.setup()
    await open()

    const suggestion = await screen.findByTestId('suggestion')
    expect(suggestion).toHaveTextContent('ran low')
    expect(suggestion).toHaveTextContent('multiplier of 1.67')
    await user.click(within(suggestion).getByRole('button', { name: /Use 1\.67/ }))

    expect(screen.getByLabelText('Contacts multiplier')).toHaveValue(1.67)
    await waitFor(() => expect(backend.backtestQueries.at(-1)).toContain('volume_multiplier=1.67'))
  })

  it('says a forecast that ran high ran high', async () => {
    seedScheduling()
    backend.tuning = tuningOf()
    backend.backtest = backtestOf({
      candidate: { dailyPct: 70, intervalPct: 50, biasPct: 25, days: 3 },
      suggestedVolumeMultiplier: 0.8,
    })
    await openScheduling('/calibration')
    expect(await screen.findByTestId('suggestion')).toHaveTextContent('ran high')
    expect(screen.getByTestId('bias-candidate')).toHaveTextContent('+25.0% (ran high)')
  })

  it('offers no suggestion when there is nothing to base one on', async () => {
    seedScheduling()
    backend.tuning = tuningOf()
    backend.backtest = backtestOf({ suggestedVolumeMultiplier: null })
    await openScheduling('/calibration')
    await screen.findByTestId('daily-current')
    expect(screen.queryByTestId('suggestion')).toBeNull()
  })

  it('says there is nothing to score instead of drawing zeros when no past day can be used', async () => {
    seedScheduling()
    backend.tuning = tuningOf()
    backend.backtest = backtestOf({
      candidate: { dailyPct: null, intervalPct: null, biasPct: null, days: 0 },
      current: { dailyPct: null, intervalPct: null, biasPct: null, days: 0 },
      suggestedVolumeMultiplier: null,
    })
    await openScheduling('/calibration')
    expect(await screen.findByTestId('nothing-to-score')).toBeVisible()
    expect(screen.queryByTestId('daily-current')).toBeNull()
  })

  it('shows why a back-test was refused', async () => {
    const user = userEvent.setup()
    await open()
    await screen.findByTestId('daily-current')
    backend.backtest = null // the next one fails

    await user.clear(await field('Look back (weeks)'))
    await user.type(screen.getByLabelText('Look back (weeks)'), '3')
    await user.click(screen.getByRole('button', { name: 'Back-test these settings' }))

    expect(await screen.findByTestId('backtest-error')).toBeVisible()
  })
})

describe('the comparison tiles', () => {
  it('sets these settings beside the saved ones, with the change in words', async () => {
    // Failure caught: a comparison told by colour alone, or a delta worked the wrong way round.
    await open()
    const candidate = await screen.findByTestId('tile-candidate')
    const saved = screen.getByTestId('tile-current')
    expect(within(candidate).getByTestId('stat-value')).toHaveTextContent('60.0%')
    expect(within(saved).getByTestId('stat-value')).toHaveTextContent('51.8%')
    const chips = within(candidate).getAllByTestId('delta-chip')
    expect(chips[0]).toHaveTextContent('Up 8.2 pts vs saved') // 60.00 - 51.76
    expect(chips[0]).toHaveAttribute('data-tone', 'good')
    // Bias moved from 48.2 to 40.0 away from zero: less error, which is good news.
    expect(chips[1]).toHaveTextContent('Down 8.2 pts vs saved')
    expect(chips[1]).toHaveAttribute('data-tone', 'good')
    expectAriaReferencesResolve()
  })

  it('calls worse settings worse, in words and tone', async () => {
    seedScheduling()
    backend.tuning = tuningOf()
    backend.backtest = backtestOf({
      candidate: { dailyPct: 40, intervalPct: 30, biasPct: -60, days: 2 },
    })
    await openScheduling('/calibration')
    const chips = within(await screen.findByTestId('tile-candidate')).getAllByTestId('delta-chip')
    expect(chips[0]).toHaveTextContent('Down 11.8 pts vs saved')
    expect(chips[0]).toHaveAttribute('data-tone', 'bad')
    expect(chips[1]).toHaveAttribute('data-tone', 'bad')
  })

  it('shows each setting as a row with helper text', async () => {
    await open()
    expect(
      await screen.findByText(/same-weekday history each forecast is built from/),
    ).toBeVisible()
    expect(screen.getByText(/how many contacts arrive/)).toBeVisible()
  })
})

describe('saving', () => {
  it('sends the queue and the typed values with the CSRF token, and flips to saved', async () => {
    const user = userEvent.setup()
    await open()
    const weeks = await field('Look back (weeks)')
    await user.clear(weeks)
    await user.type(weeks, '2')

    await user.click(screen.getByRole('button', { name: "Save as this queue's tuning" }))

    await waitFor(() => expect(backend.writes).toHaveLength(1))
    expect(backend.writes[0]).toEqual({
      method: 'PUT',
      path: '/api/v1/forecasting/tuning',
      body: { queueId: 1, weeks: 2, decay: 0.7, volumeMultiplier: 1, ahtMultiplier: 1 },
      csrf: 'test-csrf-token',
    })
    await waitFor(() => expect(screen.getByTestId('tuning-state')).toHaveTextContent('Saved'))
  })

  it('shows why a tuning was refused, and does not pretend it saved', async () => {
    const user = userEvent.setup()
    await open()
    backend.nextProblem = {
      status: 422,
      code: 'tuning.weeks_invalid',
      title: 'Invalid tuning',
      detail: 'Look back over 1 to 12 weeks.',
    }

    await user.click(await screen.findByRole('button', { name: "Save as this queue's tuning" }))

    expect(await screen.findByTestId('tuning-error')).toHaveTextContent(/1 to 12 weeks/)
    expect(screen.getByTestId('tuning-state')).toHaveTextContent('Defaults')
  })
})

describe('who may open it', () => {
  it.each(['planner', 'admin'])('opens for %s, who may save', async (role) => {
    await open(role)
    expect(await screen.findByRole('button', { name: "Save as this queue's tuning" })).toBeVisible()
  })

  it.each(['lead', 'agent', 'executive', 'customer_ops'])('does not open for %s', async (role) => {
    await open(role)
    expect(
      await screen.findByRole('heading', { name: "You don't have access to this page" }),
    ).toBeVisible()
  })

  it('asks for a queue first when none is chosen', async () => {
    seedScheduling()
    backend.queues = []
    await openScheduling('/calibration')
    expect(await screen.findByText(/Choose a queue at the top/)).toBeVisible()
  })
})
