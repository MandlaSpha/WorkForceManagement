import { api, unwrap } from '@/shared/api'

import type { CopilotAnswer } from '../model/types'

/** One question, one answer. The server keeps no conversation: the page does, in memory only. */
export async function askCopilot(question: string): Promise<CopilotAnswer> {
  return unwrap(await api.POST('/api/v1/copilot/ask', { body: { question } }))
}
