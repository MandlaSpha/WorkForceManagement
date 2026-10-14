import userEvent from '@testing-library/user-event'
import { screen, waitFor, within } from '@testing-library/vue'
import { describe, expect, it } from 'vitest'

import { backend } from '@/test/fake-backend'
import { openScheduling, seedScheduling } from '@/test/open-scheduling'
import { shiftOf, swapOf, THEIRS } from '@/test/swap-fixtures'

async function open(
  role = 'agent',
  over: { swaps?: ReturnType<typeof swapOf>[]; options?: ReturnType<typeof shiftOf>[] } = {},
) {
  seedScheduling()
  backend.myShifts = [shiftOf(), shiftOf({ assignmentId: 3, day: '2099-06-03', shift: 'E1' })]
  backend.swapOptions = over.options ?? [THEIRS]
  backend.swaps = over.swaps ?? []
  return openScheduling('/shift-swaps', role)
}

describe('offering a swap', () => {
  it('sends my shift and the colleague shift I picked, with the CSRF token, and says who must accept', async () => {
    const user = userEvent.setup()
    await open()
    const form = await screen.findByRole('form', { name: 'Offer a shift swap' })
    await within(form).findByRole('option', { name: /Sam Colleague: Tue 02 Jun, L1/ })

    await user.click(within(form).getByRole('button', { name: 'Offer swap' }))

    await waitFor(() => expect(backend.writes).toHaveLength(1))
    // Failure caught: the two ids sent the wrong way round would swap who gives and who takes.
    expect(backend.writes[0]).toEqual({
      method: 'POST',
      path: '/api/v1/people/swaps',
      body: { giveAssignmentId: 1, takeAssignmentId: 2 },
      csrf: 'test-csrf-token',
    })
    expect(await screen.findByTestId('offer-result')).toHaveTextContent(
      /waiting for Sam Colleague to accept/,
    )
  })

  it('asks for the colleague shifts of the shift I pick, and forgets the earlier choice', async () => {
    const user = userEvent.setup()
    await open()
    const form = await screen.findByRole('form', { name: 'Offer a shift swap' })
    await within(form).findByRole('option', { name: /Sam Colleague/ })

    await user.selectOptions(within(form).getByLabelText('Your shift'), '3')

    // Failure caught: options left over from the first shift would let me send a pair that was
    // never checked against the rules for the second.
    await waitFor(() => expect(backend.optionQueries).toContain('?give_assignment_id=3'))
  })

  it('says when no colleague shift fits, and does not let me send an empty offer', async () => {
    await open('agent', { options: [] })
    expect(await screen.findByTestId('no-options')).toHaveTextContent(/fits the rules/)
    expect(screen.getByRole('button', { name: 'Offer swap' })).toBeDisabled()
  })

  it('says so when I have no shift to give', async () => {
    seedScheduling()
    backend.myShifts = []
    await openScheduling('/shift-swaps', 'agent')
    expect(await screen.findByTestId('no-shifts')).toBeVisible()
    expect(screen.queryByRole('form', { name: 'Offer a shift swap' })).toBeNull()
  })

  it('shows why the swap was refused, in words', async () => {
    const user = userEvent.setup()
    await open()
    backend.nextProblem = {
      status: 422,
      code: 'roster.rest_period',
      title: 'Swap refused',
      detail: 'This would leave less than 11 hours of rest between shifts.',
    }
    const form = await screen.findByRole('form', { name: 'Offer a shift swap' })
    await within(form).findByRole('option', { name: /Sam Colleague/ })
    await user.click(within(form).getByRole('button', { name: 'Offer swap' }))
    expect(await screen.findByTestId('offer-error')).toHaveTextContent(/11 hours of rest/)
  })
})

describe('answering a swap', () => {
  it('lets the colleague accept, and keeps saying what happened once the row has moved on', async () => {
    const user = userEvent.setup()
    await open('agent', {
      swaps: [
        swapOf({
          asker: false,
          colleague: true,
          fromEmployee: 'Sam Colleague',
          toEmployee: 'Alex Agent',
        }),
      ],
    })
    const row = await screen.findByTestId('for-me-1')
    await user.click(
      within(row).getByRole('button', { name: /Accept the swap with Sam Colleague/ }),
    )

    await waitFor(() => expect(backend.writes).toHaveLength(1))
    expect(backend.writes[0]).toMatchObject({
      method: 'POST',
      path: '/api/v1/people/swaps/1/accept',
      csrf: 'test-csrf-token',
    })
    // Failure caught: the row leaves "waiting for your answer" at once, and its message with it.
    expect(await screen.findByTestId('swap-result')).toHaveTextContent(/^Accepted: /)
    await waitFor(() => expect(screen.queryByTestId('for-me-1')).toBeNull())
  })

  it('offers the asker only a way to withdraw, never to accept their own swap', async () => {
    await open('agent', { swaps: [swapOf()] })
    const row = await screen.findByTestId('mine-1')
    expect(
      within(row).getByRole('button', { name: /Withdraw the swap with Sam Colleague/ }),
    ).toBeVisible()
    expect(within(row).queryByRole('button', { name: /Accept|Decline|Approve|Reject/ })).toBeNull()
  })

  it('offers nothing on a swap that is finished', async () => {
    await open('agent', {
      swaps: [
        swapOf({ id: 1, status: 'approved' }),
        swapOf({ id: 2, status: 'declined' }),
        swapOf({ id: 3, status: 'rejected' }),
        swapOf({ id: 4, status: 'cancelled' }),
      ],
    })
    await screen.findByTestId('mine-1')
    for (const id of [1, 2, 3, 4]) {
      expect(within(screen.getByTestId(`mine-${id}`)).queryByRole('button')).toBeNull()
    }
    expect(within(screen.getByTestId('mine-1')).getByText('Approved')).toBeVisible()
  })
})

describe('approving a swap', () => {
  const agreed = swapOf({ status: 'awaiting_approval', asker: false, colleague: false })

  it('gives an agent no approvals tab', async () => {
    await open('agent', { swaps: [agreed] })
    await screen.findByRole('tab', { name: 'My swaps' })
    expect(screen.queryByRole('tab', { name: 'Approvals' })).toBeNull()
  })

  it.each(['lead', 'planner', 'admin'])(
    'lets a %s approve, and says the roster changed',
    async (role) => {
      const user = userEvent.setup()
      await open(role, { swaps: [agreed] })
      await user.click(await screen.findByRole('tab', { name: 'Approvals' }))
      const row = await screen.findByTestId('approve-1')
      await user.click(
        within(row).getByRole('button', {
          name: /Approve the swap between Alex Agent and Sam Colleague/,
        }),
      )

      await waitFor(() => expect(backend.writes).toHaveLength(1))
      expect(backend.writes[0]).toMatchObject({ path: '/api/v1/people/swaps/1/approve' })
      expect(await screen.findByTestId('swap-result')).toHaveTextContent(/exchanged on the roster/)
    },
  )

  it('can reject, which sends reject and not approve', async () => {
    const user = userEvent.setup()
    await open('lead', { swaps: [agreed] })
    await user.click(await screen.findByRole('tab', { name: 'Approvals' }))
    await user.click(await screen.findByRole('button', { name: /Reject the swap between/ }))
    await waitFor(() => expect(backend.writes).toHaveLength(1))
    expect(backend.writes[0]).toMatchObject({ path: '/api/v1/people/swaps/1/reject' })
  })

  it('does not offer a decider the buttons for a swap they are in', async () => {
    const user = userEvent.setup()
    await open('lead', { swaps: [swapOf({ status: 'awaiting_approval', asker: true })] })
    await user.click(await screen.findByRole('tab', { name: 'Approvals' }))
    const row = await screen.findByTestId('approve-1')
    expect(within(row).getByText(/Somebody else decides/)).toBeVisible()
    expect(within(row).queryByRole('button')).toBeNull()
  })

  it('says so when nothing waits for approval', async () => {
    const user = userEvent.setup()
    await open('lead', { swaps: [swapOf({ status: 'awaiting_colleague', asker: false })] })
    await user.click(await screen.findByRole('tab', { name: 'Approvals' }))
    expect(await screen.findByTestId('nothing-to-approve')).toBeVisible()
  })
})
