import { fireEvent, screen, waitFor } from '@testing-library/vue'
import { describe, expect, it } from 'vitest'

import { backend } from '@/test/fake-backend'
import { openScheduling, seedScheduling } from '@/test/open-scheduling'

async function open(role = 'planner') {
  seedScheduling()
  backend.shrinkage = {
    month: '2031-03-01',
    unplannedMeasured: false,
    teams: [
      {
        team: 'Sam Lead',
        people: 3,
        contractedHours: '480.0',
        awayHours: '48.0',
        plannedPct: '10.0',
        assumedPct: '30.00',
      },
      {
        team: 'No lead',
        people: 1,
        contractedHours: '0.0',
        awayHours: '0.0',
        plannedPct: null,
        assumedPct: null,
      },
    ],
  } as never
  return openScheduling('/shrinkage', role)
}

describe('shrinkage', () => {
  it('shows planned shrinkage by team and says unplanned is not measured', async () => {
    // Failure caught: an unmeasured figure presented as a measurement.
    await open()
    const row = await screen.findByTestId('team-Sam Lead')
    expect(row).toHaveTextContent('10.0%')
    expect(row).toHaveTextContent('30.0%')
    expect(screen.getByTestId('unplanned-note')).toHaveTextContent('not guessed')
  })

  it('shows a dash, not 0%, when a team has no contracted hours', async () => {
    // Failure caught: "no share" shown as a good 0%.
    await open()
    expect(await screen.findByTestId('team-No lead')).toHaveTextContent('-')
    expect(
      screen.getByTestId('team-No lead').querySelector('[data-testid=planned]'),
    ).toHaveTextContent(/^-$/)
  })

  it('asks for the month chosen, as its first day', async () => {
    await open()
    await screen.findByTestId('team-Sam Lead')
    await fireEvent.update(screen.getByLabelText('Month'), '2031-03')
    await waitFor(() => expect(backend.shrinkageQueries).toContain('2031-03-01'))
  })

  it.each(['agent', 'executive', 'customer_ops'])('keeps %s out', async (role) => {
    await open(role)
    expect(
      await screen.findByRole('heading', { name: "You don't have access to this page" }),
    ).toBeVisible()
  })
})
