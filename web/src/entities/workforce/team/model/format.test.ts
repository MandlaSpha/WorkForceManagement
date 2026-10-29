import { describe, expect, it } from 'vitest'

import { contractLine, initials, sortPeople, summaryParts } from './format'
import type { TeamPerson, TeamSummary } from './types'

function person(empNo: string, over: Partial<TeamPerson> = {}): TeamPerson {
  return {
    employeeId: 1,
    empNo,
    name: `Person ${empNo}`,
    contractType: 'permanent',
    contractHours: 40,
    rosteredHours: 40,
    shifts: 5,
    adherencePct: null,
    onTrack: null,
    pendingLeave: 0,
    openSwaps: 0,
    checkIn: false,
    shiftList: [],
    leaveBalances: [],
    pendingRequests: [],
    ...over,
  }
}

const sentence = (s: TeamSummary) =>
  summaryParts(s)
    .map((p) => p.text)
    .join('')

const summary = (over: Partial<TeamSummary>): TeamSummary => ({
  headcount: 6,
  withAdherence: 6,
  onTrack: 4,
  rosteredHours: 220,
  contractHours: 240,
  rosteredPct: 91.7,
  ...over,
})

describe('team formatting', () => {
  it('makes initials from the first and last word', () => {
    expect(initials('Ann Agent')).toBe('AA')
    expect(initials('Ann van der Merwe')).toBe('AM')
    expect(initials('Cher')).toBe('C')
    expect(initials('  ')).toBe('?')
  })

  it('describes the contract without pay', () => {
    expect(contractLine({ contractType: 'seasonal', contractHours: 37.5 })).toBe(
      'Seasonal · 37.5 h a week',
    )
  })

  describe('sorting', () => {
    const people = [
      person('E003', { adherencePct: 80, rosteredHours: 30 }),
      person('E001', { adherencePct: null, rosteredHours: 40 }),
      person('E002', { adherencePct: 95, rosteredHours: 30 }),
    ]
    it('defaults to employee number, which is not a performance order', () => {
      // Failure caught: a default order that ranks people by how well they adhere.
      expect(sortPeople(people, 'az').map((p) => p.empNo)).toEqual(['E001', 'E002', 'E003'])
    })
    it('puts people without adherence data last, never first as a zero', () => {
      expect(sortPeople(people, 'adherence').map((p) => p.empNo)).toEqual(['E002', 'E003', 'E001'])
    })
    it('orders by rostered hours, ties by number, without changing the input', () => {
      expect(sortPeople(people, 'hours').map((p) => p.empNo)).toEqual(['E001', 'E002', 'E003'])
      expect(people.map((p) => p.empNo)).toEqual(['E003', 'E001', 'E002'])
    })
  })

  describe('the summary sentence', () => {
    it('counts on track out of everybody when all have data', () => {
      expect(sentence(summary({}))).toBe(
        '4 of 6 are on track this week; together they are rostered for 92% of contract hours.',
      )
      expect(
        summaryParts(summary({}))
          .filter((p) => p.bold)
          .map((p) => p.text),
      ).toEqual(['4', '6', '92%'])
    })
    it('says so when only some have data', () => {
      expect(sentence(summary({ withAdherence: 5 }))).toContain(
        '4 of 5 people with adherence data are on track',
      )
    })
    it('never claims zero on track when there is no data at all', () => {
      // Failure caught: "0 of 6 are on track" when the agent-state feed was never loaded.
      const text = sentence(summary({ withAdherence: 0, onTrack: 0 }))
      expect(text).toContain('No adherence data for this week yet')
      expect(text).not.toMatch(/0 of 6/)
    })
    it('handles an empty team and missing contract hours', () => {
      expect(sentence(summary({ headcount: 0, withAdherence: 0, onTrack: 0 }))).toBe(
        'Nobody is on this team for this week.',
      )
      expect(sentence(summary({ rosteredPct: null }))).toBe('4 of 6 are on track this week.')
    })
  })
})
