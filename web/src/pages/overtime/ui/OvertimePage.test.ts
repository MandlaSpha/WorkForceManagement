import userEvent from '@testing-library/user-event'
import { screen, waitFor, within } from '@testing-library/vue'
import { describe, expect, it } from 'vitest'

import type { Overtime, OvertimeSummary, PayStatus, Standby } from '@/entities/overtime'
import { backend } from '@/test/fake-backend'
import { openScheduling, seedScheduling } from '@/test/open-scheduling'

const overtime = (over: Partial<Overtime> = {}): Overtime => ({
  id: 1,
  employeeId: 7,
  employee: 'Sam Planner',
  empNo: 'E001',
  day: '2099-05-27',
  startTime: '18:00:00',
  endTime: '20:30:00',
  minutes: 150,
  reason: 'Month end',
  status: 'pending',
  kind: 'weekday',
  costRands: 375,
  costMissing: false,
  mine: false,
  workedMinutes: null,
  paidMinutes: null,
  extraMinutes: 0,
  workedCostRands: null,
  ...over,
})

async function open(role = 'planner', rows: Overtime[] = [overtime()]) {
  seedScheduling()
  backend.overtime = rows
  backend.pay = [
    {
      employeeId: 7,
      employee: 'Sam Planner',
      empNo: 'E001',
      hasSalary: true,
      ordinarilyWorksSundays: false,
    },
    {
      employeeId: 8,
      employee: 'Alex Agent',
      empNo: 'E002',
      hasSalary: false,
      ordinarilyWorksSundays: false,
    },
  ] as PayStatus[]
  return openScheduling('/overtime', role)
}

describe('overtime requests', () => {
  it('shows who, when, the kind of day, the cost in rands and the status', async () => {
    await open()
    const row = await screen.findByTestId('overtime-1')
    expect(row).toHaveTextContent('Sam Planner')
    expect(row).toHaveTextContent('Month end')
    expect(row).toHaveTextContent('18:00 to 20:30 (2h 30m)')
    expect(row).toHaveTextContent('Weekday')
    expect(within(row).getByTestId('cost')).toHaveTextContent(/R\s*375[.,]00/)
    expect(row).toHaveTextContent('Waiting')
  })

  it('says a missing salary is missing, not nothing', async () => {
    // Failure caught: an unpriced request shown as R 0.00.
    await open('planner', [overtime({ costRands: null, costMissing: true })])
    expect(await screen.findByTestId('cost')).toHaveTextContent('No salary on file')
  })

  it('names the kind of day', async () => {
    await open('planner', [
      overtime({ id: 1, kind: 'sunday' }),
      overtime({ id: 2, kind: 'holiday' }),
    ])
    expect(await screen.findByTestId('overtime-1')).toHaveTextContent('Sunday')
    expect(screen.getByTestId('overtime-2')).toHaveTextContent('Public holiday')
  })

  it('says so when there is none', async () => {
    await open('planner', [])
    expect(await screen.findByTestId('no-overtime')).toBeVisible()
  })

  it('filters by status through the API', async () => {
    const user = userEvent.setup()
    await open()
    await screen.findByTestId('overtime-1')
    await user.selectOptions(screen.getByLabelText('Show'), 'Waiting')
    await waitFor(() => expect(backend.overtimeQueries).toContain('pending'))
  })
})

describe('asking for overtime', () => {
  it('sends the person, day and times with the CSRF token', async () => {
    const user = userEvent.setup()
    await open()
    const form = await screen.findByRole('form', { name: 'Ask for overtime' })
    await within(form).findByRole('option', { name: 'Alex Agent' })
    await user.selectOptions(within(form).getByLabelText('Person'), 'Alex Agent')
    await user.type(within(form).getByLabelText('Day'), '2099-06-02')
    await user.type(within(form).getByLabelText('Reason (optional)'), 'Backlog')
    await user.click(within(form).getByRole('button', { name: 'Ask for overtime' }))
    await waitFor(() => expect(backend.writes).toHaveLength(1))
    expect(backend.writes[0]).toEqual({
      method: 'POST',
      path: '/api/v1/overtime/requests',
      body: {
        employeeId: 10,
        day: '2099-06-02',
        startTime: '18:00',
        endTime: '20:00',
        reason: 'Backlog',
      },
      csrf: 'test-csrf-token',
    })
    expect(await screen.findByTestId('ask-result')).toBeVisible()
  })

  it('cannot be sent without a person and a day', async () => {
    await open()
    const form = await screen.findByRole('form', { name: 'Ask for overtime' })
    expect(within(form).getByRole('button', { name: 'Ask for overtime' })).toBeDisabled()
  })

  it('shows why it was refused', async () => {
    const user = userEvent.setup()
    await open()
    backend.nextProblem = {
      status: 409,
      code: 'overtime.rest_period',
      title: 'Overtime refused',
      detail: 'This would leave less than 11 hours of rest.',
    }
    const form = await screen.findByRole('form', { name: 'Ask for overtime' })
    await within(form).findByRole('option', { name: 'Alex Agent' })
    await user.selectOptions(within(form).getByLabelText('Person'), 'Alex Agent')
    await user.type(within(form).getByLabelText('Day'), '2099-06-02')
    await user.click(within(form).getByRole('button', { name: 'Ask for overtime' }))
    expect(await screen.findByTestId('ask-error')).toHaveTextContent('11 hours of rest')
  })
})

describe('deciding and cancelling', () => {
  it('approves and rejects with the CSRF token', async () => {
    const user = userEvent.setup()
    await open('planner', [
      overtime({ id: 1 }),
      overtime({ id: 2, startTime: '08:00:00', endTime: '09:00:00' }),
    ])
    await user.click((await screen.findAllByRole('button', { name: /^Approve overtime for/ }))[0]!)
    await waitFor(() => expect(backend.writes).toHaveLength(1))
    expect(backend.writes[0]).toMatchObject({
      method: 'POST',
      path: '/api/v1/overtime/requests/1/approve',
      csrf: 'test-csrf-token',
    })
    await user.click(await screen.findByRole('button', { name: /^Reject overtime for/ }))
    await waitFor(() => expect(backend.writes).toHaveLength(2))
    expect(backend.writes[1]?.path).toBe('/api/v1/overtime/requests/2/reject')
  })

  it('does not offer to decide your own overtime', async () => {
    await open('planner', [overtime({ mine: true })])
    expect(await screen.findByText('Somebody else decides your overtime.')).toBeVisible()
    expect(screen.queryByRole('button', { name: /^Approve overtime/ })).toBeNull()
  })

  it('offers to cancel a waiting or future approved request, never a finished one', async () => {
    await open('planner', [
      overtime({ id: 1 }),
      overtime({ id: 2, status: 'approved' }),
      overtime({ id: 3, status: 'approved', day: '2020-01-01' }),
      overtime({ id: 4, status: 'rejected' }),
    ])
    await screen.findByTestId('overtime-1')
    expect(
      within(screen.getByTestId('overtime-1')).getByRole('button', { name: /Cancel/ }),
    ).toBeVisible()
    expect(
      within(screen.getByTestId('overtime-2')).getByRole('button', { name: /Cancel/ }),
    ).toBeVisible()
    expect(
      within(screen.getByTestId('overtime-3')).queryByRole('button', { name: /Cancel/ }),
    ).toBeNull()
    expect(
      within(screen.getByTestId('overtime-4')).queryByRole('button', { name: /Cancel/ }),
    ).toBeNull()
  })

  it('shows why a decision was refused', async () => {
    const user = userEvent.setup()
    await open()
    backend.nextProblem = {
      status: 409,
      code: 'overtime.on_leave',
      title: 'Overtime refused',
      detail: 'This person is on approved leave that day.',
    }
    await user.click(await screen.findByRole('button', { name: /^Approve overtime for/ }))
    expect(await screen.findByRole('alert')).toHaveTextContent('approved leave')
  })
})

describe('who sees what', () => {
  it('lets a lead ask and cancel but never decide, and never shows a cost', async () => {
    await open('lead', [overtime({ costRands: null })])
    await screen.findByTestId('overtime-1')
    expect(screen.getByRole('form', { name: 'Ask for overtime' })).toBeVisible()
    expect(screen.queryByRole('columnheader', { name: 'Cost' })).toBeNull()
    expect(screen.queryByTestId('cost')).toBeNull()
    expect(screen.queryByRole('button', { name: /^Approve overtime/ })).toBeNull()
    expect(screen.getByRole('button', { name: /^Cancel overtime/ })).toBeVisible()
    expect(screen.queryByRole('tab', { name: 'Pay' })).toBeNull()
  })

  it.each(['agent', 'executive', 'customer_ops'])('keeps %s out', async (role) => {
    await open(role)
    expect(
      await screen.findByRole('heading', { name: "You don't have access to this page" }),
    ).toBeVisible()
  })

  it('gives a planner no Pay tab', async () => {
    await open('planner')
    await screen.findByTestId('overtime-1')
    expect(screen.queryByRole('tab', { name: 'Pay' })).toBeNull()
  })
})

describe('pay (admin only)', () => {
  async function openPay() {
    const user = userEvent.setup()
    await open('admin')
    await user.click(await screen.findByRole('tab', { name: 'Pay' }))
    await screen.findByTestId('pay-note')
    return user
  }

  it('says who has a salary on file but never shows one', async () => {
    // Failure caught: a salary figure rendered back to the screen.
    await openPay()
    expect(screen.getByTestId('pay-E001')).toHaveTextContent('Salary on file')
    expect(screen.getByTestId('pay-E002')).toHaveTextContent('No salary on file')
    expect(screen.getByLabelText('Monthly salary for Sam Planner (R)')).toHaveValue(null)
  })

  it('sends the salary as a number and never clears by accident', async () => {
    const user = await openPay()
    await user.type(screen.getByLabelText('Monthly salary for Alex Agent (R)'), '17332.5')
    const form = screen.getByRole('form', { name: 'Pay for Alex Agent' })
    await user.click(within(form).getByRole('button', { name: 'Save pay' }))
    await waitFor(() => expect(backend.writes).toHaveLength(1))
    expect(backend.writes[0]).toEqual({
      method: 'PUT',
      path: '/api/v1/overtime/pay/8',
      body: { monthlySalary: 17332.5, ordinarilyWorksSundays: false, clear: false },
      csrf: 'test-csrf-token',
    })
  })

  it('changes only the Sunday flag when the salary box is left empty', async () => {
    // Failure caught: re-saving with an empty box wiping the salary on file.
    const user = await openPay()
    const form = screen.getByRole('form', { name: 'Pay for Sam Planner' })
    await user.click(within(form).getByLabelText('Ordinarily works Sundays'))
    await user.click(within(form).getByRole('button', { name: 'Save pay' }))
    await waitFor(() => expect(backend.writes).toHaveLength(1))
    expect(backend.writes[0]?.body).toEqual({
      monthlySalary: null,
      ordinarilyWorksSundays: true,
      clear: false,
    })
  })

  it('removes a salary only through its own button, and only when there is one', async () => {
    const user = await openPay()
    const sam = screen.getByRole('form', { name: 'Pay for Sam Planner' })
    const alex = screen.getByRole('form', { name: 'Pay for Alex Agent' })
    expect(within(alex).queryByRole('button', { name: 'Remove salary' })).toBeNull()
    expect(within(alex).getByRole('button', { name: 'Save pay' })).toBeDisabled()
    await user.click(within(sam).getByRole('button', { name: 'Remove salary' }))
    await waitFor(() => expect(backend.writes).toHaveLength(1))
    expect(backend.writes[0]?.body).toMatchObject({ clear: true })
  })
})

const standbyOf = (over: Partial<Standby> = {}): Standby => ({
  id: 1,
  employeeId: 7,
  employee: 'Sam Planner',
  empNo: 'E001',
  day: '2099-05-27',
  status: 'booked',
  allowanceRands: 150,
  callOutMinutes: null,
  callOutCostRands: null,
  callOutCostMissing: false,
  mine: false,
  ...over,
})

const summaryOf = (over: Partial<OvertimeSummary> = {}): OvertimeSummary => ({
  month: '2026-10-01',
  approved: 3,
  approvedMinutes: 360,
  unreconciled: 0,
  workedMinutes: 300,
  extraMinutes: 0,
  overtimeCostRands: 900,
  missingPrices: 0,
  standbyDays: 4,
  standbyAllowancesRands: 600,
  callOutMinutes: 90,
  callOutCostRands: 225,
  totalRands: 1725,
  budgetRands: 2000,
  standbyAllowanceRands: 150,
  ...over,
})

describe('reconciling worked time (OT-03)', () => {
  it('records the minutes really worked on approved overtime that has happened', async () => {
    const user = userEvent.setup()
    await open('planner', [overtime({ status: 'approved', day: '2020-01-01' })])
    const form = await screen.findByRole('form', { name: /Record worked time for Sam Planner/ })
    await user.type(within(form).getByLabelText('Minutes worked'), '90')
    await user.click(within(form).getByRole('button', { name: 'Record' }))
    await waitFor(() => expect(backend.writes).toHaveLength(1))
    expect(backend.writes[0]).toMatchObject({
      method: 'POST',
      path: '/api/v1/overtime/requests/1/worked',
      body: { minutes: 90 },
      csrf: 'test-csrf-token',
    })
    expect(await screen.findByTestId('worked')).toHaveTextContent('1h 30m worked')
  })

  it('offers no way to record time that has not happened yet', async () => {
    // Failure caught: worked time typed in for a day still to come.
    await open('planner', [overtime({ status: 'approved', day: '2099-01-01' })])
    await screen.findByTestId('overtime-1')
    expect(screen.queryByRole('form', { name: /Record worked time/ })).toBeNull()
  })

  it('says what was worked beyond the approval and that it is not paid', async () => {
    await open('planner', [
      overtime({
        status: 'approved',
        day: '2020-01-01',
        workedMinutes: 180,
        paidMinutes: 150,
        extraMinutes: 30,
        workedCostRands: 375,
      }),
    ])
    expect(await screen.findByTestId('extra')).toHaveTextContent('0h 30m beyond what was approved')
    expect(screen.getByTestId('worked-cost')).toHaveTextContent(/Paid R\s*375[.,]00/)
  })

  it('does not let a person record their own overtime', async () => {
    await open('planner', [overtime({ status: 'approved', day: '2020-01-01', mine: true })])
    expect(await screen.findByText('Somebody else records your overtime.')).toBeVisible()
    expect(screen.queryByRole('form', { name: /Record worked time/ })).toBeNull()
  })

  it('shows a lead the worked time and no rands', async () => {
    await open('lead', [
      overtime({
        status: 'approved',
        day: '2020-01-01',
        workedMinutes: 120,
        paidMinutes: 120,
        costRands: null,
        workedCostRands: null,
      }),
    ])
    expect(await screen.findByTestId('worked')).toHaveTextContent('2h 00m worked')
    expect(screen.queryByTestId('worked-cost')).toBeNull()
    expect(screen.queryByRole('form', { name: /Record worked time/ })).toBeNull()
  })
})

describe('standby (OT-02)', () => {
  async function openStandby(role: string, rows: Standby[]) {
    const user = userEvent.setup()
    await open(role)
    backend.standby = rows
    await user.click(await screen.findByRole('tab', { name: 'Standby' }))
    return user
  }

  it('lists who is on standby with the allowance for those who see pay', async () => {
    await openStandby('planner', [standbyOf()])
    const row = await screen.findByTestId('standby-1')
    expect(row).toHaveTextContent('Sam Planner')
    expect(row).toHaveTextContent(/allowance R\s*150[.,]00/)
  })

  it('shows a lead the rota but no rands', async () => {
    // Failure caught: a lead reading what standby pays.
    await openStandby('lead', [standbyOf({ allowanceRands: null })])
    const row = await screen.findByTestId('standby-1')
    expect(row).not.toHaveTextContent('allowance')
    expect(row).not.toHaveTextContent('R')
  })

  it('books somebody with the CSRF token', async () => {
    const user = await openStandby('planner', [])
    const form = await screen.findByRole('form', { name: 'Put somebody on standby' })
    await within(form).findByRole('option', { name: 'Alex Agent' })
    await user.selectOptions(within(form).getByLabelText('Person'), 'Alex Agent')
    await user.type(within(form).getByLabelText('Day'), '2099-06-02')
    await user.click(within(form).getByRole('button', { name: 'Put on standby' }))
    await waitFor(() => expect(backend.writes).toHaveLength(1))
    expect(backend.writes[0]).toEqual({
      method: 'POST',
      path: '/api/v1/overtime/standby',
      body: { employeeId: 10, day: '2099-06-02' },
      csrf: 'test-csrf-token',
    })
  })

  it('shows why a booking was refused', async () => {
    const user = await openStandby('planner', [])
    backend.nextProblem = {
      status: 409,
      code: 'standby.already_booked',
      title: 'Overtime refused',
      detail: 'This person is already on standby that day.',
    }
    const form = await screen.findByRole('form', { name: 'Put somebody on standby' })
    await within(form).findByRole('option', { name: 'Alex Agent' })
    await user.selectOptions(within(form).getByLabelText('Person'), 'Alex Agent')
    await user.type(within(form).getByLabelText('Day'), '2099-06-02')
    await user.click(within(form).getByRole('button', { name: 'Put on standby' }))
    expect(await screen.findByTestId('standby-error')).toHaveTextContent('already on standby')
  })

  it('records a call-out only once the day has come, and cancels only what is ahead', async () => {
    const user = await openStandby('planner', [
      standbyOf({ id: 1, day: '2020-01-01' }),
      standbyOf({ id: 2, day: '2099-01-01' }),
    ])
    const past = await screen.findByTestId('standby-1')
    const future = screen.getByTestId('standby-2')
    expect(within(past).getByRole('form', { name: /Record a call-out/ })).toBeVisible()
    expect(within(past).queryByRole('button', { name: /Cancel standby/ })).toBeNull()
    expect(within(future).queryByRole('form', { name: /Record a call-out/ })).toBeNull()
    await user.click(within(future).getByRole('button', { name: /Cancel standby/ }))
    await waitFor(() => expect(backend.writes).toHaveLength(1))
    expect(backend.writes[0]?.path).toBe('/api/v1/overtime/standby/2/cancel')
  })
})

describe('the month, against the budget', () => {
  async function openMonth(role: string, summary: OvertimeSummary) {
    const user = userEvent.setup()
    await open(role)
    backend.summary = summary
    await user.click(await screen.findByRole('tab', { name: 'Month' }))
    return user
  }

  it('adds overtime, standby and call-outs and says what is left of the budget', async () => {
    await openMonth('planner', summaryOf())
    expect(await screen.findByTestId('total-cost')).toHaveTextContent(/R\s*1\s?725[.,]00/)
    expect(screen.getByTestId('budget-line')).toHaveTextContent(/R\s*275[.,]00 left/)
  })

  it('says by how much the budget is exceeded', async () => {
    await openMonth('planner', summaryOf({ totalRands: 2300, budgetRands: 2000 }))
    expect(await screen.findByTestId('budget-line')).toHaveTextContent(/R\s*300[.,]00 over/)
  })

  it('says when there is no budget instead of showing zero', async () => {
    await openMonth('planner', summaryOf({ budgetRands: null }))
    expect(await screen.findByTestId('budget-line')).toHaveTextContent('No budget set')
  })

  it('warns about what is not yet reconciled, unpaid extra time and unpriced requests', async () => {
    // Failure caught: a total presented as final when part of it is only the approved amount.
    await openMonth('planner', summaryOf({ unreconciled: 2, extraMinutes: 45, missingPrices: 1 }))
    expect(await screen.findByTestId('unreconciled')).toHaveTextContent(/2 approved requests have/)
    expect(screen.getByTestId('extra-minutes')).toHaveTextContent('45 minutes')
    expect(screen.getByTestId('missing-prices')).toHaveTextContent('no salary on file')
  })

  it('gives only the admin the allowance and budget forms', async () => {
    await openMonth('planner', summaryOf())
    await screen.findByTestId('total-cost')
    expect(screen.queryByRole('form', { name: 'Standby allowance' })).toBeNull()
  })

  it('lets the admin set the allowance and the budget for the month shown', async () => {
    const user = await openMonth('admin', summaryOf())
    const allowance = await screen.findByRole('form', { name: 'Standby allowance' })
    await user.type(within(allowance).getByLabelText(/Allowance for a day/), '175')
    await user.click(within(allowance).getByRole('button', { name: 'Save allowance' }))
    await waitFor(() => expect(backend.writes).toHaveLength(1))
    expect(backend.writes[0]).toMatchObject({
      method: 'PUT',
      path: '/api/v1/overtime/rates',
      body: { standbyAllowance: 175 },
    })
    const budget = screen.getByRole('form', { name: 'Budget for the month' })
    await user.type(within(budget).getByLabelText(/Budget for this month/), '5000')
    await user.click(within(budget).getByRole('button', { name: 'Save budget' }))
    await waitFor(() => expect(backend.writes).toHaveLength(2))
    expect(backend.writes[1]?.path).toMatch(/\/api\/v1\/overtime\/budget\/\d{4}-\d{2}-01$/)
    expect(backend.writes[1]?.body).toEqual({ amount: 5000 })
  })

  it('links to the payroll file for the month shown', async () => {
    await openMonth('planner', summaryOf())
    const link = await screen.findByTestId('payroll-link')
    expect(link).toHaveAttribute(
      'href',
      expect.stringMatching(/\/api\/v1\/overtime\/payroll\.csv\?month=\d{4}-\d{2}-01$/),
    )
    expect(link).toHaveAttribute('download')
  })

  it('has no Month tab for a lead', async () => {
    await open('lead')
    await screen.findByTestId('overtime-1')
    expect(screen.queryByRole('tab', { name: 'Month' })).toBeNull()
  })
})
