import { api, unwrap } from '@/shared/api'

import type { Demand, WorkImport } from '../model/types'

export async function fetchDemand(asOf: string, days: number): Promise<Demand> {
  return unwrap(
    await api.GET('/api/v1/service-desk/demand', { params: { query: { as_of: asOf, days } } }),
  )
}

/** Upload a work-item CSV as multipart form data. The CSRF header is added by the client. */
export async function importWorkItems(file: File): Promise<WorkImport> {
  return unwrap(
    await api.POST('/api/v1/service-desk/imports', {
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

export async function setProductiveMinutes(poolId: number, minutes: number): Promise<void> {
  unwrap(
    await api.PUT('/api/v1/service-desk/pools/{pool_id}', {
      params: { path: { pool_id: poolId } },
      body: { productiveMinutesPerDay: minutes },
    }),
  )
}
