import { api, unwrap } from '@/shared/api'

import type { ImportReport, KpiSummary, Months, QueueInfo } from '../model/types'

export async function fetchMonths(): Promise<Months> {
  return unwrap(await api.GET('/api/v1/telephony/months'))
}

export async function fetchQueues(): Promise<QueueInfo[]> {
  return unwrap(await api.GET('/api/v1/telephony/queues'))
}

export interface QueueSettings {
  slTargetPct: number
  slThresholdS: number
  occupancyCeilingPct: number
  shrinkagePct: number
  /** Leave out to keep what it is. */
  outboundOnly?: boolean
}

/** Set a queue's staffing assumptions and confirm them (admin). */
export async function saveQueueSettings(
  queueId: number,
  settings: QueueSettings,
): Promise<QueueInfo> {
  return unwrap(
    await api.PUT('/api/v1/telephony/queues/{queue_id}/settings', {
      params: { path: { queue_id: queueId } },
      body: settings,
    }),
  )
}

export async function fetchKpis(range: { from: string; to: string }): Promise<KpiSummary> {
  return unwrap(
    await api.GET('/api/v1/telephony/kpis', {
      params: { query: { date_from: range.from, date_to: range.to } },
    }),
  )
}

export async function fetchImports(): Promise<ImportReport[]> {
  return unwrap(await api.GET('/api/v1/telephony/imports'))
}

/** Upload a Call Detail Report as multipart form data. The CSRF header is added by the client. */
export async function uploadReport(file: File): Promise<ImportReport> {
  return unwrap(
    await api.POST('/api/v1/telephony/imports', {
      // The generated type calls a file a string; the serializer sends the real File.
      body: { file: file as unknown as string },
      bodySerializer: (body) => {
        const form = new FormData()
        form.append('file', body.file as unknown as File)
        return form
      },
    }),
  )
}
