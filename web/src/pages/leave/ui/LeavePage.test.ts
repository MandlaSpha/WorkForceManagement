import userEvent from '@testing-library/user-event'
import { screen, waitFor, within } from '@testing-library/vue'
import { describe, expect, it } from 'vitest'

import { backend } from '@/test/fake-backend'
import { balancesOf, impactOf, LEAVE_TYPES, requestOf } from '@/test/leave-fixtures'
import { openScheduling, seedScheduling } from '@/test/open-scheduling'

async function open(role = 'agent', requests = [requestOf()]) {
  seedScheduling()
  backend.leaveTypes = LEAVE_TYPES
  backend.balances = balancesOf()
  backend.leaveRequests = requests
  backend.impact = impactOf()
  return openScheduling('/leave', role)
}

describe('my leave', () => {
  it('shows how many days are left of each kind, and that unpaid leave has no limit', async () => {
    await open()
    expect(await screen.findByTestId('balance-annual')).toHaveTextContent('11 of 15 days left')
    expect(screen.getByTestId('balance-annual')).toHaveTextContent('2 taken, 2 waiting')
    expect(screen.getByTestId('balance-sick')).toHaveTextContent('10 of 10 days left')
    expect(screen.getByTestId('balance-unpaid')).toHaveTextContent('no limit')
  })

  it('says the entitlements are BCEA defaults until an admin confirms them', async () => {
    await open()
    expect(await screen.findByTestId('defaults-notice')).toHaveTextContent(/BCEA\) defaults/)
  })

  it('stays quiet about it once every kind is confirmed', async () => {
    seedScheduling()
    backend.leaveTypes = LEAVE_TYPES.map((t) => ({ ...t, confirmed: true }))
    backend.balances = balancesOf()
    await openScheduling('/leave', 'agent')
    await screen.findByTestId('balance-annual')
    expect(screen.queryByTestId('defaults-notice')).toBeNull()
  })

  it('says so when the person is not on the employee list, and offers no form', async () => {
    seedScheduling()
    backend.leaveTypes = LEAVE_TYPES
    backend.noEmployeeRecord = true
    await openScheduling('/leave', 'agent')
    expect(await screen.findByTestId('no-record')).toHaveTextContent(/not on the employee list/)
    expect(screen.queryByRole('form', { name: 'Ask for leave' })).toBeNull()
  })

  it('lists only my own requests, with their status', async () => {
    seedScheduling()
    backend.leaveTypes = LEAVE_TYPES
    backend.balances = balancesOf()
    backend.leaveRequests = [
      requestOf({ id: 1, status: 'approved' }),
      requestOf({ id: 2, mine: false, employee: 'Sam Planner' }),
    ]
    await openScheduling('/leave', 'agent')
    const table = await screen.findByTestId('my-requests')
    expect(within(table).getAllByRole('row')).toHaveLength(2) // the header and one request
    expect(within(table).getByText('Approved')).toBeVisible()
    expect(within(table).getByText('Mon 25 May to Tue 26 May')).toBeVisible()
  })
})

describe('asking for leave', () => {
  it('sends the kind and the dates with the CSRF token, and says how many days it was', async () => {
    const user = userEvent.setup()
    await open()
    const form = await screen.findByRole('form', { name: 'Ask for leave' })

    await within(form).findByRole('option', { name: 'Sick leave' }) // the kinds load first
    await user.selectOptions(within(form).getByLabelText('Kind of leave'), 'Sick leave')
    await user.clear(within(form).getByLabelText('First day'))
    await user.type(within(form).getByLabelText('First day'), '2099-06-01')
    await user.clear(within(form).getByLabelText('Last day'))
    await user.type(within(form).getByLabelText('Last day'), '2099-06-02')
    await user.click(within(form).getByRole('button', { name: 'Ask for leave' }))

    await waitFor(() => expect(backend.writes).toHaveLength(1))
    expect(backend.writes[0]).toEqual({
      method: 'POST',
      path: '/api/v1/people/leave/requests',
      body: { leaveTypeId: 2, startDate: '2099-06-01', endDate: '2099-06-02' },
      csrf: 'test-csrf-token',
    })
    expect(await screen.findByTestId('apply-result')).toHaveTextContent('Asked for 2 working days')
  })

  it('shows why a request was refused', async () => {
    const user = userEvent.setup()
    await open()
    backend.nextProblem = {
      status: 422,
      code: 'leave.insufficient_balance',
      title: 'Leave refused',
      detail: 'Sick leave has 0.0 days left in 2026; 1 were asked for.',
    }
    const form = await screen.findByRole('form', { name: 'Ask for leave' })
    await user.click(within(form).getByRole('button', { name: 'Ask for leave' }))
    expect(await screen.findByTestId('apply-error')).toHaveTextContent(/0.0 days left/)
  })
})

describe('cancelling', () => {
  it('offers it for a waiting request and for approved leave still to come', async () => {
    seedScheduling()
    backend.leaveTypes = LEAVE_TYPES
    backend.balances = balancesOf()
    backend.leaveRequests = [
      requestOf({ id: 1, status: 'pending' }),
      requestOf({ id: 2, status: 'approved' }),
      requestOf({ id: 3, status: 'approved', startDate: '2020-01-06', endDate: '2020-01-07' }),
      requestOf({ id: 4, status: 'rejected' }),
      requestOf({ id: 5, status: 'cancelled' }),
    ]
    await openScheduling('/leave', 'agent')
    await screen.findByTestId('my-requests')
    const has = (id: number) => within(screen.getByTestId(`mine-${id}`)).queryByRole('button')
    expect(has(1)).not.toBeNull()
    expect(has(2)).not.toBeNull()
    expect(has(3)).toBeNull() // already taken
    expect(has(4)).toBeNull()
    expect(has(5)).toBeNull()
  })

  it('sends the cancel with the CSRF token and says what went back on the roster', async () => {
    const user = userEvent.setup()
    seedScheduling()
    backend.leaveTypes = LEAVE_TYPES
    backend.balances = balancesOf()
    backend.leaveRequests = [requestOf({ id: 2, status: 'approved' })]
    backend.decision = { shiftsCleared: 0, shiftsRestored: 2, shiftsNotRestored: 1 }
    await openScheduling('/leave', 'agent')

    await user.click(await screen.findByRole('button', { name: /Cancel leave Mon 25 May/ }))

    await waitFor(() => expect(backend.writes).toHaveLength(1))
    expect(backend.writes[0]).toMatchObject({
      method: 'POST',
      path: '/api/v1/people/leave/requests/2/cancel',
      csrf: 'test-csrf-token',
    })
    expect(await screen.findByTestId('decision-result')).toHaveTextContent(
      'Cancelled leave for Alex Agent: 2 shifts put back on the roster, 1 could not be put back.',
    )
  })
})

describe('approvals', () => {
  const asLead = async (requests = [requestOf()]) => {
    await open('lead', requests)
    const user = userEvent.setup()
    await user.click(await screen.findByRole('tab', { name: 'Approvals' }))
    return user
  }

  it('lists the requests waiting for a decision, asking for exactly those', async () => {
    await asLead()
    const item = await screen.findByTestId('request-1')
    expect(item).toHaveTextContent('Alex Agent')
    expect(item).toHaveTextContent('Annual leave: Mon 25 May to Tue 26 May, 2 days')
    expect(backend.requestQueries).toContain('?status=pending')
  })

  it('shows what approving would do to coverage before anyone approves', async () => {
    const user = await asLead()
    backend.leaveRequests = [requestOf({ mine: false })]

    await user.click(
      await screen.findByRole('button', { name: /Show coverage impact for Alex Agent/ }),
    )

    const impact = await screen.findByTestId('impact')
    expect(impact).toHaveTextContent('Takes 2 shifts (17h) off the roster.')
    expect(impact).toHaveTextContent('17 half-hours that are covered now would be short.')
    expect(backend.writes).toEqual([]) // looking decided nothing
  })

  it('says when there is no impact because the person is not rostered', async () => {
    const user = await asLead()
    backend.impact = impactOf({ shifts: 0, hours: 0, intervals: 0, newlyUnder: 0 })
    await user.click(await screen.findByRole('button', { name: /Show coverage impact/ }))
    expect(await screen.findByTestId('impact')).toHaveTextContent(/nothing changes in the roster/)
  })

  it('approves with the CSRF token and says how many shifts came off the roster', async () => {
    const user = await asLead([requestOf({ mine: false })])
    backend.decision = { shiftsCleared: 2, shiftsRestored: 0, shiftsNotRestored: 0 }

    await user.click(await screen.findByRole('button', { name: 'Approve leave for Alex Agent' }))

    await waitFor(() => expect(backend.writes).toHaveLength(1))
    expect(backend.writes[0]).toMatchObject({
      method: 'POST',
      path: '/api/v1/people/leave/requests/1/approve',
      csrf: 'test-csrf-token',
    })
    expect(await screen.findByTestId('decision-result')).toHaveTextContent(
      'Approved leave for Alex Agent: 2 shifts taken off the roster.',
    )
    // The request has left the waiting list, and the outcome is still on screen.
    await waitFor(() => expect(screen.queryByTestId('request-1')).toBeNull())
    expect(screen.getByTestId('decision-result')).toBeVisible()
  })

  it('rejects', async () => {
    const user = await asLead([requestOf({ mine: false })])
    await user.click(await screen.findByRole('button', { name: 'Reject leave for Alex Agent' }))
    await waitFor(() =>
      expect(backend.writes[0]?.path).toBe('/api/v1/people/leave/requests/1/reject'),
    )
    expect(await screen.findByTestId('decision-result')).toHaveTextContent(
      'Rejected leave for Alex Agent.',
    )
  })

  it('gives nobody a way to decide their own request', async () => {
    await asLead()
    const item = await screen.findByTestId('request-1') // requestOf() is mine
    expect(item).toHaveTextContent('Somebody else decides your leave')
    expect(within(item).queryByRole('button', { name: /^Approve/ })).toBeNull()
  })

  it('shows why a decision was refused', async () => {
    const user = await asLead([requestOf({ mine: false })])
    backend.nextProblem = {
      status: 409,
      code: 'leave.not_pending',
      title: 'Leave refused',
      detail: 'This request is already approved.',
    }
    await user.click(await screen.findByRole('button', { name: 'Approve leave for Alex Agent' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/already approved/)
  })

  it('says when nothing is waiting', async () => {
    const user = await asLead([requestOf({ mine: false })])
    await screen.findByTestId('request-1')
    await user.selectOptions(screen.getByLabelText('Show'), 'Rejected')
    expect(await screen.findByTestId('nothing-to-decide')).toBeVisible()
  })
})

describe('entitlements', () => {
  it('lets an admin set the days a year, and confirms them', async () => {
    const user = userEvent.setup()
    await open('admin')
    await user.click(await screen.findByRole('tab', { name: 'Entitlements' }))
    expect(await screen.findByTestId('entitlement-state-1')).toHaveTextContent(
      'BCEA default, not confirmed',
    )

    const input = screen.getByLabelText('Days a year of Annual leave, blank for no limit')
    await user.clear(input)
    await user.type(input, '20')
    await user.click(
      within(screen.getByRole('form', { name: 'Days a year for Annual leave' })).getByRole(
        'button',
        { name: 'Save' },
      ),
    )

    await waitFor(() => expect(backend.writes).toHaveLength(1))
    expect(backend.writes[0]).toEqual({
      method: 'PUT',
      path: '/api/v1/people/leave/types/1',
      body: { daysPerYear: 20 },
      csrf: 'test-csrf-token',
    })
    await waitFor(() =>
      expect(screen.getByTestId('entitlement-state-1')).toHaveTextContent('Confirmed'),
    )
  })

  it('sends a blank as no limit', async () => {
    const user = userEvent.setup()
    await open('admin')
    await user.click(await screen.findByRole('tab', { name: 'Entitlements' }))
    const input = await screen.findByLabelText('Days a year of Annual leave, blank for no limit')
    await user.clear(input)
    await user.click(
      within(screen.getByRole('form', { name: 'Days a year for Annual leave' })).getByRole(
        'button',
        { name: 'Save' },
      ),
    )
    await waitFor(() => expect(backend.writes[0]?.body).toEqual({ daysPerYear: null }))
  })

  it('shows why it was refused', async () => {
    const user = userEvent.setup()
    await open('admin')
    backend.nextProblem = {
      status: 422,
      code: 'leave.entitlement_invalid',
      title: 'Leave refused',
      detail: 'Days a year is between 0 and 366.',
    }
    await user.click(await screen.findByRole('tab', { name: 'Entitlements' }))
    await user.click(
      within(await screen.findByRole('form', { name: 'Days a year for Annual leave' })).getByRole(
        'button',
        { name: 'Save' },
      ),
    )
    expect(await screen.findByTestId('entitlement-error-1')).toHaveTextContent(/0 and 366/)
  })
})

describe('who sees which tab', () => {
  it('gives an agent only their own leave', async () => {
    await open('agent')
    await screen.findByRole('tab', { name: 'My leave' })
    expect(screen.queryByRole('tab', { name: 'Approvals' })).toBeNull()
    expect(screen.queryByRole('tab', { name: 'Entitlements' })).toBeNull()
  })

  it.each(['lead', 'planner'])('gives %s approvals but not entitlements', async (role) => {
    await open(role)
    expect(await screen.findByRole('tab', { name: 'Approvals' })).toBeVisible()
    expect(screen.queryByRole('tab', { name: 'Entitlements' })).toBeNull()
  })

  it('gives an admin all three', async () => {
    await open('admin')
    for (const name of ['My leave', 'Approvals', 'Entitlements']) {
      expect(await screen.findByRole('tab', { name })).toBeVisible()
    }
  })

  it.each(['executive', 'customer_ops'])('does not open for %s', async (role) => {
    await open(role)
    expect(
      await screen.findByRole('heading', { name: "You don't have access to this page" }),
    ).toBeVisible()
  })
})
