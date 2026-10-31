import { api, unwrap } from '@/shared/api'

import type {
  Backtest,
  EventRequest,
  ForecastAccuracy,
  ForecastMethod,
  ForecastEvent,
  ForecastInterval,
  ForecastJob,
  ForecastRange,
  ForecastVersion,
  RunForecastRequest,
  ScenarioRequest,
  ScenarioResult,
  Tuning,
  TuningRequest,
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

export async function fetchRange(
  versionId: string,
  from: string,
  to: string,
  detail: boolean,
): Promise<ForecastRange> {
  return unwrap(
    await api.GET('/api/v1/forecasting/versions/{version_id}/range', {
      params: {
        path: { version_id: versionId },
        query: { date_from: from, date_to: to, detail },
      },
    }),
  )
}

export async function fetchAccuracy(
  queueId: number,
  method: ForecastMethod = 'baseline',
): Promise<ForecastAccuracy> {
  return unwrap(
    await api.GET('/api/v1/forecasting/accuracy', {
      params: { query: { queue_id: queueId, method } },
    }),
  )
}

/** Queue the forecast for the worker; the job says when the draft exists. */
export async function startForecast(body: RunForecastRequest): Promise<ForecastJob> {
  return unwrap(await api.POST('/api/v1/forecasting/versions/jobs', { body }))
}

export async function publishVersion(versionId: string): Promise<ForecastVersion> {
  return unwrap(
    await api.POST('/api/v1/forecasting/versions/{version_id}/publish', {
      params: { path: { version_id: versionId } },
    }),
  )
}

/** Delete a draft that was never published. The reason goes to the audit trail. */
export async function discardVersion(versionId: string, reason: string): Promise<void> {
  unwrap(
    await api.POST('/api/v1/forecasting/versions/{version_id}/discard', {
      params: { path: { version_id: versionId } },
      body: { reason },
    }),
  )
}

/** Withdraw the live forecast: the queue then has none. */
export async function archiveVersion(versionId: string, reason: string): Promise<ForecastVersion> {
  return unwrap(
    await api.POST('/api/v1/forecasting/versions/{version_id}/archive', {
      params: { path: { version_id: versionId } },
      body: { reason },
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

export async function runScenario(body: ScenarioRequest): Promise<ScenarioResult> {
  return unwrap(await api.POST('/api/v1/forecasting/scenarios', { body }))
}

export interface TuningTrial {
  weeks?: number
  decay?: number
  volumeMultiplier?: number
  ahtMultiplier?: number
}

export async function fetchTuning(queueId: number): Promise<Tuning> {
  return unwrap(
    await api.GET('/api/v1/forecasting/tuning', { params: { query: { queue_id: queueId } } }),
  )
}

export async function saveTuning(body: TuningRequest): Promise<Tuning> {
  return unwrap(await api.PUT('/api/v1/forecasting/tuning', { body }))
}

/** Score a tuning that has not been saved; anything left out is the saved value. */
export async function fetchBacktest(queueId: number, trial: TuningTrial): Promise<Backtest> {
  return unwrap(
    await api.GET('/api/v1/forecasting/tuning/backtest', {
      params: {
        query: {
          queue_id: queueId,
          weeks: trial.weeks,
          decay: trial.decay,
          volume_multiplier: trial.volumeMultiplier,
          aht_multiplier: trial.ahtMultiplier,
        },
      },
    }),
  )
}
