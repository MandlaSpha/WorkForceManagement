<script setup lang="ts">
import { computed, ref } from 'vue'

import { useActivities, type ShiftActivity } from '@/entities/scheduling'
import { problemMessage } from '@/shared/api'
import { formatDayLabel } from '@/shared/lib/datetime'
import AppButton from '@/shared/ui/AppButton.vue'
import NoticeBox from '@/shared/ui/NoticeBox.vue'
import SelectField from '@/shared/ui/SelectField.vue'
import TextField from '@/shared/ui/TextField.vue'

import { useAddActivity, useRemoveActivity } from '../model/useActivityWrites'

const props = defineProps<{
  queueId: number
  weekStart: string
  /** The people on the roster with the days they have a shift. */
  rows: ReadonlyArray<{
    employeeId: number
    name: string
    cells: ReadonlyArray<{ day: string; code: string }>
  }>
  canChange: boolean
}>()

const activities = useActivities(
  computed(() => props.queueId),
  computed(() => props.weekStart),
)
const add = useAddActivity()
const remove = useRemoveActivity()

const KINDS = [
  { value: 'break', label: 'Break' },
  { value: 'lunch', label: 'Lunch' },
  { value: 'training', label: 'Training' },
  { value: 'meeting', label: 'Meeting' },
  { value: 'coaching', label: 'Coaching' },
  { value: 'other', label: 'Other' },
]
const KIND_LABEL = Object.fromEntries(KINDS.map((k) => [k.value, k.label]))
const LENGTHS = [30, 60, 90, 120, 180, 240].map((m) => ({
  value: String(m),
  label:
    m < 60
      ? `${m} minutes`
      : `${m / 60} ${m === 60 ? 'hour' : 'hours'}`.replace('1.5 hours', '90 minutes'),
}))

const employeeId = ref('')
const day = ref('')
const kind = ref('break')
const start = ref('12:00')
const minutes = ref('30')

const people = computed(() =>
  props.rows
    .filter((r) => r.cells.length > 0)
    .map((r) => ({ value: String(r.employeeId), label: r.name })),
)
const days = computed(() => {
  const row = props.rows.find((r) => String(r.employeeId) === employeeId.value)
  return (row?.cells ?? []).map((c) => ({
    value: c.day,
    label: `${formatDayLabel(c.day)} (${c.code})`,
  }))
})

function submit(): void {
  add.mutate({
    queueId: props.queueId,
    employeeId: Number(employeeId.value),
    day: day.value,
    kind: kind.value,
    startTime: start.value,
    minutes: Number(minutes.value),
  })
}

const label = (a: ShiftActivity) =>
  `${a.employee}, ${formatDayLabel(a.day)}: ${KIND_LABEL[a.kind] ?? a.kind} ${a.startTime} to ${a.endTime}`
</script>

<template>
  <section class="space-y-3" aria-labelledby="activities-title">
    <h2 id="activities-title" class="text-sm font-semibold text-ink">Breaks and activities</h2>
    <p class="text-xs text-ink-muted">
      Time inside a shift when someone is not on the phones. Coverage on the planner counts only the
      people on the phones.
    </p>

    <form
      v-if="canChange"
      class="flex flex-wrap items-end gap-3 rounded-xl border border-line bg-surface p-4"
      aria-label="Add a break or activity"
      @submit.prevent="submit"
    >
      <SelectField
        v-model="employeeId"
        label="Person"
        :options="people"
        empty-text="Nobody rostered"
      />
      <SelectField v-model="day" label="Day" :options="days" empty-text="Choose a person" />
      <SelectField v-model="kind" label="What" :options="KINDS" />
      <TextField v-model="start" type="time" label="From" :step="1800" />
      <SelectField v-model="minutes" label="For" :options="LENGTHS" />
      <AppButton type="submit" :loading="add.isPending.value" :disabled="!employeeId || !day">
        Add
      </AppButton>
      <p
        v-if="add.isError.value"
        class="w-full text-sm text-danger"
        role="alert"
        data-testid="activity-error"
      >
        {{ problemMessage(add.error.value) }}
      </p>
    </form>

    <p v-if="activities.isPending.value" class="text-sm text-ink-muted">Loading…</p>
    <NoticeBox v-else-if="(activities.data.value ?? []).length === 0" data-testid="no-activities">
      No breaks or activities this week.
    </NoticeBox>
    <ul v-else class="space-y-1 text-sm" aria-label="Breaks and activities">
      <li
        v-for="a in activities.data.value"
        :key="a.id"
        class="flex items-center justify-between gap-3 rounded-lg border border-line bg-surface px-3 py-2"
        :data-testid="`activity-${a.id}`"
      >
        <span>{{ label(a) }}</span>
        <button
          v-if="canChange"
          type="button"
          class="text-xs font-medium text-danger underline disabled:opacity-60"
          :aria-label="`Remove ${label(a)}`"
          :disabled="remove.isPending.value"
          @click="remove.mutate(a.id)"
        >
          Remove
        </button>
      </li>
    </ul>
  </section>
</template>
