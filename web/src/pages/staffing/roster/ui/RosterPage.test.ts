import userEvent from '@testing-library/user-event'
import { screen, waitFor, within } from '@testing-library/vue'
import { describe, expect, it } from 'vitest'

import { backend } from '@/test/fake-backend'
import { openScheduling, seedScheduling } from '@/test/open-scheduling'
import { DAYS, rosterOf } from '@/test/scheduling-fixtures'

const MON = DAYS[0]!
const cell = async (name: string, day = 'Mon 25 May') =>
  (await screen.findByLabelText(`Shift for ${name} on ${day}`)) as HTMLSelectElement

describe('the roster grid', () => {
  it('shows each person, their shifts, their hours and how many are on each day', async () => {
    seedScheduling()
    await openScheduling('/roster')

    expect(await cell('Alex Agent')).toHaveValue('2') // D1
    expect(await cell('Alex Agent', 'Tue 26 May')).toHaveValue('2')
    expect(await cell('Sam Planner')).toHaveValue('') // no shift
    expect(screen.getByText(/2d · 16h of 40h/)).toBeVisible()
    expect(screen.getByTestId(`on-${MON}`)).toHaveTextContent('1 on')
    expect(screen.getByTestId(`on-${DAYS[2]}`)).toHaveTextContent('0 on')
  })

  it('offers every shift of the library and a way to clear', async () => {
    seedScheduling()
    await openScheduling('/roster')

    const options = within(await cell('Sam Planner')).getAllByRole('option')
    expect(options.map((o) => o.textContent?.trim())).toEqual(['—', 'E1', 'D1', 'L1', 'N1'])
  })

  it('says what is missing instead of drawing an empty grid', async () => {
    seedScheduling()
    backend.roster = rosterOf({ rows: [] })
    await openScheduling('/roster')
    expect(await screen.findByText(/Nobody is skilled on QueueA yet/)).toBeVisible()
  })

  it('says shifts are needed when the library is empty', async () => {
    seedScheduling()
    backend.roster = rosterOf({ shifts: [] })
    await openScheduling('/roster')
    expect(await screen.findByText(/no shift templates yet/)).toBeVisible()
  })
})

describe('assigning a shift', () => {
  it('sends the queue, person, day and shift with the CSRF token, and shows the result', async () => {
    seedScheduling()
    backend.onAssign = () => {
      // The server accepted it: Sam is now on D1 on Monday.
      backend.roster = rosterOf({
        rows: rosterOf().rows.map((r) =>
          r.employeeId === 11
            ? {
                ...r,
                daysWorked: 1,
                paidMinutes: 480,
                cells: [{ day: MON, shiftId: 2, code: 'D1' }],
              }
            : r,
        ),
        onCounts: { ...rosterOf().onCounts, [MON]: 2 },
      })
    }
    const user = userEvent.setup()
    await openScheduling('/roster')

    await user.selectOptions(await cell('Sam Planner'), 'D1')

    await waitFor(() => expect(backend.writes).toHaveLength(1))
    expect(backend.writes[0]).toEqual({
      method: 'PUT',
      path: '/api/v1/scheduling/roster/assignments',
      body: { queueId: 1, employeeId: 11, day: MON, templateId: 2 },
      csrf: 'test-csrf-token',
    })
    await waitFor(() => expect(screen.getByTestId(`on-${MON}`)).toHaveTextContent('2 on'))
    expect(await cell('Sam Planner')).toHaveValue('2')
  })

  it('clears a shift by choosing the dash', async () => {
    seedScheduling()
    const user = userEvent.setup()
    await openScheduling('/roster')

    await user.selectOptions(await cell('Alex Agent'), '—')

    await waitFor(() => expect(backend.writes).toHaveLength(1))
    expect(backend.writes[0]?.body).toEqual({
      queueId: 1,
      employeeId: 10,
      day: MON,
      templateId: null,
    })
  })

  it('puts the cell back and says why when the server refuses the change', async () => {
    seedScheduling()
    backend.nextProblem = {
      status: 422,
      code: 'roster.rest_period',
      title: 'Roster change refused',
      detail: 'This would leave less than 11 hours of rest between shifts.',
    }
    const user = userEvent.setup()
    await openScheduling('/roster')
    const select = await cell('Sam Planner')

    await user.selectOptions(select, 'L1')

    const notice = await screen.findByTestId('assign-refusal')
    expect(notice).toHaveTextContent(/That change was not made/)
    expect(notice).toHaveTextContent(/11 hours of rest/)
    // The grid must not keep showing a shift the server did not accept.
    expect(select).toHaveValue('')
  })

  it('clears the old refusal once a later change is accepted', async () => {
    seedScheduling()
    backend.nextProblem = {
      status: 422,
      code: 'roster.over_hours',
      title: 'Roster change refused',
      detail: 'Over the contract hours.',
    }
    const user = userEvent.setup()
    await openScheduling('/roster')

    await user.selectOptions(await cell('Sam Planner'), 'L1')
    await screen.findByTestId('assign-refusal')
    await user.selectOptions(await cell('Sam Planner'), 'E1')

    await waitFor(() => expect(screen.queryByTestId('assign-refusal')).toBeNull())
  })
})

describe('publishing', () => {
  it('publishes the week and locks the grid', async () => {
    seedScheduling()
    const user = userEvent.setup()
    await openScheduling('/roster')

    await user.click(await screen.findByRole('button', { name: 'Publish' }))

    await waitFor(() => expect(screen.getByTestId('roster-status')).toHaveTextContent('published'))
    expect(backend.writes[0]).toMatchObject({
      path: '/api/v1/scheduling/roster/publish',
      body: { queueId: 1, weekStart: '2026-05-25' },
      csrf: 'test-csrf-token',
    })
    expect(await cell('Sam Planner')).toBeDisabled()
    expect(screen.getByText(/published, so it is locked/)).toBeVisible()
  })

  it('shows a published week locked, and returning it to draft unlocks it', async () => {
    seedScheduling()
    backend.roster = rosterOf({ status: 'published' })
    const user = userEvent.setup()
    await openScheduling('/roster')
    expect(await cell('Alex Agent')).toBeDisabled()

    await user.click(await screen.findByRole('button', { name: 'Return to draft' }))

    await waitFor(async () => expect(await cell('Alex Agent')).toBeEnabled())
    expect(screen.getByTestId('roster-status')).toHaveTextContent('draft')
  })

  it('shows why publishing was refused', async () => {
    seedScheduling()
    backend.nextProblem = {
      status: 422,
      code: 'roster.empty',
      title: 'Roster change refused',
      detail: 'There are no shifts to publish.',
    }
    const user = userEvent.setup()
    await openScheduling('/roster')

    await user.click(await screen.findByRole('button', { name: 'Publish' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/no shifts to publish/)
    expect(screen.getByTestId('roster-status')).toHaveTextContent('draft')
  })
})

describe('who may change the roster', () => {
  it('lets a lead read it but gives them no way to change or publish it', async () => {
    seedScheduling()
    await openScheduling('/roster', 'lead')

    expect(await cell('Alex Agent')).toBeDisabled()
    expect(await cell('Sam Planner')).toBeDisabled()
    expect(screen.getByText(/Planners and admins build it/)).toBeVisible()
    expect(screen.queryByRole('button', { name: 'Publish' })).toBeNull()
    expect(backend.writes).toEqual([])
  })

  it.each(['agent', 'executive', 'customer_ops'])('does not open for %s', async (role) => {
    seedScheduling()
    await openScheduling('/roster', role)
    expect(
      await screen.findByRole('heading', { name: "You don't have access to this page" }),
    ).toBeVisible()
  })
})

describe('export', () => {
  it('links to the CSV for this queue and week', async () => {
    seedScheduling()
    await openScheduling('/roster')
    const link = await screen.findByRole('link', { name: 'Export CSV' })
    expect(link).toHaveAttribute(
      'href',
      '/api/v1/scheduling/roster/export.csv?queue_id=1&week_start=2026-05-25',
    )
  })
})

describe('breaks and activities', () => {
  const lunch = {
    id: 5,
    assignmentId: 1,
    employeeId: 10,
    employee: 'Alex Agent',
    day: MON,
    shift: 'D1',
    kind: 'lunch',
    startTime: '12:00',
    endTime: '13:00',
    slots: 2,
    offsetSlots: 6,
  }

  it("lists the week's breaks in clock time", async () => {
    seedScheduling()
    backend.activities = [lunch]
    await openScheduling('/roster')
    expect(await screen.findByTestId('activity-5')).toHaveTextContent(
      'Alex Agent, Mon 25 May: Lunch 12:00 to 13:00',
    )
  })

  it('adds one for a chosen person, day and time with the CSRF token', async () => {
    const user = userEvent.setup()
    seedScheduling()
    await openScheduling('/roster')
    const form = await screen.findByRole('form', { name: 'Add a break or activity' })
    await user.selectOptions(within(form).getByLabelText('Person'), 'Alex Agent')
    await user.selectOptions(within(form).getByLabelText('Day'), MON)
    await user.selectOptions(within(form).getByLabelText('What'), 'Training')
    await user.selectOptions(within(form).getByLabelText('For'), '60')
    await user.click(within(form).getByRole('button', { name: 'Add' }))
    await waitFor(() => expect(backend.writes).toHaveLength(1))
    expect(backend.writes[0]).toEqual({
      method: 'POST',
      path: '/api/v1/scheduling/roster/activities',
      body: {
        queueId: 1,
        employeeId: 10,
        day: MON,
        kind: 'training',
        startTime: '12:00',
        minutes: 60,
      },
      csrf: 'test-csrf-token',
    })
  })

  it('cannot add until a person and a day are chosen', async () => {
    seedScheduling()
    await openScheduling('/roster')
    const form = await screen.findByRole('form', { name: 'Add a break or activity' })
    expect(within(form).getByRole('button', { name: 'Add' })).toBeDisabled()
  })

  it('shows why one was refused', async () => {
    const user = userEvent.setup()
    seedScheduling()
    await openScheduling('/roster')
    backend.nextProblem = {
      status: 422,
      code: 'activity.outside_shift',
      title: 'Activity refused',
      detail: 'That falls outside the shift.',
    }
    const form = await screen.findByRole('form', { name: 'Add a break or activity' })
    await user.selectOptions(within(form).getByLabelText('Person'), 'Alex Agent')
    await user.selectOptions(within(form).getByLabelText('Day'), MON)
    await user.click(within(form).getByRole('button', { name: 'Add' }))
    expect(await screen.findByTestId('activity-error')).toHaveTextContent('outside the shift')
  })

  it('removes one', async () => {
    const user = userEvent.setup()
    seedScheduling()
    backend.activities = [lunch]
    await openScheduling('/roster')
    await user.click(await screen.findByRole('button', { name: /^Remove Alex Agent/ }))
    await waitFor(() => expect(backend.writes).toHaveLength(1))
    expect(backend.writes[0]).toMatchObject({
      method: 'DELETE',
      path: '/api/v1/scheduling/roster/activities/5',
    })
  })

  it('lets a lead read them but not change them', async () => {
    seedScheduling()
    backend.activities = [lunch]
    await openScheduling('/roster', 'lead')
    expect(await screen.findByTestId('activity-5')).toBeVisible()
    expect(screen.queryByRole('form', { name: 'Add a break or activity' })).toBeNull()
    expect(screen.queryByRole('button', { name: /^Remove/ })).toBeNull()
  })
})
