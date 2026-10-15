import { api, unwrap } from '@/shared/api'

import type { AvailabilityBody, AvailabilityWindow } from '../model/types'

export async function fetchAvailability(): Promise<AvailabilityWindow[]> {
  return unwrap(await api.GET('/api/v1/people/availability', { params: { query: {} } }))
}

export async function declareWindow(body: AvailabilityBody): Promise<AvailabilityWindow> {
  return unwrap(await api.POST('/api/v1/people/availability', { body }))
}

export async function removeWindow(windowId: number): Promise<void> {
  unwrap(
    await api.DELETE('/api/v1/people/availability/{window_id}', {
      params: { path: { window_id: windowId } },
    }),
  )
}
