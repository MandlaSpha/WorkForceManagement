import userEvent from '@testing-library/user-event'
import { screen, waitFor, within } from '@testing-library/vue'
import { describe, expect, it } from 'vitest'

import type { ReportSchedule } from '@/entities/report-schedule'
import { backend } from '@/test/fake-backend'
import { expectAriaReferencesResolve } from '@/test/aria'
import { openScheduling, seedScheduling } from '@/test/open-scheduling'

const schedule = (over: Partial<ReportSchedule> = {}): ReportSchedule => ({
  id: 1,
  report: 'scorecard',
  queueId: null,
  queue: '',
  recipients: ['boss@example.co.za'],
  frequency: 'daily',
  hour: 7,
  weekday: 0,
  dayOfMonth: 1,
  paused: false,
  lastSentAt: null,
  lastOutcome: '',
  mine: true,
  owner: '',
  ...over,
})

async function open(role = 'planner', rows: ReportSchedule[] = [], domains = ['example.co.za']) {
  seedScheduling()
  backend.schedules = rows
  backend.reportDomains = domains
  return openScheduling('/reports', role)
}

describe('scheduling a report', () => {
  it('sends the report, the time and the addresses one per line, with the CSRF token', async () => {
    const user = userEvent.setup()
    await open()
    const form = await screen.findByRole('form', { name: 'Schedule a report' })
    await user.type(
      within(form).getByLabelText(/Send to/),
      'boss@example.co.za{Enter}ops@example.co.za, finance@example.co.za',
    )
    await user.click(within(form).getByRole('button', { name: 'Schedule report' }))
    await waitFor(() => expect(backend.writes).toHaveLength(1))
    expect(backend.writes[0]).toEqual({
      method: 'POST',
      path: '/api/v1/reports/schedules',
      body: {
        report: 'scorecard',
        queueId: null,
        recipients: ['boss@example.co.za', 'ops@example.co.za', 'finance@example.co.za'],
        frequency: 'daily',
        hour: 7,
        weekday: 0,
        dayOfMonth: 1,
        paused: false,
      },
      csrf: 'test-csrf-token',
    })
    expect(await screen.findByTestId('schedule-result')).toBeVisible()
  })

  it('needs a queue for peaks and troughs and will not send without one', async () => {
    const user = userEvent.setup()
    await open()
    const form = await screen.findByRole('form', { name: 'Schedule a report' })
    await user.click(screen.getByRole('radio', { name: /^Peaks and troughs/ }))
    await user.type(within(form).getByLabelText(/Send to/), 'boss@example.co.za')
    expect(within(form).getByRole('button', { name: 'Schedule report' })).toBeDisabled()
  })

  it('warns that nothing can be sent while no email domain is allowed', async () => {
    // Failure caught: a person scheduling reports that can never go out, with no explanation.
    await open('planner', [], [])
    expect(await screen.findByTestId('no-domains')).toHaveTextContent('Ask your administrator')
  })

  it('shows why a schedule was refused', async () => {
    const user = userEvent.setup()
    await open()
    backend.nextProblem = {
      status: 422,
      code: 'report.domain_not_allowed',
      title: 'Report schedule refused',
      detail: 'x@gmail.com is not on a domain your administrator has allowed.',
    }
    const form = await screen.findByRole('form', { name: 'Schedule a report' })
    await user.type(within(form).getByLabelText(/Send to/), 'x@gmail.com')
    await user.click(within(form).getByRole('button', { name: 'Schedule report' }))
    expect(await screen.findByTestId('schedule-error')).toHaveTextContent('not on a domain')
  })

  it.each(['admin', 'planner', 'executive', 'customer_ops'])(
    'offers %s the board pack, which needs no queue',
    async (role) => {
      // Failure caught: the board pack missing from the choices, or sent with a queue it has none of.
      const user = userEvent.setup()
      await open(role)
      const form = await screen.findByRole('form', { name: 'Schedule a report' })
      await user.click(screen.getByRole('radio', { name: /^Investment-board KPI pack/ }))
      expect(within(form).queryByLabelText('Queue')).toBeNull()
      await user.type(within(form).getByLabelText(/Send to/), 'board@example.co.za')
      await user.click(within(form).getByRole('button', { name: 'Schedule report' }))
      await waitFor(() => expect(backend.writes).toHaveLength(1))
      expect(backend.writes[0]?.body).toMatchObject({ report: 'board', queueId: null })
    },
  )

  it('can start a schedule paused', async () => {
    const user = userEvent.setup()
    await open()
    const form = await screen.findByRole('form', { name: 'Schedule a report' })
    await user.click(within(form).getByRole('checkbox', { name: 'Start paused' }))
    await user.type(within(form).getByLabelText(/Send to/), 'boss@example.co.za')
    await user.click(within(form).getByRole('button', { name: 'Schedule report' }))
    await waitFor(() => expect(backend.writes).toHaveLength(1))
    expect(backend.writes[0]?.body).toMatchObject({ paused: true })
  })

  it('names each report type by its title only, with the blurb as the description', async () => {
    await open()
    const radio = await screen.findByRole('radio', { name: 'Peaks and troughs' })
    expect(radio).toHaveAccessibleDescription(/\S/)
  })

  it('offers the list as a CSV once there is a schedule', async () => {
    await open('planner', [schedule()])
    const link = await screen.findByTestId('schedules-csv')
    expect(link).toHaveAttribute('href', '/api/v1/reports/schedules.csv')
  })

  it('does not offer a lead the board pack', async () => {
    // Failure caught: offering a lead a pack the API will refuse.
    await open('lead')
    await screen.findByRole('form', { name: 'Schedule a report' })
    expect(screen.queryByRole('radio', { name: /^Investment-board KPI pack/ })).toBeNull()
  })

  it('offers a lead only the report a lead may see', async () => {
    // Failure caught: offering a lead a report the API will refuse.
    await open('lead')
    await screen.findByRole('form', { name: 'Schedule a report' })
    const picker = screen.getByRole('radiogroup', { name: 'Report type' })
    expect(
      within(picker)
        .getAllByRole('radio')
        .map((r) => r.getAttribute('value')),
    ).toEqual(['peaks'])
  })
})

describe('the schedules', () => {
  it('says when, to whom and how the last send went', async () => {
    await open('planner', [schedule({ lastOutcome: 'failed' })])
    const row = await screen.findByTestId('schedule-1')
    expect(row).toHaveTextContent('Analytics scorecard')
    expect(row).toHaveTextContent('every day at 07:00')
    expect(row).toHaveTextContent('boss@example.co.za')
    expect(within(row).getByTestId('outcome')).toHaveTextContent('Could not be sent')
  })

  it('says so when there are none', async () => {
    await open()
    expect(await screen.findByTestId('no-schedules')).toBeVisible()
  })

  it('pauses, resumes and deletes with the CSRF token', async () => {
    const user = userEvent.setup()
    await open('planner', [schedule()])
    await user.click(
      await screen.findByRole('button', { name: /^Pause Analytics scorecard schedule/ }),
    )
    await waitFor(() => expect(backend.writes).toHaveLength(1))
    expect(backend.writes[0]).toMatchObject({
      method: 'PATCH',
      path: '/api/v1/reports/schedules/1',
      body: { paused: true },
      csrf: 'test-csrf-token',
    })
    expect(await screen.findByRole('button', { name: /^Resume/ })).toBeVisible()
    await user.click(screen.getByRole('button', { name: /^Delete Analytics scorecard schedule/ }))
    // Failure caught: one stray click deleting a schedule; nothing is sent until it is confirmed.
    expect(backend.writes).toHaveLength(1)
    await user.click(
      within(await screen.findByRole('dialog')).getByRole('button', { name: 'Delete schedule' }),
    )
    await waitFor(() => expect(backend.writes).toHaveLength(2))
    expect(backend.writes[1]).toMatchObject({
      method: 'DELETE',
      path: '/api/v1/reports/schedules/1',
    })
  })

  it('keeps a schedule when the delete is not confirmed', async () => {
    // Failure caught: Keep it (or Escape) still deleting.
    const user = userEvent.setup()
    await open('planner', [schedule()])
    await user.click(await screen.findByRole('button', { name: /^Delete Analytics scorecard/ }))
    await user.click(
      within(await screen.findByRole('dialog')).getByRole('button', { name: 'Keep it' }),
    )
    expect(backend.writes).toHaveLength(0)
    expect(screen.getByTestId('schedule-1')).toBeVisible()
  })

  it('shows the last send as words in a chip and the schedule as a table row', async () => {
    await open('planner', [schedule({ lastOutcome: 'sent', lastSentAt: '2031-03-01T05:00:00Z' })])
    const row = await screen.findByTestId('schedule-1')
    expect(within(row).getByTestId('outcome')).toHaveTextContent('Sent')
    expect(row).not.toHaveTextContent('Not yet')
    expect(screen.getByRole('table')).toBeVisible()
  })

  it('writes a sentence counting scheduled and paused reports', async () => {
    await open('planner', [schedule(), schedule({ id: 2, paused: true })])
    expect(await screen.findByText(/reports? (is|are) scheduled/)).toHaveTextContent(
      '1 report is scheduled to be emailed, and 1 paused.',
    )
  })

  it('offers the report types with a line on what each holds', async () => {
    await open()
    const picker = await screen.findByRole('radiogroup', { name: 'Report type' })
    expect(within(picker).getAllByRole('radio')).toHaveLength(3)
    expect(within(picker).getByText(/Measured, Modelled or Needs data/)).toBeVisible()
    expectAriaReferencesResolve()
  })

  it('shows the weekday row only for a weekly schedule', async () => {
    const user = userEvent.setup()
    await open()
    const form = await screen.findByRole('form', { name: 'Schedule a report' })
    expect(within(form).queryByLabelText('On')).toBeNull()
    await user.selectOptions(within(form).getByLabelText('How often'), 'Every week')
    expect(within(form).getByLabelText('On')).toBeVisible()
  })

  it('tells the admin whose a schedule is, and nobody else', async () => {
    await open('admin', [schedule({ mine: false, owner: 'Pat Planner' })])
    expect(await screen.findByTestId('schedule-1')).toHaveTextContent('made by Pat Planner')
  })
})

describe('allowed domains (admin)', () => {
  it('lets the admin set them, one per line', async () => {
    const user = userEvent.setup()
    await open('admin', [], ['example.co.za'])
    const form = await screen.findByRole('form', { name: 'Allowed email domains' })
    const box = within(form).getByLabelText(/Email domains reports may be sent to/)
    await waitFor(() => expect(box).toHaveValue('example.co.za')) // the saved list loads first
    await user.clear(box)
    await user.type(box, 'example.co.za{Enter}partner.co.za')
    await user.click(within(form).getByRole('button', { name: 'Save domains' }))
    await waitFor(() => expect(backend.writes).toHaveLength(1))
    expect(backend.writes[0]).toMatchObject({
      method: 'PUT',
      path: '/api/v1/reports/settings',
      body: { allowedDomains: ['example.co.za', 'partner.co.za'] },
    })
  })

  it('is not shown to anyone else', async () => {
    await open('planner')
    await screen.findByRole('form', { name: 'Schedule a report' })
    expect(screen.queryByRole('form', { name: 'Allowed email domains' })).toBeNull()
  })

  it.each(['agent'])('keeps %s out', async (role) => {
    await open(role)
    expect(
      await screen.findByRole('heading', { name: "You don't have access to this page" }),
    ).toBeVisible()
  })
})
