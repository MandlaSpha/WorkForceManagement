import type { Attention } from './types'

/** Where each kind of attention item is dealt with. */
export const ATTENTION_ROUTE: Record<string, { path: string; action: string }> = {
  understaffed: { path: '/planner', action: 'Open planner' },
  no_forecast: { path: '/forecast', action: 'Open forecast' },
  assumptions: { path: '/configure', action: 'Open configure' },
  draft_roster: { path: '/roster', action: 'Open roster' },
}

export function attentionRoute(item: Pick<Attention, 'kind'>): { path: string; action: string } {
  return ATTENTION_ROUTE[item.kind] ?? { path: '/planner', action: 'Open planner' }
}

/** How tall a day's bar is, as a share of the worst day. A week with no gap draws no bars. */
export function barShare(gap: number, worst: number): string {
  return worst <= 0 ? '0%' : `${Math.max(2, Math.round((gap / worst) * 100))}%`
}
