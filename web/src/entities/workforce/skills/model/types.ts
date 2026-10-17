import type { components } from '@/shared/api'

export type Credential = components['schemas']['CredentialOut']
export type CredentialInput = components['schemas']['CredentialIn']
export type Requirement = components['schemas']['RequirementOut']
export type RequirementInput = components['schemas']['RequirementIn']
export type SkillGap = components['schemas']['SkillGapOut']

export const CREDENTIAL_KINDS = ['certification', 'language', 'clearance'] as const

export const KIND_LABEL: Record<string, string> = {
  certification: 'Certification',
  language: 'Language',
  clearance: 'Security clearance',
}
