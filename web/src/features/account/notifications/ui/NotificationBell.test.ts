import userEvent from '@testing-library/user-event'
import { screen, waitFor, within } from '@testing-library/vue'
import { describe, expect, it } from 'vitest'

import type { Notification } from '@/entities/notification'
import { backend } from '@/test/fake-backend'
import { balancesOf, LEAVE_TYPES } from '@/test/leave-fixtures'
import { openScheduling, seedScheduling } from '@/test/open-scheduling'

const note = (over: Partial<Notification> = {}): Notification => ({
  id: 1,
  kind: 'leave.approved',
  message: 'Your annual leave request for 25 May was approved.',
  link: '/leave',
  createdAt: '2026-05-20T08:00:00Z',
  read: false,
  ...over,
})

async function open(items: Notification[]) {
  seedScheduling()
  backend.leaveTypes = LEAVE_TYPES
  backend.balances = balancesOf()
  backend.inbox = { unread: items.filter((n) => !n.read).length, items }
  return openScheduling('/leave', 'agent')
}

describe('the notification bell', () => {
  it('says how many are unread, to everyone including screen readers', async () => {
    await open([note({ id: 1 }), note({ id: 2 }), note({ id: 3, read: true })])
    // Failure caught: a badge with no text alternative is invisible to a screen reader.
    const bell = await screen.findByRole('button', { name: 'Notifications, 2 unread' })
    expect(within(bell).getByTestId('unread-count')).toHaveTextContent('2')
  })

  it('shows no badge and a plain label when everything is read', async () => {
    await open([note({ read: true })])
    expect(await screen.findByRole('button', { name: 'Notifications' })).toBeVisible()
    expect(screen.queryByTestId('unread-count')).toBeNull()
  })

  it('opens a list, unread first in weight, with the message and when', async () => {
    const user = userEvent.setup()
    await open([note()])
    await user.click(await screen.findByRole('button', { name: /^Notifications/ }))
    const row = await screen.findByTestId('notification-1')
    expect(row).toHaveTextContent('Your annual leave request for 25 May was approved.')
    expect(row).toHaveTextContent('Unread:')
  })

  it('says so when there is nothing', async () => {
    const user = userEvent.setup()
    await open([])
    await user.click(await screen.findByRole('button', { name: 'Notifications' }))
    expect(await screen.findByTestId('no-notifications')).toBeVisible()
  })

  it('marks one read with the CSRF token and goes to where it points', async () => {
    const user = userEvent.setup()
    const view = await open([note({ link: '/shift-swaps' })])
    await user.click(await screen.findByRole('button', { name: /^Notifications/ }))
    await user.click(await screen.findByTestId('notification-1'))

    await waitFor(() => expect(backend.writes).toHaveLength(1))
    expect(backend.writes[0]).toMatchObject({
      method: 'POST',
      path: '/api/v1/notifications/1/read',
      csrf: 'test-csrf-token',
    })
    await waitFor(() => expect(view.router.currentRoute.value.path).toBe('/shift-swaps'))
    await waitFor(() => expect(screen.queryByTestId('unread-count')).toBeNull())
  })

  it('does not mark one that is already read, but still goes there', async () => {
    const user = userEvent.setup()
    await open([note({ read: true, link: '/shift-swaps' })])
    await user.click(await screen.findByRole('button', { name: 'Notifications' }))
    await user.click(await screen.findByTestId('notification-1'))
    expect(backend.writes).toHaveLength(0)
  })

  it('marks everything read in one go', async () => {
    const user = userEvent.setup()
    await open([note({ id: 1 }), note({ id: 2 })])
    await user.click(await screen.findByRole('button', { name: /^Notifications/ }))
    await user.click(await screen.findByRole('button', { name: 'Mark all as read' }))
    await waitFor(() =>
      expect(backend.writes[0]).toMatchObject({ path: '/api/v1/notifications/read-all' }),
    )
    await waitFor(() => expect(screen.queryByTestId('unread-count')).toBeNull())
  })

  it('closes with Escape and puts focus back on the bell', async () => {
    // Failure caught: Escape closing the card but dropping keyboard users at the top of the page.
    const user = userEvent.setup()
    await open([note()])
    const bell = await screen.findByRole('button', { name: /^Notifications/ })
    await user.click(bell)
    expect(await screen.findByRole('region', { name: 'Notifications' })).toBeVisible()
    await user.keyboard('{Escape}')
    await waitFor(() => expect(screen.queryByRole('region', { name: 'Notifications' })).toBeNull())
    expect(bell).toHaveFocus()
  })

  it('moves between notices with the arrow keys', async () => {
    // Failure caught: a list only reachable by tabbing through every row.
    const user = userEvent.setup()
    await open([note({ id: 1 }), note({ id: 2, message: 'A swap was answered.' })])
    await user.click(await screen.findByRole('button', { name: /^Notifications/ }))
    const first = await screen.findByTestId('notification-1')
    await waitFor(() => expect(first).toHaveFocus())
    await user.keyboard('{ArrowDown}')
    expect(screen.getByTestId('notification-2')).toHaveFocus()
    await user.keyboard('{ArrowUp}')
    expect(first).toHaveFocus()
  })

  it('announces the unread count politely, and shows how long ago', async () => {
    // Failure caught: a badge change nobody using a screen reader hears about.
    const user = userEvent.setup()
    await open([note({ id: 1 })])
    await waitFor(() =>
      expect(screen.getByTestId('unread-live')).toHaveTextContent('1 unread notifications'),
    )
    await user.click(await screen.findByRole('button', { name: /^Notifications/ }))
    expect(await screen.findByTestId('notification-1')).toHaveTextContent(/ago|\d/)
  })
})
