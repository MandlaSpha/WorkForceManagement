import userEvent from '@testing-library/user-event'
import { fireEvent, screen, waitFor, within } from '@testing-library/vue'
import { describe, expect, it } from 'vitest'

import type { Swap } from '@/entities/swap'
import { backend } from '@/test/fake-backend'
import { openScheduling, seedScheduling } from '@/test/open-scheduling'
import { matchedOf, swapOf } from '@/test/swap-fixtures'

const waiting = matchedOf({ asker: false, colleague: false })

async function open(role: string, swaps: Swap[]) {
  seedScheduling()
  backend.swaps = swaps
  return openScheduling('/shift-swaps', role)
}

describe('the swap board', () => {
  it('opens on the board for a lead, with swaps in their columns', async () => {
    await open('lead', [swapOf({ id: 2, asker: false }), waiting])
    expect(await screen.findByTestId('kanban-card-1')).toBeVisible()
    expect(
      within(screen.getByTestId('kanban-col-accepted')).getByTestId('kanban-card-1'),
    ).toBeVisible()
    expect(screen.getByTestId('kanban-count-waiting')).toHaveTextContent('1')
    expect(screen.getByTestId('kanban-empty-approved')).toHaveTextContent('Nothing approved yet')
    // The deciders see the names they see today.
    expect(screen.getByTestId('kanban-card-1')).toHaveTextContent('Alex Agent and Sam Colleague')
  })

  it('opens an agent on the list, and the board shows only their swaps with no names added', async () => {
    // Failure caught: the board showing colleagues' swaps or names to an agent.
    const user = userEvent.setup()
    await open('agent', [
      matchedOf({ id: 1, asker: true, toEmployee: 'A colleague' }),
      swapOf({ id: 2, asker: false, fromEmployee: 'Casey Teammate' }),
    ])
    await screen.findByRole('tab', { name: 'My swaps' })
    await user.click(screen.getByRole('tab', { name: 'Board' }))
    expect(await screen.findByTestId('kanban-card-1')).toBeVisible()
    expect(screen.queryByTestId('kanban-card-2')).toBeNull()
    expect(screen.queryByTestId('swap-people')).toBeNull()
    expect(document.body.textContent).not.toMatch(/Casey/)
    expect(screen.queryByRole('button', { name: /Move .* to/ })).toBeNull()
  })

  it('approves by keyboard through Move to, and announces it', async () => {
    const user = userEvent.setup()
    await open('planner', [waiting])
    await user.click(await screen.findByRole('button', { name: /Move .* to…/ }))
    await user.click(screen.getByTestId('kanban-move-1-approved'))
    await waitFor(() => expect(backend.writes).toHaveLength(1))
    expect(backend.writes[0]).toMatchObject({ path: '/api/v1/people/swaps/1/approve' })
    expect(screen.getByTestId('kanban-live')).toHaveTextContent(/Approved/)
    expect(await screen.findByTestId('swap-result')).toHaveTextContent(/exchanged on the roster/)
  })

  it('approves when the card is dragged onto Approved', async () => {
    await open('lead', [waiting])
    const card = await screen.findByTestId('kanban-card-1')
    const target = screen.getByTestId('kanban-col-approved')
    await fireEvent.dragStart(card)
    await fireEvent.dragOver(target)
    expect(target).toHaveAttribute('data-drop', 'yes')
    await fireEvent.drop(target)
    await waitFor(() => expect(backend.writes).toHaveLength(1))
    expect(backend.writes[0]).toMatchObject({ path: '/api/v1/people/swaps/1/approve' })
  })

  it('shows a not-allowed reason over a column the card may not enter', async () => {
    await open('lead', [waiting])
    const card = await screen.findByTestId('kanban-card-1')
    await fireEvent.dragStart(card)
    await fireEvent.dragOver(screen.getByTestId('kanban-col-waiting'))
    expect(screen.getByTestId('kanban-not-allowed')).toHaveTextContent(/cannot go back to waiting/)
    await fireEvent.drop(screen.getByTestId('kanban-col-waiting'))
    expect(backend.writes).toHaveLength(0)
  })

  it('will not decline without a reason, then declines with one', async () => {
    const user = userEvent.setup()
    await open('lead', [waiting])
    await user.click(await screen.findByRole('button', { name: /Move .* to…/ }))
    await user.click(screen.getByTestId('kanban-move-1-declined'))
    const dialog = await screen.findByRole('dialog')
    await user.click(within(dialog).getByRole('button', { name: 'Decline swap' }))
    // Failure caught: a decline sent with no reason.
    expect(within(dialog).getByText('Give a reason.')).toBeVisible()
    expect(backend.writes).toHaveLength(0)
    await user.type(within(dialog).getByLabelText('Reason'), 'Short on cover')
    await user.click(within(dialog).getByRole('button', { name: 'Decline swap' }))
    await waitFor(() => expect(backend.writes).toHaveLength(1))
    expect(backend.writes[0]).toMatchObject({ path: '/api/v1/people/swaps/1/reject' })
    expect(await screen.findByTestId('swap-result')).toHaveTextContent(/Reason: Short on cover/)
  })

  it('puts the card back and says why when the API refuses', async () => {
    const user = userEvent.setup()
    await open('lead', [waiting])
    await user.click(await screen.findByRole('button', { name: /Move .* to…/ }))
    backend.nextProblem = {
      status: 409,
      code: 'swap.not_waiting',
      title: 'Swap refused',
      detail: 'That swap was already decided.',
    }
    await user.click(screen.getByTestId('kanban-move-1-approved'))
    expect(await screen.findByTestId('board-failure')).toHaveTextContent(
      /already decided.*back where it was/,
    )
    // Failure caught: a refused move leaving the card in the wrong column.
    expect(
      within(screen.getByTestId('kanban-col-accepted')).getByTestId('kanban-card-1'),
    ).toBeVisible()
  })

  it('shows a swap the lead is in as not theirs to decide', async () => {
    const user = userEvent.setup()
    await open('lead', [matchedOf({ asker: true })])
    await user.click(await screen.findByRole('button', { name: /Move .* to…/ }))
    const item = screen.getByTestId('kanban-move-1-approved')
    expect(item).toBeDisabled()
    expect(item).toHaveTextContent('Somebody else decides a swap you are in.')
  })
})
