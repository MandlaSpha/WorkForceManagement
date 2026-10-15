import userEvent from '@testing-library/user-event'
import { screen, waitFor, within } from '@testing-library/vue'
import { describe, expect, it } from 'vitest'

import type { ContractRow } from '@/entities/contract'
import { queueInfo } from '@/test/forecast-fixtures'
import { backend } from '@/test/fake-backend'
import { openScheduling, seedScheduling } from '@/test/open-scheduling'

const contract = (over: Partial<ContractRow> = {}): ContractRow => ({
  id: 1,
  customerId: 5,
  customer: 'Acme',
  name: 'Gold',
  slTargetPct: 80,
  slThresholdS: 20,
  active: true,
  queues: [{ id: 1, name: 'QueueA' }],
  offered: 1200,
  measuredSlPct: 82.5,
  intervalsKnown: 48,
  underIntervals: 0,
  gap: 0,
  atRisk: false,
  risks: [],
  ...over,
})

async function open(role = 'admin', rows: ContractRow[] = [contract()]) {
  seedScheduling()
  backend.queues = [queueInfo()]
  backend.contracts = rows
  backend.customers = [{ id: 5, name: 'Acme' }]
  return openScheduling('/contracts', role)
}

describe('how each contract is doing', () => {
  it('shows what is promised, what was measured, how the week looks and whether it is at risk', async () => {
    await open('planner', [
      contract({
        id: 2,
        name: 'Silver',
        measuredSlPct: 75,
        underIntervals: 17,
        atRisk: true,
        risks: ['service level 75.0% over the last 28 days is below the 80% promised'],
      }),
    ])
    const row = await screen.findByTestId('contract-2')
    expect(row).toHaveTextContent('Acme')
    expect(row).toHaveTextContent('80% in 20 s')
    expect(row).toHaveTextContent(/75.0% from 1.200 calls/)
    expect(row).toHaveTextContent('17 half-hours short')
    expect(within(row).getByText('At risk')).toBeVisible()
    expect(row).toHaveTextContent('below the 80% promised')
    expect(screen.getByTestId('risk-summary')).toHaveTextContent('1 of 1 contract is at risk')
  })

  it('says which figure is measured and which is modelled', async () => {
    await open('planner')
    expect(await screen.findByTestId('how-measured')).toHaveTextContent(/modelled/)
  })

  it('shows a missing figure as missing, not zero', async () => {
    await open('planner', [contract({ measuredSlPct: null, offered: 0, intervalsKnown: 0 })])
    const row = await screen.findByTestId('contract-1')
    expect(row).toHaveTextContent('No calls in the last 28 days')
    expect(row).toHaveTextContent('No forecast for this week')
    expect(within(row).queryByText('At risk')).toBeNull()
  })

  it('says so when there are no contracts', async () => {
    await open('admin', [])
    expect(await screen.findByTestId('no-contracts')).toBeVisible()
  })

  it('marks an ended contract', async () => {
    await open('planner', [contract({ active: false })])
    expect(await screen.findByTestId('contract-1')).toHaveTextContent('ended')
  })
})

describe('changing contracts', () => {
  it('adds a customer with the CSRF token', async () => {
    const user = userEvent.setup()
    await open('admin')
    await user.type(await screen.findByLabelText('Customer name'), 'Beta Corp')
    await user.click(screen.getByRole('button', { name: 'Add customer' }))
    await waitFor(() => expect(backend.writes).toHaveLength(1))
    expect(backend.writes[0]).toEqual({
      method: 'POST',
      path: '/api/v1/contracts/customers',
      body: { name: 'Beta Corp' },
      csrf: 'test-csrf-token',
    })
  })

  it('adds a contract holding the chosen queues to the numbers typed', async () => {
    const user = userEvent.setup()
    await open('admin', [])
    await user.click(await screen.findByRole('button', { name: 'Add contract' }))
    const form = await screen.findByRole('form', { name: 'Add a contract' })
    await user.type(within(form).getByLabelText('Contract name'), 'Gold')
    await user.clear(within(form).getByLabelText('Service level promised (%)'))
    await user.type(within(form).getByLabelText('Service level promised (%)'), '90')
    await user.clear(within(form).getByLabelText('Within (seconds)'))
    await user.type(within(form).getByLabelText('Within (seconds)'), '30')
    await user.click(await within(form).findByLabelText('QueueA'))
    await user.click(within(form).getByRole('button', { name: 'Add contract' }))

    await waitFor(() => expect(backend.writes).toHaveLength(1))
    // Failure caught: numbers sent as text, or the queue ids dropped.
    expect(backend.writes[0]).toEqual({
      method: 'POST',
      path: '/api/v1/contracts',
      body: {
        customerId: 5,
        name: 'Gold',
        slTargetPct: 90,
        slThresholdS: 30,
        queueIds: [1],
      },
      csrf: 'test-csrf-token',
    })
  })

  it('changes a contract starting from its values, and can end it', async () => {
    const user = userEvent.setup()
    await open('admin')
    await user.click(await screen.findByRole('button', { name: 'Change Acme Gold' }))
    const form = await screen.findByRole('form', { name: 'Change Gold' })
    expect(within(form).getByLabelText('Service level promised (%)')).toHaveValue(80)
    expect(within(form).getByLabelText('QueueA')).toBeChecked()
    await user.click(within(form).getByLabelText(/Active/))
    await user.click(within(form).getByRole('button', { name: 'Save changes' }))

    await waitFor(() => expect(backend.writes).toHaveLength(1))
    expect(backend.writes[0]).toEqual({
      method: 'PUT',
      path: '/api/v1/contracts/1',
      body: { name: 'Gold', slTargetPct: 80, slThresholdS: 20, queueIds: [1], active: false },
      csrf: 'test-csrf-token',
    })
  })

  it('shows why a contract was refused', async () => {
    const user = userEvent.setup()
    await open('admin', [])
    backend.nextProblem = {
      status: 409,
      code: 'contract.queue_taken',
      title: 'Invalid request',
      detail: 'A queue in the list is already under another contract.',
    }
    await user.click(await screen.findByRole('button', { name: 'Add contract' }))
    const form = await screen.findByRole('form', { name: 'Add a contract' })
    await user.type(within(form).getByLabelText('Contract name'), 'Gold')
    await user.click(within(form).getByRole('button', { name: 'Add contract' }))
    expect(await screen.findByTestId('contract-error')).toHaveTextContent(/another contract/)
  })
})

describe('who sees what', () => {
  it.each(['planner', 'lead', 'executive', 'customer_ops'])(
    'lets %s read but offers no way to change',
    async (role) => {
      await open(role)
      await screen.findByTestId('contract-1')
      expect(screen.queryByRole('button', { name: 'Add contract' })).toBeNull()
      expect(screen.queryByRole('button', { name: /^Change/ })).toBeNull()
      expect(screen.queryByRole('button', { name: 'Add customer' })).toBeNull()
    },
  )

  it('keeps an agent out', async () => {
    await open('agent')
    expect(
      await screen.findByRole('heading', { name: "You don't have access to this page" }),
    ).toBeVisible()
  })
})
