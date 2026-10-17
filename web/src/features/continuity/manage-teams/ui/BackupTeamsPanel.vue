<script setup lang="ts">
import { computed, ref } from 'vue'

import { useEmployees } from '@/entities/scheduling'
import { WORK_MODE_LABEL, useBackupTeams } from '@/entities/workforce/continuity'
import { problemMessage } from '@/shared/api'
import AppButton from '@/shared/ui/AppButton.vue'
import NoticeBox from '@/shared/ui/NoticeBox.vue'
import SelectField from '@/shared/ui/SelectField.vue'
import TextField from '@/shared/ui/TextField.vue'

import { useManageTeams } from '../model/useManageTeams'

const props = defineProps<{ queueId: number; canEdit: boolean }>()

const queueRef = computed(() => props.queueId)
const teams = useBackupTeams(queueRef)
// Only a planner or admin picks people, so only they load the whole employee list.
const employees = useEmployees(
  null,
  computed(() => props.canEdit),
)
const manage = useManageTeams()

const newName = ref('')
const picked = ref<Record<number, string>>({})
const failure = ref('')

const options = computed(() =>
  (employees.data.value ?? []).map((e) => ({
    value: String(e.id),
    label: `${e.name} (${e.empNo})`,
  })),
)

async function attempt(work: () => Promise<unknown>): Promise<void> {
  failure.value = ''
  try {
    await work()
  } catch (problem) {
    failure.value = problemMessage(problem)
  }
}

const create = () =>
  attempt(async () => {
    await manage.create.mutateAsync({ queueId: props.queueId, name: newName.value })
    newName.value = ''
  })

const add = (teamId: number) =>
  attempt(async () => {
    const chosen = picked.value[teamId]
    if (!chosen) return
    await manage.add.mutateAsync({ teamId, employeeId: Number(chosen) })
    picked.value[teamId] = ''
  })
</script>

<template>
  <section class="space-y-3" aria-labelledby="teams-title" data-testid="backup-teams">
    <h2 id="teams-title" class="text-base font-semibold text-ink">Backup teams</h2>
    <p v-if="teams.isPending.value" class="text-sm text-ink-muted">Loading…</p>
    <NoticeBox v-else-if="teams.isError.value" tone="danger">
      Could not load the backup teams. {{ problemMessage(teams.error.value) }}
    </NoticeBox>
    <NoticeBox v-else-if="(teams.data.value ?? []).length === 0" data-testid="no-teams">
      No backup team is named for this queue yet.
    </NoticeBox>
    <ul v-else class="grid gap-3 md:grid-cols-2">
      <li
        v-for="t in teams.data.value"
        :key="t.id"
        class="space-y-2 rounded-xl border border-line bg-surface p-4"
        :data-testid="`team-${t.name}`"
      >
        <div class="flex items-center justify-between gap-2">
          <h3 class="text-sm font-semibold text-ink">
            {{ t.name }} <span class="font-normal text-ink-muted">({{ t.memberCount }})</span>
          </h3>
          <AppButton
            v-if="canEdit"
            variant="ghost"
            :aria-label="`Delete team ${t.name}`"
            @click="attempt(() => manage.remove.mutateAsync(t.id))"
          >
            Delete
          </AppButton>
        </div>
        <p v-if="t.members.length === 0 && t.memberCount > 0" class="text-xs text-ink-muted">
          Names are shown to planners, admins and team leads only.
        </p>
        <ul class="space-y-1">
          <li v-for="m in t.members" :key="m.employeeId" class="flex items-center gap-2 text-sm">
            <span class="min-w-0 flex-1 truncate">
              {{ m.employee }} <span class="text-ink-muted">({{ m.empNo }})</span>
            </span>
            <span
              class="rounded-full px-2 py-0.5 text-[11px] font-semibold"
              :class="m.remoteCapable ? 'bg-ok-soft text-ok' : 'bg-surface-muted text-ink-muted'"
            >
              {{ WORK_MODE_LABEL[m.workMode] ?? m.workMode }}
            </span>
            <AppButton
              v-if="canEdit"
              variant="ghost"
              :aria-label="`Remove ${m.employee} from ${t.name}`"
              @click="
                attempt(() => manage.drop.mutateAsync({ teamId: t.id, employeeId: m.employeeId }))
              "
            >
              Remove
            </AppButton>
          </li>
        </ul>
        <form v-if="canEdit" class="flex items-end gap-2" @submit.prevent="add(t.id)">
          <div class="min-w-0 flex-1">
            <SelectField
              :model-value="picked[t.id] ?? ''"
              :label="`Add a person to ${t.name}`"
              :options="options"
              @update:model-value="picked[t.id] = $event"
            />
          </div>
          <AppButton type="submit" variant="secondary" :disabled="!picked[t.id]">Add</AppButton>
        </form>
      </li>
    </ul>

    <form v-if="canEdit" class="flex flex-wrap items-end gap-2" @submit.prevent="create">
      <TextField v-model="newName" label="New team name" />
      <AppButton type="submit" :disabled="newName.trim() === ''">Create team</AppButton>
    </form>
    <NoticeBox v-if="failure" tone="danger" data-testid="teams-error">{{ failure }}</NoticeBox>
  </section>
</template>
