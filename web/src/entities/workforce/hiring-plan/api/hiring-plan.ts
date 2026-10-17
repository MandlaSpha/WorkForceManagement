import { api, unwrap } from '@/shared/api'

import type { HiringPlan, HiringPlanBody, HiringPlanSummary } from '../model/types'

export async function fetchPlans(): Promise<HiringPlanSummary[]> {
  return unwrap(await api.GET('/api/v1/capacity/hiring-plans'))
}

export async function fetchPlan(planId: number): Promise<HiringPlan> {
  return unwrap(
    await api.GET('/api/v1/capacity/hiring-plans/{plan_id}', {
      params: { path: { plan_id: planId } },
    }),
  )
}

export async function createPlan(body: HiringPlanBody): Promise<HiringPlan> {
  return unwrap(await api.POST('/api/v1/capacity/hiring-plans', { body }))
}

export async function changePlan(planId: number, body: HiringPlanBody): Promise<HiringPlan> {
  return unwrap(
    await api.PUT('/api/v1/capacity/hiring-plans/{plan_id}', {
      params: { path: { plan_id: planId } },
      body,
    }),
  )
}

export async function deletePlan(planId: number): Promise<void> {
  unwrap(
    await api.DELETE('/api/v1/capacity/hiring-plans/{plan_id}', {
      params: { path: { plan_id: planId } },
    }),
  )
}
