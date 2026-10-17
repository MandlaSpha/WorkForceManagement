import userEvent from '@testing-library/user-event'
import { screen, waitFor } from '@testing-library/vue'
import { describe, expect, it } from 'vitest'

import { backend } from '@/test/fake-backend'
import { openScheduling, seedScheduling } from '@/test/open-scheduling'

function seedErasure(): void {
  seedScheduling()
  backend.erasure.removes = {
    agentLogins: 2,
    availabilityWindows: 1,
    notifications: 3,
    overtimeReasons: 1,
    payRecords: 1,
    signInLinks: 1,
  }
  backend.erasure.keeps = { shifts: 40, leaveRequests: 2, overtimeRequests: 1, standbyShifts: 0 }
  backend.erasure.retention = [{ employeeId: 10, employeeNumber: 'E001', endDate: '2019-03-31' }]
}

describe('anonymising a leaver', () => {
  it('is not offered to anyone but the admin', async () => {
    // Failure caught: the destructive action (or the retention list) showing for a planner.
    seedErasure()
    await openScheduling('/employees', 'planner')
    await screen.findByText('Alex Agent')
    expect(screen.queryByRole('button', { name: /Anonymise/ })).toBeNull()
    expect(screen.queryByText('Past the retention period')).toBeNull()
  })

  it('shows the counts first and sends nothing until the typed number matches', async () => {
    // Failure caught: a one-click erase, or a confirm that does not need the typed number.
    seedErasure()
    const user = userEvent.setup()
    await openScheduling('/employees', 'admin')

    await user.click(await screen.findByRole('button', { name: 'Anonymise Alex Agent' }))
    expect(await screen.findByText(/2 ACD logins/)).toBeVisible()
    expect(screen.getByText(/40 shifts/)).toBeVisible()

    const confirm = screen.getByRole('button', { name: 'Anonymise permanently' })
    expect(confirm).toBeDisabled()
    await user.type(screen.getByLabelText('Type the employee number to confirm'), 'E00')
    expect(confirm).toBeDisabled()
    await user.type(screen.getByLabelText('Type the employee number to confirm'), '2')
    expect(confirm).toBeDisabled()
    expect(backend.writes.filter((w) => w.path.endsWith('/anonymise'))).toEqual([])

    await user.clear(screen.getByLabelText('Type the employee number to confirm'))
    await user.type(screen.getByLabelText('Type the employee number to confirm'), 'E001')
    expect(confirm).toBeEnabled()
    await user.click(confirm)

    await waitFor(() =>
      expect(backend.writes.filter((w) => w.path.endsWith('/anonymise'))).toHaveLength(1),
    )
    expect(backend.writes.at(-1)?.body).toEqual({ employeeNumber: 'E001' })
    expect(await screen.findByText('Former employee AB12CD34EF')).toBeVisible()
    expect(screen.queryByText('Alex Agent')).toBeNull()
  })

  it('says why when the person cannot be anonymised, and offers no confirm', async () => {
    // Failure caught: a refusal (still has future shifts) swallowed, leaving a live confirm.
    seedErasure()
    backend.nextProblem = {
      status: 409,
      code: 'erasure.future_work',
      title: 'Anonymising refused',
      detail: 'This person still has shifts in the future. Clear them first.',
    }
    const user = userEvent.setup()
    await openScheduling('/employees', 'admin')
    await user.click(await screen.findByRole('button', { name: 'Anonymise Alex Agent' }))
    expect(await screen.findByText(/still has shifts in the future/)).toBeVisible()
    expect(screen.queryByRole('button', { name: 'Anonymise permanently' })).toBeNull()
  })

  it('lists people past retention and reviews one without acting', async () => {
    // Failure caught: the retention list acting by itself, or showing names.
    seedErasure()
    const user = userEvent.setup()
    await openScheduling('/employees', 'admin')

    const list = await screen.findByRole('list', { name: 'Leavers past retention' })
    expect(list).toHaveTextContent('E001')
    expect(list).toHaveTextContent('2019-03-31')
    expect(list).not.toHaveTextContent('Alex Agent')

    await user.click(screen.getByRole('button', { name: 'Review E001 for anonymising' }))
    expect(await screen.findByLabelText('Type the employee number to confirm')).toBeVisible()
    expect(backend.writes.filter((w) => w.path.endsWith('/anonymise'))).toEqual([])
  })
})
