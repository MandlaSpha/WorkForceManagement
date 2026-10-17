import { fireEvent, screen, waitFor } from '@testing-library/vue'
import { describe, expect, it } from 'vitest'

import type { Peaks } from '@/entities/peaks'
import { backend } from '@/test/fake-backend'
import { openScheduling, seedScheduling } from '@/test/open-scheduling'

const report = (over: Partial<Peaks> = {}): Peaks => ({
  queueId: 1,
  dateFrom: '2031-03-01',
  dateTo: '2031-03-31',
  daysMeasured: 2,
  busiestDays: [{ day: '2031-03-03', offered: 40 }],
  quietestDays: [{ day: '2031-03-04', offered: 20 }],
  busiestIntervals: [{ start: '2031-03-03 08:00', offered: 30 }],
  busiestSlots: [{ slot: '08:00', averageOffered: '25.0', days: 2 }],
  quietestSlots: [{ slot: '08:30', averageOffered: '5.0', days: 1 }],
  ...over,
})

async function open(role = 'planner', peaks: Peaks = report()) {
  seedScheduling()
  backend.peaks = peaks
  return openScheduling('/peaks', role)
}

describe('peaks and troughs', () => {
  it('lists the busiest and quietest days and half-hours', async () => {
    await open()
    expect(await screen.findByTestId('busiest-days')).toHaveTextContent('2031-03-03: 40 calls')
    expect(screen.getByTestId('quietest-days')).toHaveTextContent('2031-03-04: 20 calls')
    expect(screen.getByTestId('busiest-slots')).toHaveTextContent('08:00: 25.0 calls over 2 days')
    expect(screen.getByTestId('quietest-slots')).toHaveTextContent('08:30')
    expect(screen.getByTestId('busiest-intervals')).toHaveTextContent('2031-03-03 08:00: 30 calls')
  })

  it('says so, and ranks nothing, when no calls were measured', async () => {
    // Failure caught: empty lists shown as if every day were equally quiet.
    await open('planner', report({ daysMeasured: 0, busiestDays: [], quietestDays: [] }))
    expect(await screen.findByTestId('peaks-none')).toBeVisible()
    expect(screen.queryByTestId('busiest-days')).toBeNull()
  })

  it('asks again for the range chosen and never when the dates are backwards', async () => {
    await open()
    await screen.findByTestId('busiest-days')
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
