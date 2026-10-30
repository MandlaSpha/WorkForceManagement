import userEvent from '@testing-library/user-event'
import { screen, waitFor, within } from '@testing-library/vue'
import { describe, expect, it } from 'vitest'

import { backend } from '@/test/fake-backend'
import { openScheduling, seedScheduling } from '@/test/open-scheduling'
import { DAYS, MONDAY_CELLS, planOf, rosterOf } from '@/test/scheduling-fixtures'

const MON = DAYS[0]!
const cellText = async (slot: number, day = MON) =>
  (await screen.findByTestId(`cell-${day}-${slot}`)).textContent?.trim()

describe('the planner heatmap', () => {
  it('shows scheduled minus required per half-hour, with a real minus sign', async () => {
    seedScheduling()
    await openScheduling('/planner')

    expect(await cellText(18)).toBe('−2')
    expect(await cellText(20)).toBe('0')
    expect(await cellText(22)).toBe('+2')
  })

  it('draws an unknown requirement as a dot, never as zero', async () => {
    seedScheduling()
    const user = userEvent.setup()
    await openScheduling('/planner')

    // Slot 30 on Tuesday has no requirement in the fixture. The grid opens on the busy hours, so
    // the whole day is asked for first.
    await user.click(await screen.findByTestId('show-all-hours'))
    expect(await cellText(30, DAYS[1])).toBe('·')
    expect(await cellText(30, DAYS[1])).not.toBe('0')
  })

  it('summarises the week from the server figures', async () => {
    seedScheduling()
    await openScheduling('/planner')

    expect(await screen.findByTestId('kpi-under')).toHaveTextContent('2 of 336 (1%)')
    expect(screen.getByTestId('kpi-gap')).toHaveTextContent('4')
    expect(screen.getByTestId('kpi-gap')).toHaveTextContent('25 scheduled · 10 required')
    expect(screen.getByTestId('kpi-worst')).toHaveTextContent('−2 at 09:00 on Mon 25 May')
    expect(screen.getByTestId('kpi-roster')).toHaveTextContent('Draft')
  })

  it('opens a day as a chart when its heading is chosen', async () => {
    seedScheduling()
    const user = userEvent.setup()
    await openScheduling('/planner')

    await user.click(await screen.findByRole('button', { name: /Open Tue 26 May as a chart/ }))

    expect(await screen.findByRole('heading', { name: 'Tue 26 May' })).toBeVisible()
    expect(screen.queryByTestId('heatmap')).toBeNull()
    expect(screen.getByRole('img', { name: /Tue 26 May/ })).toBeVisible()
  })
})

describe('when the plan cannot be trusted', () => {
  it('says there is no forecast, links to the Forecast screen and invents no numbers', async () => {
    seedScheduling()
    backend.plan = planOf(
      {},
      {
        forecast: null,
        summary: {
          intervalsKnown: 0,
          underIntervals: 0,
          gap: 0,
          requiredTotal: 0,
          scheduledTotal: 25,
          worst: null,
        },
      },
    )
    await openScheduling('/planner')

    const notice = await screen.findByTestId('no-forecast')
    expect(within(notice).getByRole('link', { name: 'Forecast' })).toHaveAttribute(
      'href',
      '/forecast',
    )
    expect(screen.getByTestId('kpi-gap')).toHaveTextContent('—')
    expect(screen.getByTestId('kpi-worst')).toHaveTextContent('—')
    expect(screen.getByTestId('kpi-under')).toHaveTextContent('none known')
    expect(await cellText(18)).toBe('·')
  })

  it('warns when the staffing assumptions behind the requirement are unconfirmed', async () => {
    seedScheduling()
    backend.plan = planOf(MONDAY_CELLS, {
      forecast: {
        id: 'f1',
        label: 'Week 22',
        publishedAt: '2026-05-20T09:00:00Z',
        assumptionsConfirmed: false,
      },
    })
    await openScheduling('/planner')
    expect(await screen.findByTestId('assumptions-notice')).toHaveTextContent(
      /nobody\s+has confirmed/,
    )
  })

  it('says how much of the week the forecast covers when it is partial', async () => {
    seedScheduling()
    backend.plan = planOf(MONDAY_CELLS, {
      summary: { ...planOf().summary, intervalsKnown: 100 },
    })
    await openScheduling('/planner')
    expect(await screen.findByTestId('partial-notice')).toHaveTextContent(/100 of the week's\s+336/)
  })

  it('stays quiet when the forecast covers the whole week and is confirmed', async () => {
    seedScheduling()
    await openScheduling('/planner')
    await screen.findByTestId('heatmap')
    expect(screen.queryByTestId('partial-notice')).toBeNull()
    expect(screen.queryByTestId('assumptions-notice')).toBeNull()
    expect(screen.queryByTestId('no-forecast')).toBeNull()
  })
})

describe('the plan follows the roster', () => {
  it('refetches after a shift is assigned, so the planner never shows a stale gap', async () => {
    seedScheduling()
    backend.onAssign = () => {
      backend.roster = rosterOf()
      backend.plan = planOf({
        ...MONDAY_CELLS,
        [`${MON}:18`]: { scheduled: 2, required: 3, variance: -1, state: 'under' },
      })
    }
    const user = userEvent.setup()
    await openScheduling('/planner')
    expect(await cellText(18)).toBe('−2')

    await user.click(screen.getByRole('link', { name: /Roster/ }))
    await user.selectOptions(
      await screen.findByLabelText('Shift for Sam Planner on Mon 25 May'),
      'D1',
    )
    await waitFor(() => expect(backend.writes).toHaveLength(1))
    await user.click(screen.getByRole('link', { name: /Planner/ }))

    await waitFor(async () => expect(await cellText(18)).toBe('−1'))
  })
})

describe('who may open the planner', () => {
  it.each(['planner', 'admin', 'lead'])('opens for %s', async (role) => {
    seedScheduling()
    await openScheduling('/planner', role)
    expect(await screen.findByTestId('heatmap')).toBeVisible()
  })

  it.each(['agent', 'executive', 'customer_ops'])('does not open for %s', async (role) => {
    seedScheduling()
    await openScheduling('/planner', role)
    expect(
      await screen.findByRole('heading', { name: "You don't have access to this page" }),
    ).toBeVisible()
  })
})
