import type { AuditFilters } from './types'

/** South Africa keeps +02:00 all year (no daylight saving), so a local day is a fixed UTC span. */
const OFFSET = '+02:00'

function nextDay(day: string): string {
  const d = new Date(`${day}T12:00:00Z`)
  d.setUTCDate(d.getUTCDate() + 1)
  return d.toISOString().slice(0, 10)
}

/** The query the API understands: a day range becomes the instants it covers, in South African
 * time. Empty filters are left out so they are not sent at all. */
export function toQuery(filters: AuditFilters): Record<string, string> {
  const query: Record<string, string> = {}
  const text = {
    actor: filters.actor.trim(),
    action: filters.action,
    entityType: filters.entityType,
    outcome: filters.outcome,
  }
  for (const [key, value] of Object.entries(text)) if (value) query[key] = value
  if (filters.fromDay) query.since = `${filters.fromDay}T00:00:00${OFFSET}`
  if (filters.toDay) query.until = `${nextDay(filters.toDay)}T00:00:00${OFFSET}`
  return query
}
