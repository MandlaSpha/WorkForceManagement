import userEvent from '@testing-library/user-event'
import { screen, waitFor, within } from '@testing-library/vue'
import { describe, expect, it } from 'vitest'

import { backend } from '@/test/fake-backend'
import { openScheduling, seedScheduling } from '@/test/open-scheduling'
import { employeeOf } from '@/test/scheduling-fixtures'

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
        managerId: null,
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

describe('who manages whom', () => {
  const lead = () =>
    employeeOf({ id: 12, empNo: 'L001', name: 'Lee Lead', canManage: true, skills: [] })

  it('shows each persons manager, and a dash for nobody', async () => {
    seedScheduling()
    backend.employees = [employeeOf({ managerId: 12, manager: 'Lee Lead' }), lead()]
    await openScheduling('/employees')
    const alex = (await screen.findByText('Alex Agent')).closest('tr')!
    expect(within(alex).getByText('Lee Lead')).toBeVisible()
    const lee = screen.getByText('Lee Lead', { selector: 'th' }).closest('tr')!
    // No queues and no manager: two dashes.
    expect(within(lee).getAllByText('—')).toHaveLength(2)
  })

  it('offers only people who can approve as managers, never the person themselves', async () => {
    seedScheduling()
    backend.employees = [employeeOf(), lead(), employeeOf({ id: 13, empNo: 'E003', name: 'Sam' })]
    const user = userEvent.setup()
    await openScheduling('/employees')
    await user.click(await screen.findByRole('button', { name: 'Change Alex Agent' }))
    const select = screen.getByLabelText(/^Manager/)
    const names = within(select)
      .getAllByRole('option')
      .map((o) => o.textContent)
    // Failure caught: offering an agent as a manager would send a choice the API refuses.
    expect(names).toEqual(['Nobody (a planner or admin decides)', 'Lee Lead (L001)'])
  })

  it('sends the chosen manager as a number, and null for nobody', async () => {
    seedScheduling()
    backend.employees = [employeeOf({ managerId: 12, manager: 'Lee Lead' }), lead()]
    const user = userEvent.setup()
    await openScheduling('/employees')
    await user.click(await screen.findByRole('button', { name: 'Change Alex Agent' }))
    expect(screen.getByLabelText(/^Manager/)).toHaveValue('12')
    await user.click(screen.getByRole('button', { name: 'Save changes' }))
    await waitFor(() => expect(backend.writes[0]?.body).toMatchObject({ managerId: 12 }))

    await user.click(await screen.findByRole('button', { name: 'Change Alex Agent' }))
    await user.selectOptions(
      screen.getByLabelText(/^Manager/),
      'Nobody (a planner or admin decides)',
    )
    await user.click(screen.getByRole('button', { name: 'Save changes' }))
    await waitFor(() => expect(backend.writes[1]?.body).toMatchObject({ managerId: null }))
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
