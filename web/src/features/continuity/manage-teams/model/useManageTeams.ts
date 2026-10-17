import { useMutation, useQueryClient } from '@tanstack/vue-query'

import {
  addMember,
  continuityKeys,
  createTeam,
  deleteTeam,
  removeMember,
} from '@/entities/workforce/continuity'
import { refreshQueries } from '@/shared/lib/refresh'

/** Every write refreshes the team lists and the mobilise answer, which is built from them. */
export function useManageTeams() {
  const client = useQueryClient()
  const done = () => refreshQueries(client, continuityKeys.all)
  return {
    create: useMutation({
      mutationFn: (v: { queueId: number; name: string }) => createTeam(v.queueId, v.name),
      onSuccess: done,
    }),
    remove: useMutation({ mutationFn: (teamId: number) => deleteTeam(teamId), onSuccess: done }),
    add: useMutation({
      mutationFn: (v: { teamId: number; employeeId: number }) => addMember(v.teamId, v.employeeId),
      onSuccess: done,
    }),
    drop: useMutation({
      mutationFn: (v: { teamId: number; employeeId: number }) =>
        removeMember(v.teamId, v.employeeId),
      onSuccess: done,
    }),
  }
}
