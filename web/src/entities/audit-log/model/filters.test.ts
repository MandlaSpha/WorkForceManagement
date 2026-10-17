import { describe, expect, it } from 'vitest'

import { toQuery } from './filters'
import { NO_FILTERS } from './types'

describe('toQuery', () => {
  it('sends nothing for empty filters', () => {
    expect(toQuery(NO_FILTERS)).toEqual({})
  })

  it('turns a South African day range into the instants it covers, end day included', () => {
    const query = toQuery({ ...NO_FILTERS, fromDay: '2026-10-01', toDay: '2026-10-31' })
    // Failure caught: ending the range at midnight of the last day would drop that whole day.
    expect(query.since).toBe('2026-10-01T00:00:00+02:00')
    expect(query.until).toBe('2026-11-01T00:00:00+02:00')
  })

  it('rolls over a year end and trims the actor', () => {
    const query = toQuery({ ...NO_FILTERS, actor: ' amy ', toDay: '2026-12-31' })
    expect(query.actor).toBe('amy')
    expect(query.until).toBe('2027-01-01T00:00:00+02:00')
  })
})
