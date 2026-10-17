import userEvent from '@testing-library/user-event'
import { screen, waitFor, within } from '@testing-library/vue'
import { describe, expect, it } from 'vitest'

import { backend } from '@/test/fake-backend'
import { openScheduling, seedScheduling } from '@/test/open-scheduling'

async function open(path: string, role = 'planner') {
  seedScheduling()
  backend.overtime = []
  return openScheduling(path, role)
}

describe('the overtime request form arriving filled in', () => {
  it('starts with the person, day and times from the link, and sends exactly those', async () => {
    // Failure caught: the intraday "Ask for overtime" link opening an empty form, so the planner
    // must retype what the screen already knew, or sending something other than what was shown.
    const user = userEvent.setup()
    await open('/overtime?employeeId=11&day=2031-03-03&from=11:30&to=12:30')
    const form = await screen.findByRole('form', { name: 'Ask for overtime' })
    await waitFor(() => expect(within(form).getByLabelText('Person')).toHaveValue('11'))
    expect(within(form).getByLabelText('Day')).toHaveValue('2031-03-03')
    expect(within(form).getByLabelText('From')).toHaveValue('11:30')
    expect(within(form).getByLabelText('To')).toHaveValue('12:30')
    await user.click(within(form).getByRole('button', { name: 'Ask for overtime' }))
    await waitFor(() => expect(backend.writes).toHaveLength(1))
    expect(backend.writes[0]?.body).toMatchObject({
      employeeId: 11,
      day: '2031-03-03',
      startTime: '11:30',
      endTime: '12:30',
    })
  })

  it('is empty, with the usual evening times, when opened without a link', async () => {
    await open('/overtime')
    const form = await screen.findByRole('form', { name: 'Ask for overtime' })
    expect(within(form).getByLabelText('Day')).toHaveValue('')
    expect(within(form).getByLabelText('From')).toHaveValue('18:00')
  })

  it('ignores values in the link when the role may not ask', async () => {
    // Failure caught: a prefilled form shown to a role the API would refuse.
    await open('/overtime?employeeId=11&day=2031-03-03', 'executive')
    expect(
      await screen.findByRole('heading', { name: "You don't have access to this page" }),
    ).toBeVisible()
  })
})
