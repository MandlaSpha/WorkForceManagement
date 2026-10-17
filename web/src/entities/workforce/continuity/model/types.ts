import type { components } from '@/shared/api'

export type BackupTeam = components['schemas']['BackupTeamOut']
export type BackupPerson = components['schemas']['BackupPersonOut']
export type Mobilise = components['schemas']['MobiliseOut']
export type MobiliseCandidate = components['schemas']['MobiliseCandidateOut']
export type Scenario = 'site' | 'outbreak'

export const SCENARIO_LABEL: Record<Scenario, string> = {
  site: 'A site fails',
  outbreak: 'An outbreak',
}

/** Why a backup person can or cannot cover (the API's answer, in plain words). */
export const COVER_STATUS_LABEL: Record<string, string> = {
  free: 'Free to cover',
  rostered_elsewhere: 'Can cover, but is rostered on another queue',
  already_rostered: 'Already on this roster',
  on_leave: 'On approved leave',
  unavailable: 'Unavailable most of the day',
  needs_office: 'Works from the office only',
}

export const WORK_MODE_LABEL: Record<string, string> = {
  office: 'Office',
  hybrid: 'Hybrid',
  remote: 'Remote',
}
