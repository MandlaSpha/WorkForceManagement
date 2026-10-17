import type { components } from '@/shared/api'

export type WorkloadBalance = components['schemas']['BalanceDayOut']
export type QueueBalance = components['schemas']['BalanceQueueOut']
export type MoveSuggestion = components['schemas']['BalanceMoveOut']

export const STATE_LABEL: Record<string, string> = {
  stretched: 'Stretched',
  slack: 'Slack',
  balanced: 'Balanced',
  unknown: 'No forecast',
}
