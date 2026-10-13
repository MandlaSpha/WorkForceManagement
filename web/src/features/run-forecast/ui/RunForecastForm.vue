<script setup lang="ts">
import { computed, ref } from 'vue'

import type { QueueInfo } from '@/entities/call-data'
import type { ForecastVersion } from '@/entities/forecast'
import { problemMessage } from '@/shared/api'
import { addDays, todayInJohannesburg, weekStartOf } from '@/shared/lib/week'
import AppButton from '@/shared/ui/AppButton.vue'
import NoticeBox from '@/shared/ui/NoticeBox.vue'
import SelectField from '@/shared/ui/SelectField.vue'
import TextField from '@/shared/ui/TextField.vue'

import { useRunForecast } from '../model/useRunForecast'

const props = defineProps<{ queues: ReadonlyArray<QueueInfo> }>()
const queueId = defineModel<number | null>('queueId', { required: true })
const emit = defineEmits<{ ran: [version: ForecastVersion] }>()

// Default to the current week, Monday to Sunday: the usual horizon a planner works to.
const monday = weekStartOf(todayInJohannesburg())
const dateFrom = ref(monday)
const dateTo = ref(addDays(monday, 6))
const label = ref('')

const options = computed(() => props.queues.map((q) => ({ value: String(q.id), label: q.name })))
const selected = computed({
  get: () => (queueId.value === null ? '' : String(queueId.value)),
  set: (value: string) => (queueId.value = value === '' ? null : Number(value)),
})

const run = useRunForecast()

function submit(): void {
  if (queueId.value === null) return
  run.mutate(
    {
      queueId: queueId.value,
      dateFrom: dateFrom.value,
      dateTo: dateTo.value,
      label: label.value.trim(),
    },
    { onSuccess: (version) => emit('ran', version) },
  )
}
</script>

<template>
  <form class="space-y-3" aria-label="Run a forecast" @submit.prevent="submit">
    <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      <SelectField v-model="selected" label="Queue" :options="options" empty-text="No queues yet" />
      <TextField v-model="dateFrom" type="date" label="From" />
      <TextField v-model="dateTo" type="date" label="To" />
      <TextField v-model="label" label="Label (optional)" />
    </div>
    <div class="flex items-center gap-3">
      <AppButton
        type="submit"
        :loading="run.isPending.value"
        :disabled="queueId === null || !dateFrom || !dateTo"
      >
        {{ run.isPending.value ? 'Running…' : 'Run forecast' }}
      </AppButton>
      <p class="text-xs text-ink-muted">
        Creates a draft. Nothing changes for anyone until it is published.
      </p>
    </div>
    <NoticeBox v-if="run.isError.value" tone="danger" data-testid="run-error">
      <p class="font-medium">No forecast was created.</p>
      <p>{{ problemMessage(run.error.value) }}</p>
    </NoticeBox>
  </form>
</template>
