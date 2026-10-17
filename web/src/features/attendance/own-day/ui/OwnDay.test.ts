import { screen } from '@testing-library/vue'
import { describe, expect, it } from 'vitest'

import type { MyAttendance } from '@/entities/workforce/attendance'
import { backend } from '@/test/fake-backend'
import { openScheduling, seedScheduling } from '@/test/open-scheduling'

const mine = (over: Partial<MyAttendance> = {}): MyAttendance => ({
  day: '2031-03-03',
  hasShift: true,
  shiftCode: 'D1',
  planned: [
    { start: '2031-03-03T09:00:00+02:00', end: '2031-03-03T12:00:00+02:00' },
    { start: '2031-03-03T12:30:00+02:00', end: '2031-03-03T17:30:00+02:00' },
  ],
  actual: [
    { state: 'available', start: '2031-03-03T09:00:00+02:00', end: '2031-03-03T12:00:00+02:00' },
    { state: 'lunch', start: '2031-03-03T12:00:00+02:00', end: '2031-03-03T12:30:00+02:00' },
  ],
  hasData: true,
  scheduledMin: 480,
  inAdherenceMin: 420,
  outOfAdherenceMin: 60,
  adherencePct: 87.5,
  lateStartMin: 0,
  earlyFinishMin: 0,
  exceptions: ['out_of_adherence'],
  ...over,
})

async function open(over: Partial<MyAttendance> | null = {}) {
  seedScheduling()
  backend.myAttendance = over === null ? null : mine(over)
  return openScheduling('/my-schedule', 'agent')
}

describe('my attendance on the schedule', () => {
  it('shows the agent their planned and actual day', async () => {
    // Failure caught: planned and actual shown without the break being left out of the plan.
    await open()
    expect(await screen.findByTestId('own-planned')).toHaveTextContent(
      '09:00 to 12:00, 12:30 to 17:30',
    )
    expect(screen.getByTestId('own-adherence')).toHaveTextContent('87.5% in adherence')
    expect(screen.getByTestId('own-actual')).toHaveTextContent('12:00 to 12:30: Lunch')
  })

  it('does not compare anything when no states are loaded', async () => {
    await open({ hasData: false, adherencePct: null, actual: [], exceptions: [] })
    expect(await screen.findByTestId('own-day-no-data')).toBeVisible()
    expect(screen.queryByTestId('own-adherence')).not.toBeInTheDocument()
  })

  it('says so on a day with no shift', async () => {
    await open({ hasShift: false, shiftCode: null, planned: [], actual: [], hasData: false })
    expect(await screen.findByTestId('own-day-no-shift')).toBeVisible()
  })

  it('stays out of the way for a person not on the employee list', async () => {
    await open(null)
    expect(await screen.findByText('Need time off?')).toBeVisible()
    expect(screen.queryByTestId('own-day')).not.toBeInTheDocument()
    expect(screen.queryByTestId('own-day-error')).not.toBeInTheDocument()
  })
})
