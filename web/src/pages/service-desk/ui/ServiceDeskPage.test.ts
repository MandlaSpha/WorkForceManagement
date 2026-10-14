import userEvent from '@testing-library/user-event'
import { screen, waitFor, within } from '@testing-library/vue'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { backend } from '@/test/fake-backend'
import { openScheduling, seedScheduling } from '@/test/open-scheduling'
import { demandOf, importResult } from '@/test/service-desk-fixtures'
import { interceptWorkImport } from '@/test/work-import'

async function open(role = 'planner') {
  seedScheduling()
  backend.demand = demandOf()
  return openScheduling('/service-desk', role)
}

describe('demand and capacity', () => {
  it('says plainly that this is not Erlang', async () => {
    await open()
    expect(await screen.findByTestId('not-erlang')).toHaveTextContent(/This is not Erlang/)
    expect(screen.getByTestId('not-erlang')).toHaveTextContent(/never the SLA window/)
  })

  it('shows the summary from the server figures, a minimum when something is missing', async () => {
    await open()
    expect(await screen.findByTestId('kpi-fte')).toHaveTextContent('at least 1.10')
    expect(screen.getByTestId('kpi-fte')).toHaveTextContent('over 5 working days')
    expect(screen.getByTestId('kpi-backlog')).toHaveTextContent('30h') // 1800 minutes
    expect(screen.getByTestId('kpi-arriving')).toHaveTextContent('15h') // 900 minutes
    expect(screen.getByTestId('kpi-breached')).toHaveTextContent('1')
    expect(screen.getByTestId('minimum-notice')).toBeVisible()
  })

  it('lists each pool with its effort in hours, most people needed first', async () => {
    await open()
    const sd = await screen.findByTestId('pool-1')
    const col = (name: string) => sd.querySelector(`[data-col="${name}"]`)?.textContent?.trim()
    expect([col('backlog'), col('due'), col('arriving'), col('fte'), col('breached')]).toEqual([
      '24h',
      '12h',
      '15h',
      'at least 0.90',
      '1',
    ])
    const rows = within(screen.getByTestId('pool-table')).getAllByRole('row').slice(1)
    expect(rows.map((r) => within(r).getByRole('rowheader').textContent)).toEqual([
      expect.stringContaining('Service Desk'),
      expect.stringContaining('NOC'),
    ])
  })

  it('says what is missing for a pool', async () => {
    await open()
    expect(await screen.findByText(/1 with no estimate/)).toBeVisible()
    expect(screen.getByText(/1 with no deadline/)).toBeVisible()
  })

  it('shows an unknown arrival rate as a dash, never as no arrivals', async () => {
    await open()
    const noc = await screen.findByTestId('pool-2')
    expect(noc.querySelector('[data-col="arriving"]')?.textContent?.trim()).toBe('\u2014')
    expect(noc.querySelector('[data-col="fte"]')?.textContent?.trim()).toBe('at least 0.20')
  })

  it('shows no minimum notice and no "at least" when everything is known', async () => {
    seedScheduling()
    backend.demand = demandOf({
      complete: true,
      pools: demandOf().pools.map((p) => ({
        ...p,
        complete: true,
        arrivingMin: 60,
        unestimated: 0,
      })),
    })
    await openScheduling('/service-desk')
    expect(await screen.findByTestId('kpi-fte')).toHaveTextContent('1.10')
    expect(screen.getByTestId('kpi-fte')).not.toHaveTextContent('at least')
    expect(screen.queryByTestId('minimum-notice')).toBeNull()
  })

  it('asks for the period chosen, from today', async () => {
    const user = userEvent.setup()
    await open()
    await screen.findByTestId('kpi-fte')
    expect(backend.demandQueries.at(-1)).toMatch(/^\?as_of=\d{4}-\d{2}-\d{2}&days=7$/)

    await user.selectOptions(screen.getByLabelText('Period'), 'Next 28 days')

    await waitFor(() => expect(backend.demandQueries.at(-1)).toMatch(/&days=28$/))
  })

  it('says there is nothing to size, and where work comes from, when there are no pools', async () => {
    seedScheduling()
    backend.demand = demandOf({
      pools: [],
      requiredFte: null,
      backlogMin: 0,
      arrivingMin: null,
      breached: 0,
    })
    await openScheduling('/service-desk')
    const notice = await screen.findByTestId('no-work')
    expect(notice).toHaveTextContent(/nothing to size/)
    expect(notice).toHaveTextContent(/Bring it in/)
  })
})

describe('productive time', () => {
  it('lets a planner change it, with the CSRF token, and marks an unconfirmed default', async () => {
    const user = userEvent.setup()
    await open()
    const form = await screen.findByRole('form', { name: 'Productive minutes for Service Desk' })
    expect(screen.getByTestId('pool-1')).toHaveTextContent('Default, not confirmed')

    const input = within(form).getByLabelText('Productive minutes a day for Service Desk')
    await user.clear(input)
    await user.type(input, '420')
    await user.click(within(form).getByRole('button', { name: 'Save' }))

    await waitFor(() => expect(backend.writes).toHaveLength(1))
    expect(backend.writes[0]).toEqual({
      method: 'PUT',
      path: '/api/v1/service-desk/pools/1',
      body: { productiveMinutesPerDay: 420 },
      csrf: 'test-csrf-token',
    })
  })

  it('shows why it was refused', async () => {
    const user = userEvent.setup()
    await open()
    backend.nextProblem = {
      status: 422,
      code: 'pool.minutes_invalid',
      title: 'Invalid request',
      detail: 'Productive time is between 30 and 600 minutes a day.',
    }
    const form = await screen.findByRole('form', { name: 'Productive minutes for Service Desk' })
    await user.click(within(form).getByRole('button', { name: 'Save' }))
    expect(await screen.findByTestId('minutes-error-1')).toHaveTextContent(/30 and 600/)
  })

  it('is read-only for customer operations, who also get no way to bring work in', async () => {
    await open('customer_ops')
    const sd = await screen.findByTestId('pool-1')
    expect(within(sd).queryByRole('form')).toBeNull()
    expect(sd).toHaveTextContent('360')
    expect(screen.queryByRole('tab', { name: 'Bring in work' })).toBeNull()
  })
})

describe('bringing work in', () => {
  afterEach(() => vi.restoreAllMocks())
  const csv = 'ref,pool,opened\nINC1,Service Desk,2026-05-01 09:00\n'

  it('sends the file with the CSRF token and reports what happened', async () => {
    const user = userEvent.setup()
    await open()
    interceptWorkImport()
    backend.workImport = importResult({ created: 7, updated: 2, unchanged: 5 })

    await user.click(await screen.findByRole('tab', { name: 'Bring in work' }))
    await user.upload(
      screen.getByLabelText('Work items (.csv)'),
      new File([csv], 'items.csv', { type: 'text/csv' }),
    )
    await user.click(screen.getByRole('button', { name: 'Import work items' }))

    await waitFor(() => expect(backend.writes).toHaveLength(1))
    expect(backend.writes[0]).toMatchObject({
      method: 'POST',
      path: '/api/v1/service-desk/imports',
      body: { multipart: true, filePart: true },
      csrf: 'test-csrf-token',
    })
    const result = await screen.findByTestId('work-import-result')
    expect(result).toHaveTextContent('7 added, 2 updated, 5 already up to date')
  })

  it('cannot import before a file is chosen', async () => {
    const user = userEvent.setup()
    await open()
    await user.click(await screen.findByRole('tab', { name: 'Bring in work' }))
    expect(screen.getByRole('button', { name: 'Import work items' })).toBeDisabled()
  })

  it('explains rows that were not kept and columns that were not read', async () => {
    const user = userEvent.setup()
    await open()
    interceptWorkImport()
    backend.workImport = importResult({
      created: 1,
      rejected: { bad_effort: 2, repeated_ref: 1 },
      ignoredColumns: ['requester', 'summary'],
    })

    await user.click(await screen.findByRole('tab', { name: 'Bring in work' }))
    await user.upload(screen.getByLabelText('Work items (.csv)'), new File([csv], 'items.csv'))
    await user.click(screen.getByRole('button', { name: 'Import work items' }))

    const result = within(await screen.findByTestId('work-import-result'))
    expect(result.getByText(/2 with an effort that is not a whole number of minutes/)).toBeVisible()
    expect(result.getByText(/1 with a reference that appears twice/)).toBeVisible()
    expect(result.getByTestId('ignored-columns')).toHaveTextContent('requester, summary')
  })

  it('shows why a file was refused, and no result', async () => {
    const user = userEvent.setup()
    await open()
    interceptWorkImport()
    backend.nextProblem = {
      status: 422,
      code: 'workitems.unreadable',
      title: 'Unusable file',
      detail: 'The header is missing: ref.',
    }

    await user.click(await screen.findByRole('tab', { name: 'Bring in work' }))
    await user.upload(screen.getByLabelText('Work items (.csv)'), new File(['x'], 'bad.csv'))
    await user.click(screen.getByRole('button', { name: 'Import work items' }))

    expect(await screen.findByTestId('work-import-error')).toHaveTextContent(/header is missing/)
    expect(screen.queryByTestId('work-import-result')).toBeNull()
  })
})

describe('who may open it', () => {
  it.each(['planner', 'admin', 'customer_ops'])('opens for %s', async (role) => {
    await open(role)
    expect(await screen.findByTestId('kpi-fte')).toBeVisible()
  })

  it.each(['lead', 'agent', 'executive'])('does not open for %s', async (role) => {
    await open(role)
    expect(
      await screen.findByRole('heading', { name: "You don't have access to this page" }),
    ).toBeVisible()
  })
})
