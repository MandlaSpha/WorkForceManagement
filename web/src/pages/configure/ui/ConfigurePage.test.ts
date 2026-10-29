import userEvent from '@testing-library/user-event'
import { screen, waitFor, within } from '@testing-library/vue'
import { describe, expect, it } from 'vitest'

import { capacityOf } from '@/test/capacity-fixtures'
import { backend } from '@/test/fake-backend'
import { openScheduling, seedScheduling } from '@/test/open-scheduling'
import { shiftOf } from '@/test/scheduling-fixtures'

const codesIn = (table: HTMLElement) =>
  within(table)
    .getAllByRole('rowheader')
    .map((c) => c.textContent)

describe('shift templates', () => {
  it('lists the library as a table with times, overnight marker and paid hours', async () => {
    seedScheduling()
    await openScheduling('/configure', 'admin')

    const table = await screen.findByRole('table', { name: 'Shifts' })
    const row = within(table).getByRole('row', { name: /D1/ })
    expect(within(row).getByText('09:00')).toBeVisible()
    expect(within(table).getByRole('row', { name: /N1/ })).toHaveTextContent('(overnight)')
    expect(within(table).getAllByText(/8h paid/).length).toBeGreaterThan(0)
    expect(codesIn(table)).toEqual(['E1', 'D1', 'L1', 'N1']) // earliest start first
  })

  it('sorts by a column and says which way', async () => {
    seedScheduling()
    const user = userEvent.setup()
    await openScheduling('/configure', 'admin')
    const table = await screen.findByRole('table', { name: 'Shifts' })

    await user.click(within(table).getByRole('button', { name: /^Code/ }))
    expect(within(table).getByRole('columnheader', { name: /Code/ })).toHaveAttribute(
      'aria-sort',
      'ascending',
    )
    expect(codesIn(table)).toEqual(['D1', 'E1', 'L1', 'N1'])

    await user.click(within(table).getByRole('button', { name: /^Code/ }))
    expect(within(table).getByRole('columnheader', { name: /Code/ })).toHaveAttribute(
      'aria-sort',
      'descending',
    )
    expect(codesIn(table)).toEqual(['N1', 'L1', 'E1', 'D1'])
  })

  it('finds a shift by search and says when nothing matches', async () => {
    seedScheduling()
    const user = userEvent.setup()
    await openScheduling('/configure', 'admin')

    await user.type(await screen.findByLabelText('Search shifts'), 'n1')
    expect(codesIn(screen.getByRole('table', { name: 'Shifts' }))).toEqual(['N1'])

    await user.clear(screen.getByLabelText('Search shifts'))
    await user.type(screen.getByLabelText('Search shifts'), 'zzz')
    expect(screen.queryByRole('table', { name: 'Shifts' })).toBeNull()
    expect(screen.getByText(/No shift matches "zzz"/)).toBeVisible()
  })

  it('says so when there are no shifts yet, and the add form is still there', async () => {
    // Failure caught: an empty library showing an empty table, or hiding the way to add one.
    seedScheduling()
    backend.shifts = []
    await openScheduling('/configure', 'admin')

    expect(await screen.findByText('No shifts yet. Add one below.')).toBeVisible()
    expect(screen.queryByRole('table', { name: 'Shifts' })).toBeNull()
    expect(screen.getByRole('button', { name: 'Add shift' })).toBeVisible()
    expect(document.querySelector('.skeleton')).toBeNull() // the loading state does not linger
  })

  it('shows 20 shifts at a time and adds 20 more on request', async () => {
    // Failure caught: a long library rendered in one go, or "show more" skipping or repeating rows.
    seedScheduling()
    backend.shifts = Array.from({ length: 45 }, (_, i) =>
      shiftOf({ id: 100 + i, code: `S${String(i).padStart(2, '0')}` }),
    )
    const user = userEvent.setup()
    await openScheduling('/configure', 'admin')

    const table = await screen.findByRole('table', { name: 'Shifts' })
    expect(codesIn(table)).toHaveLength(20)
    expect(screen.getByText('Showing 20 of 45')).toBeVisible()

    await user.click(screen.getByRole('button', { name: 'Show more (25 left)' }))
    expect(codesIn(table)).toHaveLength(40)
    await user.click(screen.getByRole('button', { name: 'Show more (5 left)' }))
    expect(codesIn(table)).toHaveLength(45)
    expect(screen.queryByRole('button', { name: /Show more/ })).toBeNull()
  })

  it('lays the add form out as rows that stack on a phone', async () => {
    // Failure caught: label and control side by side on a narrow screen, squeezing both.
    seedScheduling()
    await openScheduling('/configure', 'admin')
    const form = await screen.findByRole('form', { name: 'Add a shift' })
    const row = within(form).getByText('Paid minutes', { selector: 'p' }).closest('div.flex')
    expect(row).toHaveClass('flex-col')
    expect(row).toHaveClass('sm:flex-row')
    expect(within(form).getByText('What the person is paid for.')).toBeVisible()
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
    await user.click(screen.getByRole('button', { name: 'Yes, delete' }))

    expect(await screen.findByTestId('shift-delete-error')).toHaveTextContent(/rostered/)
    expect(backend.writes[0]).toMatchObject({
      method: 'DELETE',
      path: '/api/v1/scheduling/shifts/2',
    })
    // The confirmation closes; the shift is still listed.
    expect(screen.queryByText('Delete D1?')).toBeNull()
    expect(screen.getByRole('table', { name: 'Shifts' })).toHaveTextContent('D1')
  })

  it('asks before deleting and sends nothing if you cancel', async () => {
    // Failure caught: one stray click deleting a shift.
    seedScheduling()
    const user = userEvent.setup()
    await openScheduling('/configure', 'admin')

    await user.click(await screen.findByRole('button', { name: 'Delete shift D1' }))
    expect(screen.getByText('Delete D1?')).toBeVisible()
    expect(backend.writes).toHaveLength(0)

    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(screen.queryByText('Delete D1?')).toBeNull()
    expect(backend.writes).toHaveLength(0)

    await user.click(screen.getByRole('button', { name: 'Delete shift D1' }))
    await user.click(screen.getByRole('button', { name: 'Yes, delete' }))
    await waitFor(() => expect(backend.writes).toHaveLength(1))
  })
})

describe('settings footer and tabs', () => {
  it('flags edits as unsaved and Discard puts the saved value back', async () => {
    // Failure caught: a footer claiming "saved" while edits are pending, or a Discard that leaves
    // the edit in the box.
    seedScheduling()
    const user = userEvent.setup()
    await openScheduling('/configure', 'admin')
    await user.click(await screen.findByRole('tab', { name: 'Queues' }))

    const shrinkage = await screen.findByLabelText('Shrinkage (%)')
    expect(screen.getByRole('button', { name: 'Discard' })).toBeDisabled()
    await user.clear(shrinkage)
    await user.type(shrinkage, '25')
    expect(screen.getByText('You have unsaved changes')).toBeVisible()

    await user.click(screen.getByRole('button', { name: 'Discard' }))
    expect(shrinkage).toHaveValue(30)
    expect(screen.queryByText('You have unsaved changes')).toBeNull()
    expect(backend.writes).toHaveLength(0)
  })

  it('draws the tabs as a segmented control and keeps each tab in its panel', async () => {
    seedScheduling()
    const user = userEvent.setup()
    await openScheduling('/configure', 'admin')
    expect(await screen.findByRole('tablist', { name: 'Configuration' })).toHaveClass(
      'rounded-full',
    )
    await user.click(screen.getByRole('tab', { name: 'Rules' }))
    expect(screen.getByRole('tabpanel')).toHaveAttribute('id', 'configure-panel-rules')
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
