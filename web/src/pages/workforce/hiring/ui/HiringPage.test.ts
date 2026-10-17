import userEvent from '@testing-library/user-event'
import { screen, waitFor, within } from '@testing-library/vue'
import { describe, expect, it } from 'vitest'

import type { HiringPlan } from '@/entities/workforce/hiring-plan'
import { backend } from '@/test/fake-backend'
import { openScheduling, seedScheduling } from '@/test/open-scheduling'

const months = ['2031-03-01', '2031-04-01', '2031-05-01', '2031-06-01']
const plan = (over: Partial<HiringPlan> = {}): HiringPlan => ({
  id: 1,
  name: 'FY plan',
  startMonth: '2031-03-01',
  incumbents: 100,
  attritionPctPerMonth: 2,
  ramp: [0, 0.5, 1],
  costPerPersonMonth: 20000,
  totalHires: 12,
  shortfallMonths: 2,
  unavoidableMonths: 1,
  totalCostRands: 8000000,
  rows: months.map((month, i) => ({
    month,
    required: 110,
    headcount: 100 + i,
    hires: i === 0 ? 12 : 0,
    effective: 98 + i * 3,
    gap: i === 0 ? -12 : i === 3 ? 2 : -1,
    unavoidable: i === 0,
    costRands: (100 + i) * 20000,
  })),
  ...over,
})

async function open(role = 'planner', plans: HiringPlan[] = [plan()]) {
  seedScheduling()
  backend.hiringPlans = plans
  return openScheduling('/hiring', role)
}

describe('the hiring plan', () => {
  it('shows what to hire, how many months are short and what it costs', async () => {
    await open()
    expect(await screen.findByTestId('total-hires')).toHaveTextContent('12')
    expect(screen.getByTestId('short-months')).toHaveTextContent('2')
    expect(screen.getByTestId('summary')).toHaveTextContent('1 too soon for any hire to help')
    expect(screen.getByTestId('total-cost')).toHaveTextContent(/R\s*8\s?000\s?000/)
  })

  it('marks a shortfall and says when no hire could have prevented it', async () => {
    // Failure caught: a planner told to hire for a month that nobody could arrive in time for.
    await open()
    const first = await screen.findByTestId('month-2031-03-01')
    expect(within(first).getByTestId('gap')).toHaveTextContent('-12')
    expect(first).toHaveTextContent('too soon to hire for')
    const last = screen.getByTestId('month-2031-06-01')
    expect(within(last).getByTestId('gap')).toHaveTextContent('+2')
    expect(last).not.toHaveTextContent('too soon')
  })

  it('shows an executive the plan without any rands and without a way to change it', async () => {
    // Failure caught: a cost per person shown to a role kept away from pay.
    await open('executive', [
      plan({
        costPerPersonMonth: null,
        totalCostRands: null,
        rows: plan().rows.map((r) => ({ ...r, costRands: null })),
      }),
    ])
    await screen.findByTestId('total-hires')
    expect(screen.queryByTestId('total-cost')).toBeNull()
    expect(screen.queryByRole('columnheader', { name: 'Cost' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'New plan' })).toBeNull()
    expect(screen.queryByText('Edit these inputs')).toBeNull()
  })

  it('says so when there is no plan yet', async () => {
    await open('planner', [])
    expect(await screen.findByTestId('no-plans')).toBeVisible()
  })

  it.each(['agent', 'lead', 'customer_ops'])('keeps %s out', async (role) => {
    await open(role)
    expect(
      await screen.findByRole('heading', { name: "You don't have access to this page" }),
    ).toBeVisible()
  })
})

describe('making and changing a plan', () => {
  it('sends the numbers as numbers, with the first of the month and the CSRF token', async () => {
    const user = userEvent.setup()
    await open('planner', [])
    await user.click(await screen.findByRole('button', { name: 'New plan' }))
    const form = await screen.findByRole('form', { name: 'Make a hiring plan' })
    await user.type(within(form).getByLabelText('Name'), 'Next year')
    await user.type(within(form).getByLabelText('People employed now'), '100')
    await user.clear(within(form).getByLabelText('Leave each month (%)'))
    await user.type(within(form).getByLabelText('Leave each month (%)'), '1.5')
    await user.clear(within(form).getByLabelText(/How productive a new hire is/))
    await user.type(within(form).getByLabelText(/How productive a new hire is/), '0, 0.5, 1')
    await user.type(
      within(form).getByLabelText(/People needed each month/),
      '100, 100, 100, 100, 100, 100, 110, 110, 110, 110, 110, 110',
    )
    await user.type(within(form).getByLabelText(/Cost of one person/), '20000')
    await user.click(within(form).getByRole('button', { name: 'Make plan' }))
    await waitFor(() => expect(backend.writes).toHaveLength(1))
    expect(backend.writes[0]?.body).toMatchObject({
      name: 'Next year',
      incumbents: 100,
      attritionPctPerMonth: 1.5,
      ramp: [0, 0.5, 1],
      required: [100, 100, 100, 100, 100, 100, 110, 110, 110, 110, 110, 110],
      costPerPersonMonth: 20000,
    })
    expect(backend.writes[0]?.body).toMatchObject({ startMonth: expect.stringMatching(/-01$/) })
    expect(backend.writes[0]).toMatchObject({ method: 'POST', csrf: 'test-csrf-token' })
  })

  it('shows why a plan was refused', async () => {
    const user = userEvent.setup()
    await open('planner', [])
    backend.nextProblem = {
      status: 422,
      code: 'hiring.invalid',
      title: 'Hiring plan refused',
      detail: 'A plan covers 12 to 18 months.',
    }
    await user.click(await screen.findByRole('button', { name: 'New plan' }))
    const form = await screen.findByRole('form', { name: 'Make a hiring plan' })
    await user.type(within(form).getByLabelText('Name'), 'Short')
    await user.type(within(form).getByLabelText(/People needed each month/), '100')
    await user.click(within(form).getByRole('button', { name: 'Make plan' }))
    expect(await screen.findByTestId('plan-error')).toHaveTextContent('12 to 18 months')
  })

  it('edits a plan with its needs filled in, and deletes one', async () => {
    const user = userEvent.setup()
    await open()
    await user.click(await screen.findByText('Edit these inputs'))
    const form = await screen.findByRole('form', { name: 'Change this hiring plan' })
    expect(within(form).getByLabelText(/People needed each month/)).toHaveValue(
      '110, 110, 110, 110',
    )
    await user.click(within(form).getByRole('button', { name: 'Save changes' }))
    await waitFor(() => expect(backend.writes).toHaveLength(1))
    expect(backend.writes[0]).toMatchObject({
      method: 'PUT',
      path: '/api/v1/capacity/hiring-plans/1',
    })
    await user.click(await screen.findByRole('button', { name: /^Delete the plan FY plan/ }))
    await waitFor(() => expect(backend.writes).toHaveLength(2))
    expect(backend.writes[1]).toMatchObject({
      method: 'DELETE',
      path: '/api/v1/capacity/hiring-plans/1',
    })
  })
})
