import userEvent from '@testing-library/user-event'
import { screen, waitFor, within } from '@testing-library/vue'
import { describe, expect, it } from 'vitest'

import type { AvailabilityWindow } from '@/entities/availability'
import { backend } from '@/test/fake-backend'
import { openScheduling, seedScheduling } from '@/test/open-scheduling'

const window = (over: Partial<AvailabilityWindow> = {}): AvailabilityWindow => ({
  id: 1,
  employeeId: 10,
  employee: 'Alex Agent',
  weekday: 0,
  startTime: '12:00:00',
  endTime: '13:00:00',
  kind: 'unavailable',
  ...over,
})

async function open(windows: AvailabilityWindow[] = []) {
  seedScheduling()
  backend.availability = windows
  return openScheduling('/my-availability', 'agent')
}

describe('my availability', () => {
  it('says that declaring nothing does not mean being free', async () => {
    await open()
    // Failure caught: a planner reading silence as "available" rosters someone who cannot work.
    expect(await screen.findByTestId('how-it-works')).toHaveTextContent(
      /does not mean you are free/,
    )
    expect(await screen.findByTestId('nothing-declared')).toBeVisible()
  })

  it('lists declared windows under their weekday, with their kind', async () => {
    await open([
      window({ id: 1, weekday: 0 }),
      window({ id: 2, weekday: 4, startTime: '18:00:00', endTime: '00:00:00', kind: 'preferred' }),
    ])
    const monday = await screen.findByTestId('day-Monday')
    expect(within(monday).getByText('12:00-13:00')).toBeVisible()
    expect(within(monday).getByText('Cannot work')).toBeVisible()
    const friday = screen.getByTestId('day-Friday')
    expect(within(friday).getByText('18:00-24:00')).toBeVisible() // midnight reads as end of day
    expect(within(friday).getByText('Would rather work')).toBeVisible()
    expect(screen.queryByTestId('day-Tuesday')).toBeNull()
  })

  it('sends the day, times and kind with the CSRF token', async () => {
    const user = userEvent.setup()
    await open()
    const form = await screen.findByRole('form', { name: 'Declare availability' })
    await user.selectOptions(within(form).getByLabelText('Day'), 'Wednesday')
    await user.clear(within(form).getByLabelText('From'))
    await user.type(within(form).getByLabelText('From'), '08:00')
    await user.clear(within(form).getByLabelText('To'))
    await user.type(within(form).getByLabelText('To'), '10:30')
    await user.click(within(form).getByRole('button', { name: 'Add' }))

    await waitFor(() => expect(backend.writes).toHaveLength(1))
    // Failure caught: weekday sent as text, or times in the wrong fields, would be refused or
    // declare the wrong hours.
    expect(backend.writes[0]).toEqual({
      method: 'POST',
      path: '/api/v1/people/availability',
      body: { weekday: 2, startTime: '08:00', endTime: '10:30', kind: 'unavailable' },
      csrf: 'test-csrf-token',
    })
    expect(await screen.findByTestId('day-Wednesday')).toHaveTextContent('08:00-10:30')
  })

  it('shows why a window was refused', async () => {
    const user = userEvent.setup()
    await open()
    backend.nextProblem = {
      status: 409,
      code: 'availability.overlaps',
      title: 'Availability refused',
      detail: 'That overlaps a window already declared on that day.',
    }
    const form = await screen.findByRole('form', { name: 'Declare availability' })
    await user.click(within(form).getByRole('button', { name: 'Add' }))
    expect(await screen.findByTestId('declare-error')).toHaveTextContent(/overlaps/)
  })

  it('removes a window with a DELETE and the list updates', async () => {
    const user = userEvent.setup()
    await open([window()])
    await user.click(await screen.findByRole('button', { name: 'Remove Monday 12:00-13:00' }))
    await waitFor(() => expect(backend.writes).toHaveLength(1))
    expect(backend.writes[0]).toMatchObject({
      method: 'DELETE',
      path: '/api/v1/people/availability/1',
      csrf: 'test-csrf-token',
    })
    expect(await screen.findByTestId('nothing-declared')).toBeVisible()
  })

  it('says so when the person is not on the employee list, and offers no form', async () => {
    seedScheduling()
    backend.noScheduleRecord = true
    await openScheduling('/my-availability', 'agent')
    expect(await screen.findByTestId('no-record')).toHaveTextContent(/not on the employee list/)
    expect(screen.queryByRole('form', { name: 'Declare availability' })).toBeNull()
  })
})
