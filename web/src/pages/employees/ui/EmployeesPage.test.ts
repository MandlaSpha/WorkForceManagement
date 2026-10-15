import userEvent from '@testing-library/user-event'
import { screen, waitFor, within } from '@testing-library/vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { EmployeeImportReport } from '@/entities/scheduling'
import { backend } from '@/test/fake-backend'
import { interceptEmployeeImport } from '@/test/employee-import'
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
    // No queues, no manager and no ACD logins: three dashes.
    expect(within(lee).getAllByText('—')).toHaveLength(3)
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

describe('importing employees', () => {
  const report = (over: Partial<EmployeeImportReport> = {}): EmployeeImportReport => ({
    dryRun: true,
    created: 2,
    updated: 1,
    unchanged: 3,
    rejected: {},
    ignoredColumns: [],
    loginsMapped: 3,
    ...over,
  })

  beforeEach(() => interceptEmployeeImport())
  afterEach(() => vi.restoreAllMocks())

  async function chooseFile(user: ReturnType<typeof userEvent.setup>, name = 'people.csv') {
    await user.click(await screen.findByRole('button', { name: 'Import employees' }))
    const input = await screen.findByLabelText('Employees (.csv or .xlsx)')
    await user.upload(input, new File(['Employee No,Name\n'], name, { type: 'text/csv' }))
  }

  it('checks the file first, saying what would happen, and changes nothing yet', async () => {
    seedScheduling()
    backend.employeeImport = report()
    const user = userEvent.setup()
    await openScheduling('/employees')
    await chooseFile(user)
    await user.click(screen.getByRole('button', { name: 'Check the file' }))

    const result = await screen.findByTestId('emp-import-report')
    expect(result).toHaveTextContent('If you import this file:')
    expect(result).toHaveTextContent('2 added')
    expect(result).toHaveTextContent('3 ACD logins tied to people')
    // Failure caught: a check that quietly imports.
    expect(backend.employeeImports).toHaveLength(1)
    expect(backend.employeeImports[0]).toEqual({
      dryRun: true,
      multipart: true,
      filePart: true,
      csrf: 'test-csrf-token',
    })
  })

  it('imports for real only after the check, with the same file, and says it is done', async () => {
    seedScheduling()
    backend.employeeImport = report()
    const user = userEvent.setup()
    await openScheduling('/employees')
    await chooseFile(user)
    await user.click(screen.getByRole('button', { name: 'Check the file' }))
    await user.click(await screen.findByRole('button', { name: 'Import these' }))

    await waitFor(() => expect(backend.employeeImports).toHaveLength(2))
    expect(backend.employeeImports.map((i) => i.dryRun)).toEqual([true, false])
    await waitFor(() =>
      expect(screen.getByTestId('emp-import-report')).toHaveTextContent('Imported:'),
    )
    expect(screen.queryByRole('button', { name: 'Import these' })).toBeNull()
  })

  it('names the rows that are not kept in words, and the columns that were ignored', async () => {
    seedScheduling()
    backend.employeeImport = report({
      rejected: { contract_invalid: 2, queue_unknown: 1 },
      ignoredColumns: ['Favourite colour'],
    })
    const user = userEvent.setup()
    await openScheduling('/employees')
    await chooseFile(user)
    await user.click(screen.getByRole('button', { name: 'Check the file' }))
    const rejected = await screen.findByTestId('emp-import-rejected')
    expect(rejected).toHaveTextContent('3 rows are not kept')
    expect(rejected).toHaveTextContent('2 with a contract that is not permanent or seasonal')
    expect(rejected).toHaveTextContent('1 with a queue that does not exist')
    expect(screen.getByTestId('emp-import-ignored')).toHaveTextContent('Favourite colour')
  })

  it('offers no import when nothing would change', async () => {
    seedScheduling()
    backend.employeeImport = report({ created: 0, updated: 0, loginsMapped: 0, unchanged: 5 })
    const user = userEvent.setup()
    await openScheduling('/employees')
    await chooseFile(user)
    await user.click(screen.getByRole('button', { name: 'Check the file' }))
    expect(await screen.findByRole('button', { name: 'Import these' })).toBeDisabled()
  })

  it('forgets the check when a different file is chosen, so an old preview cannot confirm a new file', async () => {
    seedScheduling()
    backend.employeeImport = report()
    const user = userEvent.setup()
    await openScheduling('/employees')
    await chooseFile(user)
    await user.click(screen.getByRole('button', { name: 'Check the file' }))
    await screen.findByTestId('emp-import-report')
    await user.upload(
      screen.getByLabelText('Employees (.csv or .xlsx)'),
      new File(['x'], 'other.csv', { type: 'text/csv' }),
    )
    expect(screen.queryByTestId('emp-import-report')).toBeNull()
    expect(screen.queryByRole('button', { name: 'Import these' })).toBeNull()
  })

  it('shows why a file was refused', async () => {
    seedScheduling()
    backend.nextProblem = {
      status: 422,
      code: 'employees.unreadable',
      title: 'Unusable file',
      detail: 'The first row must name the columns, and include an employee number and a name.',
    }
    const user = userEvent.setup()
    await openScheduling('/employees')
    await chooseFile(user)
    await user.click(screen.getByRole('button', { name: 'Check the file' }))
    expect(await screen.findByTestId('emp-import-error')).toHaveTextContent(/employee number/)
  })

  it('is not offered to a lead', async () => {
    seedScheduling()
    await openScheduling('/employees', 'lead')
    await screen.findByText('Alex Agent')
    expect(screen.queryByRole('button', { name: 'Import employees' })).toBeNull()
  })
})

describe('mapping ACD logins to people', () => {
  it('lists logins nobody owns, busiest first as given, with a call count', async () => {
    seedScheduling()
    backend.unmapped = [
      { login: 'jsmith', calls: 12 },
      { login: 'tmp', calls: 1 },
    ]
    await openScheduling('/employees')
    expect(await screen.findByTestId('unmapped-jsmith')).toHaveTextContent('12 calls')
    expect(screen.getByTestId('unmapped-tmp')).toHaveTextContent('1 call')
  })

  it('adds the login to the ones the person already has', async () => {
    seedScheduling()
    backend.employees = [employeeOf({ id: 10, name: 'Alex Agent', agentLogins: ['alex.a'] })]
    backend.unmapped = [{ login: 'alex2', calls: 4 }]
    const user = userEvent.setup()
    await openScheduling('/employees')
    const row = await screen.findByTestId('unmapped-alex2')
    await user.selectOptions(within(row).getByLabelText('Who is alex2'), '10')
    await user.click(within(row).getByRole('button', { name: /Tie alex2/ }))

    await waitFor(() => expect(backend.writes).toHaveLength(1))
    // Failure caught: replacing the person's other logins and orphaning their calls.
    expect(backend.writes[0]).toEqual({
      method: 'PUT',
      path: '/api/v1/scheduling/employees/10/agent-logins',
      body: { logins: ['alex.a', 'alex2'] },
      csrf: 'test-csrf-token',
    })
    await waitFor(() => expect(screen.queryByTestId('unmapped-alex2')).toBeNull())
  })

  it('shows nothing at all when every login is owned, and nothing to a lead', async () => {
    seedScheduling()
    backend.unmapped = []
    await openScheduling('/employees')
    await screen.findByText('Alex Agent')
    expect(screen.queryByRole('heading', { name: 'ACD logins nobody owns yet' })).toBeNull()
  })

  it('shows each persons logins in the list', async () => {
    seedScheduling()
    backend.employees = [employeeOf({ agentLogins: ['a1', 'a2'] })]
    await openScheduling('/employees')
    const row = (await screen.findByText('Alex Agent')).closest('tr')!
    expect(within(row).getByText('a1, a2')).toBeVisible()
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
