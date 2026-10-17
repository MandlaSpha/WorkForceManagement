<script setup lang="ts">
import { computed, ref } from 'vue'

import type { QueueInfo } from '@/entities/call-data'
import { FREQUENCY_LABEL, REPORT_LABEL, WEEKDAYS } from '@/entities/report-schedule'
import { problemMessage } from '@/shared/api'
import AppButton from '@/shared/ui/AppButton.vue'
import NoticeBox from '@/shared/ui/NoticeBox.vue'
import SelectField from '@/shared/ui/SelectField.vue'
import TextField from '@/shared/ui/TextField.vue'

import { useCreateSchedule } from '../model/useSchedules'

const props = defineProps<{
  queues: ReadonlyArray<QueueInfo>
  /** Reports this person may schedule (a lead has no scorecard). */
  reports: ReadonlyArray<string>
  domains: ReadonlyArray<string>
}>()

const create = useCreateSchedule()
const report = ref(props.reports[0] ?? 'scorecard')
const queueId = ref('')
const recipients = ref('')
const frequency = ref('daily')
const hour = ref('7')
const weekday = ref('0')
const dayOfMonth = ref('1')

const reportOptions = computed(() =>
  props.reports.map((r) => ({ value: r, label: REPORT_LABEL[r] ?? r })),
)
const queueOptions = computed(() =>
  props.queues.map((q) => ({ value: String(q.id), label: q.name })),
)
const frequencyOptions = Object.entries(FREQUENCY_LABEL).map(([value, label]) => ({ value, label }))
const weekdayOptions = WEEKDAYS.map((label, n) => ({ value: String(n), label }))
const hourOptions = Array.from({ length: 24 }, (_, n) => ({
  value: String(n),
  label: `${String(n).padStart(2, '0')}:00`,
}))

function submit(): void {
  create.mutate(
    {
      report: report.value,
      queueId: report.value === 'peaks' && queueId.value !== '' ? Number(queueId.value) : null,
      recipients: recipients.value
        .split(/[\n,;]+/)
        .map((a) => a.trim())
        .filter(Boolean),
      frequency: frequency.value,
      hour: Number(hour.value),
      weekday: Number(weekday.value),
      dayOfMonth: Number(dayOfMonth.value),
    },
    { onSuccess: () => (recipients.value = '') },
  )
}
</script>

<template>
  <form
    class="space-y-3 rounded-xl border border-line bg-surface p-4"
    aria-label="Schedule a report"
    @submit.prevent="submit"
  >
    <NoticeBox v-if="domains.length === 0" tone="warn" data-testid="no-domains">
      No email domain has been allowed yet, so reports cannot be sent. Ask your administrator to
      allow one.
    </NoticeBox>
    <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      <SelectField v-model="report" label="Report" :options="reportOptions" />
      <SelectField
        v-if="report === 'peaks'"
        v-model="queueId"
        label="Queue"
        :options="queueOptions"
        empty-text="No queues yet"
      />
      <SelectField v-model="frequency" label="How often" :options="frequencyOptions" />
      <SelectField
        v-if="frequency === 'weekly'"
        v-model="weekday"
        label="On"
        :options="weekdayOptions"
      />
      <TextField
        v-if="frequency === 'monthly'"
        v-model="dayOfMonth"
        type="number"
        label="Day of the month (1 to 28)"
        :min="1"
        :max="28"
      />
      <SelectField v-model="hour" label="At (South African time)" :options="hourOptions" />
    </div>
    <label class="block text-xs font-medium text-ink-muted">
      Send to (one address per line)
      <textarea
        v-model="recipients"
        rows="3"
        class="mt-1 block w-full rounded-lg border border-line bg-surface p-2 text-sm text-ink"
      />
    </label>
    <p class="text-xs text-ink-muted">
      Addresses must be on
      <template v-if="domains.length > 0">{{ domains.join(', ') }}</template
      ><template v-else>an allowed domain</template>. The report holds only what you may see.
    </p>
    <div class="flex items-center gap-3">
      <AppButton
        type="submit"
        :loading="create.isPending.value"
        :disabled="recipients.trim() === '' || (report === 'peaks' && queueId === '')"
      >
        Schedule report
      </AppButton>
      <span v-if="create.isSuccess.value" class="text-sm text-ink" data-testid="schedule-result">
        Scheduled.
      </span>
    </div>
    <p
      v-if="create.isError.value"
      class="text-sm text-danger"
      role="alert"
      data-testid="schedule-error"
    >
      {{ problemMessage(create.error.value) }}
    </p>
  </form>
</template>
