import type { components } from '@/shared/api'

export type CopilotAnswer = components['schemas']['CopilotAnswerOut']
export type CopilotAction = components['schemas']['CopilotActionOut']
export type CopilotSource = components['schemas']['CopilotSourceOut']

/** The most a question may hold; the API refuses more. */
export const COPILOT_MAX_QUESTION = 300
