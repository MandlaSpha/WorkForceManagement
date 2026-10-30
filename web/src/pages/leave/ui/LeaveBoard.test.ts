import userEvent from '@testing-library/user-event'
import { fireEvent, screen, waitFor, within } from '@testing-library/vue'
import { describe, expect, it } from 'vitest'

import type { LeaveRequest } from '@/entities/leave'
import { backend } from '@/test/fake-backend'
import { balancesOf, impactOf, LEAVE_TYPES, requestOf } from '@/test/leave-fixtures'
import { openScheduling, seedScheduling } from '@/test/open-scheduling'

async function open(role: string, requests: LeaveRequest[]) {
  seedScheduling()
  backend.leaveTypes = LEAVE_TYPES
  backend.balances = balancesOf()
  backend.leaveRequests = requests
  backend.impact = impactOf()
  return openScheduling('/leave', role)
}
const theirs = (over: Partial<LeaveRequest> = {}) =>
  requestOf({ mine: false, employee: 'Sam Planner', ...over })

describe('the leave board', () => {
  it('groups requests, counts them and totals the days', async () => {
    await open('lead', [
      theirs({ id: 1, days: 2 }),
      theirs({ id: 2, days: 3 }),
      theirs({ id: 3, status: 'approved', days: 1 }),
    ])
    await waitFor(() => expect(screen.getByTestId('kanban-count-pending')).toHaveTextContent('2'))
    expect(screen.getByTestId('kanban-total-pending')).toHaveTextContent('5 days')
    expect(screen.getByTestId('kanban-total-approved')).toHaveTextContent('1 day')
    expect(screen.getByTestId('kanban-empty-rejected')).toHaveTextContent('Nothing rejected')
    expect(screen.queryByTestId('kanban-col-cancelled')).toBeNull()
  })

  it('shows the effect on coverage from the impact data', async () => {
    await open('lead', [theirs()])
    await waitFor(() =>
      expect(screen.getByTestId('coverage-chip')).toHaveTextContent('17 half-hours would be short'),
    )
  })

  it('approves a pending request dragged onto Approved', async () => {
    await open('planner', [theirs()])
    const card = await screen.findByTestId('kanban-card-1')
    const target = screen.getByTestId('kanban-col-approved')
    await fireEvent.dragStart(card)
    await fireEvent.dragOver(target)
    await fireEvent.drop(target)
    await waitFor(() => expect(backend.writes).toHaveLength(1))
    expect(backend.writes[0]).toMatchObject({ path: '/api/v1/people/leave/requests/1/approve' })
    expect(await screen.findByTestId('decision-result')).toHaveTextContent(
      /Approved leave for Sam Planner/,
    )
  })

  it('needs a reason to reject, by keyboard path', async () => {
    const user = userEvent.setup()
    await open('lead', [theirs()])
    await user.click(await screen.findByRole('button', { name: /Move .* to…/ }))
    await user.click(screen.getByTestId('kanban-move-1-rejected'))
    const dialog = await screen.findByRole('dialog')
    await user.click(within(dialog).getByRole('button', { name: 'Reject leave' }))
    // Failure caught: a rejection sent with no reason.
    expect(within(dialog).getByText('Give a reason.')).toBeVisible()
    expect(backend.writes).toHaveLength(0)
    await user.type(within(dialog).getByLabelText('Reason'), 'Year-end close')
    await user.click(within(dialog).getByRole('button', { name: 'Reject leave' }))
    await waitFor(() => expect(backend.writes).toHaveLength(1))
    expect(backend.writes[0]).toMatchObject({
      path: '/api/v1/people/leave/requests/1/reject',
      body: { reason: 'Year-end close' },
    })
    // Failure caught: the reason shown in the toast but never sent or kept on the card.
    expect(await screen.findByTestId('decision-reason')).toHaveTextContent('Year-end close')
    expect(await screen.findByTestId('decision-result')).toHaveTextContent(/Reason: Year-end close/)
  })

  it('rolls the card back when the API refuses', async () => {
    const user = userEvent.setup()
    await open('lead', [theirs()])
    await user.click(await screen.findByRole('button', { name: /Move .* to…/ }))
    backend.nextProblem = {
      status: 403,
      code: 'forbidden',
      title: 'Refused',
      detail: 'You may not decide this.',
    }
    await user.click(screen.getByTestId('kanban-move-1-approved'))
    expect(await screen.findByTestId('board-failure')).toHaveTextContent(/may not decide/)
    expect(
      within(screen.getByTestId('kanban-col-pending')).getByTestId('kanban-card-1'),
    ).toBeVisible()
  })

  it('gives an agent only their own requests and no way to move them', async () => {
    const user = userEvent.setup()
    await open('agent', [requestOf({ id: 1 }), theirs({ id: 2 })])
    await user.click(await screen.findByRole('tab', { name: 'Board' }))
    expect(await screen.findByTestId('kanban-card-1')).toBeVisible()
    expect(screen.queryByTestId('kanban-card-2')).toBeNull()
    expect(screen.queryByRole('button', { name: /Move .* to/ })).toBeNull()
  })
})
