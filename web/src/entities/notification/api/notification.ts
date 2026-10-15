import { api, unwrap } from '@/shared/api'

import type { Inbox, Notification } from '../model/types'

export async function fetchInbox(): Promise<Inbox> {
  return unwrap(await api.GET('/api/v1/notifications'))
}

export async function markNotificationRead(id: number): Promise<Notification> {
  return unwrap(
    await api.POST('/api/v1/notifications/{notification_id}/read', {
      params: { path: { notification_id: id } },
    }),
  )
}

export async function markAllNotificationsRead(): Promise<void> {
  unwrap(await api.POST('/api/v1/notifications/read-all'))
}
