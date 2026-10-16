import userEvent from '@testing-library/user-event'
import { screen, waitFor } from '@testing-library/vue'
import { describe, expect, it } from 'vitest'

import { backend } from '@/test/fake-backend'
import { openScheduling, seedScheduling } from '@/test/open-scheduling'

async function open() {
  seedScheduling()
  const user = userEvent.setup()
  await openScheduling('/configure', 'admin')
  await user.click(await screen.findByRole('tab', { name: 'Rules' }))
  await screen.findByRole('form', { name: 'Compliance rules' })
  return user
}

describe('compliance rules', () => {
  it('starts from the rules in force and says when they are the built-in defaults', async () => {
    await open()
    expect(await screen.findByTestId('rules-in-force')).toHaveTextContent(
      '11 h rest, at most 6 days in a row, no weekly cap (built-in defaults)',
    )
    expect(screen.getByLabelText('Rest between shifts (hours)')).toHaveValue(11)
    expect(screen.getByLabelText(/Weekly hours cap/)).toHaveValue(null)
  })

  it('sends numbers, the start day and a blank cap as none, with the CSRF token', async () => {
    const user = await open()
    const rest = await screen.findByLabelText('Rest between shifts (hours)')
    await user.clear(rest)
    await user.type(rest, '12')
    await user.click(screen.getByRole('button', { name: 'Save rules' }))
    await waitFor(() => expect(backend.writes).toHaveLength(1))
    // Failure caught: numbers sent as text, or an empty cap sent as 0 (which would refuse every shift).
    expect(backend.writes[0]).toMatchObject({
      method: 'PUT',
      path: '/api/v1/scheduling/compliance-rules',
      body: {
        minRestHours: 12,
        maxConsecutiveDays: 6,
        maxWeeklyHours: null,
        overtimeMultiplier: 1.5,
        sundayMultiplier: 2,
        holidayMultiplier: 2,
      },
      csrf: 'test-csrf-token',
    })
    expect(await screen.findByTestId('rules-saved')).toBeVisible()
  })

  it('sends a cap when one is typed', async () => {
    const user = await open()
    await user.type(await screen.findByLabelText(/Weekly hours cap/), '45')
    await user.click(screen.getByRole('button', { name: 'Save rules' }))
    await waitFor(() => expect(backend.writes).toHaveLength(1))
    expect(backend.writes[0]?.body).toMatchObject({ maxWeeklyHours: 45 })
  })

  it('saves a loosened rule but says it is below the statutory minimum', async () => {
    // Failure caught: a rule loosened past the law with no word to the admin.
    const user = await open()
    backend.rulesWarnings = ['Rest of 9 hours is below the statutory 11.']
    await user.click(await screen.findByRole('button', { name: 'Save rules' }))
    expect(await screen.findByTestId('rules-saved-warning')).toHaveTextContent(
      'Saved, but: Rest of 9 hours is below the statutory 11.',
    )
    expect(screen.queryByTestId('rules-saved')).toBeNull()
  })

  it('shows the warning for the rules already in force', async () => {
    seedScheduling()
    backend.rules = {
      ...backend.rules,
      warnings: ['7 days in a row is above the statutory 6.'],
    }
    const user = userEvent.setup()
    await openScheduling('/configure', 'admin')
    await user.click(await screen.findByRole('tab', { name: 'Rules' }))
    expect(await screen.findByTestId('rules-warning')).toHaveTextContent('7 days in a row')
  })

  it('lists the versions', async () => {
    seedScheduling()
    backend.rules = {
      ...backend.rules,
      versions: [
        {
          effectiveFrom: '2027-03-01',
          minRestHours: 12,
          maxConsecutiveDays: 5,
          maxWeeklyHours: 45,
          overtimeMultiplier: 1.5,
          sundayMultiplier: 2,
          holidayMultiplier: 2,
        },
      ],
    }
    const user = userEvent.setup()
    await openScheduling('/configure', 'admin')
    await user.click(await screen.findByRole('tab', { name: 'Rules' }))
    expect(await screen.findByRole('list', { name: 'Rule versions' })).toHaveTextContent(
      'From 2027-03-01: 12 h rest, at most 5 days in a row, weekly cap 45 h',
    )
  })

  it('shows why the rules were refused', async () => {
    const user = await open()
    backend.nextProblem = {
      status: 422,
      code: 'rules.in_the_past',
      title: 'Rule refused',
      detail: 'Rules can only start today or later.',
    }
    await user.click(await screen.findByRole('button', { name: 'Save rules' }))
    expect(await screen.findByTestId('rules-error')).toHaveTextContent('today or later')
  })

  it('shows what overtime pays and sends the three multipliers as numbers', async () => {
    // Failure caught: pay rates typed on the screen but sent as text or dropped.
    const user = await open()
    expect(await screen.findByTestId('rules-pay')).toHaveTextContent(
      '1.5x on a weekday, 2x on a Sunday, 2x on a public holiday',
    )
    const overtime = screen.getByLabelText('Overtime pay (times the hourly rate)')
    await user.clear(overtime)
    await user.type(overtime, '1.75')
    const holiday = screen.getByLabelText('Public holiday pay (times the hourly rate)')
    await user.clear(holiday)
    await user.type(holiday, '3')
    await user.click(screen.getByRole('button', { name: 'Save rules' }))
    await waitFor(() => expect(backend.writes).toHaveLength(1))
    expect(backend.writes[0]?.body).toMatchObject({
      overtimeMultiplier: 1.75,
      sundayMultiplier: 2,
      holidayMultiplier: 3,
    })
  })
})
