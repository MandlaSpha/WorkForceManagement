import userEvent from '@testing-library/user-event'
import { screen, waitFor, within } from '@testing-library/vue'
import { describe, expect, it } from 'vitest'

import { dayIntervals, forecastVersion, queueInfo } from '@/test/forecast-fixtures'
import { backend } from '@/test/fake-backend'
import { renderApp } from '@/test/render-app'

const asRole = (role: string) => {
  backend.signedIn = { username: role, displayName: `Test ${role}`, role }
  document.cookie = 'csrftoken=test-csrf-token'
}
const user = () => userEvent.setup()

const draft = forecastVersion({
  id: 'v-draft',
  label: 'Draft plan',
  status: 'draft',
  publishedAt: null,
})

function versions() {
  backend.queues = [queueInfo()]
  backend.versions = [draft, forecastVersion()]
  backend.intervals = { 'v-live': dayIntervals(), 'v-draft': dayIntervals() }
}

const lastWrite = () => backend.writes[backend.writes.length - 1]

describe('discarding a draft', () => {
  it('asks first, needs a reason, then deletes it with the CSRF token', async () => {
    versions()
    asRole('planner')
    const u = user()
    await renderApp('/forecast')

    await u.click(await screen.findByRole('button', { name: /Discard Draft plan/ }))
    const form = screen.getByRole('form', { name: 'Discard Draft plan' })
    expect(within(form).getByTestId('retire-consequence')).toHaveTextContent(/cannot be undone/)
    const confirm = within(form).getByRole('button', { name: /Confirm: discard/ })
    // Failure caught: a one-click delete with no reason for the audit trail.
    expect(confirm).toBeDisabled()
    expect(backend.writes).toEqual([])

    await u.type(within(form).getByLabelText(/Reason/), 'Wrong week')
    await u.click(confirm)

    await waitFor(() => expect(screen.queryByText('Draft plan')).toBeNull())
    expect(lastWrite()).toMatchObject({
      method: 'POST',
      path: '/api/v1/forecasting/versions/v-draft/discard',
      body: { reason: 'Wrong week' },
      csrf: 'test-csrf-token',
    })
  })

  it('does nothing when the planner keeps it', async () => {
    versions()
    asRole('planner')
    const u = user()
    await renderApp('/forecast')

    await u.click(await screen.findByRole('button', { name: /Discard Draft plan/ }))
    await u.click(screen.getByRole('button', { name: 'Keep it' }))

    expect(screen.queryByRole('form', { name: 'Discard Draft plan' })).toBeNull()
    expect(screen.getByText('Draft plan')).toBeVisible()
    expect(backend.writes).toEqual([])
  })

  it('shows why the server refused and keeps the draft', async () => {
    versions()
    backend.nextProblem = {
      status: 409,
      code: 'forecast.not_draft',
      title: 'Forecast is not a draft',
      detail: 'Only a draft can be discarded. Withdraw a published forecast instead.',
    }
    asRole('planner')
    const u = user()
    await renderApp('/forecast')

    await u.click(await screen.findByRole('button', { name: /Discard Draft plan/ }))
    const form = screen.getByRole('form', { name: 'Discard Draft plan' })
    await u.type(within(form).getByLabelText(/Reason/), 'Wrong week')
    await u.click(within(form).getByRole('button', { name: /Confirm: discard/ }))

    expect(await within(form).findByRole('alert')).toHaveTextContent(
      /Only a draft can be discarded/,
    )
    expect(screen.getByText('Draft plan')).toBeVisible()
  })
})

describe('archiving the live forecast', () => {
  it('says the queue will have no forecast, then withdraws it and keeps it viewable', async () => {
    versions()
    asRole('planner')
    const u = user()
    await renderApp('/forecast')

    await u.click(await screen.findByRole('button', { name: /Archive Week 22 for QueueA/ }))
    const form = screen.getByRole('form', { name: 'Archive Week 22' })
    expect(within(form).getByTestId('retire-consequence')).toHaveTextContent(
      /QueueA will have no published forecast/,
    )
    await u.type(within(form).getByLabelText(/Reason/), 'Built on a bad import')
    await u.click(within(form).getByRole('button', { name: /Confirm: archive/ }))

    const table = within(await screen.findByRole('table', { name: 'Versions' }))
    await waitFor(() => {
      const rows = table.getAllByRole('row')
      expect(within(rows[2]!).getByText('archived')).toBeVisible() // Week 22, withdrawn
    })
    expect(table.queryByText('published')).toBeNull() // nothing is live any more
    expect(table.getAllByRole('button', { name: /^View/ })).toHaveLength(2) // still viewable
    expect(lastWrite()).toMatchObject({
      path: '/api/v1/forecasting/versions/v-live/archive',
      body: { reason: 'Built on a bad import' },
    })
  })

  // Failure caught: the roster and capacity keeping the withdrawn forecast's numbers on screen.
  it('marks the planner and capacity figures stale, because they rested on the live forecast', async () => {
    versions()
    asRole('planner')
    const u = user()
    const { queryClient } = await renderApp('/forecast')
    queryClient.setQueryData(['capacity', '2026-05-25', 4], { limits: {}, weeks: [] })
    queryClient.setQueryData(['scheduling', 'plan', 1, '2026-05-25'], { cells: {} })

    await u.click(await screen.findByRole('button', { name: /Archive Week 22 for QueueA/ }))
    const form = screen.getByRole('form', { name: 'Archive Week 22' })
    await u.type(within(form).getByLabelText(/Reason/), 'Bad import')
    await u.click(within(form).getByRole('button', { name: /Confirm: archive/ }))

    await waitFor(() => {
      expect(queryClient.getQueryState(['capacity', '2026-05-25', 4])?.isInvalidated).toBe(true)
      expect(
        queryClient.getQueryState(['scheduling', 'plan', 1, '2026-05-25'])?.isInvalidated,
      ).toBe(true)
    })
  })

  it('offers the right action for each status and none for an archived version', async () => {
    versions()
    backend.versions = [...backend.versions, forecastVersion({ id: 'v-old', status: 'archived' })]
    backend.intervals['v-old'] = dayIntervals()
    asRole('planner')
    await renderApp('/forecast')

    await screen.findByRole('table', { name: 'Versions' })
    expect(screen.getAllByRole('button', { name: /^Discard/ })).toHaveLength(1)
    expect(screen.getAllByRole('button', { name: /^Archive/ })).toHaveLength(1)
  })
})

describe('who may retire a forecast', () => {
  it('offers a lead neither action', async () => {
    versions()
    asRole('lead')
    await renderApp('/forecast')

    await screen.findByRole('table', { name: 'Versions' })
    expect(screen.queryByRole('button', { name: /^Discard/ })).toBeNull()
    expect(screen.queryByRole('button', { name: /^Archive/ })).toBeNull()
  })

  it('offers an admin both', async () => {
    versions()
    asRole('admin')
    await renderApp('/forecast')

    expect(await screen.findByRole('button', { name: /^Discard/ })).toBeVisible()
    expect(screen.getByRole('button', { name: /^Archive/ })).toBeVisible()
  })
})
