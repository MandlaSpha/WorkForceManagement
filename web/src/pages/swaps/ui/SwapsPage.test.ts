import userEvent from '@testing-library/user-event'
import { screen, waitFor, within } from '@testing-library/vue'
import { describe, expect, it } from 'vitest'

import type { BoardEntry, Swap, SwapShift } from '@/entities/swap'
import { backend } from '@/test/fake-backend'
import { openScheduling, seedScheduling } from '@/test/open-scheduling'
import { boardOf, matchedOf, shiftOf, swapOf } from '@/test/swap-fixtures'

async function open(
  role = 'agent',
  over: { swaps?: Swap[]; board?: BoardEntry[]; offers?: SwapShift[] } = {},
) {
  seedScheduling()
  backend.myShifts = [shiftOf(), shiftOf({ assignmentId: 3, day: '2099-06-03', shift: 'E1' })]
  backend.board = over.board ?? []
  backend.swapOffers = over.offers ?? []
  backend.swaps = over.swaps ?? []
  return openScheduling('/shift-swaps', role)
}

describe('posting a swap request', () => {
  it('sends only my own shift with the CSRF token, and says nobody sees my name until it is taken', async () => {
    const user = userEvent.setup()
    await open()
    const form = await screen.findByRole('form', { name: 'Post a shift swap' })
    await within(form).findByRole('option', { name: /Mon 01 Jun, D1/ })

    await user.click(within(form).getByRole('button', { name: 'Post swap request' }))

    await waitFor(() => expect(backend.writes).toHaveLength(1))
    // Failure caught: the request names a colleague's shift or person; it must carry just mine.
    expect(backend.writes[0]).toEqual({
      method: 'POST',
      path: '/api/v1/people/swaps',
      body: { giveAssignmentId: 1 },
      csrf: 'test-csrf-token',
    })
    expect(await screen.findByTestId('offer-result')).toHaveTextContent(
      /will not see your name until someone does/,
    )
  })

  it('sends the shift I picked, not the first one', async () => {
    const user = userEvent.setup()
    await open()
    const form = await screen.findByRole('form', { name: 'Post a shift swap' })
    await within(form).findByRole('option', { name: /Wed 03 Jun, E1/ }) // the shifts load first
    await user.selectOptions(within(form).getByLabelText(/swap away/), '3')
    await user.click(within(form).getByRole('button', { name: 'Post swap request' }))
    await waitFor(() => expect(backend.writes[0]?.body).toEqual({ giveAssignmentId: 3 }))
  })

  it('says so when I have no shift to give', async () => {
    seedScheduling()
    backend.myShifts = []
    await openScheduling('/shift-swaps', 'agent')
    expect(await screen.findByTestId('no-shifts')).toBeVisible()
    expect(screen.queryByRole('form', { name: 'Post a shift swap' })).toBeNull()
  })

  it('shows why the request was refused, in words', async () => {
    const user = userEvent.setup()
    await open()
    backend.nextProblem = {
      status: 409,
      code: 'swap.already_open',
      title: 'Swap refused',
      detail: 'That shift is already in a swap.',
    }
    const form = await screen.findByRole('form', { name: 'Post a shift swap' })
    await within(form).findByRole('option', { name: /Mon 01 Jun, D1/ })
    await user.click(within(form).getByRole('button', { name: 'Post swap request' }))
    expect(await screen.findByTestId('offer-error')).toHaveTextContent(/already in a swap/)
  })

  it('shows my open request as waiting, with a way to withdraw it', async () => {
    await open('agent', { swaps: [swapOf()] })
    const row = await screen.findByTestId('mine-1')
    expect(within(row).getByText('Open: waiting for a colleague')).toBeVisible()
    expect(within(row).getByRole('button', { name: 'Withdraw this swap request' })).toBeVisible()
  })

  it('offers nothing on a swap that is finished', async () => {
    await open('agent', {
      swaps: [
        matchedOf({ id: 1, status: 'approved' }),
        matchedOf({ id: 2, status: 'rejected' }),
        swapOf({ id: 3, status: 'cancelled' }),
      ],
    })
    await screen.findByTestId('mine-1')
    for (const id of [1, 2, 3]) {
      expect(within(screen.getByTestId(`mine-${id}`)).queryByRole('button')).toBeNull()
    }
  })

  it('withdraws with a cancel and keeps saying what happened', async () => {
    const user = userEvent.setup()
    await open('agent', { swaps: [swapOf()] })
    await user.click(await screen.findByRole('button', { name: 'Withdraw this swap request' }))
    await waitFor(() => expect(backend.writes).toHaveLength(1))
    expect(backend.writes[0]).toMatchObject({ path: '/api/v1/people/swaps/1/cancel' })
    expect(await screen.findByTestId('swap-result')).toHaveTextContent(/^Withdrew: /)
  })
})

describe('the open requests board', () => {
  async function onBoard(over: Parameters<typeof open>[1] = {}) {
    const user = userEvent.setup()
    await open('agent', { board: [boardOf()], ...over })
    await user.click(await screen.findByRole('tab', { name: 'Open requests' }))
    return user
  }

  it('shows the shift and queue but never a name', async () => {
    await onBoard()
    const card = await screen.findByTestId('board-5')
    expect(card).toHaveTextContent('QueueA')
    expect(card).toHaveTextContent('Tue 02 Jun, L1 13:00-22:00')
    // Failure caught: any name on a request nobody has taken yet.
    expect(card).toHaveTextContent('A colleague')
    expect(card.textContent).not.toMatch(/Alex|Sam|E00\d/)
  })

  it('says so when there is nothing I could take', async () => {
    const user = userEvent.setup()
    await open('agent', { board: [] })
    await user.click(await screen.findByRole('tab', { name: 'Open requests' }))
    expect(await screen.findByTestId('board-empty')).toBeVisible()
  })

  it('asks which of my shifts would work, and takes the request offering the one I pick', async () => {
    const user = await onBoard({
      offers: [shiftOf({ assignmentId: 7, day: '2099-06-04', shift: 'E1' })],
    })
    await user.click(await screen.findByRole('button', { name: /Take the L1 request/ }))
    const form = await screen.findByRole('form', { name: 'Take the L1 request' })
    expect(backend.offerQueries).toContain('/api/v1/people/swaps/5/offers')
    await user.click(await within(form).findByRole('button', { name: 'Take this swap' }))

    await waitFor(() => expect(backend.writes).toHaveLength(1))
    // Failure caught: offering the posted shift's id, or none, instead of one of mine.
    expect(backend.writes[0]).toEqual({
      method: 'POST',
      path: '/api/v1/people/swaps/5/accept',
      body: { assignmentId: 7 },
      csrf: 'test-csrf-token',
    })
    expect(await screen.findByTestId('swap-result')).toHaveTextContent(/A lead decides next/)
    await waitFor(() => expect(screen.queryByTestId('board-5')).toBeNull())
  })

  it('says when none of my shifts work any more, and offers no button', async () => {
    const user = await onBoard({ offers: [] })
    await user.click(await screen.findByRole('button', { name: /Take the L1 request/ }))
    expect(await screen.findByTestId('no-offers')).toBeVisible()
    expect(screen.queryByRole('button', { name: 'Take this swap' })).toBeNull()
  })

  it('shows why taking was refused', async () => {
    const user = await onBoard({ offers: [shiftOf({ assignmentId: 7, shift: 'E1' })] })
    backend.nextProblem = {
      status: 409,
      code: 'swap.not_open',
      title: 'Swap refused',
      detail: 'That request has already been taken.',
    }
    await user.click(await screen.findByRole('button', { name: /Take the L1 request/ }))
    await user.click(await screen.findByRole('button', { name: 'Take this swap' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/already been taken/)
  })
})

describe('approving a swap', () => {
  const matched = matchedOf({ asker: false, colleague: false })

  it('gives an agent no approvals tab', async () => {
    await open('agent', { swaps: [matched] })
    await screen.findByRole('tab', { name: 'My swaps' })
    expect(screen.queryByRole('tab', { name: 'Approvals' })).toBeNull()
  })

  it.each(['lead', 'planner', 'admin'])(
    'lets a %s approve, and says the roster changed',
    async (role) => {
      const user = userEvent.setup()
      await open(role, { swaps: [matched] })
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
    await open('lead', { swaps: [matched] })
    await user.click(await screen.findByRole('tab', { name: 'Approvals' }))
    await user.click(await screen.findByRole('button', { name: /Reject the swap between/ }))
    await waitFor(() => expect(backend.writes).toHaveLength(1))
    expect(backend.writes[0]).toMatchObject({ path: '/api/v1/people/swaps/1/reject' })
  })

  it('does not offer a decider the buttons for a swap they are in', async () => {
    const user = userEvent.setup()
    await open('lead', { swaps: [matchedOf({ asker: true })] })
    await user.click(await screen.findByRole('tab', { name: 'Approvals' }))
    const row = await screen.findByTestId('approve-1')
    expect(within(row).getByText(/Somebody else decides/)).toBeVisible()
    expect(within(row).queryByRole('button')).toBeNull()
  })

  it('does not list a request nobody has taken for approval', async () => {
    const user = userEvent.setup()
    await open('lead', { swaps: [swapOf({ asker: false })] })
    await user.click(await screen.findByRole('tab', { name: 'Approvals' }))
    expect(await screen.findByTestId('nothing-to-approve')).toBeVisible()
  })
})
