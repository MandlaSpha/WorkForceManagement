import type { TeamPerson, TeamSort, TeamSummary } from './types'

/** Up to two letters for the avatar: first and last word of the name. */
export function initials(name: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean)
  if (words.length === 0) return '?'
  const first = words[0]!.charAt(0)
  const last = words.length > 1 ? words[words.length - 1]!.charAt(0) : ''
  return (first + last).toUpperCase()
}

export function hoursText(hours: number): string {
  return `${Number.isInteger(hours) ? hours : hours.toFixed(1)} h`
}

const CONTRACT_LABEL: Record<string, string> = { permanent: 'Permanent', seasonal: 'Seasonal' }

export function contractLine(person: Pick<TeamPerson, 'contractType' | 'contractHours'>): string {
  const label = CONTRACT_LABEL[person.contractType] ?? 'Contract'
  return `${label} · ${hoursText(person.contractHours)} a week`
}

/** Order the people as the viewer asked. Adherence and hours are highest first with the people
 * who have no adherence data last; ties and the default fall back to employee number. */
export function sortPeople(people: readonly TeamPerson[], sort: TeamSort): TeamPerson[] {
  const byNumber = (a: TeamPerson, b: TeamPerson) => a.empNo.localeCompare(b.empNo, 'en-ZA')
  const copy = [...people]
  if (sort === 'adherence') {
    return copy.sort((a, b) => {
      if (a.adherencePct === null && b.adherencePct === null) return byNumber(a, b)
      if (a.adherencePct === null) return 1
      if (b.adherencePct === null) return -1
      return b.adherencePct - a.adherencePct || byNumber(a, b)
    })
  }
  if (sort === 'hours') {
    return copy.sort((a, b) => b.rosteredHours - a.rosteredHours || byNumber(a, b))
  }
  return copy.sort(byNumber)
}

export interface SummaryPart {
  text: string
  bold: boolean
}

/** The one sentence under the title, as parts so the numbers can be bold without v-html. */
export function summaryParts(summary: TeamSummary): SummaryPart[] {
  const t = (text: string): SummaryPart => ({ text, bold: false })
  const b = (text: string): SummaryPart => ({ text, bold: true })
  if (summary.headcount === 0) return [t('Nobody is on this team for this week.')]
  const parts: SummaryPart[] = []
  if (summary.withAdherence === 0) {
    // Never "0 are on track": with no feed there is nothing to be on or off track against.
    parts.push(t('No adherence data for this week yet'))
  } else if (summary.withAdherence === summary.headcount) {
    parts.push(b(String(summary.onTrack)), t(' of '), b(String(summary.headcount)))
    parts.push(t(' are on track this week'))
  } else {
    parts.push(b(String(summary.onTrack)), t(' of '), b(String(summary.withAdherence)))
    parts.push(t(' people with adherence data are on track this week'))
  }
  if (summary.rosteredPct !== null) {
    parts.push(t('; together they are rostered for '), b(`${Math.round(summary.rosteredPct)}%`))
    parts.push(t(' of contract hours'))
  }
  parts.push(t('.'))
  return parts
}

export function dayLabel(iso: string): string {
  return new Intl.DateTimeFormat('en-ZA', {
    timeZone: 'UTC',
    weekday: 'short',
    day: 'numeric',
    month: 'short',
  }).format(new Date(`${iso}T00:00:00Z`))
}
