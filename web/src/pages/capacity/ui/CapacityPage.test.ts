import userEvent from '@testing-library/user-event'
import { screen, waitFor, within } from '@testing-library/vue'
import { describe, expect, it } from 'vitest'

import { capacityOf, emptyCapacity, LIMITS } from '@/test/capacity-fixtures'
import { backend } from '@/test/fake-backend'
import { openScheduling, seedScheduling } from '@/test/open-scheduling'
import { DAYS } from '@/test/scheduling-fixtures'

const row = (day: string) => within(screen.getByTestId(`day-${day}`))
const col = (day: string, name: string) =>
  screen.getByTestId(`day-${day}`).querySelector(`[data-col="${name}"]`)?.textContent?.trim()

async function open(role = 'planner') {
  seedScheduling()
  backend.capacity = capacityOf()
  return openScheduling('/capacity', role)
}

describe('the capacity view', () => {
  it('splits a day into permanent, seasonal and overflow from the server figures', async () => {
    await open()

    await screen.findByTestId(`day-${DAYS[0]}`)
    expect(['peak', 'permanent', 'seasonal', 'overflow'].map((c) => col(DAYS[0]!, c))).toEqual([
      '160',
      '100',
      '60',
      '0',
    ])
    expect(['peak', 'permanent', 'seasonal', 'overflow'].map((c) => col(DAYS[2]!, c))).toEqual([
      '410',
      '100',
      '250',
      '60',
    ])
  })

  it('shows a day with no forecast as dashes, never as zeros', async () => {
    await open()
    await screen.findByTestId(`day-${DAYS[3]}`)
    for (const c of ['peak', 'permanent', 'seasonal', 'overflow', 'hire']) {
      expect(col(DAYS[3]!, c)).toBe('\u2014')
    }
  })

  it('says how many seasonal agents are engaged and still to find', async () => {
    await open()
    await screen.findByTestId(`day-${DAYS[2]}`)
    expect(col(DAYS[2]!, 'engaged')).toBe('3')
    expect(col(DAYS[2]!, 'hire')).toBe('247')
  })

  it('flags a day built from only some queues as a minimum', async () => {
    await open()
    await screen.findByTestId(`day-${DAYS[1]}`)
    expect(await row(DAYS[1]!).findByText(/At least this many: 1 of 2 queues/)).toBeVisible()
    expect(row(DAYS[0]!).queryByText(/At least this many/)).toBeNull()
    expect(await screen.findByTestId('incomplete-notice')).toHaveTextContent(
      '1 day has a forecast for only some queues',
    )
  })

  it('summarises the horizon', async () => {
    await open()
    expect(await screen.findByTestId('kpi-peak')).toHaveTextContent('410')
    expect(screen.getByTestId('kpi-peak')).toHaveTextContent('of 350 in the workforce')
    expect(screen.getByTestId('kpi-seasonal')).toHaveTextContent('250')
    expect(screen.getByTestId('kpi-overflow')).toHaveTextContent('1')
  })

  it('describes every day to a screen reader, not only by colour', async () => {
    await open()
    const wed = await screen.findByTestId(`day-${DAYS[2]}`)
    expect(within(wed).getByText('Beyond everyone')).toBeInTheDocument()
    expect(
      within(screen.getByTestId(`day-${DAYS[0]}`)).getByText('Needs seasonal agents'),
    ).toBeInTheDocument()
    expect(
      within(screen.getByTestId(`day-${DAYS[3]}`)).getByText('No forecast'),
    ).toBeInTheDocument()
  })
})

describe('when capacity cannot be trusted', () => {
  it('warns that the pools are the tender figures until an admin confirms them', async () => {
    seedScheduling()
    backend.capacity = capacityOf({ limits: { ...LIMITS, confirmed: false } })
    await openScheduling('/capacity')
    expect(await screen.findByTestId('limits-notice')).toHaveTextContent(
      '100 permanent, 250 seasonal',
    )
  })

  it('is quiet about it once confirmed', async () => {
    await open()
    await screen.findByTestId('kpi-peak')
    expect(screen.queryByTestId('limits-notice')).toBeNull()
  })

  it('says there is nothing to plan from, and invents no figures, when nothing is forecast', async () => {
    seedScheduling()
    backend.capacity = emptyCapacity()
    await openScheduling('/capacity')

    expect(await screen.findByTestId('no-forecast')).toHaveTextContent(/published forecast/)
    expect(screen.getByTestId('kpi-peak')).toHaveTextContent('\u2014')
    expect(screen.getByTestId('kpi-overflow')).toHaveTextContent('\u2014')
    expect(screen.queryByTestId('incomplete-notice')).toBeNull()
  })
})

describe('the horizon', () => {
  it('asks for four weeks from the chosen week, and for more when told to', async () => {
    const user = userEvent.setup()
    await open()
    await screen.findByTestId('kpi-peak')
    expect(backend.capacityQueries.at(-1)).toBe('?week_start=2026-05-25&weeks=4')

    await user.selectOptions(screen.getByLabelText('Show'), '12 weeks')

    await waitFor(() =>
      expect(backend.capacityQueries.at(-1)).toBe('?week_start=2026-05-25&weeks=12'),
    )
  })
})

describe('who may open capacity', () => {
  it.each(['planner', 'admin', 'executive', 'customer_ops'])('opens for %s', async (role) => {
    await open(role)
    expect(await screen.findByTestId('kpi-peak')).toBeVisible()
  })

  it.each(['lead', 'agent'])('does not open for %s', async (role) => {
    await open(role)
    expect(
      await screen.findByRole('heading', { name: "You don't have access to this page" }),
    ).toBeVisible()
  })
})
