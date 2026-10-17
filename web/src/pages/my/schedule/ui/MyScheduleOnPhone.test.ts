import userEvent from '@testing-library/user-event'
import { screen } from '@testing-library/vue'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { monthOf } from '@/entities/my-schedule'
import type { MySchedule } from '@/entities/my-schedule'
import { PHONE_QUERY } from '@/shared/ui/viewport'
import { todayInJohannesburg } from '@/shared/lib/week'
import { backend } from '@/test/fake-backend'
import { openScheduling, seedScheduling } from '@/test/open-scheduling'

const MONTH = monthOf(todayInJohannesburg())

const schedule = (): MySchedule => ({
  employee: 'Alex Agent',
  fromDate: `${MONTH}-01`,
  toDate: `${MONTH}-28`,
  shifts: [
    {
      day: `${MONTH}-15`,
      shift: 'D1',
      startTime: '09:00:00',
      endTime: '17:30:00',
      queue: 'QueueA',
      activities: [],
    },
  ],
  leave: [],
  unpublishedShifts: 0,
  openSwaps: 0,
})

afterEach(() => {
  vi.unstubAllGlobals()
})

async function open(phone: boolean) {
  vi.stubGlobal(
    'matchMedia',
    vi.fn((query: string) => ({ matches: phone && query === PHONE_QUERY })),
  )
  seedScheduling()
  backend.mySchedule = schedule()
  return openScheduling('/my-schedule', 'agent')
}

describe('my schedule at phone width (MOB-01)', () => {
  it('starts on the list of days, not the month grid', async () => {
    // Failure caught: a seven-column grid forced onto a 360px screen.
    await open(true)
    expect(await screen.findByRole('list', { name: 'My days' })).toBeVisible()
    expect(screen.queryByTestId('month-grid')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'List' })).toHaveAttribute('aria-pressed', 'true')
  })

  it('still lets the person switch to the month', async () => {
    await open(true)
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'Month' }))
    expect(await screen.findByTestId('month-grid')).toBeVisible()
  })

  it('starts on the month on a wide screen', async () => {
    await open(false)
    expect(await screen.findByTestId('month-grid')).toBeVisible()
  })
})

describe('the navigation drawer (MOB-01)', () => {
  it('opens from the menu button and closes on Escape', async () => {
    await open(true)
    const user = userEvent.setup()
    const button = await screen.findByRole('button', { name: 'Open navigation' })
    expect(button).toHaveAttribute('aria-expanded', 'false')
    await user.click(button)
    expect(button).toHaveAttribute('aria-expanded', 'true')
    await user.keyboard('{Escape}')
    expect(button).toHaveAttribute('aria-expanded', 'false')
  })

  it('hides the closed drawer from keyboard and screen readers on a phone', async () => {
    // Failure caught: a drawer that is only slid off-screen still takes Tab focus.
    await open(true)
    const drawer = (
      await screen.findByRole('button', { name: 'Open navigation' })
    ).ownerDocument.querySelector('#sidebar')
    expect(drawer?.className).toContain('invisible')
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'Open navigation' }))
    expect(drawer?.className).not.toContain('invisible')
  })
})
