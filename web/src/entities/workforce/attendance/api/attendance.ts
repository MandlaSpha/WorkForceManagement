import { api, unwrap } from '@/shared/api'

import type { AttendanceDay, MyAttendance, StateImportReport } from '../model/types'

export async function fetchAdherence(queueId: number, day: string): Promise<AttendanceDay> {
  return unwrap(
    await api.GET('/api/v1/attendance/adherence', {
      params: { query: { queue_id: queueId, day } },
    }),
  )
}

export async function fetchMyAttendance(day: string): Promise<MyAttendance> {
  return unwrap(await api.GET('/api/v1/attendance/mine', { params: { query: { day } } }))
}

/** Upload an agent-state CSV as multipart form data. The CSRF header is added by the client. */
export async function uploadStates(file: File): Promise<StateImportReport> {
  return unwrap(
    await api.POST('/api/v1/attendance/imports', {
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
