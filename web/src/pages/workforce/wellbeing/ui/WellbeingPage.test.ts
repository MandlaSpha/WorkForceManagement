import { screen } from '@testing-library/vue'
import { describe, expect, it } from 'vitest'

import { flagText } from '@/entities/workforce/wellbeing'
import { backend } from '@/test/fake-backend'
import { openScheduling, seedScheduling } from '@/test/open-scheduling'

describe('wellbeing', () => {
  it('shows each prompt as a plain fact, with no score or ranking', async () => {
    // Failure caught: a number or ordering that ranks people, or a code shown raw.
    seedScheduling()
    backend.wellbeing = {
      asOf: '2026-06-15',
      people: [
        {
          employeeId: 10,
          empNo: 'E001',
          employee: 'Alex Agent',
          flags: [
            { code: 'long_run', value: 8 },
            { code: 'repeated_overtime', value: 5 },
          ],
        },
      ],
    }
    await openScheduling('/wellbeing', 'lead')
    const card = await screen.findByTestId('person-E001')
    expect(card).toHaveTextContent('8 days worked in a row')
    expect(card).toHaveTextContent('Overtime on 5 different days in the last four weeks')
    expect(card).not.toHaveTextContent('long_run')
    expect(screen.getByTestId('how-it-works')).toHaveTextContent('not a score')
    expect(screen.queryByText(/score:|rank|risk level/i)).toBeNull()
  })

  it('says so when nobody has a prompt', async () => {
    seedScheduling()
    backend.wellbeing = { asOf: '2026-06-15', people: [] }
    await openScheduling('/wellbeing', 'planner')
    expect(await screen.findByTestId('nobody')).toHaveTextContent('2026-06-15')
  })

  it('shows the refusal when the API says no', async () => {
    seedScheduling()
    backend.wellbeing = null
    await openScheduling('/wellbeing', 'planner')
    expect(await screen.findByTestId('wellbeing-error')).toBeVisible()
  })

  it('is not in the menu or reachable for an agent', async () => {
    // Failure caught: the screen shown to the very people it is about, or to peers.
    seedScheduling()
    backend.wellbeing = { asOf: '2026-06-15', people: [] }
    await openScheduling('/wellbeing', 'agent')
    expect(screen.queryByTestId('how-it-works')).toBeNull()
  })
})

describe('flagText', () => {
  it('has words for every code the API sends and a safe fallback', () => {
    for (const code of ['long_run', 'no_rest', 'repeated_overtime', 'rising_absence']) {
      expect(flagText(code, 3)).not.toBe('Worth a conversation')
    }
    expect(flagText('no_rest', 1)).toBe('1 day off in the last fortnight')
    expect(flagText('mystery', 1)).toBe('Worth a conversation')
  })
})
