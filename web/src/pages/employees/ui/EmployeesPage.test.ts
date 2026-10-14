import userEvent from '@testing-library/user-event'
import { screen, waitFor, within } from '@testing-library/vue'
import { describe, expect, it } from 'vitest'

import { backend } from '@/test/fake-backend'
import { openScheduling, seedScheduling } from '@/test/open-scheduling'

describe('the employee list', () => {
  it('shows hours, and marks hours nobody entered as a default', async () => {
    seedScheduling()
    await openScheduling('/employees')

    const alex = (await screen.findByText('Alex Agent')).closest('tr')!
    expect(within(alex).getByText('E001')).toBeVisible()
    expect(within(alex).getByText('40h')).toBeVisible()
    expect(within(alex).queryByText('Default')).toBeNull()
    expect(within(alex).getByText('QueueA L1')).toBeVisible()

    // A default must never pass for a contract figure someone typed.
    const sam = screen.getByText('Sam Planner').closest('tr')!
    expect(within(sam).getByText('Default')).toBeVisible()
  })

  it('says so when there is nobody yet', async () => {
    seedScheduling()
    backend.employees = []
    await openScheduling('/employees')
    expect(await screen.findByText(/There are no employees yet/)).toBeVisible()
  })
})

describe('adding an employee', () => {
  it('sends null hours when the box is blank, so the default is recorded as a default', async () => {
    seedScheduling()
    const user = userEvent.setup()
    await openScheduling('/employees')

    await user.click(await screen.findByRole('button', { name: 'Add employee' }))
    await user.type(screen.getByLabelText('Employee number'), 'E900')
    await user.type(screen.getByLabelText('Name'), 'Pat Example')
    await user.click(screen.getByLabelText('QueueA'))
    await user.click(screen.getByRole('button', { name: 'Add employee', description: '' }))

    await waitFor(() => expect(backend.writes).toHaveLength(1))
    expect(backend.writes[0]).toEqual({
      method: 'POST',
      path: '/api/v1/scheduling/employees',
      body: {
        empNo: 'E900',
        name: 'Pat Example',
        contractType: 'permanent',
        workMode: 'office',
        weeklyHours: null,
        skills: [{ queueId: 1, level: 1 }],
      },
      csrf: 'test-csrf-token',
    })
  })

  it('sends the hours that were typed as a number', async () => {
    seedScheduling()
    const user = userEvent.setup()
    await openScheduling('/employees')

    await user.click(await screen.findByRole('button', { name: 'Add employee' }))
    await user.type(screen.getByLabelText('Employee number'), 'E901')
    await user.type(screen.getByLabelText('Name'), 'Part Timer')
    await user.type(screen.getByLabelText(/Weekly hours/), '22.5')
    await user.click(screen.getByRole('button', { name: 'Add employee', description: '' }))

    await waitFor(() => expect(backend.writes).toHaveLength(1))
    expect(backend.writes[0]?.body).toMatchObject({ weeklyHours: 22.5, skills: [] })
  })

  it('keeps the form and shows the reason when the server refuses', async () => {
    seedScheduling()
    backend.nextProblem = {
      status: 409,
      code: 'employee.duplicate',
      title: 'Conflict',
      detail: 'That employee number is already in use.',
    }
    const user = userEvent.setup()
    await openScheduling('/employees')

    await user.click(await screen.findByRole('button', { name: 'Add employee' }))
    await user.type(screen.getByLabelText('Employee number'), 'E001')
    await user.type(screen.getByLabelText('Name'), 'Someone')
    await user.click(screen.getByRole('button', { name: 'Add employee', description: '' }))

    expect(await screen.findByTestId('employee-error')).toHaveTextContent(/already in use/)
    expect(screen.getByLabelText('Name')).toHaveValue('Someone')
  })

  it('does not let a blank number or name be submitted', async () => {
    seedScheduling()
    const user = userEvent.setup()
    await openScheduling('/employees')
    await user.click(await screen.findByRole('button', { name: 'Add employee' }))
    expect(screen.getByRole('button', { name: 'Add employee', description: '' })).toBeDisabled()
  })
})

describe('changing an employee', () => {
  it('starts from the current values and sends a full change', async () => {
    seedScheduling()
    const user = userEvent.setup()
    await openScheduling('/employees')

    await user.click(await screen.findByRole('button', { name: 'Change Alex Agent' }))
    expect(screen.getByLabelText('Name')).toHaveValue('Alex Agent')
    expect(screen.getByLabelText(/Weekly hours/)).toHaveValue(40)
    await user.click(screen.getByRole('button', { name: 'Save changes' }))

    await waitFor(() => expect(backend.writes).toHaveLength(1))
    expect(backend.writes[0]).toMatchObject({
      method: 'PUT',
      path: '/api/v1/scheduling/employees/10',
      body: { empNo: 'E001', weeklyHours: 40, skills: [{ queueId: 1, level: 1 }] },
    })
  })

  it('leaves hours blank for a person whose hours are only the default', async () => {
    seedScheduling()
    const user = userEvent.setup()
    await openScheduling('/employees')

    await user.click(await screen.findByRole('button', { name: 'Change Sam Planner' }))
    expect(screen.getByLabelText(/Weekly hours/)).toHaveValue(null)
    await user.click(screen.getByRole('button', { name: 'Save changes' }))

    await waitFor(() => expect(backend.writes).toHaveLength(1))
    expect(backend.writes[0]?.body).toMatchObject({ weeklyHours: null })
  })
})

describe('who may change employees', () => {
  it('lets a lead read the list but offers no way to add or change', async () => {
    seedScheduling()
    await openScheduling('/employees', 'lead')

    expect(await screen.findByText('Alex Agent')).toBeVisible()
    expect(screen.queryByRole('button', { name: 'Add employee' })).toBeNull()
    expect(screen.queryByRole('button', { name: /^Change / })).toBeNull()
  })

  it.each(['agent', 'executive', 'customer_ops'])('does not open for %s', async (role) => {
    seedScheduling()
    await openScheduling('/employees', role)
    expect(
      await screen.findByRole('heading', { name: "You don't have access to this page" }),
    ).toBeVisible()
  })
})
