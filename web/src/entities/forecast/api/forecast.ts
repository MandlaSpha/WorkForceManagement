import { api, unwrap } from '@/shared/api'

import type {
  EventRequest,
  ForecastAccuracy,
  ForecastEvent,
  ForecastInterval,
  ForecastVersion,
  RunForecastRequest,
} from '../model/types'

export async function fetchVersions(queueId: number | null): Promise<ForecastVersion[]> {
  return unwrap(
    await api.GET('/api/v1/forecasting/versions', {
      params: { query: queueId === null ? {} : { queue_id: queueId } },
    }),
  )
}

export async function fetchIntervals(versionId: string): Promise<ForecastInterval[]> {
  return unwrap(
    await api.GET('/api/v1/forecasting/versions/{version_id}/intervals', {
      params: { path: { version_id: versionId } },
    }),
  )
}

export async function fetchAccuracy(queueId: number): Promise<ForecastAccuracy> {
  return unwrap(
    await api.GET('/api/v1/forecasting/accuracy', { params: { query: { queue_id: queueId } } }),
  )
}

export async function runForecast(body: RunForecastRequest): Promise<ForecastVersion> {
  return unwrap(await api.POST('/api/v1/forecasting/versions', { body }))
}

export async function publishVersion(versionId: string): Promise<ForecastVersion> {
  return unwrap(
    await api.POST('/api/v1/forecasting/versions/{version_id}/publish', {
      params: { path: { version_id: versionId } },
    }),
  )
}

export async function fetchEvents(queueId: number | null): Promise<ForecastEvent[]> {
  return unwrap(
    await api.GET('/api/v1/forecasting/events', {
      params: { query: queueId === null ? {} : { queue_id: queueId } },
    }),
  )
}

export async function createEvent(body: EventRequest): Promise<ForecastEvent> {
  return unwrap(await api.POST('/api/v1/forecasting/events', { body }))
}

export async function deleteEvent(eventId: number): Promise<void> {
  unwrap(
    await api.DELETE('/api/v1/forecasting/events/{event_id}', {
      params: { path: { event_id: eventId } },
    }),
  )
}
