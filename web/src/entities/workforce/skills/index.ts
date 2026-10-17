export {
  fetchCredentials,
  fetchGaps,
  fetchRequirements,
  saveCredentials,
  saveRequirements,
} from './api/skills'
export { skillKeys, useCredentials, useGaps, useRequirements } from './model/queries'
export { CREDENTIAL_KINDS, KIND_LABEL } from './model/types'
export type {
  Credential,
  CredentialInput,
  Requirement,
  RequirementInput,
  SkillGap,
} from './model/types'
