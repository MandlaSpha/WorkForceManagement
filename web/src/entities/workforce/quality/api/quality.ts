import { api, unwrap } from '@/shared/api'

import type { QualityImportReport, QualityPerson, QualityTeam } from '../model/types'

export async function fetchQualityTeam(days: number): Promise<QualityTeam> {
  return unwrap(await api.GET('/api/v1/quality/team', { params: { query: { days } } }))
}

export async function fetchQualityPerson(employeeId: number, days: number): Promise<QualityPerson> {
  return unwrap(
    await api.GET('/api/v1/quality/people/{employee_id}', {
      params: { path: { employee_id: employeeId }, query: { days } },
    }),
  )
}

export async function fetchMyQuality(days: number): Promise<QualityPerson> {
  return unwrap(await api.GET('/api/v1/quality/mine', { params: { query: { days } } }))
}

/** Upload a quality file (.csv or .xlsx) as multipart form data. The CSRF header is added by the
 * client. */
export async function uploadQuality(file: File): Promise<QualityImportReport> {
  return unwrap(
    await api.POST('/api/v1/quality/imports', {
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
