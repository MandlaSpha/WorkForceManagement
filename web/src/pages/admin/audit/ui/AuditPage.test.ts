import userEvent from '@testing-library/user-event'
import { screen, waitFor, within } from '@testing-library/vue'
import { describe, expect, it } from 'vitest'

import type { AuditEvent } from '@/entities/audit-log'
import { backend } from '@/test/fake-backend'
import { openScheduling, seedScheduling } from '@/test/open-scheduling'

const event = (seq: number, over: Partial<AuditEvent> = {}): AuditEvent => ({
  id: seq,
  seq,
  occurredAt: '2026-10-16T22:30:00Z',
  actor: 'amy',
  actorRole: 'planner',
  actorType: 'user',
  action: 'leave.approved',
  actionLabel: 'Leave approved',
  entityType: 'leave',
  entityId: '7',
  outcome: 'success',
  reason: '',
  requestId: 'req-1',
  ip: null,
  changes: [],
  ...over,
})

async function open(events: AuditEvent[]) {
  seedScheduling()
  backend.auditEvents = events
  return openScheduling('/audit', 'admin')
}

describe('the audit log screen', () => {
  it('lists events with who, what, South African time and old and new values', async () => {
    await open([
      event(2, {
        changes: [
          { entityType: 'leave', entityId: '7', field: 'status', old: 'pending', new: 'approved' },
        ],
      }),
    ])
    const row = await screen.findByTestId('audit-2')
    expect(row).toHaveTextContent('amy')
    expect(row).toHaveTextContent('Leave approved')
    // 22:30 UTC is half past midnight the next day in Johannesburg.
    expect(row).toHaveTextContent('17 Oct 2026')
    expect(row).toHaveTextContent('00:30')
    expect(row).toHaveTextContent('status: pending → approved')
    expect(screen.getByTestId('audit-count')).toHaveTextContent('1 event')
  })

  it('says the hash chain is intact', async () => {
    await open([event(1)])
    const box = await screen.findByTestId('chain-status')
    await waitFor(() => expect(box).toHaveTextContent('Hash chain intact'))
  })

  it('shows a broken chain as an alert with the problems', async () => {
    backend.auditChain = {
      intact: false,
      events: 3,
      problemCount: 1,
      problems: [{ seq: 2, eventId: 9, problem: 'hash mismatch' }],
      checkedAt: '2026-10-17T08:00:00Z',
    }
    await open([event(1)])
    const box = await screen.findByTestId('chain-status')
    await waitFor(() => expect(within(box).getByRole('alert')).toHaveTextContent('broken'))
    expect(box).toHaveTextContent('hash mismatch')
  })

  it('searches with the chosen filters, going back to page one', async () => {
    const user = userEvent.setup()
    await open([event(1), event(2, { outcome: 'denied', action: 'roster.refused' })])
    await screen.findByTestId('audit-2')
    await user.selectOptions(screen.getByLabelText('Outcome'), 'denied')
    await user.type(screen.getByLabelText(/^Who/), 'amy')
    await user.type(screen.getByLabelText(/^From/), '2026-10-01')
    await user.click(within(screen.getByRole('main')).getByRole('button', { name: 'Search' }))

    await waitFor(() => expect(screen.queryByTestId('audit-1')).toBeNull())
    const last = backend.auditQueries.at(-1) ?? ''
    expect(last).toContain('outcome=denied')
    expect(last).toContain('actor=amy')
    expect(last).toContain('since=2026-10-01T00%3A00%3A00%2B02%3A00')
  })

  it('offers the CSV and has no way to edit or delete', async () => {
    await open([event(1)])
    const link = await screen.findByTestId('audit-csv')
    expect(link.getAttribute('href')).toBe('/api/v1/audit/events.csv')
    expect(screen.queryByRole('button', { name: /delete|edit|remove/i })).toBeNull()
  })

  it('is honest when nothing matches', async () => {
    await open([])
    expect(await screen.findByText('No events match these filters.')).toBeVisible()
  })

  it('does not ask for the log again when the window regains focus', async () => {
    await open([event(1)])
    await screen.findByTestId('audit-1')
    const before = backend.auditQueries.length
    window.dispatchEvent(new Event('focus'))
    await new Promise((r) => setTimeout(r, 50))
    // Failure caught: every refocus writing another "audit log viewed" event.
    expect(backend.auditQueries.length).toBe(before)
  })
})

describe('who can reach the audit log', () => {
  it.each(['planner', 'lead', 'agent'])('keeps a %s out and never asks the API', async (role) => {
    seedScheduling()
    await openScheduling('/audit', role)
    await waitFor(() => expect(screen.queryByTestId('audit-table')).toBeNull())
    expect(backend.auditQueries).toHaveLength(0)
  })
})
