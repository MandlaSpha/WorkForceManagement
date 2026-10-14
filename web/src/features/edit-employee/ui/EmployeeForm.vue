<script setup lang="ts">
import { computed, ref } from 'vue'

import type { QueueInfo } from '@/entities/call-data'
import type { Employee } from '@/entities/scheduling'
import { problemMessage } from '@/shared/api'
import AppButton from '@/shared/ui/AppButton.vue'
import NoticeBox from '@/shared/ui/NoticeBox.vue'
import SelectField from '@/shared/ui/SelectField.vue'
import TextField from '@/shared/ui/TextField.vue'

import { useEmployeeMutations } from '../model/useEmployeeMutations'

const props = defineProps<{ employee: Employee | null; queues: ReadonlyArray<QueueInfo> }>()
const emit = defineEmits<{ saved: []; cancel: [] }>()

const empNo = ref(props.employee?.empNo ?? '')
const name = ref(props.employee?.name ?? '')
const contractType = ref(props.employee?.contractType ?? 'permanent')
const workMode = ref(props.employee?.workMode ?? 'office')
// Blank means "use the default and say so"; an entered value is a real one (DAT-10).
const hours = ref(
  props.employee && !props.employee.weeklyHoursIsDefault ? String(props.employee.weeklyHours) : '',
)
const levels = ref<Record<number, number>>(
  Object.fromEntries((props.employee?.skills ?? []).map((s) => [s.queueId, s.level])),
)

const { create, update } = useEmployeeMutations()
const pending = computed(() => create.isPending.value || update.isPending.value)
const failed = computed(() => create.isError.value || update.isError.value)
const failure = computed(() => (create.isError.value ? create.error.value : update.error.value))

const CONTRACTS = [
  { value: 'permanent', label: 'Permanent' },
  { value: 'seasonal', label: 'Seasonal' },
]
const MODES = [
  { value: 'office', label: 'Office' },
  { value: 'remote', label: 'Remote' },
  { value: 'hybrid', label: 'Hybrid' },
]

function toggle(queueId: number, on: boolean): void {
  const next = { ...levels.value }
  if (on) next[queueId] = next[queueId] ?? 1
  else delete next[queueId]
  levels.value = next
}

function submit(): void {
  const body = {
    empNo: empNo.value.trim(),
    name: name.value.trim(),
    contractType: contractType.value,
    workMode: workMode.value,
    weeklyHours: hours.value.trim() === '' ? null : Number(hours.value),
    skills: Object.entries(levels.value).map(([queueId, level]) => ({
      queueId: Number(queueId),
      level,
    })),
  }
  const done = { onSuccess: () => emit('saved') }
  if (props.employee) update.mutate({ id: props.employee.id, body }, done)
  else create.mutate(body, done)
}
</script>

<template>
  <form
    class="space-y-4 rounded-xl border border-line bg-surface p-4"
    :aria-label="employee ? 'Change an employee' : 'Add an employee'"
    @submit.prevent="submit"
  >
    <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      <TextField v-model="empNo" label="Employee number" />
      <TextField v-model="name" label="Name" />
      <TextField
        v-model="hours"
        type="number"
        label="Weekly hours (blank for the default)"
        :min="1"
        :max="60"
        :step="0.5"
      />
      <SelectField v-model="contractType" label="Contract" :options="CONTRACTS" />
      <SelectField v-model="workMode" label="Works" :options="MODES" />
    </div>

    <fieldset class="space-y-2">
      <legend class="text-xs font-medium text-ink-muted">Queues this person can work</legend>
      <p v-if="queues.length === 0" class="text-sm text-ink-muted">
        There are no queues yet. They are created when call data is imported.
      </p>
      <div v-for="q in queues" :key="q.id" class="flex items-center gap-3">
        <label class="flex min-w-48 items-center gap-2 text-sm text-ink">
          <input
            type="checkbox"
            :checked="levels[q.id] !== undefined"
            @change="toggle(q.id, ($event.target as HTMLInputElement).checked)"
          />
          {{ q.name }}
        </label>
        <label
          v-if="levels[q.id] !== undefined"
          class="flex items-center gap-2 text-xs text-ink-muted"
        >
          Level
          <select
            v-model.number="levels[q.id]"
            class="rounded-md border border-line bg-surface px-1 py-0.5 text-sm text-ink"
            :aria-label="`Skill level on ${q.name}`"
          >
            <option :value="1">1</option>
            <option :value="2">2</option>
            <option :value="3">3</option>
          </select>
        </label>
      </div>
    </fieldset>

    <div class="flex items-center gap-2">
      <AppButton
        type="submit"
        :loading="pending"
        :disabled="empNo.trim() === '' || name.trim() === ''"
      >
        {{ employee ? 'Save changes' : 'Add employee' }}
      </AppButton>
      <AppButton v-if="employee" variant="ghost" @click="emit('cancel')">Cancel</AppButton>
    </div>
    <NoticeBox v-if="failed" tone="danger" data-testid="employee-error">
      <p class="font-medium">The employee was not saved.</p>
      <p>{{ problemMessage(failure) }}</p>
    </NoticeBox>
  </form>
</template>
