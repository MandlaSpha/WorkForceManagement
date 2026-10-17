import userEvent from '@testing-library/user-event'
import { screen, waitFor, within } from '@testing-library/vue'
import { describe, expect, it } from 'vitest'

import { capacityOf } from '@/test/capacity-fixtures'
import { backend } from '@/test/fake-backend'
import { openScheduling, seedScheduling } from '@/test/open-scheduling'

describe('shift templates', () => {
  it('lists the library with times, overnight marker and paid hours', async () => {
    seedScheduling()
    await openScheduling('/configure', 'admin')

    const list = await screen.findByRole('list', { name: 'Shifts' })
    expect(within(list).getByText('D1')).toBeVisible()
    expect(within(list).getByText(/22:00–06:00 \(overnight\)/)).toBeVisible()
    expect(within(list).getAllByText(/8h paid/).length).toBeGreaterThan(0)
  })

  it('sends the new shift with the CSRF token and clears the code box', async () => {
    seedScheduling()
    const user = userEvent.setup()
    await openScheduling('/configure', 'admin')

    await user.type(await screen.findByLabelText('Code'), 'X9')
    await user.click(screen.getByRole('button', { name: 'Add shift' }))

    await waitFor(() => expect(backend.writes).toHaveLength(1))
    expect(backend.writes[0]).toEqual({
      method: 'POST',
      path: '/api/v1/scheduling/shifts',
      body: { code: 'X9', startTime: '09:00', endTime: '17:30', paidMinutes: 480 },
      csrf: 'test-csrf-token',
    })
    await waitFor(() => expect(screen.getByLabelText('Code')).toHaveValue(''))
  })

  it('cannot submit a shift without a code', async () => {
    seedScheduling()
    await openScheduling('/configure', 'admin')
    expect(await screen.findByRole('button', { name: 'Add shift' })).toBeDisabled()
  })

  it('shows why a shift was refused and keeps what was typed', async () => {
    seedScheduling()
    backend.nextProblem = {
      status: 422,
      code: 'shift.off_grid',
      title: 'Shift refused',
      detail: 'Shift times must be on the hour or half-hour.',
    }
    const user = userEvent.setup()
    await openScheduling('/configure', 'admin')

    await user.type(await screen.findByLabelText('Code'), 'X9')
    await user.click(screen.getByRole('button', { name: 'Add shift' }))

    expect(await screen.findByTestId('shift-error')).toHaveTextContent(/on the hour or half-hour/)
    expect(screen.getByLabelText('Code')).toHaveValue('X9')
  })

  it('shows why a shift in use cannot be deleted', async () => {
    seedScheduling()
    backend.nextProblem = {
      status: 409,
      code: 'shift.in_use',
      title: 'Conflict',
      detail: 'People are rostered on this shift.',
    }
    const user = userEvent.setup()
    await openScheduling('/configure', 'admin')

    await user.click(await screen.findByRole('button', { name: 'Delete shift D1' }))

    expect(await screen.findByTestId('shift-delete-error')).toHaveTextContent(/rostered/)
    expect(backend.writes[0]).toMatchObject({
      method: 'DELETE',
      path: '/api/v1/scheduling/shifts/2',
    })
  })
})

describe('queue staffing settings', () => {
  it('says the settings are defaults until confirmed, then sends them and flips', async () => {
    seedScheduling()
    const user = userEvent.setup()
    await openScheduling('/configure', 'admin')

    await user.click(await screen.findByRole('tab', { name: 'Queues' }))
    expect(await screen.findByTestId('settings-state-1')).toHaveTextContent(
      'Defaults, not confirmed',
    )

    await user.click(screen.getByRole('button', { name: 'Confirm settings' }))

    await waitFor(() => expect(backend.writes).toHaveLength(1))
    expect(backend.writes[0]).toEqual({
      method: 'PUT',
      path: '/api/v1/telephony/queues/1/settings',
      body: {
        slTargetPct: 80,
        slThresholdS: 20,
        occupancyCeilingPct: 85,
        shrinkagePct: 30,
        outboundOnly: false,
      },
      csrf: 'test-csrf-token',
    })
    await waitFor(() =>
      expect(screen.getByTestId('settings-state-1')).toHaveTextContent('Confirmed'),
    )
    expect(screen.getByRole('button', { name: 'Save settings' })).toBeVisible()
  })

  it('marks a queue as outbound only so no forecast is made for it', async () => {
    // Failure caught: the flag shown but not sent, so staffing keeps being invented for the queue.
    seedScheduling()
    const user = userEvent.setup()
    await openScheduling('/configure', 'admin')
    await user.click(await screen.findByRole('tab', { name: 'Queues' }))
    await user.click(await screen.findByLabelText(/Outbound calls only/))
    await user.click(screen.getByRole('button', { name: 'Confirm settings' }))
    await waitFor(() => expect(backend.writes).toHaveLength(1))
    expect(backend.writes[0]?.body).toMatchObject({ outboundOnly: true })
  })

  it('sends changed values as numbers', async () => {
    seedScheduling()
    const user = userEvent.setup()
    await openScheduling('/configure', 'admin')

    await user.click(await screen.findByRole('tab', { name: 'Queues' }))
    const shrinkage = await screen.findByLabelText('Shrinkage (%)')
    await user.clear(shrinkage)
    await user.type(shrinkage, '25')
    await user.click(screen.getByRole('button', { name: 'Confirm settings' }))

    await waitFor(() => expect(backend.writes).toHaveLength(1))
    expect(backend.writes[0]?.body).toMatchObject({ shrinkagePct: 25 })
  })

  it('shows the reason and stays unconfirmed when the server refuses', async () => {
    seedScheduling()
    backend.nextProblem = {
      status: 422,
      code: 'queue.settings_invalid',
      title: 'Settings refused',
      detail: 'Shrinkage must be below 100.',
    }
    const user = userEvent.setup()
    await openScheduling('/configure', 'admin')

    await user.click(await screen.findByRole('tab', { name: 'Queues' }))
    await user.click(await screen.findByRole('button', { name: 'Confirm settings' }))

    expect(await screen.findByTestId('settings-error')).toHaveTextContent(/below 100/)
    expect(screen.getByTestId('settings-state-1')).toHaveTextContent('Defaults, not confirmed')
  })
})

describe('workforce limits', () => {
  it('says the pools are the tender figures until confirmed, then sends them and flips', async () => {
    seedScheduling()
    backend.capacity = capacityOf({
      limits: { permanentLimit: 100, seasonalLimit: 250, confirmed: false },
    })
    const user = userEvent.setup()
    await openScheduling('/configure', 'admin')

    await user.click(await screen.findByRole('tab', { name: 'Workforce' }))
    expect(await screen.findByTestId('limits-state')).toHaveTextContent(
      'Tender figures, not confirmed',
    )
    const seasonal = screen.getByLabelText(/Seasonal agents/)
    await user.clear(seasonal)
    await user.type(seasonal, '200')
    await user.click(screen.getByRole('button', { name: 'Confirm limits' }))

    await waitFor(() => expect(backend.writes).toHaveLength(1))
    expect(backend.writes[0]).toEqual({
      method: 'PUT',
      path: '/api/v1/capacity/limits',
      body: { permanentLimit: 100, seasonalLimit: 200 },
      csrf: 'test-csrf-token',
    })
    await waitFor(() => expect(screen.getByTestId('limits-state')).toHaveTextContent('Confirmed'))
    expect(screen.getByRole('button', { name: 'Save limits' })).toBeVisible()
  })

  it('shows the reason and stays unconfirmed when the server refuses', async () => {
    seedScheduling()
    backend.capacity = capacityOf({
      limits: { permanentLimit: 100, seasonalLimit: 250, confirmed: false },
    })
    backend.nextProblem = {
      status: 422,
      code: 'capacity.no_workforce',
      title: 'Invalid request',
      detail: 'The workforce cannot be empty.',
    }
    const user = userEvent.setup()
    await openScheduling('/configure', 'admin')

    await user.click(await screen.findByRole('tab', { name: 'Workforce' }))
    await user.click(await screen.findByRole('button', { name: 'Confirm limits' }))

    expect(await screen.findByTestId('limits-error')).toHaveTextContent(/cannot be empty/)
    expect(screen.getByTestId('limits-state')).toHaveTextContent('not confirmed')
  })
})

describe('who may open Configure', () => {
  it.each(['planner', 'lead', 'agent', 'executive', 'customer_ops'])(
    'does not open for %s',
    async (role) => {
      seedScheduling()
      await openScheduling('/configure', role)
      expect(
        await screen.findByRole('heading', { name: "You don't have access to this page" }),
      ).toBeVisible()
    },
  )
})
