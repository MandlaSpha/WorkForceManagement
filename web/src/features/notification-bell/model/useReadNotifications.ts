import { useMutation, useQueryClient } from '@tanstack/vue-query'

import {
  markAllNotificationsRead,
  markNotificationRead,
  notificationKeys,
} from '@/entities/notification'
import { refreshQueries } from '@/shared/lib/refresh'

export function useReadNotifications() {
  const queryClient = useQueryClient()
  const refresh = () => refreshQueries(queryClient, notificationKeys.all)
  return {
    readOne: useMutation({ mutationFn: markNotificationRead, onSuccess: refresh }),
    readAll: useMutation({ mutationFn: markAllNotificationsRead, onSuccess: refresh }),
  }
}
